# S-09 · Memory Systems

What persists between LLM calls — and how to make agents remember things without stuffing everything in context.

## Forces
- LLMs are stateless by default — each call starts fresh
- Stuffing all history into context gets expensive and hits limits fast
- You need some memory to be fast (sub-millisecond), some to be rich (semantic search)
- Wrong memory architecture makes agents either amnesiac or slow

## The move

Separate **what** to remember (types) from **where** it lives (tiers).

**What to remember — three cognitive types (2026 standard vocabulary):**
- **Episodic** — specific past events: what happened, the action taken, the outcome. Lets the agent learn from history.
- **Semantic** — durable facts: user preferences, domain truths, entity relations. Retrieved as needed.
- **Procedural** — learned how-to: workflows and tool sequences the agent reuses. Often lives in the system prompt or a skill ([S-20](s20-agent-skills.md)).

**Where it lives — three storage tiers:**

### Tier 1: In-context (fastest, most expensive at scale)
The conversation history, injected directly. Use for: the current session, short task state.  
Limit: whatever fits in the window. Prune old turns aggressively.

### Tier 2: File / key-value (fast, structured)
Persist state to disk or a database between sessions. Use for: user preferences, task progress, known facts.
```python
import json, pathlib

def save_memory(key: str, value: dict, path="memory.json"):
    store = json.loads(pathlib.Path(path).read_text()) if pathlib.Path(path).exists() else {}
    store[key] = value
    pathlib.Path(path).write_text(json.dumps(store, indent=2))

def load_memory(key: str, path="memory.json") -> dict:
    store = json.loads(pathlib.Path(path).read_text()) if pathlib.Path(path).exists() else {}
    return store.get(key, {})
```

### Tier 3: Vector / semantic (richest, highest latency)
Embed facts and retrieve by semantic similarity. Use for: large personal knowledge bases, long-running agents with thousands of memories.  
Tools: Chroma (local), pgvector (Postgres), Pinecone (hosted).

**Dual-tier production pattern:**
- Hot path: in-context + key-value (fast)
- Cold path: vector search for older, large, or fuzzy memories
- Write to both; read hot path first, fall back to cold

**Forgetting is a feature:** not everything needs to be remembered. Decide on a TTL and eviction policy, or your memory grows without bound.

## Receipt
> Verified 2026-06-25 — cross-session memory demonstrated against llama3.2 via Ollama (localhost:11435): four facts saved to a key-value store in "session 1," then a **fresh** call (zero conversation history) with selective retrieval.

```
Question (fresh session): "What AWS region do I deploy to, and who is my on-call escalation?"

BASELINE (stateless, no memory):  "I do not know."

RETRIEVED (4 facts stored, 2 matched the query):
  - aws region deploy: eu-west-1 (Ireland)
  - on-call escalation contact: page Dana, then the platform channel
  (distractors NOT retrieved: favorite_editor, coffee_order)

WITH MEMORY (fresh session + retrieved facts):
  AWS region: eu-west-1 (Ireland); On-call: page Dana, then the platform channel  ✓
```

Two things the run shows: (1) the model is genuinely stateless — with no memory it correctly admits it doesn't know, rather than guessing; (2) Tier-2 retrieval pulled only the **2 relevant** facts out of 4, so the fresh session answered correctly without re-injecting the whole history. Retrieval here is crude keyword matching; swap in embeddings ([S-17](s17-embeddings.md)) for semantic recall at scale. The Python snippet above is the same save/load pattern; vector-DB API shapes vary by provider — verify before use.

## See also
[S-07](s07-rag.md) · [S-17](s17-embeddings.md) · [S-21](s21-context-compaction.md) · [S-02](s02-context-budget.md) · [S-05](s05-multi-agent-patterns.md)

## Go deeper
Keywords: `agent memory` · `Mem0` · `Letta` · `Zep` · `episodic memory` · `semantic memory` · `pgvector` · `Chroma`
