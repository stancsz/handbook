# R-14 · Agent Memory Controller

Most memory discussions focus on storage backends and retrieval algorithms. The component that consistently gets skipped is the controller — the subsystem that decides *what* to store, *where*, *which operation applies*, and *what to retrieve next*. A memory system without a controller is just a database. The controller is what turns storage into a coherent, safe, compoundable memory architecture.

## Forces

- **Storage ≠ memory.** Vector stores and key-value tables hold data. They don't decide what matters, what contradicts prior beliefs, or what to evict. Without a controller, memory accumulates unchecked and retrieves incoherently.
- **The LLM already has context management pressure.** Models with 200K+ context still degrade on long documents and lose track of early decisions. The controller must work *outside* the model — it pre-filters what enters context, not everything in the store.
- **Cross-session poisoning is now the primary attack surface.** A malicious webpage, email, or document can write to memory that persists across sessions and surfaces. Without a validation gate, the attack payload compounds silently (see [F-185 · Cross-Session Memory Poisoning](../forward-deployed/f185-cross-session-memory-poisoning.md)).
- **Write conflicts are non-obvious.** If Session A records "user prefers concise responses" and Session B records "user wants detailed explanations," a naive merge produces contradictory memory. The controller must detect and resolve this.
- **The cost of retrieval is real.** Embedding queries, re-ranking, and context window fill are token costs. An unconstrained memory system generates expensive retrieval for every query. The controller scopes retrieval to what is plausibly relevant.

## The move

The memory controller sits between the agent's experience layer (tool calls, user messages, task outcomes) and the storage layer (vector DB, KV store, episodic log). It has four responsibilities:

**1. Event interception and classification**

Not every interaction merits a memory write. The controller classifies incoming events:

```python
from enum import Enum, auto
from dataclasses import dataclass
from typing import Literal

class MemoryValue(Enum):
    """Three cognitive types (from S-09, enforced by the controller)."""
    EPISODIC = auto()   # "what happened in this interaction"
    SEMANTIC  = auto()  # "a durable fact about user/domain"
    PROCEDURAL = auto() # "a reusable skill or workflow"

@dataclass
class MemoryEvent:
    content: str
    value_type: MemoryValue
    source: Literal["user", "agent", "tool", "env"]
    confidence: float          # LLM-assessed extraction confidence
    ttl_seconds: int | None   # None = permanent; episodic defaults to 7d
    labels: list[str]         # "preference", "fact", "error_pattern", etc.
```

**2. Write dispatch — deciding the operation**

```python
async def process_event(self, event: MemoryEvent) -> None:
    if event.confidence < self.min_confidence_threshold:
        return  # discard: too uncertain to store

    existing = await self.store.lookup(event.content, event.value_type)

    if existing is None:
        await self.store.add(event)                    # ADD
    elif self._contradicts(existing, event):
        await self._resolve_conflict(existing, event)  # UPDATE or FLAG
    elif event.ttl_seconds is not None:
        await self.store.add_with_ttl(event)           # ephemeral episodic
    else:
        pass  # no-op: duplicate of recent entry
```

**3. Conflict resolution**

The hardest part. When a new entry contradicts existing memory, three strategies:

- **Overwrite** — newer wins for fast-moving facts (user's current project context)
- **Merge** — combine into a disjunction for stable facts (user prefers both A and B in different contexts)
- **Flag** — surface the conflict to the agent in-context rather than resolving silently; let the model decide

```python
async def _resolve_conflict(self, existing: MemoryEntry, new: MemoryEvent) -> None:
    if existing.value_type == MemoryValue.SEMANTIC:
        # Facts shouldn't silently contradict. Flag rather than overwrite.
        await self.store.flag_conflict(existing, new)
    elif existing.value_type == MemoryValue.EPISODIC:
        # Episodic is append-only; conflicts here are recording errors, not memory errors
        return
    elif existing.value_type == MemoryValue.PROCEDURAL:
        # Procedures get overwritten if the new entry is higher-confidence
        if new.confidence > existing.confidence:
            await self.store.update(existing.id, new)
```

**4. Retrieval gating — controlling context injection**

The controller doesn't dump the entire memory store into context. It gates what gets retrieved based on relevance, recency, and context budget:

```python
async def retrieve_for_context(
    self,
    query: str,
    max_tokens: int,
    session_state: dict,
) -> list[MemoryEntry]:
    # Step 1: semantic search with conservative threshold
    candidates = await self.store.semantic_search(query, top_k=20)

    # Step 2: filter by value type relevance to the current task phase
    phase = session_state.get("phase", "general")
    candidates = self._filter_by_phase(candidates, phase)

    # Step 3: enforce token budget
    budgeted = self._fit_to_budget(candidates, max_tokens)

    # Step 4: inject recency decay for episodic — recent events rank higher
    budgeted = self._apply_recency_decay(budgeted)

    return budgeted
```

## Receipt

> Receipt pending — 2026-07-02

The controller architecture is implemented in production at several companies, described in the Redis-authored "Long-Horizon AI Agents: Memory & State Infrastructure" (redis.io/blog, 2026) and in open-source projects including Memex and GPT Researcher. The four-responsibility model (classify → dispatch → resolve → gate) maps to production systems handling 50K+ daily sessions. The implementation above is representative; exact APIs vary by framework.

## See also

- [S-09 · Memory Systems](../stacks/s09-memory-systems.md) — the storage and tier model the controller orchestrates
- [F-185 · Cross-Session Memory Poisoning](../forward-deployed/f185-cross-session-memory-poisoning.md) — the threat model that makes write validation non-optional
- [R-05 · Self-Evolving Agents](../frontier/r05-self-evolving-agents.md) — why compoundable memory is the precondition for agents that improve over time
