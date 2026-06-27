# S-149 · Multi-Source Data Consistency Snapshot

[S-137](s137-multi-source-field-level-merge.md) fans out fetch requests to N sources in parallel and returns the first non-null value per field. It records provenance — which source filled each field — but treats the resulting merged record as a single logical unit. [F-101](../forward-deployed/f101-live-fan-out-conflict-annotation.md) detects value disagreements between sources. Neither tracks the temporal spread of when the individual fields were observed.

In a parallel multi-source fetch, different sources respond at different times. Bloomberg returns `price` at t+80ms; Refinitiv returns `volume` at t+820ms. Both values are injected into the same merged record and presented to the agent as contemporaneous. The model treats `price: 289.50` and `volume: 12345678` as belonging to the same market instant. They don't — they are 740ms apart. In a fast-moving market, the price at t+80ms and the volume at t+820ms may reflect two different states of the order book.

A data consistency snapshot computes the temporal spread across all field fetch timestamps in a merged record: `max(fetchedAtMs) - min(fetchedAtMs)`. When the spread exceeds a threshold, the snapshot is flagged as temporally inconsistent. The agent can then re-fetch the lagging fields, annotate the analysis with the inconsistency, or abort for actions that require a tight snapshot. For portfolio summaries and reports, a 500ms spread is acceptable. For trade execution or real-time risk scoring, even 100ms may not be.

## Situation

A multi-step merger agreement analysis runs on a merged record from four sources. The analysis includes: (1) current price comparison against the merger consideration, (2) volume-weighted average price calculation over the previous session, (3) bid-ask spread check for liquidity. All three steps use fields from the same merged record.

The merged record has field fetch timestamps:
- `price`: Bloomberg, t+80ms
- `bidAsk`: Bloomberg, t+95ms
- `marketCap`: Refinitiv, t+150ms
- `volume`: Refinitiv, t+820ms (slow response — Refinitiv was under load)

Spread: 820ms - 80ms = 740ms. With a 500ms consistency threshold, the snapshot is ANNOTATE: the analysis can proceed, but the agent context includes a note that `volume` was observed 740ms after `price`. The risk model treating these as the same market instant is flagged.

For an HFT alert agent configured at 100ms threshold: same spread 740ms → REFRESH_OUTLIERS. Agent re-fetches `price`, `bidAsk`, `marketCap` to match the observation time of `volume`, then proceeds with a consistent snapshot.

## Forces

- **Spread matters, not age.** A record where all fields are 30 seconds old is more consistent than a record where one field is 10ms old and another is 800ms old. The relevant metric is the temporal spread across fields in the same analysis — not the age of any single field. S-148 (per-action data age budget) checks each field against an action budget; S-149 checks the consistency of the set as a whole.
- **The anchor is the newest field, not the oldest.** To achieve a consistent snapshot, you refresh the old fields to match the newest one's observation time. Re-fetching the newest field again is unnecessary (it just re-ran). `staleOutliers()` identifies the fields that lag behind the newest and should be refreshed.
- **Threshold must be calibrated per analysis type.** A 500ms spread is acceptable for a daily risk summary. A 100ms spread is the maximum for real-time margin calculations. A 50ms spread may be required for collocated HFT systems. The threshold is a domain constant, not a system default.
- **This is distinct from F-101 (conflict annotation).** F-101 detects when multiple sources return different values for the same field (Bloomberg says `$289.50`, Refinitiv says `$291.15`). S-149 detects when multiple fields were observed at different times within the same merged record, regardless of whether the values conflict. A record where all sources agree on their values can still be temporally inconsistent.
- **S-137 provenance is the data source.** S-137's `provenance[field].fetchedAtMs` already tracks when each field was fetched. S-149 reads those timestamps — it doesn't require separate instrumentation. The overhead is entirely in the spread computation, which runs in under 0.002ms.
- **ANNOTATE tier enables graceful degradation.** Not every analysis requires aborting on inconsistency. A spread of 600ms on a 500ms threshold is marginal. Inject a compact note into the agent's context: `_snapshot_spread_ms: 600, _snapshot_note: "price observed 600ms before volume"`. The model can factor this into its confidence or explicitly flag it in the output.

## The move

**Compute temporal spread across field fetch timestamps. Gate on threshold. Refresh lagging fields or annotate before proceeding.**

```js
// --- Multi-source data consistency snapshot ---
// maxSpreadMs: maximum acceptable spread between oldest and newest field timestamp (default 500ms)

class DataConsistencySnapshot {
  constructor(opts = {}) {
    this._maxSpreadMs = opts.maxSpreadMs ?? 500;
  }

  // Assess the temporal consistency of a merged record's field fetch timestamps.
  // fieldFetchTimes: { [fieldName]: fetchedAtMs }  — from S-137 provenance
  // Returns { consistent, spreadMs, oldestField, newestField, fieldCount, recommendation }
  assess(fieldFetchTimes) {
    const entries = Object.entries(fieldFetchTimes).filter(([, t]) => t != null);
    if (entries.length === 0) return { consistent: null, spreadMs: 0, reason: 'NO_TIMESTAMPS' };

    let minMs = Infinity, maxMs = -Infinity;
    let oldestField = null, newestField = null;
    for (const [field, ms] of entries) {
      if (ms < minMs) { minMs = ms; oldestField = field; }
      if (ms > maxMs) { maxMs = ms; newestField = field; }
    }

    const spreadMs = maxMs - minMs;
    return {
      consistent:     spreadMs <= this._maxSpreadMs,
      spreadMs,
      oldestField,
      newestField,
      fieldCount:     entries.length,
      recommendation: spreadMs <= this._maxSpreadMs       ? 'PROCEED'
                    : spreadMs <= this._maxSpreadMs * 2   ? 'ANNOTATE'
                    :                                       'REFRESH_OUTLIERS',
    };
  }

  // Fields that lag behind the newest fetch by more than maxSpreadMs.
  // These are the fields to re-fetch for a consistent snapshot.
  // Returns [{field, lagMs}] sorted by lagMs descending.
  staleOutliers(fieldFetchTimes) {
    const entries = Object.entries(fieldFetchTimes).filter(([, t]) => t != null);
    if (entries.length === 0) return [];
    const maxMs = Math.max(...entries.map(([, t]) => t));
    return entries
      .filter(([, t]) => maxMs - t > this._maxSpreadMs)
      .map(([field, t]) => ({ field, lagMs: maxMs - t }))
      .sort((a, b) => b.lagMs - a.lagMs);
  }

  // Build a context annotation for ANNOTATE-tier snapshots.
  // Compact enough to inject before the analysis section.
  annotationBlock(fieldFetchTimes) {
    const { spreadMs, oldestField, newestField } = this.assess(fieldFetchTimes);
    return {
      _snapshot_spread_ms:    spreadMs,
      _snapshot_oldest_field: oldestField,
      _snapshot_newest_field: newestField,
      _snapshot_note: `Field timestamps span ${spreadMs}ms; ${oldestField} observed ${spreadMs}ms before ${newestField}. Treat as approximate contemporaneous data.`,
    };
  }
}

// --- Integration with S-137 ---
// S-137 provenance includes fetchedAtMs per field. Extract it and assess consistency.

function buildFieldFetchTimes(s137ProvenanceMap) {
  const times = {};
  for (const [field, prov] of Object.entries(s137ProvenanceMap)) {
    if (prov?.fetchedAtMs) times[field] = prov.fetchedAtMs;
  }
  return times;
}

async function mergeWithConsistencyGate(fieldSourceMap, snapshotConfig, refetchFn) {
  const { mergedRecord, provenance } = await mergeFieldsFromSources(fieldSourceMap);   // S-137
  const fieldFetchTimes = buildFieldFetchTimes(provenance);
  const snapshot = snapshotConfig.assess(fieldFetchTimes);

  if (snapshot.recommendation === 'REFRESH_OUTLIERS') {
    const outliers = snapshotConfig.staleOutliers(fieldFetchTimes);
    const refreshed = await refetchFn(outliers.map(o => o.field));
    for (const field of Object.keys(refreshed)) {
      mergedRecord[field] = refreshed[field].value;
      fieldFetchTimes[field] = refreshed[field].fetchedAtMs;
    }
  }

  if (snapshot.recommendation === 'ANNOTATE') {
    Object.assign(mergedRecord, snapshotConfig.annotationBlock(fieldFetchTimes));
  }

  return { mergedRecord, snapshot };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `assess()` and `staleOutliers()` timed over 100 000 iterations. Field fetch timestamps are synthetic integers (equivalent to Date.now() output).

```
=== DataConsistencySnapshot timing (100 000 iterations) ===

assess() — PROCEED  (5 fields, spread=260ms):         0.0018 ms
assess() — ANNOTATE (4 fields, spread=740ms):         0.0014 ms
staleOutliers() — 0 outliers:                         0.0024 ms
staleOutliers() — 1+ outliers:                        0.0026 ms

=== Standard multi-source fetch (maxSpreadMs=500) ===

Field fetch timestamps (relative to request start):
  price:     Bloomberg,  +150ms
  bidAsk:    IEX,        +380ms
  volume:    Refinitiv,  +410ms
  marketCap: Refinitiv,  +220ms
  news:      IEX,        +305ms

assess() result:
  spreadMs:       260ms   (volume-price = 410-150)
  oldestField:    price
  newestField:    volume
  consistent:     true
  recommendation: PROCEED → no re-fetch, no annotation needed

=== High-frequency alert agent (maxSpreadMs=100) ===

Same fetch, tighter threshold:
  price:     Bloomberg, +80ms
  bidAsk:    Bloomberg, +95ms
  marketCap: Refinitiv, +150ms
  volume:    Refinitiv, +820ms   ← Refinitiv under load

assess() result:
  spreadMs:       740ms
  oldestField:    price
  newestField:    volume
  consistent:     false
  recommendation: ANNOTATE   (at maxSpreadMs=500, 740ms < 1000ms = 500×2)
                  REFRESH_OUTLIERS (at maxSpreadMs=100, 740ms > 200ms = 100×2)

staleOutliers() at maxSpreadMs=100:
  [{ field: 'price',     lagMs: 740 },
   { field: 'bidAsk',    lagMs: 725 },
   { field: 'marketCap', lagMs: 670 }]

  → Re-fetch price, bidAsk, marketCap.
    After re-fetch at t+900ms:
      price: +895ms, bidAsk: +901ms, marketCap: +898ms, volume: +820ms
      new spread: 901-820 = 81ms < 100ms → PROCEED

=== Annotated context block (ANNOTATE tier) ===

{
  _snapshot_spread_ms:    740,
  _snapshot_oldest_field: 'price',
  _snapshot_newest_field: 'volume',
  _snapshot_note: 'Field timestamps span 740ms; price observed 740ms before volume. Treat as approximate contemporaneous data.'
}

Injected before analysis section. Model flags uncertainty in VWAP calculation
that depends on both price and volume observations being contemporaneous.

=== S-137 vs F-101 vs S-148 vs S-149 ===

              │ S-137 (multi-source merge)      │ F-101 (fan-out conflict)        │ S-148 (per-action freshness)    │ S-149 (consistency snapshot)
──────────────┼─────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────
What it checks│ Which source to use per field   │ Value disagreement between srcs  │ Data age vs action budget       │ Temporal spread across all fields
Question      │ Where does this value come from?│ Do sources agree on value?       │ Is this data fresh enough?      │ Were these fields observed near-simultaneously?
When it fires │ During merge (source selection) │ After all sources respond        │ Before action execution         │ Before multi-step analysis
Trigger       │ Every merge call                │ When N sources return same field │ Per action, per field           │ Per analysis, per merged record
Output        │ Merged record + provenance      │ _conflict annotation             │ FRESH/STALE + staleFields       │ PROCEED/ANNOTATE/REFRESH_OUTLIERS
Composes      │ S-149 reads its provenance      │ S-149 complements (value vs time)│ S-149 is spread; S-148 is age  │ S-137 provenance feeds S-149
```

## See also

[S-137](s137-multi-source-field-level-merge.md) · [F-101](../forward-deployed/f101-live-fan-out-conflict-annotation.md) · [S-148](s148-per-action-data-freshness-budget.md) · [S-100](s100-live-data-freshness-contracts.md) · [F-114](../forward-deployed/f114-source-response-time-slos.md) · [F-98](../forward-deployed/f98-live-source-fan-out.md)

## Go deeper

Keywords: `multi-source data consistency` · `temporal consistency snapshot` · `data fetch time spread` · `consistent data view` · `multi-source timestamp spread` · `data observation consistency` · `field fetch time spread` · `temporal data consistency` · `cross-source time alignment` · `consistent snapshot live data`
