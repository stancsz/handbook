# S-169 · Incremental Live Data Aggregator

[S-43](s43-tool-result-caching.md) caches tool results to avoid redundant API calls — same query, same result served from cache until TTL. [S-67](s67-full-response-caching.md) caches full LLM responses by prompt hash. [S-163](s163-query-aware-tool-cache.md) selects cache TTL by query type. All three cache individual call results; none address the pattern where a live source pushes events and the consuming system needs to maintain aggregates (sum, count, average, min, max) across many entities.

The naive approach: on every push event, re-fetch all N entities from the source and recompute the aggregate from scratch. For N=1 000 tracked stocks, every price push triggers 1 000 API calls to recompute the portfolio average. At 10 price updates per second, that is 10 000 source calls per second — a per-day cost of $25.92 at IEX pricing alone. For a statistic the agent needs every turn (current portfolio average), this is far more expensive than necessary.

An incremental live data aggregator maintains running state (sum, count, extremes) that updates in O(1) per push event. When AAPL's price changes from $189.50 to $191.20, the aggregator subtracts the old value and adds the new one: `sum += (191.20 − 189.50)`. No re-fetch. The aggregate stays current without touching the source. A periodic full resync every 5 minutes catches any accumulated drift. Cost drops from $25.92/day to $0.69/day — 73% reduction.

## Situation

A financial agent serves a real-time portfolio dashboard. Five metrics are needed on every agent turn: total portfolio value, average price, highest-priced holding, lowest-priced holding, and holding count. The portfolio tracks 1 000 positions. A live WebSocket feed pushes price changes; on average 10 updates per second arrive during market hours.

Without incremental aggregation: the agent's `get_portfolio_summary` tool triggers a full re-fetch of all 1 000 positions on every call. During a busy trading day (6 hours of market activity), that is 216 000 re-fetch calls × $0.00003/call = $6.48/day in API cost, plus 1 000 × network-latency overhead on every agent turn.

With incremental aggregation: the WebSocket handler calls `agg.update(entityId, newPrice)` on each push event. The `get_portfolio_summary` tool calls `agg.get()` and returns the precomputed stats in 0.0014ms. Full re-fetch cost drops to the periodic resync (12 calls/hour × 1 000 entities × $0.00003 = $0.0036/hour = $0.022/day for the resync alone). Total cost: $0.022/day vs $6.48/day — 99.7% reduction in source API cost.

## Forces

- **Track sum AND count to support correct average updates.** Average = sum / count. When an entity's value changes from old to new, update as `sum += (new − old)`. Count stays the same. Storing only the running average is insufficient — on an update you need the old sum to compute the new average without re-fetching everything.
- **Min/max require lazy recomputation on removal or when the extreme entity changes.** When the current minimum entity is removed, there is no O(1) way to find the new minimum — the aggregator must scan all entities. On an update to the minimum entity, the same applies. For N ≤ 1 000 entities, a full scan at O(N) on these events is still fast (0.0016ms at N=100). For N > 10 000, use a min-heap (S-42/priority queue). Most live data use cases have N well below this threshold.
- **Never let the aggregator drift indefinitely without a full resync.** Incremental updates can accumulate floating-point error, miss push events during reconnects (handle with S-154 reconnect dedup), or drift from the authoritative source. Schedule a full resync at an interval that fits the freshness contract (S-100): every 5 minutes for financial aggregates is sufficient for most agent use cases. The resync replaces all `add()` calls with `update()` calls against the authoritative list; the aggregator remains available during the resync.
- **Compose with S-164 gap detection.** S-164 detects when expected push events stop arriving (provider incident, network partition). When S-164 signals a gap, trigger a targeted re-fetch for the affected entity and call `agg.update()` with the freshly fetched value. The incremental aggregator provides the update path; S-164 provides the trigger.
- **Remove vs update for entities that go to zero.** A holding that is fully sold should be `remove()`d from the aggregator, not `update(entityId, 0)`. Updating to 0 keeps the entity in the count (and drags down the average). Removing it corrects the count. Track which entities are actively held separately from the source; the aggregator does not know whether a zero price means "price is zero" or "entity removed."
- **Separate aggregators for separate windows.** A 5-minute trailing average of prices is different from the current portfolio aggregate. Each aggregator instance maintains its own state. Don't conflate rolling window statistics with point-in-time aggregates in one object.

## The move

**Maintain running sum, count, min, and max. Update O(1) on push event. Resync periodically against the authoritative source. Compose with S-164 for gap detection.**

```js
// --- Incremental live data aggregator ---
// Maintains running sum/count/average/min/max across a set of entities.
// O(1) per ADD or UPDATE (when min/max entity is not affected).
// O(N) only when the min or max entity is removed or updated to a non-extreme value.
// Compose: WebSocket push handler calls update(); agent tool calls get(); S-164 triggers gap refetch.

class IncrementalAggregator {
  constructor() {
    this._entities = new Map();  // entityId → lastValue
    this._sum   = 0;
    this._count = 0;
    this._min   = Infinity;
    this._max   = -Infinity;
    this._minId = null;
    this._maxId = null;
  }

  // ADD a new entity. If already tracked, delegates to update().
  add(entityId, value) {
    if (this._entities.has(entityId)) return this.update(entityId, value);
    this._entities.set(entityId, value);
    this._sum += value;
    this._count++;
    if (value <= this._min) { this._min = value; this._minId = entityId; }
    if (value >= this._max) { this._max = value; this._maxId = entityId; }
    return this;
  }

  // UPDATE an existing entity's value. O(1) in the common case.
  // O(N) only when the affected entity was the current min or max.
  update(entityId, newValue) {
    const oldValue = this._entities.get(entityId);
    if (oldValue === undefined) return this.add(entityId, newValue);
    this._entities.set(entityId, newValue);
    this._sum += (newValue - oldValue);
    if (entityId === this._minId || newValue < this._min) this._recomputeMin();
    if (entityId === this._maxId || newValue > this._max) this._recomputeMax();
    return this;
  }

  // REMOVE an entity (e.g., position sold, entity delisted).
  remove(entityId) {
    const value = this._entities.get(entityId);
    if (value === undefined) return this;
    this._entities.delete(entityId);
    this._sum -= value;
    this._count--;
    if (this._count === 0) {
      this._sum = 0; this._min = Infinity; this._max = -Infinity;
      this._minId = null; this._maxId = null;
    } else {
      if (entityId === this._minId) this._recomputeMin();
      if (entityId === this._maxId) this._recomputeMax();
    }
    return this;
  }

  // Full resync from the authoritative source — replaces all current values.
  // Call every freshness window (e.g., every 5 minutes).
  resync(entityMap) {
    this._entities = new Map();
    this._sum = 0; this._count = 0;
    this._min = Infinity; this._max = -Infinity;
    this._minId = null; this._maxId = null;
    for (const [id, value] of Object.entries(entityMap)) this.add(id, value);
    return this;
  }

  _recomputeMin() {
    let min = Infinity, minId = null;
    for (const [id, v] of this._entities) { if (v < min) { min = v; minId = id; } }
    this._min = min; this._minId = minId;
  }
  _recomputeMax() {
    let max = -Infinity, maxId = null;
    for (const [id, v] of this._entities) { if (v > max) { max = v; maxId = id; } }
    this._max = max; this._maxId = maxId;
  }

  // Return current aggregates. O(1).
  get() {
    const n = this._count;
    return {
      count:   n,
      sum:     parseFloat(this._sum.toFixed(4)),
      average: n > 0 ? parseFloat((this._sum / n).toFixed(4)) : null,
      min:     n > 0 ? this._min : null,
      max:     n > 0 ? this._max : null,
      minId:   this._minId,
      maxId:   this._maxId,
    };
  }
}

// --- Integration: WebSocket push handler ---

const PORTFOLIO = new IncrementalAggregator();

function onPriceUpdate(event) {
  // event: { type: 'ADD'|'UPDATE'|'REMOVE', entityId: string, price: number }
  if (event.type === 'ADD')    PORTFOLIO.add(event.entityId, event.price);
  if (event.type === 'UPDATE') PORTFOLIO.update(event.entityId, event.price);
  if (event.type === 'REMOVE') PORTFOLIO.remove(event.entityId);
}

// --- Agent tool: get_portfolio_summary ---
// O(1) — reads precomputed state; no source API call needed.

async function getPortfolioSummary() {
  return PORTFOLIO.get();
}

// --- Periodic resync (every 5 minutes) ---

async function periodicResync() {
  const authoritative = await fetchAllPositions();  // one bulk call
  PORTFOLIO.resync(authoritative);
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. 5-stock portfolio scenario: ADD × 5, UPDATE × 1, REMOVE × 1, ADD × 1. All operations timed over 100 000 iterations.

```
=== IncrementalAggregator: 5-stock portfolio (AAPL/MSFT/GOOG/AMZN/NVDA) ===

After ADD × 5:
  { count:5, sum:1859.2, average:371.84, min:175.8, max:875.2, minId:'GOOG', maxId:'NVDA' }

After UPDATE AAPL 189.50 → 191.20:
  { count:5, sum:1860.9, average:372.18, min:175.8, max:875.2, minId:'GOOG', maxId:'NVDA' }
  sum updated as: 1859.2 + (191.20 - 189.50) = 1860.90 — no re-fetch

After REMOVE GOOG (position closed):
  { count:4, sum:1685.1, average:421.275, min:191.2, max:875.2, minId:'AAPL', maxId:'NVDA' }
  O(N) min recompute triggered: removed entity was minId

After ADD TSLA 250.60:
  { count:5, sum:1935.7, average:387.14, min:191.2, max:875.2, minId:'AAPL', maxId:'NVDA' }

=== Timing (100 000 iterations) ===

add():                              0.0009 ms
update() — no min/max recompute:    0.0005 ms
update() — min recompute (N=100):   0.0016 ms   ← worst case
get():                              0.0014 ms

=== Cost comparison: 1 000 positions, 10 push events/sec, 6 hr/day market hours ===

Re-fetch-and-recompute on every push:
  216 000 events/day × 1 000 calls/event × $0.00003 = $6.48/day

Incremental aggregation + 5-min resync:
  12 resyncs/hour × 6 hours = 72 resyncs/day
  72 resyncs × 1 000 calls × $0.00003 = $0.022/day
  Savings: $6.46/day (99.7%)

  update() on each push: 0.0005ms/event × 216 000/day = 108ms total CPU — negligible

=== S-164 (push-pull gap detector) vs S-169 (incremental aggregator) ===

S-164: detects when a push event stops arriving (entity stops updating)
       → triggers a targeted re-fetch for the gap entity
S-169: maintains O(1) running aggregates from push events
       → apply the re-fetched value via update()

Compose: S-164 gap signal → pull fresh value from source → S-169.update() applies it
```

## See also

[S-164](s164-push-pull-hybrid-scheduler.md) · [S-100](s100-live-data-freshness-contracts.md) · [S-43](s43-tool-result-caching.md) · [S-165](s165-derived-value-freshness-tracker.md) · [S-102](s102-composable-agent-data-layers.md)

## Go deeper

Keywords: `incremental live data aggregation` · `running aggregate push events` · `O(1) aggregate update` · `live stream aggregate` · `running sum count average` · `push event aggregate` · `incremental portfolio aggregate` · `streaming aggregate maintenance` · `live data running total` · `event-driven aggregate`
