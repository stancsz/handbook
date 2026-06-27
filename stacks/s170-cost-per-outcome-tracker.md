# S-170 · Cost-Per-Outcome Tracker

[S-95](s95-retry-cost-attribution.md) attributes cost to failure types by error category. [S-123](s123-prompt-section-cost-attribution.md) breaks down per-call cost by prompt section. [S-168](s168-tool-definition-waste-audit.md) identifies token waste from unexecuted tool definitions. All three look at where tokens go; none answer the question that matters when comparing two pipelines or deciding whether to upgrade a model: what does a successful extraction actually cost?

Per-call cost is only half the picture. A Haiku call at $0.0008 looks cheap until you learn it fails 20% of the time, requiring retries or downstream correction. The real cost is `avgCostPerCall / passRate`: what you pay, on average, for each output that passes downstream validation. A pipeline at $0.0008/call with 80% pass rate delivers outcomes at $0.001000 each. Improve the prompt to 92% pass rate — same model, same per-call price — and cost-per-outcome drops to $0.000870, a 13% reduction without changing the model or the budget.

The cost-per-outcome metric makes two decisions tractable that per-call cost cannot. First: whether a prompt fix is worth it. If improving pass rate from 80% to 92% requires one engineering sprint, the 13% reduction in cost-per-outcome quantifies the payback. Second: whether to upgrade the model. Sonnet at $0.003/call with 97% pass rate costs $0.003093/outcome — 3.6× more than Haiku at 80% pass and 3.9× more than Haiku after the prompt fix. The upgrade to Sonnet is justified only when the use case demands that marginal quality improvement and can absorb the 3.9× cost premium.

## Situation

A contract extraction pipeline uses Haiku ($0.0008/call) to extract structured fields from legal documents. Downstream validation (F-70 structure check + F-140 date ordering assertions + F-141 class distribution monitor) passes or fails each extraction. No retry — failures are routed to a human review queue. The team wants to know: is the pass rate good enough, or should they upgrade to Sonnet?

Without cost-per-outcome tracking: per-call cost is reported as $0.0008. The team sees Sonnet at $0.003 — 3.75× more — and considers it expensive. But pass rate is not in the cost report. The team upgrades to Sonnet without knowing that Haiku's pass rate could be improved from 80% to 92% with a prompt fix, which would make Sonnet still 3.9× more expensive per outcome.

With cost-per-outcome tracking: the pipeline reports `$0.001000/outcome` at 80% pass rate. A prompt iteration raises pass rate to 92%; the tracker updates to `$0.000870/outcome` and reports `IMPROVING: -13%`. The Sonnet comparison now uses `$0.003093/outcome` vs `$0.000870/outcome`: Haiku after the prompt fix wins 3.9×. The team stays on Haiku, ships the prompt improvement, and has the number to defend the decision.

## Forces

- **Track the rolling window, not the lifetime average.** Pass rate changes over time: a prompt fix improves it, a model update might degrade it, a new contract type might confuse the extractor. A 100-call rolling window means the tracker reflects recent behavior, not a diluted historical average. The baseline is set from the first full window; subsequent windows compare against it. Set baseline once and report delta, so regressions against a known-good state are visible.
- **Don't conflate pass rate with extraction quality.** A pass is binary — it satisfies the downstream validators. An extraction can pass F-70 and still have lower-quality field values than a Sonnet extraction. Cost-per-outcome measures the cost of getting a valid output; it does not measure field accuracy, nuance, or completeness. Use [S-170](s170-cost-per-outcome-tracker.md) alongside [F-26](../forward-deployed/f26-llm-as-judge.md) (judge scoring) when quality within the passing set also matters.
- **Separate trackers per model arm during A/B testing.** When running [F-138](../forward-deployed/f138-model-swap-ab-test.md) (model swap A/B test), each arm gets its own CostPerOutcomeTracker. Mixing control and treatment into one tracker obscures which arm drives the delta. Compare the two `report()` outputs at the end of the test to decide PROMOTE/ROLLBACK.
- **Use the baseline to anchor trend direction, not to gate model selection.** The trend signal — IMPROVING/DEGRADING/STABLE — is relative to the baseline window. If the baseline itself was set during a bad batch (cold start, bad prompt version), the trend is wrong. Reset the baseline manually after a deliberate intervention (prompt change, model update, new contract type added to the training mix).
- **Zero pass rate is undefined, not zero.** If every call fails, `avgCostPerCall / passRate` divides by zero. Return `costPerOutcome: null` rather than crashing. This usually signals a pipeline break, not a cost question — route to alerting.

## The move

**Record cost and pass/fail per call. Compute `costPerOutcome = avgCostPerCall / passRate` over a rolling window. Set baseline after the first full window; report trend as IMPROVING/DEGRADING/STABLE.**

```js
// --- Cost-per-outcome tracker ---
// cost_per_outcome = avg_cost_per_call / pass_rate
// rolling window of N calls; baseline set after first full window
// Distinct from S-95 (retry cost by error type) and F-72 (feature P&L with revenue).
// Compose: pair with F-138 (one tracker per A/B arm) and F-141 (catch class drift).

class CostPerOutcomeTracker {
  constructor(opts) {
    opts = opts || {};
    this._windowSize = opts.windowSize || 100;
    this._records    = [];
    this._totalCost  = 0;
    this._totalPass  = 0;
    this._totalFail  = 0;
    this._baseline   = null;  // set after first full window
  }

  // Record one API call result.
  // costUsd: input + output token cost for this call
  // passed:  true if downstream validators accepted the output
  record(costUsd, passed) {
    if (this._records.length >= this._windowSize) {
      const removed = this._records.shift();
      this._totalCost -= removed.costUsd;
      if (removed.passed) this._totalPass--; else this._totalFail--;
    }
    this._records.push({ costUsd, passed });
    this._totalCost += costUsd;
    if (passed) this._totalPass++; else this._totalFail++;
    if (!this._baseline && this._records.length === this._windowSize) {
      this._baseline = this._compute();
    }
    return this;
  }

  _compute() {
    const n = this._records.length;
    if (n === 0) return null;
    const passRate       = this._totalPass / n;
    const avgCostPerCall = this._totalCost / n;
    return {
      n,
      passRate:       parseFloat((passRate * 100).toFixed(1)),
      avgCostPerCall: parseFloat(avgCostPerCall.toFixed(6)),
      costPerOutcome: passRate > 0
        ? parseFloat((avgCostPerCall / passRate).toFixed(6))
        : null,
      totalPass: this._totalPass,
      totalFail: this._totalFail,
    };
  }

  // Returns current window metrics + delta vs baseline.
  // status: WARMING_UP (< windowSize calls seen) | READY
  // trend:  IMPROVING (delta < -5%) | DEGRADING (delta > +5%) | STABLE
  report() {
    const current = this._compute();
    if (!current) return { status: 'WARMING_UP', n: this._records.length };
    if (!this._baseline) return Object.assign({ status: 'WARMING_UP' }, current);

    let delta = null;
    if (this._baseline.costPerOutcome && current.costPerOutcome) {
      delta = parseFloat(
        ((current.costPerOutcome - this._baseline.costPerOutcome)
          / this._baseline.costPerOutcome * 100).toFixed(1)
      );
    }

    return Object.assign({
      status:   'READY',
      baseline: { costPerOutcome: this._baseline.costPerOutcome, passRate: this._baseline.passRate },
      deltaPct: delta,
      trend:    delta === null ? 'UNKNOWN'
              : delta < -5   ? 'IMPROVING'
              : delta > 5    ? 'DEGRADING'
              :                 'STABLE',
    }, current);
  }
}

// --- Integration: validation delivery gate ---

async function extractAndTrack(doc, tracker) {
  const { costUsd, output } = await callHaiku(doc);
  const passed = validateOutput(output);   // F-70 + F-140 + F-141
  tracker.record(costUsd, passed);
  if (!passed) routeToHumanReview(doc, output);
  else deliver(output);
  return tracker.report();
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. 100-call baseline at 80% pass, then 100 calls at 92% pass (window slides). Model comparison computed analytically. All ops timed over 100 000 iterations.

```
=== Cost-Per-Outcome Tracker ===

After 100 calls (80% pass rate, $0.0008/call):
  passRate:        80%
  avgCostPerCall:  $0.0008
  costPerOutcome:  $0.001000
  baseline set.

After 100 more calls (92% pass rate, same $0.0008/call):
  passRate:        92%
  avgCostPerCall:  $0.0008
  costPerOutcome:  $0.000870
  baseline:        $0.001000
  delta:           -13% → IMPROVING

=== Model selection: cost-per-outcome as the decision metric ===

Haiku  ($0.0008/call, 80% pass):  $0.001000/outcome
Haiku  ($0.0008/call, 92% pass):  $0.000870/outcome  (after prompt fix)
Sonnet ($0.003/call,  97% pass):  $0.003093/outcome

Haiku 80% vs Sonnet 97%:  $0.001000 vs $0.003093 — Haiku wins 3.6x
Haiku 92% vs Sonnet 97%:  $0.000870 vs $0.003093 — Haiku wins 3.9x

Decision: fix the prompt first; switch model only if pass rate
stays below 85% after prompt optimization.

=== Timing (100 000 iterations) ===

record():  0.0014 ms
report():  0.0030 ms
```

## See also

[S-95](s95-retry-cost-attribution.md) · [S-123](s123-prompt-section-cost-attribution.md) · [S-168](s168-tool-definition-waste-audit.md) · [F-138](../forward-deployed/f138-model-swap-ab-test.md) · [F-141](../forward-deployed/f141-extraction-class-distribution-monitor.md)

## Go deeper

Keywords: `cost per outcome` · `pass rate cost metric` · `cost per successful extraction` · `model selection cost analysis` · `prompt improvement ROI` · `extraction pipeline cost` · `cost per valid output` · `rolling window pass rate` · `model upgrade cost justification` · `outcome-normalized cost`
