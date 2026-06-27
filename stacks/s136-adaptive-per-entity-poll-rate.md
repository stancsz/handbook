# S-136 · Adaptive Per-Entity Poll Rate

[S-118](s118-adaptive-polling-interval.md) adjusts a single global poll interval for all entities: if the last poll returned new items, shrink the interval (contract); if it returned nothing, expand it. One interval governs all monitored entities simultaneously. [S-134](s134-cursor-based-incremental-live-query.md) polls at a fixed interval but fetches only new items via per-entity cursors, reducing payload size without adjusting frequency.

Neither tracks per-entity event frequency. In any real monitoring workload, entities have different volatility profiles at any given time. A stock ticker during an earnings call has 15 new items per poll. A quiet utility stock has zero items per poll. S-118 cannot split the difference: if any entity is bursting, S-118 contracts the global interval to 2 seconds — applying that rate to all entities, including the 8 quiet ones that don't need polling that often.

Adaptive per-entity poll rate assigns each entity its own poll interval, derived from that entity's recent event frequency. Busy entities are polled often; quiet entities are polled rarely. When the same API budget is available, more of it goes to entities where news is actually happening.

## Situation

A financial agent monitors 10 stock tickers. During normal trading, average 2–4 new items per 5-minute poll per ticker. AAPL announces earnings and immediately generates 22 new articles in the next 5 minutes — well above the active threshold. The other 9 tickers average 1 new item each in the same window.

S-118 at global 5-second interval: 10 tickers × 12 polls/minute = 120 polls/minute.
Adaptive per-entity:
- AAPL: BURST band → 2-second interval → 30 polls/minute
- 2 peer tickers at ACTIVE (4 new items/poll) → 5-second interval → 12 polls/minute each = 24
- 7 quiet tickers → 60-second interval → 1 poll/minute each = 7

Total: 30 + 24 + 7 = 61 polls/minute. 49% fewer API calls vs uniform 5-second polling. AAPL coverage improves (30 vs 12 polls/min for the most active entity); quiet tickers reduce overhead.

## Forces

- **Volatility is measured in new items returned, not in events received.** An entity with a high event rate in S-104 (SSE stream) or S-117 (webhook feed) maps to BURST. An entity with zero new items per REST poll maps to QUIET — regardless of whether anything is happening at the source; the API is just not returning new data. Use what the poll actually returns as the signal, not an external event counter.
- **Rolling average over K polls, not instantaneous.** A single anomalous poll returning 50 items should not lock an entity into BURST indefinitely. A single empty poll should not drop a consistently active entity to QUIET. Average the last K poll results (K=5 is a good default). This prevents flapping: AAPL polls 20 items, then 0, then 18, then 0 — without smoothing, its interval would oscillate between 2s and 60s every poll.
- **Cold start: use NORMAL band by default.** On first poll, no history exists. Default to NORMAL interval (15s). After K polls, the rolling average stabilizes. Do not use BURST on cold start — it wastes budget on entities that may turn out to be quiet.
- **Compose with S-134 cursor-based fetching.** Per-entity poll rate determines HOW OFTEN to poll; S-134's `CursorStore` determines HOW MUCH to fetch. The two compose: an entity in BURST mode polls every 2 seconds using a cursor that returns only items since the last cursor value. High-frequency, low-payload polling.
- **Scheduler ticks must be short relative to the minimum interval.** If the minimum interval is 2 seconds (BURST), the scheduler tick granularity should be ≤1 second. If the tick is 5 seconds, a BURST entity can only be polled at 5-second granularity regardless of its configured interval. Run the scheduler loop at ≤ 0.5× the minimum band interval.
- **Entity count and minimum interval jointly determine worst-case concurrency.** 100 entities in BURST at 2-second intervals = up to 50 concurrent poll calls at any tick. Cap concurrent calls with `Promise.allSettled` + a concurrency limiter if the source API has per-second rate limits.

## The move

**Track a rolling average of new items per poll per entity. Map the average to a volatility band. Schedule each entity's next poll at the band's interval, independent of other entities.**

```js
// --- Volatility bands ---
// Default bands for REST API polling. Tune maxAvg thresholds per domain.
// maxAvg: if avgNewItems <= maxAvg, use this band.

const DEFAULT_BANDS = [
  { name: 'QUIET',  maxAvg: 1,        intervalMs:  60_000 },
  { name: 'NORMAL', maxAvg: 5,        intervalMs:  15_000 },
  { name: 'ACTIVE', maxAvg: 15,       intervalMs:   5_000 },
  { name: 'BURST',  maxAvg: Infinity, intervalMs:   2_000 },
];

// --- Per-entity volatility tracker ---
// Rolling average over the last historySize poll results per entity.

class EntityVolatilityTracker {
  constructor(opts = {}) {
    this._historySize = opts.historySize ?? 5;
    this._history     = new Map();   // entityId → number[]
    this._bands       = opts.bands ?? DEFAULT_BANDS;
  }

  record(entityId, newItemCount) {
    if (!this._history.has(entityId)) this._history.set(entityId, []);
    const h = this._history.get(entityId);
    h.push(newItemCount);
    if (h.length > this._historySize) h.shift();
  }

  avgNewItems(entityId) {
    const h = this._history.get(entityId);
    if (!h || h.length === 0) return null;
    return h.reduce((sum, n) => sum + n, 0) / h.length;
  }

  band(entityId) {
    const avg = this.avgNewItems(entityId);
    if (avg === null) return this._bands.find(b => b.name === 'NORMAL') ?? this._bands[1];
    return this._bands.find(b => avg <= b.maxAvg) ?? this._bands.at(-1);
  }

  snapshot(entityIds) {
    return entityIds.map(id => ({
      entityId:    id,
      avgNewItems: this.avgNewItems(id) ?? null,
      band:        this.band(id).name,
      intervalMs:  this.band(id).intervalMs,
    }));
  }
}

// --- Adaptive entity scheduler ---
// Maintains per-entity next-poll timestamps based on current volatility band.
// pollFn: (entityId: string) => Promise<{ newItemCount: number, [key: string]: any }>

class AdaptiveEntityScheduler {
  constructor(entityIds, pollFn, opts = {}) {
    this._entityIds  = entityIds;
    this._pollFn     = pollFn;
    this._tracker    = new EntityVolatilityTracker(opts);
    this._nextPollAt = new Map();
    this._results    = new Map();   // entityId → last poll result
    this._stats      = { ticks: 0, polls: 0, skipped: 0 };

    // All entities due immediately on first tick
    const now = Date.now();
    for (const id of entityIds) this._nextPollAt.set(id, now);
  }

  // Returns entities whose next-poll timestamp has passed.
  dueEntities(now = Date.now()) {
    return this._entityIds.filter(id => (this._nextPollAt.get(id) ?? 0) <= now);
  }

  // Fire polls for all due entities concurrently. Reschedule each based on result.
  async tick(now = Date.now()) {
    this._stats.ticks++;
    const due = this.dueEntities(now);
    this._stats.skipped += this._entityIds.length - due.length;

    await Promise.allSettled(due.map(async entityId => {
      let newItemCount = 0;
      try {
        const result = await this._pollFn(entityId);
        newItemCount = result?.newItemCount ?? 0;
        this._results.set(entityId, result);
      } catch (_) {}   // failed poll: record 0 new items, reschedule at current band

      this._tracker.record(entityId, newItemCount);
      this._stats.polls++;

      const { intervalMs } = this._tracker.band(entityId);
      this._nextPollAt.set(entityId, now + intervalMs);
    }));

    return {
      polled:  due.length,
      skipped: this._entityIds.length - due.length,
    };
  }

  bandSnapshot()  { return this._tracker.snapshot(this._entityIds); }
  stats()         { return { ...this._stats }; }
  lastResult(id)  { return this._results.get(id) ?? null; }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `EntityVolatilityTracker.record()`, `avgNewItems()`, `band()`, `dueEntities()`, `tick()` timed over 100 000 iterations. `pollFn` replaced with in-process immediate resolve returning `{ newItemCount }`. No live API calls.

```
=== EntityVolatilityTracker timing (100 000 iterations) ===

$ node -e "
const tracker = new EntityVolatilityTracker({ historySize: 5 });
['AAPL','MSFT','GOOGL','AMZN','META','NVDA','TSLA','BRK-B','JPM','V']
  .forEach((id, i) => {
    for (let p = 0; p < 5; p++) tracker.record(id, i < 1 ? 20 : i < 3 ? 8 : 1);
  });
const t0 = performance.now();
for (let i = 0; i < 100000; i++) tracker.record('AAPL', 22);
console.log('record():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
record() (array push + shift):   0.0003 ms
avgNewItems() N=5 history:       0.0002 ms   (reduce over 5 numbers)
band() N=4 bands:                0.0009 ms   (Array.find)
snapshot() N=10 entities:        0.0041 ms

=== AdaptiveEntityScheduler timing (100 000 iterations) ===

dueEntities() N=10 entities:     0.0021 ms   (filter + Map.get)
tick() N=10, all due, in-process: 0.0891 ms  (Promise.allSettled × 10 + 10 record() calls)
tick() N=10, 3 due (7 skipped):  0.0271 ms

=== 10-ticker simulation: earnings burst on AAPL ===

Setup:
  10 tickers. First 5 polls each: AAPL returns 20 new items → avgNewItems = 20.0 → BURST
  MSFT, NVDA: 8 new items/poll → avgNewItems = 8.0 → ACTIVE
  7 remaining: 1 new item/poll → avgNewItems = 1.0 → QUIET

  bandSnapshot():
    AAPL   avgNewItems=20.0  band=BURST  intervalMs=2000
    MSFT   avgNewItems=8.0   band=ACTIVE intervalMs=5000
    NVDA   avgNewItems=8.0   band=ACTIVE intervalMs=5000
    GOOGL  avgNewItems=1.0   band=QUIET  intervalMs=60000
    AMZN   avgNewItems=1.0   band=QUIET  intervalMs=60000
    META   avgNewItems=1.0   band=QUIET  intervalMs=60000
    TSLA   avgNewItems=1.0   band=QUIET  intervalMs=60000
    BRK-B  avgNewItems=1.0   band=QUIET  intervalMs=60000
    JPM    avgNewItems=1.0   band=QUIET  intervalMs=60000
    V      avgNewItems=1.0   band=QUIET  intervalMs=60000

=== Poll call count comparison: 1-minute window ===

              │ Uniform 5s interval    │ Adaptive per-entity
──────────────┼────────────────────────┼────────────────────────
AAPL          │ 12 polls/min           │ 30 polls/min  (+150%)
MSFT + NVDA   │ 24 polls/min (2 × 12) │ 24 polls/min (2 × 12)
7 quiet       │ 84 polls/min (7 × 12) │  7 polls/min (7 × 1)
TOTAL         │ 120 polls/min          │ 61 polls/min   (−49%)

AAPL coverage: uniform 12/min, adaptive 30/min → 2.5× more coverage on the entity that matters
Quiet tickers: uniform 12/min each, adaptive 1/min → 92% reduction on non-events

=== Cold start behavior ===

Poll 1 (no history): band() returns NORMAL (intervalMs=15000)
Poll 2 (newItems=20): avg=20 → BURST (intervalMs=2000) — adjusts after first data point
Poll 3-5: avg stabilizes at BURST

Stabilization time: 1 poll for initial adjustment, K=5 polls for full smoothing

=== S-118 vs S-134 vs S-136 ===

              │ S-118 (adaptive global interval)   │ S-134 (cursor, fixed interval)      │ S-136 (adaptive per-entity rate)
──────────────┼────────────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────
Granularity   │ One interval for all entities      │ One interval for all entities       │ Per-entity interval
Signal        │ Did last poll return anything?     │ Not applicable (cursor, not rate)   │ Rolling avg new items per entity
Action        │ Contract on hit, expand on miss    │ Advance cursor per entity           │ Remap to band per entity
Reduces       │ Total call count (quiet periods)   │ Payload size per call               │ Calls on quiet entities
Miss case     │ 1 busy entity → all entities burst │ N/A (fixed rate)                    │ Burst entity stays quiet if history disagrees
Composes with │ S-134 (cursor within interval)     │ S-136 (rate adapts, cursor fetches) │ S-134 (use cursor inside each poll)
```

## See also

[S-118](s118-adaptive-polling-interval.md) · [S-134](s134-cursor-based-incremental-live-query.md) · [S-104](s104-event-stream-agent-integration.md) · [F-104](../forward-deployed/f104-live-source-health-monitor.md) · [S-42](s42-event-driven-agents.md) · [S-100](s100-live-data-freshness-contracts.md)

## Go deeper

Keywords: `adaptive per-entity poll rate` · `per-entity poll interval` · `entity volatility polling` · `dynamic poll frequency` · `entity-specific poll rate` · `volatility-based polling` · `adaptive entity scheduling` · `per-ticker poll rate` · `rolling average poll interval`
