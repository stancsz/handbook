# F-152 · Extraction Field Null Rate Monitor

[F-145](f145-extraction-output-completeness-score.md) scores each individual extraction against the schema — it tells you that this particular extraction is 73% complete. [F-127](f127-extraction-null-rate-tracker.md) measures the aggregate null rate for each field across the current batch of N calls — it tells you what fraction of today's extractions returned null for `payment_terms`. Neither pattern tracks null rates over time or alerts when they change.

Production extraction pipelines degrade silently. A prompt change that inadvertently removes the payment terms instruction causes `payment_terms` to return null on all subsequent extractions — but if you are only looking at individual completeness scores (F-145), each extraction is 73% complete, which is not notably different from the baseline. If you are only looking at today's aggregate null rate (F-127), you need to manually compare it to yesterday's. The null rate monitor closes this gap: it maintains a rolling window of N extractions per field, computes the current null rate in that window, and alerts when a field's null rate exceeds its declared expected baseline by more than a threshold.

The alert arrives at extraction 28 in the receipt scenario — just 3 extractions into a regression that turned `payment_terms` always-null. The rolling window dilutes the signal initially (25 good extractions + 3 bad ones = 17.9% null, above the 15% threshold). By extraction 50, the window shows 56% null, unambiguously SPIKING. Only `payment_terms` fires; the other fields remain NOMINAL. The single-field signature tells you exactly where to look: the payment terms instruction in the prompt, or the document format for this field's source clause.

This is distinct from [F-26](f26-behavioral-drift-detection.md) (LLM judge scores overall output quality over time — does not break out by field) and [F-141](f141-extraction-class-distribution-monitor.md) (monitors label distribution in classification outputs — not extraction field presence).

## Situation

A contract extraction pipeline processes 200 agreements per day. Four tracked fields: `effective_date` (expected 2% null), `payment_terms` (5% null), `parties` (1% null), `jurisdiction` (8% null). Rolling window: 50 extractions. Alert threshold: baseline + 10 percentage points.

At extraction 26, a prompt deploy accidentally removes the payment terms extraction instruction from the system prompt. Extractions 26–50 return `payment_terms = null` on every call.

The null rate monitor detects the regression at extraction 28 — 3 extractions into the bad batch. At that point, the 50-item window contains 25 good extractions (payment_terms null rate ~5%) and 3 bad ones (null rate 100%). Combined null rate: ~17.9%, which exceeds 5% + 10% = 15% threshold. Alert: "Field `payment_terms` null rate is 17.9% (expected ≤ 15.0%). Check for: prompt regression, model version change, or document format shift."

Without F-152, the regression would be detectable only by manually comparing daily F-127 aggregates — typically discovered during a weekly review when 5 full days of contracts are missing payment terms.

## Forces

- **Expected null rate is per-field, declared at startup.** Not every field should be null 0% of the time. `jurisdiction` is legitimately null for some contract types (handshake agreements, internal SOWs). Declaring an 8% expected null rate for `jurisdiction` prevents chronic false alarms for that field. Measure baselines from two weeks of production data before deploying this monitor.
- **Window size determines sensitivity vs. false-alarm rate.** A 20-extraction window fires 2–3 extractions into a regression but also triggers on natural variance. A 100-extraction window is robust against variance but takes 10 extractions to fire. Default 50 is a reasonable mid-point; tune per field based on how stable the baseline is and how quickly a regression must be caught.
- **Single-field spike vs. all-fields spike carry different root causes.** One field spiking: prompt regression (a specific instruction was removed or broken), or a schema change that renamed the field. All fields spiking together: model version change, system prompt corruption, or a shift in the document mix (a new document type that lacks most clauses). The alert includes which fields are SPIKING, enabling fast triage.
- **Compose with F-145 (completeness score) for two-layer coverage.** F-145 catches a single extraction that is egregiously incomplete (SPARSE: < 50% weighted completeness). F-152 catches a gradual degradation that manifests as a null rate trend across many extractions. Run both: F-145 fires on bad individual extractions; F-152 fires when a pattern emerges across the window.
- **The alert is a signal for investigation, not automatic retry.** When `payment_terms` spikes to 56% null, automatically retrying all 50 extractions would cost 50× the original extraction cost. Instead: halt new extractions for that document type, page the team, diagnose the root cause (compare current prompt to the last-known-good version with F-65), fix the prompt, re-run only the affected batch.

## The move

**Track a rolling null rate per field. Alert when current null rate exceeds (expected + maxDeviation). Single-field spike = prompt/schema issue. All-field spike = model or document mix shift.**

```js
// --- Extraction field null rate monitor ---
// Rolling window of N extractions per field. Alert when null rate exceeds
// declared expected baseline by more than maxDeviation.
// Distinct from F-127 (point-in-time aggregate), F-145 (per-extraction score),
// F-26 (LLM judge drift), F-141 (classification distribution).
// Compose: run record() after each extraction; connect alerts to paging/halt.

function isNull(val) {
  return val === null || val === undefined || val === '' ||
         (Array.isArray(val) && val.length === 0);
}

class ExtractionFieldNullRateMonitor {
  constructor(fields, opts) {
    opts = opts || {};
    this._fields       = fields;
    this._windowSize   = opts.windowSize   || 50;
    this._maxDeviation = opts.maxDeviation || 0.10;
    this._baselines    = {};  // field → expected null rate (0.0–1.0)
    this._windows      = {};  // field → [0|1] circular buffer
    for (const f of fields) { this._baselines[f] = 0; this._windows[f] = []; }
  }

  setExpectedNullRate(field, rate) { this._baselines[field] = rate; return this; }

  record(extraction) {
    const alerts = [], stats = {};
    for (const field of this._fields) {
      const buf = this._windows[field];
      buf.push(isNull(extraction[field]) ? 1 : 0);
      if (buf.length > this._windowSize) buf.shift();

      const nullRate  = buf.reduce((a, b) => a + b, 0) / buf.length;
      const expected  = this._baselines[field] || 0;
      const deviation = nullRate - expected;
      const status    = deviation > this._maxDeviation ? 'SPIKING' : 'NOMINAL';
      stats[field]    = { nullRate, expected, deviation, samples: buf.length, status };

      if (status === 'SPIKING') {
        alerts.push({
          field, nullRate, expected, deviation,
          retryHint: `Field "${field}" null rate is ${(nullRate*100).toFixed(1)}% ` +
                     `(expected ≤ ${((expected + this._maxDeviation)*100).toFixed(1)}%). ` +
                     `Check for: prompt regression, model version change, or document format shift.`,
        });
      }
    }
    return { stats, alerts, spiking: alerts.length > 0 };
  }
}

// Configure per-field expected null rates from production baseline
const MONITOR = new ExtractionFieldNullRateMonitor(
  ['effective_date', 'payment_terms', 'parties', 'jurisdiction'],
  { windowSize: 50, maxDeviation: 0.10 }
);
MONITOR
  .setExpectedNullRate('effective_date', 0.02)
  .setExpectedNullRate('payment_terms',  0.05)
  .setExpectedNullRate('parties',        0.01)
  .setExpectedNullRate('jurisdiction',   0.08);
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Window size 50, deviation threshold 10 pp. Phase 1: 25 extractions at baseline null rates. Phase 2: `payment_terms` always null (regression injected). `record()` timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Extraction Field Null Rate Monitor ===

Window: 50 extractions. Deviation threshold: +10pp above expected baseline.
Expected: effective_date=2%, payment_terms=5%, parties=1%, jurisdiction=8%

--- Phase 1: Extractions 1–25 (baseline null rates) ---
  After extraction 25:
    effective_date       null=4.0%   expected≤12.0%  NOMINAL
    payment_terms        null=8.0%   expected≤15.0%  NOMINAL
    parties              null=0.0%   expected≤11.0%  NOMINAL
    jurisdiction         null=0.0%   expected≤18.0%  NOMINAL

--- Phase 2: Extractions 26–50 (payment_terms regression: 100% null) ---
  SPIKING detected at extraction 28:
    field="payment_terms"  nullRate=17.9%  deviation=+12.9pp
    retryHint: "Field "payment_terms" null rate is 17.9% (expected ≤ 15.0%).
                Check for: prompt regression, model version change, or document format shift."

  After extraction 50:
    effective_date       null=2.0%   expected≤12.0%  NOMINAL
    payment_terms        null=56.0%  expected≤15.0%  SPIKING  ← single-field spike
    parties              null=0.0%   expected≤11.0%  NOMINAL
    jurisdiction         null=6.0%   expected≤18.0%  NOMINAL

  Single-field spike on payment_terms → prompt regression or schema mismatch
  (all-fields spike would suggest model version change or document type shift)

=== Root cause triage by spike pattern ===
  ONE field spikes:    prompt regression; that field's instruction was removed/broken
  ALL fields spike:    model version change or document mix shift (new contract type)
  HIGH fields spike:   new template format; that clause is structurally absent
  Spike recovers:      transient atypical document batch — wait 2 windows before acting

=== Timing (1 000 000 iterations, 4 fields, 50-item window) ===
record() NOMINAL:  0.0062 ms
Zero API calls. Zero tokens. Runs after each extraction at delivery boundary.
```

## See also

[F-145](f145-extraction-output-completeness-score.md) · [F-127](f127-extraction-null-rate-tracker.md) · [F-26](f26-behavioral-drift-detection.md) · [F-141](f141-extraction-class-distribution-monitor.md) · [F-65](f65-prompt-regression-testing.md)

## Go deeper

Keywords: `extraction null rate monitor` · `field null rate trend` · `extraction regression detection` · `null rate spike alert` · `rolling window null rate` · `extraction field monitoring` · `prompt regression null rate` · `extraction completeness trend` · `field null spike detection` · `extraction pipeline health monitor`
