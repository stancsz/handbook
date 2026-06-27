# F-141 · Extraction Class Distribution Monitor

[F-121](f121-output-field-value-anomaly-detection.md) detects anomalies in individual numeric field values via z-score: if `invoice_total` is suddenly $4.7M when the historical mean is $12K, that is a per-value outlier. [F-116](f116-extraction-field-error-rate-tracker.md) tracks the binary pass/fail rate per field: `risk_level` fails extraction 8% of the time. Neither checks whether the distribution of values across the valid enum classes has shifted — whether the proportion of LOW, MEDIUM, and HIGH extractions has changed over time.

Categorical distribution shift is a distinct signal. A pipeline extracting contract `risk_level` with a 60%/30%/10% LOW/MEDIUM/HIGH baseline does not raise an F-121 anomaly when HIGH suddenly climbs to 90%: each individual value is still a valid enum member, no z-score is violated, no field fails. F-116 reports no increase in field-level extraction failures. But the shift from 10% HIGH to 90% HIGH is a strong signal that something changed: the model's prompt, the model itself, the normalization step, or the actual composition of incoming contracts. Without a distribution monitor, this shift is invisible until a downstream system raises an alert or a human notices a suspicious report.

A class distribution monitor establishes a baseline from the first N calls, then compares each subsequent sliding window against that baseline. Per-category shifts above a threshold (default 15 percentage points) trigger DRIFT_DETECTED. The monitor does not know whether the shift is caused by a model change or a genuine input change — that is a root-cause question for humans. It surfaces the signal cleanly so the right investigation can start.

## Situation

A contract extraction pipeline extracts `risk_level` (LOW/MEDIUM/HIGH) and `governing_law` (US/UK/EU/OTHER) from incoming contracts. After a model update, the team notices that the risk dashboard looks unusual — many more HIGH-risk contracts than before. No individual field fails. F-121 has no numeric value to z-score. F-116 shows normal pass rates.

The monitor, registered on `risk_level` and `governing_law`, runs after each extraction. After 100 baseline contracts (60% LOW / 30% MEDIUM / 10% HIGH), it sets the baseline distribution. The next 50 contracts after the model update show a sharply different distribution: 0% LOW / 10% MEDIUM / 90% HIGH. The monitor fires DRIFT_DETECTED: HIGH shifted from 10% to 90%, a +80pp swing.

The team checks root causes in order: (1) Was there a model update? — yes. (2) Did the prompt change? — no. (3) Did the contract mix change? — no new contract types in the incoming batch. Conclusion: the model update changed how `risk_level` is classified. The team rolls back to the prior model version per F-138 ROLLBACK criteria.

`governing_law` shows 1pp shift — well under threshold. STABLE. The monitor confirms that not every field drifted, isolating the signal to `risk_level`.

## Forces

- **Baseline window size matters more than alert threshold.** A baseline of 30 calls captures too little variance — a single unusual batch can pollute it. 100 calls is a practical minimum. Set baselineN high enough that the baseline reflects your true expected distribution, not an outlier batch.
- **WARMING_UP and INSUFFICIENT_DATA are not failures.** The monitor is honest about when it has too little data. On cold start, no alert should fire before the baseline is set. On a low-traffic field, the current window may not fill enough to compare. These states should suppress alerting, not propagate a false DRIFT_DETECTED.
- **Sliding window for current, fixed for baseline.** The baseline is locked after baselineN calls and does not drift. The current window slides (default 50 calls) so the comparison is against recent behavior, not all-time. If the baseline were also sliding, it would absorb shifts gradually and mask persistent drift.
- **Track new enum values as a separate signal.** If the current window contains a value that was never in the baseline (e.g., `"CRITICAL"` appearing after the model update), it shows up as a new key in the distribution with 0% baseline and non-zero current. The max-shift calculation catches it: 0→40 is a 40pp shift, above the 15pp threshold. DRIFT_DETECTED. Don't filter out new values — they are often the most important signal.
- **Run after normalization.** If F-135 (enum normalization) is in the pipeline, run it before recording to the monitor. `"High Risk"` and `"HIGH"` must normalize to the same value before distribution comparison, or the monitor sees a spurious distribution change caused by format variance rather than extraction behavior.
- **Distinguish model drift from data drift.** DRIFT_DETECTED does not tell you which changed — the model or the inputs. The right response depends on which. Correlate the drift timestamp with deployment logs and contract source metadata before deciding. F-138 (model swap A/B test) provides the tool to isolate a model version; F-141 provides the signal that something needs isolating.

## The move

**Register categorical fields. Record each extraction. Compare current sliding window against baseline. Report WARMING_UP / INSUFFICIENT_DATA / STABLE / DRIFT_DETECTED with per-category shift breakdown.**

```js
// --- Extraction class distribution monitor ---
// Detects shifts in the distribution of categorical field values.
// Distinct from F-121 (z-score on numeric values) and F-116 (binary pass/fail rate).
// Compose: normalize with F-135 first; alert on DRIFT_DETECTED via F-38 model log.

class ClassDistributionMonitor {
  constructor(opts) {
    opts = opts || {};
    this._baselineN      = opts.baselineN      || 100;
    this._windowN        = opts.windowN        || 50;
    this._alertThreshold = opts.alertThreshold || 15;  // percentage points
    this._fields         = {};
  }

  register(fieldName) {
    this._fields[fieldName] = {
      baseline:     null,  // locked after baselineN calls
      baselineData: [],
      current:      [],    // sliding window
      calls:        0,
    };
    return this;
  }

  record(fieldName, value) {
    const f = this._fields[fieldName];
    if (!f) return this;
    f.calls++;
    if (!f.baseline) {
      f.baselineData.push(value);
      if (f.baselineData.length >= this._baselineN) f.baseline = this._dist(f.baselineData);
    } else {
      f.current.push(value);
      if (f.current.length > this._windowN) f.current.shift();
    }
    return this;
  }

  _dist(values) {
    const counts = {}, n = values.length;
    for (const v of values) counts[v] = (counts[v] || 0) + 1;
    const dist = {};
    for (const k of Object.keys(counts)) dist[k] = parseFloat((counts[k] / n * 100).toFixed(1));
    return dist;
  }

  // Returns { status, fieldName, maxShift, shiftedCategory, alertThreshold, baseline, current, shifts }
  check(fieldName) {
    const f = this._fields[fieldName];
    if (!f || !f.baseline) {
      return { status: 'WARMING_UP', fieldName, calls: f ? f.calls : 0, needed: this._baselineN };
    }
    const minCurrentN = Math.floor(this._windowN * 0.4);
    if (f.current.length < minCurrentN) {
      return { status: 'INSUFFICIENT_DATA', fieldName, currentN: f.current.length, needed: minCurrentN };
    }

    const currentDist = this._dist(f.current);
    const allKeys = new Set([...Object.keys(f.baseline), ...Object.keys(currentDist)]);
    let maxShift = 0, shiftedCategory = null;
    const shifts = {};

    for (const k of allKeys) {
      const basePct    = f.baseline[k]    || 0;
      const currentPct = currentDist[k] || 0;
      const shift = Math.abs(currentPct - basePct);
      shifts[k] = { baseline: basePct, current: currentPct, shift: parseFloat(shift.toFixed(1)) };
      if (shift > maxShift) { maxShift = shift; shiftedCategory = k; }
    }

    return {
      status:          maxShift > this._alertThreshold ? 'DRIFT_DETECTED' : 'STABLE',
      fieldName,
      maxShift:        parseFloat(maxShift.toFixed(1)),
      shiftedCategory,
      alertThreshold:  this._alertThreshold,
      baseline:        f.baseline,
      current:         currentDist,
      shifts,
    };
  }
}

// --- Integration: post-validation monitoring ---

const DIST_MONITOR = new ClassDistributionMonitor({ baselineN: 100, windowN: 50, alertThreshold: 15 });
DIST_MONITOR.register('risk_level');
DIST_MONITOR.register('governing_law');

function recordExtraction(normalizedOutput) {
  DIST_MONITOR.record('risk_level',   normalizedOutput.risk_level);
  DIST_MONITOR.record('governing_law', normalizedOutput.governing_law);
}

// Run on a schedule (e.g., every 50 extractions or every hour)
function checkDistributions() {
  const riskCheck = DIST_MONITOR.check('risk_level');
  if (riskCheck.status === 'DRIFT_DETECTED') {
    alert({
      field:           riskCheck.fieldName,
      shiftedCategory: riskCheck.shiftedCategory,
      maxShift:        riskCheck.maxShift,
      // Next: correlate timestamp with F-38 model version log
    });
  }
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Scenario: `risk_level` extraction, 100-call baseline (60% LOW / 30% MEDIUM / 10% HIGH), then a 50-call current window after a model update (distribution shifts toward HIGH). `governing_law` second scenario shows STABLE. All ops timed over 100 000 iterations.

```
=== ClassDistributionMonitor: risk_level field ===

After 100 baseline calls:
  status: INSUFFICIENT_DATA  ← current window empty; no alert

After 50 current calls (post-model-update batch):
  status:           DRIFT_DETECTED
  maxShift:         80 pp on category: HIGH
  alertThreshold:   15 pp
  baseline:         { HIGH: 10%, LOW: 60%, MEDIUM: 30% }
  current:          { HIGH: 90%, MEDIUM: 10% }
  per-category shifts:
    HIGH:   10% → 90%  (+80 pp)  ← DRIFT_DETECTED trigger
    LOW:    60% →  0%  (-60 pp)
    MEDIUM: 30% → 10%  (-20 pp)

--- governing_law field: STABLE ---
  status:    STABLE
  maxShift:  1 pp — below threshold (15 pp)

=== Root cause checklist on DRIFT_DETECTED ===

risk_level distribution shifted LOW→HIGH after model update.
Possible causes, in order of likelihood:

  1. Model update changed classification behavior
     → check F-38 model version log; compare prompts before/after
  2. Source data shift (contracts are genuinely riskier this batch)
     → verify with document-level human review; look for contract type changes
  3. Prompt change (wording changed what LOW/MEDIUM/HIGH means to model)
     → check F-65 prompt regression; compare golden outputs
  4. Normalization gap (new informal value like "High risk" not mapped by F-135)
     → check F-135 normalizer for new input formats in recent batch

=== Timing (100 000 iterations) ===

record():        0.0002 ms
check() 3-class: 0.0086 ms

Zero API calls. Zero tokens. Runs in-process after each extraction delivery.
```

## See also

[F-121](f121-output-field-value-anomaly-detection.md) · [F-116](f116-extraction-field-error-rate-tracker.md) · [F-138](f138-model-swap-ab-test.md) · [F-140](f140-extraction-date-ordering-assertions.md) · [S-170](../stacks/s170-cost-per-outcome-tracker.md)

## Go deeper

Keywords: `extraction class distribution monitor` · `categorical field drift detection` · `enum distribution shift` · `class proportion alert` · `extraction category drift` · `distribution monitoring LLM output` · `categorical distribution baseline` · `field value distribution alert` · `model update extraction drift` · `sliding window distribution comparison`
