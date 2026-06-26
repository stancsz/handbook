# S-33 · Live Data vs Stale Snapshots

Every cached, indexed, or embedded copy of your data is a snapshot frozen at the moment you built it — and the source has moved on since. An agent reading from that snapshot answers as of then, not now. Freshness is not a property you turn on; it is an architecture decision you make per field: read live and pay a fetch, or read a snapshot and accept a staleness window. The market's "agents need real-time data, not stale data" is this decision, made well or made by accident.

## Situation

Your agent gives a confidently wrong answer — the right answer for last week. The data it read was correct when you indexed it. A RAG store, a vector index, a cached API response, a "memory" written three sessions ago: all snapshots. The bug isn't retrieval quality or the model; it's that a volatile fact was served from a frozen layer.

## Forces

- A snapshot trades fetch cost for staleness risk. A live read is always current but costs a round-trip in latency and dollars ([F-18](../forward-deployed/f18-architecture-sets-the-cost-floor.md)); a snapshot is free to read but decays the moment the source changes.
- A RAG index *is* a snapshot ([S-07](s07-rag.md)). Its answers are correct only for the slice of the world that hasn't changed since you embedded it. Nothing about retrieval makes the content fresh.
- Staleness has two failure modes, and the second is sneakier: **changed values** (the snapshot returns the old number) and **missing new records** (the snapshot never had the row, so it returns "not found" for something that exists). Re-ranking and better embeddings fix neither.
- Churn rate and stakes are independent axes. A high-churn, high-stakes field (inventory, price, auth state) behind a snapshot is a latent incident. A slow-changing, low-stakes corpus (last year's docs) behind a live read is wasted spend.
- Freshness you can't see, you can't govern. A snapshot with no as-of timestamp gives the agent no way to know how stale it is — or to decide to refresh.

## The move

**Classify each data source by churn × stakes, then route.** High-churn or high-stakes → read live through a tool ([S-10](s10-mcp.md)). Slow-changing and low-stakes → snapshot or embed it ([S-07](s07-rag.md)). Don't apply one freshness policy to the whole context; the policy is per field.

**Treat the RAG index as a cache with a TTL, not a database.** Decide the re-index cadence from the source's churn rate, not from convenience. If the corpus changes faster than you re-embed, you are serving stale answers by design — either index faster or read those fields live.

**Stamp every snapshot with an as-of time, and surface it to the agent.** "Inventory as of 14:02" lets the agent — or a guardrail — decide whether that's fresh enough for the question. A snapshot with no timestamp is an unbounded staleness window.

**Watch for the missing-record mode, not just the wrong-value mode.** A snapshot can't tell you about rows that didn't exist when it was built. For "does X exist / what's the latest" questions on a growing source, a snapshot is structurally wrong — read live.

**Spend freshness where it changes the answer.** Live reads cost fetches, and fetches compound into the cost floor. Pay for liveness on the fields whose staleness would produce a wrong, costly action; snapshot the rest. Freshness is a budget, allocated, not a switch flipped on for everything.

## Receipt

> Verified 2026-06-26 — Node. No model in the loop by design: staleness is a property of the *data layer*, not the generator. An "inventory service" is the source of truth; a snapshot is taken at T0 (a stand-in for a RAG index / cached read), then a fixed stream of 7 updates moves the source on. The same queries are answered from each layer.

```
sku   live  snapshot  stale?
A1      60       100   STALE      <- value changed twice since snapshot
B2      50        50              <- unchanged: snapshot still correct
C3      10         0   STALE      <- value changed
D4     200       200              <- unchanged
E5       0        75   STALE      <- value changed
F6      40   NOT_FOUND   STALE    <- new record: snapshot never had it

snapshot served 4/6 stale answers after 7 updates
live      served 6/6 correct (cost: 1 fetch/query)
```

**What the receipt shows:**

- After only 7 updates, the snapshot is wrong on **4 of 6** queries — and the model is irrelevant to the error. No prompt, rerank, or bigger model fixes a frozen data layer.
- Both failure modes appear: three are *changed values* (A1, C3, E5) and one is the *missing-record* mode (F6 exists live, but the snapshot returns NOT_FOUND because the row didn't exist at T0). The second mode is invisible to retrieval-quality tuning.
- The two unchanged fields (B2, D4) were served correctly from the snapshot for free — which is the whole point: snapshot the stable fields, read the volatile ones live. The skill is knowing which is which *before* the wrong answer ships.

## See also

[S-07](s07-rag.md) · [S-10](s10-mcp.md) · [S-09](s09-memory-systems.md) · [S-13](s13-context-engineering.md) · [F-18](../forward-deployed/f18-architecture-sets-the-cost-floor.md)

## Go deeper

Keywords: `data freshness` · `stale index` · `re-indexing cadence` · `cache invalidation` · `as-of timestamp` · `real-time data` · `RAG staleness` · `live read vs snapshot` · `TTL` · `churn rate`
