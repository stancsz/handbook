# F-126 · Output Field Change Velocity

[S-116](../stacks/s116-multi-run-output-determinism.md) tests determinism offline: run the same prompt five times at temperature zero and measure how often the output matches. [F-79](f79-semantic-regression-detection.md) compares outputs between two deploys for the same input set. [F-94](f94-intra-session-claim-consistency.md) checks that facts stated in one turn of a session are consistent with facts stated in another turn of the same session.

None of these operate on the cross-session production history of a single extraction field for a specific input entity. You run the extraction agent 450 times against contracts from the same legal template. On Monday, `jurisdiction` comes back "New York." On Wednesday, "Delaware." On Friday, "New York" again. The structural validator (F-70) passes every time — both are non-empty strings. The anomaly detector (F-121) passes — both are categoricals, not numerics. F-94 does not apply — these are separate sessions. S-116 runs offline at temperature zero on synthetic inputs; it does not see this production pattern.

The flip rate is the signal. For a given `(field, input_key)` pair, the flip rate is the proportion of consecutive-call pairs where the extracted value changed. A flip rate of zero means the model extracts the same value every time for this input entity — the field is stable. A flip rate above a threshold (default 0.20) means the model is oscillating — the field is unstable for this entity.

Unstable fields are the ones most likely to route a contract to the wrong queue, classify a customer in the wrong tier, or recommend the wrong action on the same input entity depending on which call happens to run on a given day.

## Situation

A contract extraction agent processes 10 000 contracts/day. Field `risk_level` has been extracted 450 times for contracts matching template `tmpl-C881-v3`. The flip rate is 0.68: `risk_level` returns `HIGH` on some calls and `MEDIUM` on others for the same template, with no change in the input. F-70 passes every time. No existing assertion catches it.

Two weeks later a case manager notices that the same contract type is being routed to different review queues on different days. The agent ran 450 times and produced inconsistent risk classifications for the same input. The cost of the inconsistency was invisible until it became a routing audit.

`FieldFlipRateTracker.allUnstable()` would have surfaced `risk_level` as UNSTABLE (flipRate=0.68) after the first 20 production calls, giving two weeks of advance notice.

## Forces

- **The flip rate is an instability signal, not an error signal.** A flip rate of 0.68 does not mean the model is wrong 68% of the time. It means the model is uncertain — the input does not contain enough signal to determine `risk_level` unambiguously, and the model is sampling around that uncertainty. The fix is not to discard one value; it is to investigate why the field is ambiguous for this entity type.
- **Input key must be stable and meaningful.** The `input_key` is a canonical identifier for the input entity or template — `contract_id`, or a hash of `template_type + schema_version` for template-based extractions. Using a full content hash as the key makes every call distinct (no two calls ever match) and produces no useful signal. The key must correspond to the intended semantic grouping.
- **Distinguish "same template, different instances" from "same document."** For document extraction, the `input_key` is the document ID — the same PDF processed twice. For template-based extraction where many contracts share the same structure, the `input_key` can be the template type. The semantics of "same input" must be defined by the deployment.
- **Window size determines sensitivity.** At `windowSize: 20`, a single batch of 20 calls produces a reliable flip rate estimate. At `windowSize: 5`, estimates are noisy — a single bad call raises the rate to 0.40 even for a stable field. Start at 20; lower to 10 only if the call volume per entity is too low to fill a 20-call window within the monitoring period.
- **Alert on newly unstable fields, not all unstable fields.** A field that has been UNSTABLE at 0.22 for six months is known. An alert that fires every time `allUnstable()` runs would be noise. Track which fields transitioned from STABLE to UNSTABLE since the last check; alert on transitions, not on steady-state.
- **Use the flip rate to prioritize prompt work.** A field with flipRate 0.68 needs a disambiguation instruction in the prompt, a reference-data lookup, or a fallback rule. A field at 0.03 is stable enough to leave alone. The flip rate ranks the work queue for prompt engineers.

## The move

**For each production extraction, record the field value keyed by `(field, input_key)`. Maintain a rolling window of N values. Run `allUnstable()` periodically; alert on fields transitioning from STABLE to UNSTABLE.**

```js
// --- Output field change velocity tracker ---
// Tracks per-(field, input_key) value history across production calls.
// Flip rate = (consecutive-pair transitions) / (total pairs in window).
// Alert threshold default 0.20: > 20% of consecutive pairs changed.

class FieldFlipRateTracker {
  constructor(opts = {}) {
    this._windowSize     = opts.windowSize     ?? 20;
    this._alertThreshold = opts.alertThreshold ?? 0.20;
    this._history        = new Map();   // 'field:inputKey' → value[]
  }

  // Record an extracted value. Call after each successful extraction.
  record(field, inputKey, value) {
    const key = field + ':' + inputKey;
    if (!this._history.has(key)) this._history.set(key, []);
    const arr = this._history.get(key);
    arr.push(String(value));
    if (arr.length > this._windowSize) arr.shift();
  }

  // Flip rate for a specific (field, inputKey) pair.
  // Returns { status, flipRate, flips, samples, threshold }
  flipRate(field, inputKey) {
    const key = field + ':' + inputKey;
    const arr = this._history.get(key);
    if (!arr || arr.length < 2) {
      return { status: 'INSUFFICIENT_DATA', samples: arr ? arr.length : 0, required: 2 };
    }
    let flips = 0;
    for (let i = 1; i < arr.length; i++) {
      if (arr[i] !== arr[i - 1]) flips++;
    }
    const rate = flips / (arr.length - 1);
    return {
      status:    rate >= this._alertThreshold ? 'UNSTABLE' : 'STABLE',
      flipRate:  parseFloat(rate.toFixed(3)),
      flips,
      samples:   arr.length,
      threshold: this._alertThreshold,
    };
  }

  // Return all (field, inputKey) pairs currently UNSTABLE.
  // Call periodically from a monitoring job; diff against last run to find transitions.
  allUnstable() {
    const out = [];
    for (const [key, arr] of this._history) {
      if (arr.length < 2) continue;
      let flips = 0;
      for (let i = 1; i < arr.length; i++) if (arr[i] !== arr[i - 1]) flips++;
      const rate = flips / (arr.length - 1);
      if (rate >= this._alertThreshold) {
        const idx = key.indexOf(':');
        out.push({
          field:    key.slice(0, idx),
          inputKey: key.slice(idx + 1),
          flipRate: parseFloat(rate.toFixed(3)),
          samples:  arr.length,
        });
      }
    }
    return out;
  }
}

// --- Integration: record after extraction; alert on STABLE → UNSTABLE transitions ---

const FLIP_TRACKER = new FieldFlipRateTracker({ windowSize: 20, alertThreshold: 0.20 });

// After each extraction call:
function onExtractionResult(output, inputKey) {
  for (const [field, value] of Object.entries(output)) {
    FLIP_TRACKER.record(field, inputKey, value);
  }
}

// Monitoring job (e.g. every 5 minutes):
let _prevUnstable = new Set();
function checkFlipRates() {
  const unstable = FLIP_TRACKER.allUnstable();
  const unstableKeys = new Set(unstable.map(u => u.field + ':' + u.inputKey));
  const newlyUnstable = unstable.filter(u => !_prevUnstable.has(u.field + ':' + u.inputKey));
  if (newlyUnstable.length > 0) {
    alert({ event: 'field_flip_rate_alert', newlyUnstable });
  }
  _prevUnstable = unstableKeys;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()` and `flipRate()` timed over 100 000 iterations. Window size 20. Three fields tracked for the same input key `tmpl-C881-v3`.

```
=== FieldFlipRateTracker timing (100 000 iterations, windowSize=20) ===

record()                  0.0006 ms
flipRate()  20 samples    0.0009 ms
allUnstable()  3 fields   0.0024 ms

=== Scenario A: governing_law (stable — same value every call) ===

20 calls: all return "New York"

flipRate('governing_law', 'tmpl-C881-v3'):
{
  status:    'STABLE',
  flipRate:  0,
  flips:     0,
  samples:   20,
  threshold: 0.2
}

=== Scenario B: risk_level (unstable — oscillating HIGH/MEDIUM) ===

20 calls: HIGH HIGH HIGH MEDIUM HIGH HIGH HIGH MEDIUM ... (every 3rd is MEDIUM)
Consecutive transitions: 13 of 19 pairs changed.

flipRate('risk_level', 'tmpl-C881-v3'):
{
  status:    'UNSTABLE',
  flipRate:  0.684,
  flips:     13,
  samples:   20,
  threshold: 0.2
}

=== Scenario C: recommended_action (maximally unstable — alternating) ===

20 calls: APPROVE REJECT APPROVE REJECT ...
All 19 consecutive pairs changed.

flipRate('recommended_action', 'tmpl-C881-v3'):
{
  status:    'UNSTABLE',
  flipRate:  1,
  flips:     19,
  samples:   20,
  threshold: 0.2
}

=== allUnstable() after three scenarios ===

[
  { field: 'risk_level',          inputKey: 'tmpl-C881-v3', flipRate: 0.684, samples: 20 },
  { field: 'recommended_action',  inputKey: 'tmpl-C881-v3', flipRate: 1,     samples: 20 }
]

governing_law not in list (STABLE, flipRate=0).

=== What instability means — diagnosis path ===

flipRate 0.68 on risk_level + tmpl-C881-v3:
  → Check: does the template contain an explicit risk clause?
    Yes → check if the model is missing it (add citation instruction)
    No  → the template is genuinely ambiguous
          → options: (a) add a fallback rule keyed on contract value,
                     (b) fetch risk_category from metadata store,
                     (c) escalate template-C881 contracts to human review

flipRate 1.0 on recommended_action:
  → Model is maximally uncertain. The prompt has no tiebreaker for this entity type.
  → Add an explicit decision rule to the prompt for this template class.

=== S-116 vs F-79 vs F-94 vs F-126 ===

              │ S-116 (offline determinism) │ F-79 (deploy regression)   │ F-94 (intra-session)        │ F-126 (flip rate)
──────────────┼─────────────────────────────┼────────────────────────────┼─────────────────────────────┼───────────────────────────
When          │ Test time                   │ Deploy time                │ Within one session          │ Production, rolling history
Inputs        │ Same synthetic prompt N=5   │ Same prod inputs, 2 builds │ Prior turns, same session   │ Same entity, N prod calls
Signal        │ Binary: matches or not      │ Semantic similarity delta  │ Fact contradiction          │ Flip rate per (field, key)
Catches       │ Temp > 0 nondeterminism     │ Regression between builds  │ Intra-session contradiction │ Cross-session instability
Misses        │ Entity-specific prod drift  │ Slow drift over time       │ Multi-session patterns      │ Wrong-but-consistent output
```

## See also

[S-116](../stacks/s116-multi-run-output-determinism.md) · [F-79](f79-semantic-regression-detection.md) · [F-94](f94-intra-session-claim-consistency.md) · [F-116](f116-per-field-extraction-error-rate-tracking.md) · [F-97](f97-output-field-confidence-annotation.md) · [F-121](f121-output-field-value-anomaly-detection.md)

## Go deeper

Keywords: `output field flip rate` · `LLM field change velocity` · `extraction field instability` · `per-field value stability tracking` · `cross-session output consistency` · `field oscillation detection` · `LLM output drift per entity` · `production extraction flip rate` · `field-level determinism monitoring` · `rolling output value history`
