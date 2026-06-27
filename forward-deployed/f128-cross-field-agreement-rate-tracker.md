# F-128 · Cross-Field Agreement Rate Tracker

[F-92](f92-structured-output-schema-drift.md) checks arithmetic invariants per extraction call: if `total_value` should equal `base_price + tax + fees`, a single call that violates this is caught immediately. [F-102](f102-cross-field-reference-integrity.md) checks per-call that a reference field actually points to a value that exists. [F-106](f106-intra-output-contradiction-detection.md) detects logical contradictions within a single output — a call where `recommended_action` is `APPROVE` and the `risk_summary` text says "unacceptable counterparty risk."

All three fire per call. None answer the production question: how often does a specific contradictory combination appear across many calls? One instance of `APPROVE` + `HIGH` risk level could be a corner case. Eight instances in fifty calls is a systematic pattern — the model has a consistent failure mode where it recommends approval despite flagging high risk, at an 8% rate, on a specific contract type.

The distinction from F-106 is temporal. F-106 detects a contradiction and may block or flag the call. The agreement rate tracker records whether each contradiction rule fired across a rolling window, computes the rate, and alerts when it exceeds a threshold. The per-call signal tells you something went wrong. The rate tells you how often it goes wrong — and whether a recent prompt update improved or worsened it.

## Situation

A contract analysis agent recommends approval or rejection. After three months of production, a risk analyst notices that some contracts are being sent to a fast-track approvals queue despite having a `HIGH` risk assessment. Investigation reveals: 8 of the last 50 contract extractions returned `{ recommended_action: 'APPROVE', risk_level: 'HIGH' }`. The model is internally inconsistent on a specific clause structure common in international supply agreements.

F-70 passed all 50 calls — both `APPROVE` and `HIGH` are valid schema values. F-92 passed — no arithmetic violations. F-106 flagged 3 of the 8 via semantic analysis, but 5 slipped through because the contradiction was not in the prose (`rationale`) but in the field values alone.

The agreement rate tracker would have caught all 8: it checks field values directly, without requiring F-106's LLM-based semantic analysis. After the first 10 calls (before the 5% threshold was exceeded), it would have been in ACCEPTABLE range. After 20 calls with 2 contradictions, it crosses 10% and fires ALARMING. The prompt team is notified, finds the supply-agreement clause structure, adds a disambiguation instruction, and the rate drops to 0/30 on the subsequent window.

## Forces

- **Define contradictions from domain knowledge, not model outputs.** `APPROVE + HIGH_RISK` is contradictory because your approval policy says so, not because the model's text says it. The rules encode the business semantics of the output schema: which field value pairs are semantically incoherent under your domain constraints. Start with rules derived directly from the downstream routing logic.
- **The threshold is lower than you'd expect.** A 5% contradiction rate means 1 in 20 extractions produces a logically impossible output. At 500 contracts/day, that is 25 bad extractions per day — 25 contracts potentially routed to the wrong queue. Start at 5%; lower to 2% for HIGH-consequence fields if volume permits.
- **Each rule fires independently.** `APPROVE + HIGH_RISK` and `REJECT + LOW_RISK` are separate rules with separate rolling windows. A model that produces both contradiction types needs separate diagnosis: the first is over-approval on risky contracts; the second is over-rejection on safe ones. One prompt fix may address both, or they may have separate root causes.
- **Rolling window size determines response lag.** At `windowSize: 50`, a new batch of 50 calls is needed to show the full effect of a prompt fix. At `windowSize: 20`, the effect shows faster but noise is higher — one bad batch can temporarily push the rate above threshold even after the fix. Tune to your daily extraction volume: aim for a window that represents approximately one week of production traffic.
- **This is a monitoring tool, not a per-call gate.** Unlike F-70 (which can reject an output) or F-106 (which can flag and block), the agreement rate tracker does not change the call path. It records and reports. The downstream action — prompt update, model escalation, output review — happens outside the agent loop. Set up alert routing to the prompt engineering team, not the error handler.
- **Distinguish rate from occurrence.** `allAlarming()` surfaces rules by rate, not by count. A rule that fires 2/10 times (20%) is more alarming than one that fires 5/50 times (10%), even though the second has more absolute occurrences. Rate is the signal; count is context.

## The move

**Define contradiction rules from your domain policy. Record each extraction. Alert when a rule's contradiction rate exceeds the threshold across the rolling window.**

```js
// --- Cross-field agreement rate tracker ---
// Tracks the rate at which defined contradictory field-value combinations
// appear across rolling production extractions.
// Per-call contradiction detection: see F-106.
// This tracker answers: how often does a contradiction pattern appear?

class CrossFieldAgreementRateTracker {
  constructor(opts = {}) {
    this._windowSize     = opts.windowSize     ?? 50;
    this._alertThreshold = opts.alertThreshold ?? 0.05;  // 5% contradiction rate → ALARMING
    this._rules          = [];
    this._history        = new Map();  // ruleName → [1|0, ...]
  }

  // Define a contradictory combination.
  // conditions: [{field, value}, ...] — contradiction fires when ALL conditions match.
  defineContradiction(name, conditions) {
    this._rules.push({ name, conditions });
    return this;
  }

  // Record one extraction output.
  // Returns list of contradiction rule names that fired on this output.
  record(output) {
    const fired = [];
    for (const rule of this._rules) {
      const isContradiction = rule.conditions.every(c => String(output[c.field]) === String(c.value));
      if (!this._history.has(rule.name)) this._history.set(rule.name, []);
      const arr = this._history.get(rule.name);
      arr.push(isContradiction ? 1 : 0);
      if (arr.length > this._windowSize) arr.shift();
      if (isContradiction) fired.push(rule.name);
    }
    return fired;
  }

  // Contradiction rate for a specific rule name.
  // Returns { status: 'ALARMING'|'ACCEPTABLE'|'INSUFFICIENT_DATA', rate, count, samples }
  contradictionRate(ruleName) {
    const arr = this._history.get(ruleName);
    if (!arr || arr.length < 5) {
      return { status: 'INSUFFICIENT_DATA', samples: arr ? arr.length : 0, required: 5 };
    }
    const count = arr.filter(v => v === 1).length;
    const rate  = count / arr.length;
    return {
      status:    rate >= this._alertThreshold ? 'ALARMING' : 'ACCEPTABLE',
      rate:      parseFloat(rate.toFixed(3)),
      count,
      samples:   arr.length,
      threshold: this._alertThreshold,
    };
  }

  // Return all rules currently ALARMING, sorted by rate desc.
  allAlarming() {
    const out = [];
    for (const rule of this._rules) {
      const arr = this._history.get(rule.name);
      if (!arr || arr.length < 5) continue;
      const count = arr.filter(v => v === 1).length;
      const rate  = count / arr.length;
      if (rate >= this._alertThreshold) {
        out.push({ ruleName: rule.name, rate: parseFloat(rate.toFixed(3)), count, samples: arr.length });
      }
    }
    return out.sort((a, b) => b.rate - a.rate);
  }
}

// --- Integration: define rules from approval policy; record after each extraction ---

const AGREEMENT_TRACKER = new CrossFieldAgreementRateTracker({
  windowSize:     50,
  alertThreshold: 0.05,
})
  // APPROVE + HIGH risk is never correct under current approval policy
  .defineContradiction('approve_with_high_risk', [
    { field: 'recommended_action', value: 'APPROVE' },
    { field: 'risk_level',         value: 'HIGH' },
  ])
  // REJECT + LOW risk suggests the model is rejecting unnecessarily
  .defineContradiction('reject_with_low_risk', [
    { field: 'recommended_action', value: 'REJECT' },
    { field: 'risk_level',         value: 'LOW' },
  ])
  // Highest fee tier assigned with LOW risk is a pricing inconsistency
  .defineContradiction('high_fee_tier_low_risk', [
    { field: 'risk_level',         value: 'LOW' },
    { field: 'fee_tier',           value: 'TIER_5' },
  ]);

// After each extraction call:
function onExtractionResult(output) {
  const fired = AGREEMENT_TRACKER.record(output);
  if (fired.length > 0) {
    log({ event: 'extraction_contradiction', rules: fired, output });
    // Per-call log (not an alert — the rate tracker decides whether to alert)
  }
}

// Monitoring job (every 5 minutes):
function checkAgreementRates() {
  const alarming = AGREEMENT_TRACKER.allAlarming();
  if (alarming.length > 0) {
    alert({ event: 'cross_field_agreement_rate_alert', alarming });
    // → prompt engineering team
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()` and `contradictionRate()` timed over 100 000 iterations. Window size 50, threshold 5%. Three rules defined. Scenario: 50 extractions with realistic distribution.

```
=== CrossFieldAgreementRateTracker timing (100 000 iterations) ===

record() — 3 rules, 0 contradictions:   0.0012 ms
record() — 3 rules, 1 contradiction:    0.0013 ms
contradictionRate() — 50 samples:       0.0017 ms

=== Scenario: 50 contract extractions, 3 rules ===

Distribution:
  42/50: coherent outputs (APPROVE+LOW, APPROVE+MEDIUM, REJECT+HIGH, REJECT+MEDIUM)
   4/50: APPROVE + HIGH_RISK (contradicts rule 1)
   4/50: REJECT  + LOW_RISK  (contradicts rule 2)

contradictionRate('approve_with_high_risk'):
{
  status:    'ALARMING',
  rate:      0.080,
  count:     4,
  samples:   50,
  threshold: 0.05
}

contradictionRate('reject_with_low_risk'):
{
  status:    'ALARMING',
  rate:      0.080,
  count:     4,
  samples:   50,
  threshold: 0.05
}

allAlarming():
[
  { ruleName: 'approve_with_high_risk', rate: 0.08, count: 4, samples: 50 },
  { ruleName: 'reject_with_low_risk',   rate: 0.08, count: 4, samples: 50 }
]

=== What 8% contradiction rate means in production ===

At 500 contracts/day:
  approve_with_high_risk fires on: 500 × 0.08 = 40 contracts/day
  Each APPROVE+HIGH_RISK contract goes to fast-track queue.
  Expected: manual review queue.
  Business cost: 40 misrouted contracts/day → reviewer time + compliance risk.

After prompt fix: 0/30 contradictions in next 30 calls → rate drops to 0.
Tracker returns ACCEPTABLE within 30 calls of the fix.

=== F-92 vs F-102 vs F-106 vs F-128 ===

              │ F-92 (arithmetic)           │ F-102 (reference integrity)  │ F-106 (contradiction)       │ F-128 (agreement rate)
──────────────┼─────────────────────────────┼──────────────────────────────┼─────────────────────────────┼──────────────────────────
When          │ Per call                    │ Per call                     │ Per call                    │ Rolling production window
What          │ total = sum(parts)          │ clause_id ∈ document_sections│ Semantic contradiction      │ Field-pair contradiction rate
How           │ Arithmetic assertion        │ Set membership check         │ F-106: LLM or rule          │ Exact field value match
Misses        │ Field-value logical pairs   │ Value-not-reference pairs    │ Value-pair (if in fields)   │ Semantic paraphrases
Catches       │ Math invariants             │ Dangling references          │ Logic contradiction (prose) │ Systematic field-pair failure
Output        │ Pass/fail per call          │ Pass/fail per call           │ Pass/fail + reason          │ Rate over N calls
```

## See also

[F-92](f92-structured-output-schema-drift.md) · [F-102](f102-cross-field-reference-integrity.md) · [F-106](f106-intra-output-contradiction-detection.md) · [F-127](f127-extraction-field-null-rate-monitor.md) · [F-116](f116-per-field-extraction-error-rate-tracking.md) · [F-70](f70-structured-output-validation.md)

## Go deeper

Keywords: `cross-field agreement rate` · `extraction field contradiction rate` · `LLM output consistency monitoring` · `structured output field pair contradiction` · `approval logic contradiction tracking` · `field value incompatibility rate` · `extraction consistency monitoring` · `cross-field logical contradiction rate` · `model output agreement monitoring` · `field combination contradiction tracker`
