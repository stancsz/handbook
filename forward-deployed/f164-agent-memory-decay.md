# F-164 · Agent Memory Decay and Staleness

A customer support agent has served 200 conversations with user @alice@example.com. Over weeks of interaction, the agent has stored: "alice prefers email follow-ups," "alice's account is on the Pro plan," "alice had a billing dispute in March that was resolved." The agent starts a new session, retrieves alice's memory, and makes a confident, wrong decision because the plan name changed in April and nobody told the memory system.

The memory exists. The retrieval works. The agent acts on stale data. This is memory decay — the operational failure that follows a successful memory architecture.

## Forces

- Memory writes are event-driven and idempotent by default — but real-world facts change: plan tiers, account status, contact preferences, team rosters
- Vector retrieval surfaces semantically similar memories, not current ones — "prefers email" from six months ago ranks the same as "prefers Slack" from last week
- The agent cannot know what it doesn't know — it retrieves and trusts, never asking "is this still true?"
- Forgetting is expensive to implement correctly — TTL-based eviction discards useful history alongside stale noise
- Cross-session memory compounds silently: a wrong fact in session 1 pollutes session 2, which then writes new facts derived from the wrong one, deepening the corruption
- Legal and compliance memory (audit trails, decisions made) must be retained indefinitely; preference memory should be soft and revisable — lumping both into one store makes governance impossible

## The move

Three layers: **detect decay**, **contain propagation**, **enforce TTL by memory type**.

### Detect decay — temporal freshness scoring

Every memory record carries a `stored_at` timestamp and a `last_confirmed_at` field. Before retrieving memories for a session, score each:

```
freshness = 1.0 if last_confirmed_at within TTL
          else decay_rate ** ((now - last_confirmed_at) / TTL)
```

Where `decay_rate` is empirically tuned (common range: 0.7–0.9 per TTL period). Below a threshold (e.g., 0.4), the memory is flagged uncertain. Flag uncertain memories — don't suppress them, but surface them with a weight discount.

```python
from datetime import datetime, timedelta
from typing import Literal

MemoryType = Literal["preference", "fact", "procedure", "audit"]

class MemoryRecord:
    content: str
    mem_type: MemoryType
    stored_at: datetime
    last_confirmed_at: datetime  # last session where this fact was used and not contradicted

# TTL by type — audit lives forever, preferences are revisable
TTL_BY_TYPE: dict[MemoryType, timedelta] = {
    "preference": timedelta(weeks=4),
    "fact": timedelta(weeks=8),
    "procedure": timedelta(weeks=12),
    "audit": timedelta(days=365 * 10),
}

def freshness_score(record: MemoryRecord, decay_rate: float = 0.75) -> float:
    age = datetime.now() - record.last_confirmed_at
    ttl = TTL_BY_TYPE[record.mem_type]
    if age < ttl:
        return 1.0
    periods = (age / ttl).total_seconds()
    return decay_rate ** periods

def retrieve_memories(user_id: str, query: str, threshold: float = 0.4) -> list[dict]:
    raw = vector_db.similarity_search(query, k=20, namespace=user_id)
    scored = []
    for r in raw:
        score = freshness_score(r) * r.vector_similarity
        if score >= threshold:
            r.metadata["freshness"] = freshness_score(r)
            r.metadata["freshness_flagged"] = freshness_score(r) < 0.4
            scored.append(r)
    return scored
```

### Contain propagation — don't write derived facts without anchors

When the agent infers a new fact from retrieved memory (e.g., "alice's billing dispute is resolved" inferred from a resolved ticket), write the inference with an `inferred_from` field pointing to the source record. If the source record later expires or is corrected, the derived fact is flagged stale.

```python
def write_memory(user_id: str, content: str, mem_type: MemoryType,
                 inferred_from: str | None = None):
    record = MemoryRecord(
        content=content,
        mem_type=mem_type,
        stored_at=datetime.now(),
        last_confirmed_at=datetime.now(),
        inferred_from=inferred_from,  # provenance chain
    )
    vector_db.upsert(record, namespace=user_id)

    # If this contradicts a derived fact, invalidate it
    if inferred_from:
        invalidate_derived(user_id, inferred_from)
```

### Enforce TTL by type — separate stores, separate governance

Use separate namespaces or tables per memory type. Audit trails go to an append-only, immutable store. Preferences go to a short-TTL key-value cache backed by vector search. This lets you query "what preferences does alice currently have?" without searching a 10-year audit log, and lets compliance teams audit the fact store without touching preference data.

## Receipt

> Receipt pending — 2026-06-29

The freshness scoring and TTL-by-type pattern reflects production implementations described in AI agent memory management literature (Medium, 2026) and the architecture recommended by Arize Phoenix for trace-based memory auditing. Verification requires a live vector DB (Pinecone or pgvector) with real temporal data — the pattern is documented but the threshold calibration (`decay_rate`, `threshold`) must be tuned per application.

## See also

- [S-09 · Memory Systems](stacks/s09-memory-systems.md) — the architectural foundation; this entry covers the operational failure modes S-09 doesn't address
- [F-162 · Tool Result Freshness Assertion](f162-tool-result-freshness-assertion.md) — freshness scoring applies to tool results too; same decay concept, different data domain
- [F-104 · Live Source Health Monitor](f104-live-source-health-monitor.md) — source health monitoring detects when upstream data feeds produce stale data, which is the external source of memory decay
