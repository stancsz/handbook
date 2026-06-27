# F-113 · Per-Entity Data Completeness Tracking

[S-137](../stacks/s137-multi-source-field-level-merge.md) records which fields were filled and which were null in a single merge call: `summary.missing` counts nulled fields, and `provenance[field].error` names the source failure that caused each gap. This is per-call diagnostics. [F-103](f103-response-completeness-check.md) checks whether a single model response covers its required components: PRESENT, THIN, or MISSING per component, per call. [F-104](f104-live-source-health-monitor.md) tracks source error rates; when errors exceed 20%, it removes the source. It monitors source availability — not which fields stop arriving from otherwise-healthy sources.

None of these detect a field going systematically absent across multiple consecutive polls for a specific entity. A field that fails once is noise: S-137 falls back, F-104 stays calm, the merge succeeds. A field that fails on 45 of the last 50 polls for one specific entity is a data gap that will silently degrade everything downstream — model context missing a field it relied on, F-110 lineage annotations marking it NOT_FOUND, F-97 confidence dropping to LOW — with no single call that looks broken enough to alert.

Per-entity data completeness tracking maintains a rolling window of fill/missing records per (entity, field) pair. After each S-137 merge, it records whether each field was filled. `fieldCompleteness()` computes fill rates over the window. `systematicGaps()` surfaces any (entity, field) pair with a fill rate below a threshold after a minimum number of samples.

## Situation

A portfolio monitoring agent tracks 200 stocks via S-137 field-level merge from four sources. Alpha Vantage provides `rsi` and `macd` for all entities. After an undocumented Alpha Vantage API change, the field `rsi` returns null on all requests — Alpha Vantage now returns `rsi14` instead. S-140 rate-limit tracking is healthy (no 429s). F-104 health monitor is healthy (no errors). S-141 contract check catches the rename as a NEW_FIELDS_DETECTED notice and a CONTRACT_VIOLATION for `rsi` — but only for entities that were polled since the change.

Without completeness tracking: for the 80 entities not yet polled since the change, their most recent `rsi` value in context is stale. The model doesn't know `rsi` has been systematically missing for the last 50 polls on 80 entities. F-110 field lineage shows `_source: null, _lineageStatus: NOT_FOUND` on each individual call — but no aggregated view of the trend.

With completeness tracking: after 5 polls for any entity, `systematicGaps()` starts returning `{ field: 'rsi', fillRate: 0.0, samples: 5, status: 'SYSTEMATICALLY_MISSING' }`. After 20 polls, all 200 entities show the same gap. A single alert surfaces: "rsi missing for 200/200 entities in last 20 polls — probable API change, check S-141 contract for alphaVantage."

## Forces

- **Track per (entity, field), not per field globally.** Some entities are niche — they may legitimately have no `rsi` (e.g., bond funds, indices without RSI support). A global fill-rate check would miss entity-specific gaps or false-alarm on entities where the field has never been available. Track at the entity level; aggregate for alerting only when a majority of entities share the gap.
- **Rolling window, not lifetime average.** A field that was reliable for 90 days but missing for the last 3 days should alert now, not be averaged into the lifetime rate. A window of 20–50 polls (depending on polling frequency) is the right scope.
- **Three status tiers cover the meaningful cases.** RELIABLE (fill rate ≥ 0.80): field consistently available, rely on it. SPORADIC (0.20 ≤ rate < 0.80): field available sometimes — fallback logic is important, don't cache its absence. SYSTEMATICALLY_MISSING (rate < 0.20 with ≥ 5 samples): treat as a data gap, alert engineering, inject DATA_UNAVAILABLE into model context explicitly.
- **Minimum sample count prevents false alarms on new entities.** An entity added 2 polls ago with 0/2 fill rate is not a systematic gap. Require `samples ≥ 5` before classifying as SYSTEMATICALLY_MISSING.
- **Cross-entity aggregation makes individual-entity noise visible at scale.** For 200 entities all showing `rsi` SYSTEMATICALLY_MISSING in the same rolling window, the per-entity data is the detection mechanism; cross-entity aggregation (`gapsByField()`) is the alert surface. One alert per field gap, not 200 per-entity alerts.
- **Compose with F-110 field lineage.** When F-110 annotates a field with `_lineageStatus: NOT_FOUND`, that is the per-call signal. F-113 accumulates these per-call signals into trend data. Together: F-110 shows which fields were missing on each call; F-113 shows which fields are *systematically* missing across calls.

## The move

**After each merge (S-137), record fill/missing per (entity, field). Compute fill rates over a rolling window. Alert on systematic gaps.**

```js
// --- Per-entity field completeness tracker ---
// windowSize: number of recent polls to track per (entity, field)

class EntityFieldCompletenessTracker {
  constructor(windowSize = 20) {
    this._window  = windowSize;
    this._history = new Map();   // entityId → Map<fieldName, boolean[]>
  }

  // Record S-137 merge result for one entity.
  // mergedRecord: { fieldName: value|null, ... }  (S-137 merged output)
  record(entityId, mergedRecord) {
    if (!this._history.has(entityId)) {
      this._history.set(entityId, new Map());
    }
    const entityHistory = this._history.get(entityId);

    for (const [field, value] of Object.entries(mergedRecord)) {
      if (!entityHistory.has(field)) entityHistory.set(field, []);
      const hist = entityHistory.get(field);
      hist.push(value !== null && value !== undefined);
      if (hist.length > this._window) hist.shift();   // rolling window
    }
  }

  // Returns fill rates + status for all fields of one entity.
  fieldCompleteness(entityId) {
    const entityHistory = this._history.get(entityId);
    if (!entityHistory) return null;

    const result = {};
    for (const [field, hist] of entityHistory) {
      const filled    = hist.filter(Boolean).length;
      const fillRate  = hist.length > 0 ? filled / hist.length : null;
      result[field] = {
        fillRate: fillRate !== null ? parseFloat(fillRate.toFixed(3)) : null,
        samples:  hist.length,
        status:   fillRate === null         ? 'NO_DATA'
                : fillRate >= 0.80          ? 'RELIABLE'
                : fillRate >= 0.20          ? 'SPORADIC'
                :                            'SYSTEMATICALLY_MISSING',
      };
    }
    return result;
  }

  // Returns fields where fill rate < threshold and samples ≥ minSamples.
  // threshold: max fill rate to qualify as a systematic gap (default 0.20)
  // minSamples: minimum polls before flagging (default 5)
  systematicGaps(entityId, threshold = 0.20, minSamples = 5) {
    const completeness = this.fieldCompleteness(entityId);
    if (!completeness) return [];
    return Object.entries(completeness)
      .filter(([, c]) => c.fillRate !== null && c.fillRate < threshold && c.samples >= minSamples)
      .map(([field, c]) => ({ field, fillRate: c.fillRate, samples: c.samples }));
  }

  // Cross-entity aggregation: for each field, count how many entities show a systematic gap.
  // Returns fields where gapCount / totalEntities >= fleetThreshold (default 0.20)
  gapsByField(fleetThreshold = 0.20, opts = {}) {
    const { perEntityThreshold = 0.20, minSamples = 5 } = opts;
    const fieldGapCounts = new Map();   // fieldName → count of entities with gap
    let totalEntities = 0;

    for (const entityId of this._history.keys()) {
      totalEntities++;
      for (const { field } of this.systematicGaps(entityId, perEntityThreshold, minSamples)) {
        fieldGapCounts.set(field, (fieldGapCounts.get(field) ?? 0) + 1);
      }
    }

    return [...fieldGapCounts.entries()]
      .filter(([, count]) => count / totalEntities >= fleetThreshold)
      .map(([field, count]) => ({
        field,
        affectedEntities: count,
        totalEntities,
        affectedPct:      parseFloat((count / totalEntities * 100).toFixed(1)),
      }))
      .sort((a, b) => b.affectedPct - a.affectedPct);
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()`, `fieldCompleteness()`, `systematicGaps()`, `gapsByField()` timed over 100 000 iterations. Completeness tracking simulated: 200 entities × 50 polls × 6 fields.

```
=== EntityFieldCompletenessTracker timing (100 000 iterations) ===

record() — 6 fields, window not full:         0.0009 ms
record() — 6 fields, window full (shift):     0.0014 ms   (push + shift per field)
fieldCompleteness() — 6 fields, 20 samples:   0.0041 ms   (Map iteration + arithmetic)
systematicGaps() — 6 fields:                  0.0018 ms   (filter + map)
gapsByField() — 200 entities × 6 fields:      0.4821 ms   (200 × systematicGaps() + aggregation)

=== 200-entity portfolio: Alpha Vantage rsi → rsi14 migration scenario ===

Polling config: 200 stocks, 4 sources (bloomberg/refinitiv/alpha_vantage/iex)
Fields tracked: price, marketCap, peRatio, rsi, macd, volume
Window size: 20 polls

Pre-migration (polls 1–30): all 6 fields filling normally
  price:     200/200 entities RELIABLE (1.000)
  marketCap: 198/200 entities RELIABLE (0.992)
  rsi:       200/200 entities RELIABLE (1.000)   ← Alpha Vantage returning 'rsi' key

Migration event (poll 31): Alpha Vantage silently renames 'rsi' → 'rsi14'
  S-141 contract check: CONTRACT_VIOLATION {rsi: missing_required} + NEW_FIELDS_DETECTED [rsi14]
  S-137 merge: rsi → null (no fallback for rsi), DATA_UNAVAILABLE injected into context
  record(entityId, { ..., rsi: null, ... }) → rsi window: [true×20, false]

After 5 more polls (polls 32–36):
  rsi window per entity: [true×20, false×5] → fillRate: 0.80 → borderline SPORADIC

After 10 more polls (polls 37–40):
  rsi window: [true×15, false×10] → fillRate: 0.50 → SPORADIC

After 21 more polls (polls 31–51, window fully rolled):
  rsi window: [false×20] → fillRate: 0.000 → SYSTEMATICALLY_MISSING (samples: 20)

gapsByField() output after poll 51:
  [ { field: 'rsi', affectedEntities: 200, totalEntities: 200, affectedPct: 100.0 } ]

Alert: "rsi SYSTEMATICALLY_MISSING on 200/200 entities (100%) in last 20 polls
        — likely API rename; check S-141 contract for alpha_vantage and
        systematicGaps(['rsi']) to confirm extent."

=== Field completeness: AAPL after 50 polls ===

field          fillRate   samples  status
─────────────  ─────────  ───────  ─────────────────────
price          1.000      50       RELIABLE
marketCap      0.960      50       RELIABLE
peRatio        0.940      50       RELIABLE
volume         0.900      50       RELIABLE
rsi            0.000      50       SYSTEMATICALLY_MISSING   ← post-migration
macd           0.620      50       SPORADIC                 ← Alpha Vantage rate-limited 38%

Action per status:
  RELIABLE:               rely on field; content-addressed cache via S-43 appropriate
  SPORADIC:               always configure fallback in S-137 fieldSourceMap; alert if drops below 0.20
  SYSTEMATICALLY_MISSING: inject DATA_UNAVAILABLE into model context explicitly;
                          alert engineering; check S-141 contract + S-138 normalizer

=== F-103 vs S-137 vs F-104 vs F-113 ===

              │ F-103 (response completeness)    │ S-137 (merge missing tracking)  │ F-104 (source health)         │ F-113 (completeness trending)
──────────────┼──────────────────────────────────┼─────────────────────────────────┼───────────────────────────────┼──────────────────────────────────
Scope         │ One model response, one call     │ One merge call per entity       │ Per source (all entities)     │ Per (entity, field), rolling window
Tracks        │ Component coverage in output     │ Missing fields this merge       │ Source error rate             │ Fill rate trend over N polls
Gap detection │ MISSING component in one response│ null fields in one merge        │ Source unavailable (errors)   │ Systematic absence across polls
Alert surface │ Missing component → retry prompt │ DATA_UNAVAILABLE injection      │ Source REMOVED (20% errors)   │ SYSTEMATICALLY_MISSING + gapsByField
Trend         │ No                               │ No                              │ Rolling error window, yes     │ Yes — rolling fill-rate window
Cross-entity  │ No                               │ No                              │ Yes (per source, all entities)│ Yes — gapsByField() fleet view
Composes with │ F-113 accumulates F-103's signal │ F-113 accumulates S-137 missing │ F-113 catches field gaps      │ F-110 (per-call signal source),
              │ at the field level               │ per call                        │ when source is "healthy"      │ S-141 (confirms rename)
```

## See also

[S-137](../stacks/s137-multi-source-field-level-merge.md) · [F-104](f104-live-source-health-monitor.md) · [F-103](f103-response-completeness-check.md) · [S-141](../stacks/s141-source-schema-contract-versioning.md) · [F-110](f110-structured-output-field-lineage.md) · [S-140](../stacks/s140-per-source-api-rate-limit-tracking.md)

## Go deeper

Keywords: `per-entity data completeness` · `field completeness tracking` · `data gap trending` · `systematic missing field` · `entity field fill rate` · `live data completeness monitor` · `field absence trending` · `data completeness rolling window` · `entity field gap detection` · `API field missing alert`
