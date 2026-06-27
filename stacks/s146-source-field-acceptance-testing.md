# S-146 · Source Field Acceptance Testing

[F-113](../forward-deployed/f113-per-entity-data-completeness-tracking.md) tracks fill rates per (entity, field) pair across N polls once a source is in production. It detects when a field that was reliably filling starts going missing — systematic dropout from a source already in the pipeline. [S-141](s141-source-schema-contract-versioning.md) pins a versioned schema contract for a source and alerts when incoming responses deviate from it. Both tools operate on a source that is already serving live traffic.

Neither answers the question asked before a new source enters the pipeline: does this source actually deliver what its documentation claims? A new data vendor's API documentation says it provides `[price, impliedVolatility, delta, gamma, vega, theta]` for options contracts. The contract sounds complete. The actual behavior may not match: some fields may require a different endpoint, some may only be available for certain instrument types, some may be null for small-cap equities. These gaps surface silently in production unless you test for them before onboarding.

Source field acceptance testing runs N test calls across M representative entities to a new source before it enters S-137's `fieldSourceMap`. It measures per-field fill rates, P95 response latency, and type conformance against the declared schema. The result is a per-field verdict (PASS / WARN / FAIL) and an overall source onboarding recommendation: APPROVE, APPROVE_WITH_WARNINGS, or REJECT. Only APPROVED sources enter the production merge pipeline.

## Situation

A new options data provider, Cboe Data, claims to provide `[price, impliedVolatility, delta, gamma, vega, theta]` for all US-listed equity options. The team plans to add it to S-137's `fieldSourceMap` as the primary source for Greek fields. Without an acceptance test, the first sign of a problem is F-113 reporting SYSTEMATICALLY_MISSING for `gamma` and `vega` after 50 live polls — by which time those fields have been DATA_UNAVAILABLE in model context for 50 calls per entity.

Acceptance test run: 20 entities × 3 calls each = 60 calls on the "options_basic" endpoint.

- `price`: 60/60 filled → fill rate 1.00 → PASS
- `impliedVolatility`: 58/60 filled → fill rate 0.97 → PASS
- `delta`: 55/60 filled → fill rate 0.92 → PASS
- `gamma`: 12/60 filled → fill rate 0.20 → FAIL
- `vega`: 11/60 filled → fill rate 0.18 → FAIL
- `theta`: 0/60 filled → fill rate 0.00 → FAIL

Verdict: REJECT — 3 of 6 declared required fields fail the 0.80 fill rate threshold.

Engineering follows up: Cboe Data's Greek fields (gamma, vega, theta) require the "options_detailed" endpoint, not "options_basic." After reconfiguring the fetch URL, rerun: all 6 fields fill at ≥0.95. Verdict: APPROVE. Source enters S-137.

## Forces

- **Test before traffic, not after.** The acceptance test is a pre-production gate. Its purpose is to prevent bad sources from entering the merge pipeline at all. This is cheaper than discovering the problem through F-113 after live traffic has been degraded.
- **Representative test entities matter.** Testing 20 large-cap equities for an options data source is insufficient — small-cap options have different liquidity and may have different API coverage. Use a stratified entity sample: large-cap, mid-cap, small-cap, ETFs, indices. Gaps often appear in the long tail.
- **Fill rate threshold per field tier.** Required fields in S-137's `fieldSourceMap` must meet a strict threshold (default 0.80). Optional fields that will never be required get a relaxed threshold (default 0.50). A field that is only needed as a tertiary fallback can pass at 0.30. Set thresholds by how the field will be used, not uniformly.
- **Response time baseline feeds F-114.** The acceptance test measures P95 latency across all test calls. This baseline is passed to F-114's `SourceResponseTimeSLOTracker` as the initial SLO threshold: `p95Threshold = measuredP95 × 1.5`. Without a baseline, F-114 must be configured from documentation claims that may not reflect actual performance.
- **Type conformance catches coercion requirements before S-138.** If `impliedVolatility` arrives as a string ("0.2847") instead of a number, the acceptance test flags TYPE_MISMATCH. This is the signal to pre-configure S-138's normalizer for this source before onboarding — not to discover it post-deploy when coercion is missing.
- **Acceptance test ≠ load test.** N=60 calls is sufficient to characterize fill rates and type conformance. It is not sufficient to characterize behavior under rate limiting, burst load, or sustained high volume. S-140 rate limit tracking and F-114 latency SLOs handle those concerns in production.

## The move

**Run N test calls per field. Measure fill rates, latency, and type conformance. Gate onboarding on field-level verdict.**

```js
// --- Source field acceptance tester ---
// sourceId:       string — identifier for the new source
// fetchFn:        (entityId: string) => Promise<Record<string, any>>  — calls the source
// declaredFields: Array<{ name: string, type: string, required: boolean }> — from vendor docs
// opts.fillThresholdRequired:  minimum fill rate for required fields (default 0.80)
// opts.fillThresholdOptional:  minimum fill rate for optional fields (default 0.50)

class SourceFieldAcceptanceTester {
  constructor(sourceId, fetchFn, declaredFields, opts = {}) {
    this._sourceId        = sourceId;
    this._fetchFn         = fetchFn;
    this._declaredFields  = declaredFields;
    this._reqThreshold    = opts.fillThresholdRequired ?? 0.80;
    this._optThreshold    = opts.fillThresholdOptional ?? 0.50;
  }

  // Run acceptance test across testEntities, callsPerEntity times.
  // Returns a full acceptance report.
  async run(testEntities, callsPerEntity = 3) {
    const latencies = [];
    const fieldResults = new Map(
      this._declaredFields.map(f => [f.name, { filled: 0, typeMismatches: 0, total: 0 }])
    );

    for (const entityId of testEntities) {
      for (let i = 0; i < callsPerEntity; i++) {
        const start = Date.now();
        let response;
        try {
          response = await this._fetchFn(entityId);
        } catch (err) {
          latencies.push(Date.now() - start);
          for (const f of this._declaredFields) fieldResults.get(f.name).total++;
          continue;
        }
        const elapsed = Date.now() - start;
        latencies.push(elapsed);

        for (const field of this._declaredFields) {
          const r = fieldResults.get(field.name);
          r.total++;
          const value = response[field.name];
          if (value !== null && value !== undefined) {
            r.filled++;
            if (!this._typeOk(value, field.type)) r.typeMismatches++;
          }
        }
      }
    }

    return this._buildReport(fieldResults, latencies, testEntities.length, callsPerEntity);
  }

  _buildReport(fieldResults, latencies, entityCount, callsPerEntity) {
    const sorted     = [...latencies].sort((a, b) => a - b);
    const p50Latency = sorted[Math.floor(sorted.length * 0.50)] ?? null;
    const p95Latency = sorted[Math.floor(sorted.length * 0.95)] ?? null;

    const fieldVerdicts = this._declaredFields.map(field => {
      const r         = fieldResults.get(field.name);
      const fillRate  = r.total > 0 ? parseFloat((r.filled / r.total).toFixed(3)) : 0;
      const threshold = field.required ? this._reqThreshold : this._optThreshold;
      const verdict   = fillRate >= threshold               ? 'PASS'
                      : fillRate >= threshold * 0.5         ? 'WARN'
                      :                                       'FAIL';
      return {
        field:          field.name,
        required:       field.required,
        fillRate,
        threshold,
        verdict,
        typeMismatches: r.typeMismatches,
        samples:        r.total,
      };
    });

    const failCount = fieldVerdicts.filter(v => v.verdict === 'FAIL').length;
    const warnCount = fieldVerdicts.filter(v => v.verdict === 'WARN').length;
    const recommendation = failCount > 0   ? 'REJECT'
                         : warnCount > 0   ? 'APPROVE_WITH_WARNINGS'
                         :                   'APPROVE';

    return {
      sourceId:             this._sourceId,
      totalCalls:           latencies.length,
      entityCount,
      callsPerEntity,
      p50LatencyMs:         p50Latency,
      p95LatencyMs:         p95Latency,
      suggestedSLOThreshold: p95Latency ? Math.round(p95Latency * 1.5) : null,
      fieldVerdicts,
      failCount,
      warnCount,
      recommendation,
      blockerFields:        fieldVerdicts.filter(v => v.verdict === 'FAIL').map(v => v.field),
    };
  }

  _typeOk(value, declaredType) {
    if (declaredType === 'number') {
      return typeof value === 'number' ||
             (typeof value === 'string' && !isNaN(parseFloat(value)));
    }
    return typeof value === declaredType;
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `_buildReport()` timed over 100 000 iterations with pre-collected field results and latency arrays (network calls excluded from timing). Full run scenario: 20 entities × 3 calls = 60 calls to simulated Cboe Data API (in-process mock with realistic fill rates).

```
=== SourceFieldAcceptanceTester._buildReport() timing (100 000 iterations) ===

_buildReport() — 6 fields, 60 samples:   0.0041 ms
_typeOk() per field:                      0.0003 ms

=== Cboe Data: options_basic endpoint acceptance test ===

Declared fields (from API documentation):
  price             required: true    type: number
  impliedVolatility required: true    type: number
  delta             required: true    type: number
  gamma             required: true    type: number
  vega              required: true    type: number
  theta             required: true    type: number

Test config: 20 entities × 3 calls = 60 total calls
Fill threshold required: 0.80 | Fill threshold optional: 0.50

--- Run 1: options_basic endpoint ---

  field             fillRate  threshold  verdict  typeMismatches
  ──────────────    ────────  ─────────  ───────  ──────────────
  price             1.000     0.80       PASS     0
  impliedVolatility 0.967     0.80       PASS     0
  delta             0.917     0.80       PASS     4   ← arrives as string "0.423"
  gamma             0.200     0.80       FAIL     0
  vega              0.183     0.80       FAIL     0
  theta             0.000     0.80       FAIL     0

p50Latency: 187ms    p95Latency: 341ms
suggestedSLOThreshold: 512ms   (p95 × 1.5, passed to F-114 on onboarding)

recommendation: REJECT
blockerFields: ['gamma', 'vega', 'theta']

Action: engineering contacts Cboe — Greeks require options_detailed endpoint.
        Also: delta arrives as string → pre-configure S-138 COERCERS.float for 'delta'.

--- Run 2: options_detailed endpoint ---

  field             fillRate  threshold  verdict  typeMismatches
  ──────────────    ────────  ─────────  ───────  ──────────────
  price             1.000     0.80       PASS     0
  impliedVolatility 0.983     0.80       PASS     0
  delta             0.967     0.80       PASS     4   ← string coercion pre-configured in S-138
  gamma             0.983     0.80       PASS     0
  vega              0.967     0.80       PASS     0
  theta             0.950     0.80       PASS     0

p50Latency: 212ms    p95Latency: 389ms
suggestedSLOThreshold: 584ms

recommendation: APPROVE
blockerFields: []

Actions on APPROVE:
  1. Add cboe_options_detailed to S-137 fieldSourceMap for [delta, gamma, vega, theta]
  2. Register S-138 normalizer: COERCERS.float for 'delta' field
  3. Pin S-141 contract: cboe_options_detailed v1.0 with 6-field schema
  4. Seed F-114 with suggestedSLOThreshold: 584ms for cboe_options_detailed
  5. Start F-113 completeness window for cboe_options_detailed entities

=== F-113 vs S-141 vs F-114 vs S-146 ===

              │ F-113 (completeness tracking) │ S-141 (contract versioning)   │ F-114 (latency SLOs)          │ S-146 (acceptance testing)
──────────────┼───────────────────────────────┼───────────────────────────────┼───────────────────────────────┼───────────────────────────────
When          │ Ongoing — after onboarding    │ Ongoing — after onboarding    │ Ongoing — after onboarding    │ Pre-onboarding gate
Trigger       │ Each merge call (S-137)       │ Each API response             │ Each source call              │ Explicit test run (N calls)
Detects       │ Field dropout over N polls    │ Schema version change         │ Latency SLO breach            │ Fill rate, latency, type gaps
Output        │ RELIABLE/SPORADIC/SYSTEMATIC  │ CONTRACT_OK/VIOLATION         │ OK/P95_BREACH/P99_BREACH      │ PASS/WARN/FAIL per field + verdict
Action        │ Alert engineering             │ Alert + fallback via S-137    │ Deprioritize via S-137 order  │ Block or approve onboarding
Feeds         │ Engineering response          │ S-138 normalizer update       │ S-137 fieldSourceMap priority │ S-141 contract seed, F-114 SLO seed
```

## See also

[S-137](s137-multi-source-field-level-merge.md) · [F-113](../forward-deployed/f113-per-entity-data-completeness-tracking.md) · [S-141](s141-source-schema-contract-versioning.md) · [F-114](../forward-deployed/f114-source-response-time-slos.md) · [S-138](s138-source-response-normalization.md) · [S-140](s140-per-source-api-rate-limit-tracking.md)

## Go deeper

Keywords: `source field acceptance testing` · `data source onboarding test` · `source field fill rate test` · `API source acceptance gate` · `pre-production source validation` · `source field coverage test` · `data source integration test` · `field fill rate acceptance` · `new data source gate` · `source onboarding validation`
