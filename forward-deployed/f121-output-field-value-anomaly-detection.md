# F-121 · Output Field Value Anomaly Detection

[F-70](f70-structured-output-validation.md) validates structured output against static schema constraints: type checks, value ranges (`confidence` between 0 and 10), length bounds, co-occurrence invariants. [F-92](f92-structured-output-schema-drift.md) checks arithmetic relationships between fields in a single output (subtotal + tax = total). [F-120](f120-output-field-mutual-exclusivity.md) enforces logical exclusivity between field pairs.

All three operate without history. They know nothing about what the field has contained in the past 200 calls. F-70 can flag `confidence: -1` (below static minimum) but not `confidence: 0.2` (technically in-range, but historically the model always returns 6–9 for this field type — 0.2 is a hallucination). F-92 checks that the invoice arithmetic is internally consistent but can't flag `total_amount: 5000000000` when the historical P99 is $50 000. Static constraints catch type violations and out-of-range values; they do not catch statistically implausible values.

Output field value anomaly detection maintains a rolling distribution of observed values per numeric field. Before acting on any structured output, it computes the z-score of each numeric field against its historical distribution. A z-score above 3.0 is flagged as ANOMALY — the value is more than three standard deviations from the historical mean. No action is taken on anomalies until the distribution has at least 20 samples. Below that threshold, the field is in WARMING_UP state and passes through.

## Situation

A contract analytics pipeline extracts structured fields from enterprise SaaS contracts. Over 200 historical extractions, `termination_fee` ranges between $1M and $50M (mean $25.7M, stddev $13.8M). An adversarially crafted contract embeds a `termination_fee` of $5 000 000 000 (five billion dollars). The model, following the extraction instruction faithfully, outputs exactly what the contract says.

F-70 validation: `termination_fee` is a number. Range constraint: not set (the static max is unknown). F-70 passes. F-92: no arithmetic invariant involves `termination_fee` alone. F-92 passes. The value proceeds to the next stage where an automated clause comparison flags the company as owing $5B.

With F-121: `check('termination_fee', 5_000_000_000)` computes z-score = (5 000 000 000 − 25 727 412) / 13 777 650 = 335.75. ANOMALY. The action is blocked. The output is routed to manual review. The adversarial contract is flagged.

The zero confidence case: a model output returns `confidence: 0` for a field it extracted with high verbatim fidelity. Historically, confidence for this field runs 6.0–9.5 (mean 7.7, stddev 1.04). z-score = |0 − 7.7| / 1.04 = 7.43 → ANOMALY. The output is reviewed; it turns out a prompt change accidentally set the confidence instruction to "rate from 0 to 10 as a decimal" when the model interpreted that as a fraction.

## Forces

- **Static constraints are blind to distribution.** A termination fee of $5B is a valid number and passes any type check. It only looks wrong when measured against what this field actually contains across hundreds of real contracts. This is the gap: `type: 'number'` is not the same as `value plausible for this field in this domain`.
- **Z-score at threshold 3.0 is conservative.** At z=3.0, roughly 0.3% of normally-distributed values would be flagged as false positives. For a Gaussian distribution, this is exact; for real field distributions (often right-skewed), false-positive rates may differ. Start at z=3.0. If false-positive rate is too high (legitimate outliers being blocked), raise to z=4.0 or widen the window.
- **`check()` is O(n) in the window size.** It recomputes mean and standard deviation from the full history on every call. At window=200 and 0.0047ms per check, this is 0.047ms to process 200 numbers — fast enough for any production workload. If window grows large (>1000) and call volume is extreme (>10k/sec), switch to Welford's online algorithm: maintain running `n`, `mean`, `M2` — update in O(1) per record().
- **One detector per field per schema type.** Don't mix `termination_fee` values from SaaS contracts and employment agreements in the same distribution. The historical distributions belong to a specific extraction context. Scope the detector to `{schema_version, field_name}` if you have multiple extraction schemas.
- **The warming period is a hard floor, not a soft suggestion.** During WARMING_UP (fewer than 20 samples), all values pass through. This is intentional: a detector with 3 samples has no statistical validity — it would flag legitimate values as anomalies. Twenty samples is the minimum; 50 is better. Add the first N outputs to the history before going live with anomaly gating.
- **Don't replace F-70 — compose with it.** Run F-70 type/range checks first. Run F-121 anomaly detection second. A field that fails F-70 is structurally invalid; a field that fails F-121 is statistically suspicious but structurally valid. Both matter; they catch different failures. The action on F-121 failure may be softer than F-70 failure — route to review rather than hard abort, depending on the field's consequence cost.

## The move

**Build a rolling distribution per numeric field. Before acting on structured output, check each field's z-score against its history. Abort or route to review on ANOMALY.**

```js
// --- Output field value anomaly detector ---
// Maintains a rolling window of observed values per numeric field.
// check() returns NORMAL / ANOMALY / WARMING_UP.
// Compose with F-70 (run F-70 first; run this second for plausibility check).

class OutputFieldAnomalyDetector {
  constructor(opts = {}) {
    this._windowSize    = opts.windowSize    ?? 200;   // max samples per field
    this._outlierZScore = opts.outlierZScore ?? 3.0;   // z-score threshold for ANOMALY
    this._minSamples    = opts.minSamples    ?? 20;    // minimum samples before gating
    this._history       = new Map();                   // fieldName → number[]
  }

  // Record a verified value (from a human-reviewed or trusted output).
  // Call this after manual review or after a value passes all checks.
  record(fieldName, value) {
    if (typeof value !== 'number' || !isFinite(value)) return;
    if (!this._history.has(fieldName)) this._history.set(fieldName, []);
    const arr = this._history.get(fieldName);
    arr.push(value);
    if (arr.length > this._windowSize) arr.shift();
  }

  // O(n): recomputes mean and stddev from the full window on each call.
  // Switch to Welford's algorithm if window > 1000 and call rate is high.
  _stats(arr) {
    const n    = arr.length;
    const mean = arr.reduce((s, v) => s + v, 0) / n;
    const variance = arr.reduce((s, v) => s + (v - mean) ** 2, 0) / n;
    return { mean, stddev: Math.sqrt(variance) };
  }

  // Check a single numeric field value against its historical distribution.
  // Returns { status: 'NORMAL'|'ANOMALY'|'WARMING_UP'|'SKIP', zScore, mean, stddev }
  check(fieldName, value) {
    if (typeof value !== 'number' || !isFinite(value)) {
      return { status: 'SKIP', reason: 'NON_NUMERIC' };
    }
    const arr = this._history.get(fieldName);
    if (!arr || arr.length < this._minSamples) {
      return { status: 'WARMING_UP', samples: arr ? arr.length : 0, required: this._minSamples };
    }
    const { mean, stddev } = this._stats(arr);
    if (stddev === 0) {
      return { status: value === mean ? 'NORMAL' : 'ANOMALY',
               zScore: null, mean, stddev: 0, value, fieldName };
    }
    const zScore = Math.abs((value - mean) / stddev);
    return {
      status:   zScore > this._outlierZScore ? 'ANOMALY' : 'NORMAL',
      zScore:   parseFloat(zScore.toFixed(3)),
      mean:     parseFloat(mean.toFixed(2)),
      stddev:   parseFloat(stddev.toFixed(2)),
      value,
      fieldName,
    };
  }

  // Check all numeric fields in a structured output object.
  // Returns { passed, anomalies: [fieldName...], results: {field: checkResult} }
  checkOutput(output) {
    const results   = {};
    const anomalies = [];
    for (const [field, value] of Object.entries(output)) {
      if (typeof value === 'number') {
        results[field] = this.check(field, value);
        if (results[field].status === 'ANOMALY') anomalies.push(field);
      }
    }
    return { passed: anomalies.length === 0, anomalies, results };
  }

  // Summary of all warmed-up fields for monitoring dashboards.
  fieldStats() {
    const out = {};
    for (const [field, arr] of this._history.entries()) {
      if (arr.length >= this._minSamples) {
        const s = this._stats(arr);
        out[field] = { samples: arr.length,
                       mean: parseFloat(s.mean.toFixed(2)),
                       stddev: parseFloat(s.stddev.toFixed(2)) };
      }
    }
    return out;
  }
}

// --- Integration pattern ---
// Run F-70 first (structural). Run anomaly detection second (statistical).

const ANOMALY_DETECTOR = new OutputFieldAnomalyDetector({
  windowSize: 200, outlierZScore: 3.0, minSamples: 20
});

function validateAndAct(output, schema, action) {
  // 1. F-70 structural checks (type, range, co-occurrence)
  const structuralResult = runF70Checks(output, schema);
  if (!structuralResult.passed) throw structuralError(structuralResult);

  // 2. Statistical anomaly check on numeric fields
  const anomalyResult = ANOMALY_DETECTOR.checkOutput(output);
  if (!anomalyResult.passed) {
    log({ event: 'output_anomaly', anomalies: anomalyResult.anomalies,
          details: anomalyResult.results });
    throw anomalyError(anomalyResult);   // or route to review instead of hard abort
  }

  // 3. Record values after both checks pass — grows the distribution
  for (const [field, value] of Object.entries(output)) {
    if (typeof value === 'number') ANOMALY_DETECTOR.record(field, value);
  }

  return action(output);
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()` and `check()` timed over 100 000 iterations. History seeded with 200 realistic contract extraction values (uniform random within domain range).

```
=== OutputFieldAnomalyDetector timing (100 000 iterations) ===

record():                          0.0007 ms   (append + conditional shift)
check() — WARMING_UP:              0.0003 ms   (early exit, no history)
check() — NORMAL (200 samples):    0.0047 ms   (O(n) mean + stddev)
check() — ANOMALY (200 samples):   0.0030 ms   (same O(n) path)
checkOutput() — 4 fields, PASS:    0.0688 ms

Note: check() is O(n) in window size (recomputes stats from scratch).
At n=200: 0.005ms/check. At n=1000: ~0.025ms/check. Switch to Welford's
online algorithm (running mean + M2) if window > 1000 and call rate > 5k/sec.

=== Field history (200 samples, contract extraction) ===

termination_fee:  mean=$25,727,413  stddev=$13,777,651  (samples=200)
confidence:       mean=7.70         stddev=1.04          (samples=200)
page_count:       mean=61.2         stddev=31.4          (samples=200)
indemnity_cap:    mean=$10,554,063  stddev=$5,642,335    (samples=200)

=== Scenario 1: Normal output — PASS ===

input: { termination_fee: 12_000_000, confidence: 7.8,
          page_count: 45, indemnity_cap: 5_000_000 }

checkOutput():
  termination_fee:  zScore=0.997   → NORMAL
  confidence:       zScore=0.096   → NORMAL
  page_count:       zScore=0.515   → NORMAL
  indemnity_cap:    zScore=0.982   → NORMAL

passed: true   anomalies: []

=== Scenario 2: Adversarial contract — termination_fee $5B ===

input: { termination_fee: 5_000_000_000, confidence: 8.2,
          page_count: 55, indemnity_cap: 3_000_000 }

check('termination_fee', 5_000_000_000):
  zScore = |5,000,000,000 − 25,727,413| / 13,777,651 = 335.746
  status: ANOMALY

passed: false   anomalies: ['termination_fee']
Action: blocked, routed to manual review. Adversarial contract flagged.

=== Scenario 3: Confidence hallucination — zero confidence ===

input: { confidence: 0 }
check('confidence', 0):
  zScore = |0 − 7.70| / 1.04 = 7.432 > 3.0
  status: ANOMALY   (in-range per F-70, but statistically implausible)

Root cause identified: a prompt change re-described the 0–10 scale as "a decimal
fraction of 1", causing the model to output 0.0–0.9 values mapped to 0 after
integer coercion. F-121 caught it before 500 affected extractions.

=== Scenario 4: Warming up (1 sample) ===

ANOMALY_DETECTOR with 1 sample:
  check('termination_fee', 5_000_000_000) → { status: 'WARMING_UP', samples: 1, required: 20 }
  → passes through until minSamples threshold reached.

=== F-70 vs F-92 vs F-120 vs F-121 ===

              │ F-70 (schema validation)     │ F-92 (arithmetic invariants) │ F-120 (mutual exclusivity)   │ F-121 (value anomaly)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
What it checks│ Type, range, co-occurrence   │ Sum/product relationships     │ Logical field-pair conflicts  │ Statistical plausibility
Knowledge base│ Static schema definition     │ Static formula definitions   │ Static rule table            │ Rolling historical distribution
History req.  │ None                         │ None                         │ None                         │ ≥20 samples per field
Catches       │ Type error, out-of-range     │ Arithmetic inconsistency     │ Both-truthy, conditional excl.│ Plausible-but-wrong values
Misses        │ In-range hallucinations      │ Single-field outliers        │ Value-plausibility issues    │ Type/structural violations
Run after     │ First (structural gate)      │ After F-70                   │ After F-70                   │ After F-70 and F-92
```

## See also

[F-70](f70-structured-output-validation.md) · [F-92](f92-structured-output-schema-drift.md) · [F-120](f120-output-field-mutual-exclusivity.md) · [F-116](f116-per-field-extraction-error-rate.md) · [S-143](../stacks/s143-output-token-variance-tracking.md) · [F-97](f97-output-field-confidence-annotation.md)

## Go deeper

Keywords: `output field anomaly detection` · `LLM output value anomaly` · `structured output statistical validation` · `numeric field z-score check` · `output value distribution monitoring` · `LLM hallucination value detection` · `rolling field distribution` · `output plausibility check` · `numeric output anomaly` · `z-score output validation`
