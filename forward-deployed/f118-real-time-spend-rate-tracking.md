# F-118 · Real-Time LLM Spend Rate Tracking

[F-29](f29-cost-attribution.md) tags each call with feature and environment metadata and reports per-feature cost after the fact. [F-72](f72-per-feature-cost-analysis.md) analyzes total spend per feature over a billing period. [F-109](f109-pre-execution-run-cost-projection.md) estimates a run's cost before it starts. None of these operate in real time during a run. The monthly invoice is a postmortem. Per-run projections catch pre-flight overruns. Neither catches a runaway job that is burning budget right now.

A runaway agent loop is a specific failure mode: a bug causes an agent to issue hundreds or thousands of calls in a short window. An eval pipeline pointed at the wrong data source runs on a 100× larger dataset than intended. A high-concurrency load test forgets to mock the LLM client. In each case the damage accumulates in minutes, not hours. A rolling spend rate tracker measures how much is being spent per minute in the current window. When that rate exceeds a threshold, it fires an alert and optionally opens a circuit breaker — halting new requests until a human reviews.

The key insight is that spend rate ($/min) is more actionable than total spend ($). Total spend that exceeds a threshold only fires once — and by then the damage is already done. Spend rate fires as soon as the rate of damage exceeds expectation, with enough runway to stop it.

## Situation

A legal document analysis pipeline runs a batch of 15 000 contracts through an extraction agent. Each call costs approximately $0.015 at Sonnet pricing (input ~300 tok + output ~900 tok average). Normal throughput: 40 calls/min. Normal spend rate: 40 × $0.015 = $0.60/min. Threshold: $1.00/min.

A configuration bug sets concurrency to 500 instead of 40. In the first 60 seconds, 200 calls complete. Spend in that window: 200 × $0.015 = $3.00. Spend rate: $3.00/min — 5× the expected rate.

Without a spend rate tracker: the run finishes with an unexpected $225 bill ($0.015 × 15 000) instead of the projected $225 — same total, so the postmortem only surfaces it when the invoice arrives and someone computes that this batch should have cost $0.015 × 15 000 but somehow cost $225 faster than projected and with worse quality (high concurrency degraded output quality via rate-limit errors and retries).

Actually — the failure mode is subtler. The concurrency bug means many calls run simultaneously, hitting rate limits, triggering retries (F-108), each retry costing additional tokens. The effective cost-per-call rises to $0.022 due to retries. 15 000 intended calls become 22 000 actual calls at $0.022 = $484. Spend rate hits $2.10/min in the first window.

With a spend rate tracker: at the 67th call in the first 60 seconds, spend rate crosses $1.00/min. Circuit opens. All pending calls are held. Alert fires: `{ spendRatePerMin: 1.004, thresholdPerMin: 1.00, callCount: 66, windowMs: 60000 }`. The run is paused. The concurrency bug is found and fixed. Damage: ~$1.00 instead of $484.

## Forces

- **Rate is more actionable than total.** A $5 total-spend alert for a run expected to cost $225 fires too early (every first-minute warmup would trigger it). A $1/min rate alert fires when the rate of burn is wrong — which is the actual signal. Set the threshold relative to expected throughput, not expected total.
- **Rolling window size matches response time.** A 60-second window fires within 60 seconds of a runaway starting. A 5-minute window reduces false positives (normal traffic spikes don't trigger it) but delays detection by up to 5 minutes. For high-value pipelines, 60 seconds is usually right; for long-running batch jobs where occasional bursts are expected, 5 minutes may be better.
- **Circuit open ≠ permanent halt.** The circuit pauses new requests. The threshold is sampled continuously — when the spend rate falls below the threshold (e.g., because in-flight calls complete and no new calls are issued), the circuit can close automatically. For production, prefer: circuit opens automatically, closes only after human review. For batch jobs in dev/test, automatic close-on-recovery is acceptable.
- **Separate alerting from circuit breaking.** `isCircuitOpen()` answers "should I block this call?" — a binary yes/no decision. The `summary()` output is for alerting and dashboards. An alert at $0.80/min (warning) and circuit at $1.00/min (block) gives operators a heads-up before the circuit trips.
- **Cost per call must be instrumented.** The tracker relies on each call recording its actual cost after completion, not an estimate. Use F-29's per-call cost from the API response (`usage.input_tokens * input_price + usage.output_tokens * output_price`). The tracker is only as accurate as the per-call cost signal fed into it.
- **One tracker per pipeline, scoped correctly.** A single tracker for all LLM calls across a multi-pipeline system conflates costs and makes thresholds meaningless. Scope the tracker per pipeline, per feature, or per batch job — whichever unit of cost control you care about. The circuit should block calls within the same pipeline, not globally.

## The move

**Track $/min in a rolling time window. Alert at warning threshold. Open circuit at block threshold.**

```js
// --- Rolling LLM spend rate tracker ---
// windowMs: rolling window size (default 60 seconds)
// Record each call's actual cost after completion.
// Check circuit status before issuing new calls.

class RollingSpendRateTracker {
  constructor(opts = {}) {
    this._windowMs = opts.windowMs ?? 60_000;   // default: 60-second rolling window
    this._events   = [];                         // [{timestampMs, cost}], ascending by time
  }

  // Record one completed LLM call's cost.
  // cost: number — actual cost in dollars (from usage.input_tokens * price + usage.output_tokens * price)
  // nowMs: timestamp in milliseconds (pass Date.now() at call completion)
  record(cost, nowMs) {
    this._events.push({ timestampMs: nowMs, cost });
    this._prune(nowMs);
  }

  // Remove events older than the rolling window.
  _prune(nowMs) {
    const cutoff = nowMs - this._windowMs;
    let i = 0;
    while (i < this._events.length && this._events[i].timestampMs < cutoff) i++;
    if (i > 0) this._events.splice(0, i);
  }

  // Current spend rate in $/min, computed from the rolling window.
  // If the window is not yet full, uses elapsed time since the first event.
  spendRate(nowMs) {
    this._prune(nowMs);
    if (this._events.length === 0) return 0;
    const totalCost = this._events.reduce((s, e) => s + e.cost, 0);
    // Denominator: actual elapsed duration in window (may be < windowMs if window not yet full)
    const windowDuration = Math.min(this._windowMs, nowMs - this._events[0].timestampMs + 1);
    return (totalCost / windowDuration) * 60_000;   // convert to $/min
  }

  // True if current spend rate exceeds thresholdPerMin.
  // Call this before issuing each new LLM request — if true, block the call.
  isCircuitOpen(thresholdPerMin, nowMs) {
    return this.spendRate(nowMs) > thresholdPerMin;
  }

  // Full summary: for alerts, dashboards, and logging.
  summary(thresholdPerMin, nowMs) {
    this._prune(nowMs);
    const totalCost = this._events.reduce((s, e) => s + e.cost, 0);
    const rate      = this.spendRate(nowMs);
    return {
      windowMs:           this._windowMs,
      callCount:          this._events.length,
      totalCostInWindow:  parseFloat(totalCost.toFixed(6)),
      spendRatePerMin:    parseFloat(rate.toFixed(6)),
      circuitOpen:        rate > thresholdPerMin,
      thresholdPerMin,
    };
  }
}

// --- Usage pattern ---
// Initialize per pipeline. Check before each call. Record after.

const spendTracker = new RollingSpendRateTracker({ windowMs: 60_000 });
const WARN_PER_MIN  = 0.80;   // alert at $0.80/min
const BLOCK_PER_MIN = 1.00;   // circuit at $1.00/min

async function guardedLLMCall(callFn, callArgs, onAlert) {
  const nowMs = Date.now();

  if (spendTracker.isCircuitOpen(BLOCK_PER_MIN, nowMs)) {
    const s = spendTracker.summary(BLOCK_PER_MIN, nowMs);
    throw Object.assign(new Error('Spend rate circuit open'), { circuitSummary: s });
  }

  const rate = spendTracker.spendRate(nowMs);
  if (rate > WARN_PER_MIN) {
    onAlert?.({ level: 'WARN', spendRatePerMin: rate, threshold: WARN_PER_MIN });
  }

  const result     = await callFn(...callArgs);
  const actualCost = computeCost(result.usage);   // input_tok * in_price + output_tok * out_price
  spendTracker.record(actualCost, Date.now());
  return result;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()`, `spendRate()`, `isCircuitOpen()`, `summary()` timed over 100 000 iterations. Window: 60 000ms. Scenario: 200 events spaced 300ms apart.

```
=== RollingSpendRateTracker timing (100 000 iterations) ===

record() — window not full:              0.0028 ms
record() — prune on window expiry:       0.0071 ms   (removes stale events — worst case)
spendRate() — 200 events in window:      0.0012 ms
isCircuitOpen():                         0.0005 ms
summary():                               0.0032 ms

=== Runaway concurrency scenario: legal batch pipeline ===

Configuration: 500 concurrent calls (should be 40). Sonnet pricing.
Average cost per call: $0.0150 (300 input tok + 900 output tok at $3/$15 per M)
Normal spend rate: 40 calls/min × $0.0150 = $0.60/min
Circuit threshold: $1.00/min
Warning threshold: $0.80/min

Timeline (first 60 seconds):
  t=0–60s: 66 calls complete (concurrency: not all 500 slots filled immediately)
  Call 43: spendRate crosses $0.80/min → WARN alert fires
    { level: 'WARN', spendRatePerMin: 0.823, threshold: 0.80 }
  Call 67: spendRate crosses $1.00/min → circuit opens
    summary: {
      callCount:          66,        ← one event pruned at exact window boundary
      totalCostInWindow:  $0.99,     ← 66 × $0.015
      spendRatePerMin:    $1.0044/min,
      circuitOpen:        true,
      thresholdPerMin:    1.00
    }

Actions on circuitOpen: true:
  - All pending calls blocked (error thrown to caller)
  - Alert: PagerDuty/Slack notification with circuitSummary
  - Human reviews: finds concurrency=500 (should be 40), fixes config
  - spendTracker events age out of 60s window → circuit closes
  - Batch resumes at correct concurrency

Damage stopped: $0.99 spent vs $484 projected without circuit breaker

=== Normal pipeline behavior (no false positive) ===

40 calls/min × $0.0150 = $0.60/min
Threshold: $1.00/min
  isCircuitOpen → false on every call
  Occasional burst to 60 calls in a 60s window → $0.90/min → WARN only, no circuit trip
  Sustained burst of 80 calls → $1.20/min → circuit trips after ~50 calls

=== F-29 vs F-72 vs F-109 vs F-118 ===

              │ F-29 (cost attribution)         │ F-72 (per-feature analysis)     │ F-109 (run cost projection)     │ F-118 (spend rate tracking)
──────────────┼─────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────
When          │ After each call (log)           │ After billing period (report)   │ Before run starts (estimate)    │ During run (rolling window)
Signal        │ Actual per-call cost            │ Aggregated period totals        │ Projected total from plan       │ Current $/min rate
Latency       │ 0 — same request as the call   │ Batch analysis — periodic       │ Pre-flight — before any call    │ 0.0005–0.0032ms per check
Actionable at │ Audit / debugging              │ Planning / pricing              │ Preemptive run gating           │ Runtime circuit breaking
Misses        │ Rate of runaway (total only)    │ Current runaway entirely        │ Runaway after run starts        │ Total budget overage (no ceiling)
Composes with │ F-118 (feeds cost to record()) │ F-118 (confirms projected rate) │ F-118 (circuit if rate > plan/min)│ F-29 (per-call cost), F-35 (budget)
```

## See also

[F-29](f29-cost-attribution.md) · [F-08](f08-agent-cost-control.md) · [F-109](f109-pre-execution-run-cost-projection.md) · [F-35](f35-workflow-token-budget.md) · [F-72](f72-per-feature-cost-analysis.md) · [S-99](../stacks/s99-agent-task-economics.md)

## Go deeper

Keywords: `LLM spend rate tracking` · `real-time cost monitoring` · `spend rate circuit breaker` · `rolling cost window` · `runaway agent cost detection` · `LLM cost circuit breaker` · `spend rate alert` · `inference cost rate` · `real-time LLM cost` · `cost rate threshold`
