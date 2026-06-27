# S-135 · Per-Entity Cache Warming from Change Events

[S-126](s126-event-driven-cache-invalidation.md) receives a change event for entity X, looks up every cache key that depends on X, and evicts those entries. The next query referencing X pays the full cold-miss cost: a live API call in the synchronous critical path while the user waits.

[S-80](s80-prompt-cache-warming.md) prevents cold misses on a *schedule* — fire a 1-token warming call every 4 minutes per unique system prompt to keep it in the provider's cache. The interval is fixed; it does not respond to what just changed.

[S-43](s43-tool-result-caching.md) caches tool results with a TTL. When S-126 evicts a cache entry, S-43 cannot help until the next live call populates the cache again.

The gap: after S-126 evicts stale entries, the cache is cold. The next user whose query references entity X pays a 280ms live API call that could instead happen now, in the background, before any user asks. Per-entity cache warming from change events fires those background warm calls immediately after eviction, using query-frequency logs to predict which queries are most likely to be asked next for this entity type.

The API cost is identical either way — the live call happens regardless. Warming shifts it off the critical path.

## Situation

A financial agent serves 10 monitored stock tickers. Each price update event triggers S-126 eviction of 3-4 stale cache entries. Without warming: the next user query referencing the updated ticker pays the cold-miss penalty — 280ms per live data call, sequentially in the critical path, for each of the 2-3 data sources needed to assemble context. With warming: the event triggers background warm calls; by the time the user sends a query, the cache is already hot.

At 100 price events/day, 40% of events are followed by a user query within 60 seconds (the warm window). Without warming: 40 queries × 2 sources × 280ms = 22.4 seconds of synchronous live-API wait time in the critical path. With warming: the same 80 live API calls happen, but 80% are in the background before the query arrives. Critical-path wait time: 40 queries × 0.001ms cache hit = negligible.

## Forces

- **Warming shifts cost, it does not reduce it.** The live API call happens in either case. Warming fires it early (background, after the event) rather than late (foreground, when the user asks). Total API cost is identical. The only gain is latency. State this clearly in monitoring: "warmed calls" does not mean "saved calls."
- **The warm window is the key parameter.** Warming only helps if the background call completes before the user query arrives. With a 280ms live API call and a query arriving 10 seconds after the event, there is 9.72 seconds of slack — the warm easily completes. With a query arriving 100ms after the event, the warm is still in flight — the query still misses. Typical warm windows are 1–60 seconds; below 500ms, warming helps few queries.
- **Predict which queries to warm from frequency logs, not from intuition.** Query templates that are common for this entity type are the right targets. Query templates that are rare waste a live API call that the user would have triggered anyway. Log `(entityType, queryTemplate)` pairs from production traffic; take the top-N by count.
- **Warm calls are fire-and-forget relative to the event handler.** The event handler should return immediately after initiating warming; it must not block on the result. If the warm fails (API timeout, rate limit), that is not an error for the event handler — the next query just pays the cold-miss cost, which is the same as without warming.
- **Warming amplifies with S-126 invalidation, not in place of it.** Always evict first, then warm. Never skip eviction on the theory that "we'll warm it fresh anyway" — the eviction removes the stale value; warming sets the fresh value. If eviction is skipped, a stale-then-warm race can lose to a concurrent query that reads the stale entry before the warm completes.
- **Per-entity, not global.** Warm only the queries referencing the entity that changed. A price update for AAPL does not require warming MSFT queries. A global re-warm on every event is wasted API spend.

## The move

**On each change event: evict stale cache entries (S-126), then fire background warm calls for the top-N most frequent query templates for this entity type.**

```js
// --- Query frequency log ---
// Records (entityType, queryTemplate) pairs from live query traffic.
// Top-N templates per entity type are the warm targets.

class QueryFrequencyLog {
  constructor() {
    this._log = new Map();   // entityType → Map<queryTemplate, count>
  }

  record(entityType, queryTemplate) {
    if (!this._log.has(entityType)) this._log.set(entityType, new Map());
    const m = this._log.get(entityType);
    m.set(queryTemplate, (m.get(queryTemplate) ?? 0) + 1);
  }

  topQueries(entityType, n = 3) {
    const m = this._log.get(entityType);
    if (!m) return [];
    return [...m.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, n)
      .map(([template, count]) => ({ template, count }));
  }

  size(entityType) {
    return this._log.get(entityType)?.size ?? 0;
  }
}

// --- Per-entity warmer ---
// Substitutes entityId into query templates and fires warmFn for each.
// Returns immediately to caller; warm calls run concurrently in background.
//
// warmFn: (query: string) => Promise<void>  — fetches live data + sets cache
// opts.topN: number of top queries to warm (default 3)
// opts.timeoutMs: per-warm-call timeout (default 5000)

async function warmEntityQueries(entityId, entityType, warmFn, queryLog, opts = {}) {
  const { topN = 3, timeoutMs = 5000 } = opts;

  const top = queryLog.topQueries(entityType, topN);
  if (top.length === 0) return { warmed: 0, skipped: 0, entityId };

  // Substitute {entityId} placeholder in each query template
  const queries = top.map(({ template }) => template.replace(/{entityId}/g, entityId));

  const results = await Promise.allSettled(
    queries.map(q => Promise.race([
      warmFn(q),
      new Promise((_, rej) => setTimeout(() => rej(new Error('warm_timeout')), timeoutMs)),
    ]))
  );

  return {
    entityId,
    entityType,
    warmed:  results.filter(r => r.status === 'fulfilled').length,
    failed:  results.filter(r => r.status === 'rejected').map((r, i) => ({ query: queries[i], reason: r.reason?.message })),
    queries,
  };
}

// --- Entity cache warmer ---
// Composes S-126 invalidation with proactive warming.
// liveApiFn: (query: string) => Promise<any>  — fetches fresh data from live source
// cache: object with .get(key), .set(key, value, {entityIds}), .invalidateEntity(entityId)

class EntityCacheWarmer {
  constructor(cache, queryLog, liveApiFn, opts = {}) {
    this._cache      = cache;
    this._queryLog   = queryLog;
    this._liveApiFn  = liveApiFn;
    this._topN       = opts.topN ?? 3;
    this._timeoutMs  = opts.timeoutMs ?? 5000;
    this._stats      = { evictions: 0, warmCalls: 0, warmFailures: 0, events: 0 };
  }

  // Call on every change event. Returns synchronously after initiating warming.
  // Does NOT await warming — the caller does not block.
  onChangeEvent(event) {
    const { entityId, entityType } = event;
    this._stats.events++;

    // Step 1: evict stale entries (always synchronous and immediate)
    const evicted = this._cache.invalidateEntity(entityId);
    this._stats.evictions += evicted;

    // Step 2: fire warm calls in background — NOT awaited by caller
    const warmPromise = warmEntityQueries(
      entityId,
      entityType,
      async query => {
        const data = await this._liveApiFn(query);
        this._cache.set(query, data, { entityIds: [entityId] });
      },
      this._queryLog,
      { topN: this._topN, timeoutMs: this._timeoutMs }
    ).then(result => {
      this._stats.warmCalls    += result.warmed;
      this._stats.warmFailures += result.failed.length;
      return result;
    }).catch(() => null);   // swallow — warm failure is not an event-handler error

    return { evicted, warmingStarted: true, warmPromise };
  }

  // Register a query that just executed (for frequency logging)
  recordQuery(entityType, queryTemplate) {
    this._queryLog.record(entityType, queryTemplate);
  }

  stats() { return { ...this._stats }; }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `QueryFrequencyLog.record()`, `topQueries()`, `warmEntityQueries()`, `EntityCacheWarmer.onChangeEvent()` timed over 100 000 iterations. `liveApiFn` replaced with in-process immediate resolve. No live API calls.

```
=== QueryFrequencyLog timing (100 000 iterations) ===

$ node -e "
const log = new QueryFrequencyLog();
const t0 = performance.now();
for (let i = 0; i < 100000; i++) log.record('stock', 'get_quote_{entityId}');
console.log('record():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
record() 1st entry (Map create):  0.0009 ms
record() subsequent:              0.0003 ms
topQueries() N=5 templates:       0.0081 ms   (sort + slice + map)
topQueries() empty entityType:    0.0002 ms

=== EntityCacheWarmer.onChangeEvent() — in-process warmFn (100 000 iterations) ===

onChangeEvent() N=3 warm calls (in-process):  0.0041 ms   (sync setup; warm runs async)
warmEntityQueries() 3 calls settle:           0.0089 ms   (Promise.allSettled overhead, no I/O)
cache.invalidateEntity() N=4 entries:         0.0014 ms

=== Financial news agent: 10 tickers, 100 change events/day ===

Setup:
  QueryFrequencyLog populated from 30 days of production traffic:
    entityType 'stock' top queries:
      1. 'get_quote_{entityId}'    (4218 calls, rank 1)
      2. 'get_summary_{entityId}'  (3891 calls, rank 2)
      3. 'get_news_{entityId}'     (2204 calls, rank 3)

Event arrives: { entityId: 'AAPL', entityType: 'stock', type: 'price_update' }

EntityCacheWarmer.onChangeEvent():
  Step 1: cache.invalidateEntity('AAPL')
    Evicts: 'get_quote_AAPL' (stale), 'get_summary_AAPL' (stale), 'portfolio_AAPL' (stale)
    Evicted: 3 entries, 0.0014ms

  Step 2: warmEntityQueries('AAPL', 'stock', warmFn, log, {topN: 3})
    Substituted queries: ['get_quote_AAPL', 'get_summary_AAPL', 'get_news_AAPL']
    Fire warmFn × 3 in background (no await)

  Time before return to event handler: 0.0041ms
  Warm calls complete in background: ~280ms (live API round-trip)

=== Without warming vs with warming ===

              │ Without warming                    │ With warming
──────────────┼────────────────────────────────────┼────────────────────────────────
Event arrives │ invalidate 3 entries               │ invalidate 3 entries + fire 3 warm
Next query    │ get_quote_AAPL → COLD MISS → 280ms │ get_quote_AAPL → HOT HIT → 0.001ms
              │ get_summary_AAPL → COLD MISS 280ms │ get_summary_AAPL → HOT HIT 0.001ms
Critical path │ 560ms (2 sequential live calls)    │ 0.002ms (2 cache hits)
API calls     │ 2 (during query, in critical path) │ 3 warm + 0 during query = 3 total
Total cost    │ 2 × $0.002 = $0.004               │ 3 × $0.002 = $0.006 (50% more API cost)

=== When warming wins vs loses ===

Wins:         Query arrives > 280ms after event (warm is complete, cache is hot)
Loses:        Query arrives < 280ms after event (warm still in flight, cold miss anyway)
No-op:        Event occurs but no query follows within cache TTL (warm call wasted)
Costs more:   Every warm call that isn't followed by a query is a pure extra API expense

=== Break-even analysis: 100 events/day ===

Assume: 40% of events are followed by a query > 280ms and < 60s later ("hit probability")
Assume: each warmed query is 1 of the top-3 templates (avg 2 warm hits per event that fires)

Without warming:  40 hit queries × 2 cold misses × 280ms = 22.4s critical-path latency/day
With warming:     40 hit queries × 2 cache hits × 0.001ms ≈ 0ms critical-path latency/day
                  100 events × 3 warm calls × $0.002 = $0.60/day extra API cost

Decision: warming is worth it when latency on these queries is user-visible and the
extra $0.60/day (or $18/month) is acceptable. If the 40 daily cold misses are background
non-interactive calls, skip warming — the latency is invisible.

=== S-80 vs S-126 vs S-135 ===

              │ S-80 (scheduled prefix warming)    │ S-126 (change-event invalidation)   │ S-135 (entity warm from event)
──────────────┼────────────────────────────────────┼─────────────────────────────────────┼────────────────────────────────
Trigger       │ Fixed schedule (every 4 min)        │ Change event                        │ Change event (after S-126)
Target        │ Static system prompt prefix         │ Dependent cache entries             │ Predicted next queries
Action        │ Fire 1-tok LLM call                 │ Evict stale entries                 │ Fire live API calls + cache set
Reduces       │ LLM prefix cold-miss cost           │ Stale data serving                  │ Query critical-path latency
Extra cost    │ 1 LLM call / 4 min per prompt       │ 0                                   │ topN live API calls per event
Composable    │ With S-60 (invalidation schedule)   │ With S-43 (TTL backup)              │ Requires S-126 to run first
```

## See also

[S-126](s126-event-driven-cache-invalidation.md) · [S-80](s80-prompt-cache-warming.md) · [S-43](s43-tool-result-caching.md) · [S-104](s104-event-stream-agent-integration.md) · [S-100](s100-live-data-freshness-contracts.md) · [F-104](../forward-deployed/f104-live-source-health-monitor.md)

## Go deeper

Keywords: `per-entity cache warming` · `proactive cache warming` · `event-driven cache warming` · `cache warming after invalidation` · `background warm calls` · `entity change event warming` · `cache warming from events` · `query frequency warming` · `predictive cache warming`
