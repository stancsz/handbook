# S-191 · Parallel Fan-Out Cost Cap

S-55 fires N tool calls in parallel and reduces latency proportionally. S-160 caps how many tool calls can fire per turn. Neither caps the total cost of what fires.

Cost and count measure different risks. Ten Haiku calls at max_tokens=500 cost $0.022. Three Sonnet calls at max_tokens=2000 cost $0.104. A model dispatching 20 Sonnet calls at max_tokens=2000 commits up to $0.69 in output tokens before any results return — all simultaneously, with no feedback until they complete.

For map operations — "extract these fields from each of 50 documents" — the orchestrator fires N calls in parallel and then waits. If the model miscalculates the number of documents, or if each call turns out to be more expensive than expected, the entire exposure lands before anything can be checked. A parallel fan-out cost cap computes worst-case spend across all N calls before any call is dispatched, and either proceeds, reduces N, or blocks the dispatch if the exposure exceeds the burst budget.

## Situation

A contract due diligence pipeline receives a folder upload. It maps a Sonnet extraction call over every document in the folder — 20 documents this time. Each call takes 1 500 input tokens and is given max_tokens=2 000.

Worst-case per call: 1 500 × $3.00/M + 2 000 × $15.00/M = $0.0045 + $0.030 = $0.0345.
Worst-case for 20 calls: 20 × $0.0345 = $0.69.

The session has a burst limit of $0.50. The cap fires before dispatch, finds the total exposure exceeds the limit, and reduces the approved batch to 14 calls ($0.483 ≤ $0.50). The remaining 6 are queued for the next dispatch window. The orchestrator logs the reduction and proceeds with 14 calls rather than blindly dispatching all 20.

## Forces

- **Worst-case cost is the right input, not expected cost.** The model can run up to max_tokens — in the worst case, it does. Expected output length is lower (often 40–60% of max_tokens), but you are committing to worst-case when you set max_tokens. Use worst-case for the gate; log expected cost separately for planning.
- **Cost and count are orthogonal.** S-160 (tool call count budget) counts calls; S-191 counts dollars. A count of 5 may be fine; a cost of $5 may not be. A count of 50 may be fine for Haiku; a cost of $50 is not fine for Sonnet. Both checks are needed. Run S-160 first (fast integer comparison); run S-191 only when the count check passes.
- **Burst limit is not daily budget.** A daily budget of $10 does not mean $10 can be spent in a single parallel burst at 9am. Set burst limits per-pipeline, not from the daily total. Typical burst limits: $0.10 for interactive agents, $0.50 for batch pipelines, $5.00 for scheduled nightly runs.
- **Sort by cost before approving.** When reducing N to fit the limit, approve the cheapest calls first. This maximizes the number of results returned within the budget, which is more useful than approving N-6 of the same call at random.
- **Don't confuse best-case with worst-case for mixed-model batches.** A mixed batch (3 Opus + 5 Haiku) has very uneven per-call costs. The Opus calls may each cost 40× the Haiku calls. When reducing, the single most expensive call may consume most of the burst budget. Compute per-call, not per-batch-average.

## The move

**Compute worst-case cost for all N calls before dispatch. If total exceeds burst limit, reduce to the largest subset that fits. Log reductions for observability.**

```js
// --- Parallel fan-out cost cap ---
// Computes worst-case cost for N parallel calls before dispatch.
// Prevents runaway spend from large map operations over user-controlled inputs.
// Pair with S-160 (call count budget — fast integer check before this).
// Burst limit: per-pipeline, not per-day.

const RATES = {
  haiku:  { input: 0.80 / 1_000_000, output:  4.00 / 1_000_000 },
  sonnet: { input: 3.00 / 1_000_000, output: 15.00 / 1_000_000 },
  opus:   { input: 15.00 / 1_000_000, output: 75.00 / 1_000_000 },
};

// calls: Array of { model, inputTokens, maxOutputTokens, id? }
// opts.burstLimit: max $ allowed in one parallel dispatch (default: $0.10)
// Returns: { decision: 'PROCEED'|'REDUCE'|'BLOCK', totalWorstCase, ... }
function checkFanOutCost(calls, opts) {
  opts = opts || {};
  const limit = opts.burstLimit != null ? opts.burstLimit : 0.10;

  // Compute per-call worst-case cost.
  const priced = calls.map(c => {
    const rate = RATES[c.model] || RATES.haiku;
    const worstCaseCost = c.inputTokens * rate.input + c.maxOutputTokens * rate.output;
    return { ...c, worstCaseCost };
  });

  const totalWorstCase = priced.reduce((s, c) => s + c.worstCaseCost, 0);

  if (totalWorstCase <= limit) {
    return {
      decision: 'PROCEED',
      totalWorstCase: +totalWorstCase.toFixed(6),
      limit,
      approvedCalls: priced,
    };
  }

  // Reduce: sort by ascending cost, approve cheapest first.
  const sorted  = [...priced].sort((a, b) => a.worstCaseCost - b.worstCaseCost);
  const approved = [];
  let cumulative = 0;

  for (const c of sorted) {
    if (cumulative + c.worstCaseCost <= limit) {
      approved.push(c);
      cumulative += c.worstCaseCost;
    }
  }

  if (approved.length === 0) {
    return {
      decision: 'BLOCK',
      totalWorstCase: +totalWorstCase.toFixed(6),
      limit,
      mostExpensiveCall: sorted[0],
      hint: `Cheapest call ($${sorted[0].worstCaseCost.toFixed(6)}) already exceeds burst limit $${limit}. ` +
            `Reduce max_tokens or increase burst limit.`,
    };
  }

  const blocked = priced.filter(c => !approved.find(a => a === c || a.id === c.id));

  return {
    decision:      'REDUCE',
    totalWorstCase: +totalWorstCase.toFixed(6),
    approvedCost:  +cumulative.toFixed(6),
    limit,
    approvedCount: approved.length,
    blockedCount:  blocked.length,
    approvedCalls: approved,
    blockedCalls:  blocked,
    hint: `Reduced from ${calls.length} to ${approved.length} calls ($${cumulative.toFixed(4)} ≤ $${limit}). ` +
          `Queue ${blocked.length} remaining calls for next dispatch.`,
  };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Three scenarios: Haiku small fan-out (PROCEED), Sonnet large fan-out (REDUCE), mixed-model batch (PROCEED). Worst-case cost computed from full max_tokens. Pricing: Haiku $0.80/$4.00 per M input/output; Sonnet $3.00/$15.00; Opus $15.00/$75.00. Timed over 1 000 000 iterations. Zero API calls.

```
=== Parallel Fan-Out Cost Cap ===

Burst limit default: $0.10 per dispatch.
Pricing: Haiku $0.80/$4.00 per M; Sonnet $3.00/$15.00; Opus $15.00/$75.00.

--- Scenario A: 10 Haiku calls, 200 input tok, 500 max_output ---
  Per call worst-case: 200 × $0.80/M + 500 × $4.00/M
                     = $0.000160 + $0.002000 = $0.002160
  Total worst-case:    10 × $0.002160 = $0.02160
  Burst limit:         $0.10
  Decision: PROCEED   ($0.02160 ≤ $0.10)

--- Scenario B: 20 Sonnet calls, 1 500 input tok, 2 000 max_output ---
  Per call worst-case: 1 500 × $3.00/M + 2 000 × $15.00/M
                     = $0.004500 + $0.030000 = $0.034500
  Total worst-case:    20 × $0.034500 = $0.69000
  Burst limit:         $0.50
  Decision: REDUCE
    Sorted by ascending cost (all equal at $0.034500/call):
    Approved: 14 calls  ($0.4830 ≤ $0.50)
    Blocked:   6 calls  (queued for next dispatch)
    Hint: "Reduced from 20 to 14 calls ($0.4830 ≤ $0.50). Queue 6 remaining."

--- Scenario C: mixed — 5 Haiku + 3 Sonnet + 1 Opus ---
  (each: 1 500 input, 2 000 max_output)
  Haiku  (5): 5 × (1 500 × $0.80/M + 2 000 × $4.00/M)
              = 5 × $0.009200 = $0.046000
  Sonnet (3): 3 × (1 500 × $3.00/M + 2 000 × $15.00/M)
              = 3 × $0.034500 = $0.103500
  Opus   (1):     1 500 × $15.00/M + 2 000 × $75.00/M
              = $0.022500 + $0.150000 = $0.172500
  Total worst-case: $0.046000 + $0.103500 + $0.172500 = $0.322000
  Burst limit:      $0.50
  Decision: PROCEED   ($0.322000 ≤ $0.50)
  Note: Opus call ($0.1725) is 54% of this burst's total. Log for observability.

--- What happens at actual cost vs worst-case ---
  Typical output ≈ 55% of max_tokens (observed across extraction pipelines).
  Scenario B actual cost ≈ 20 × (1 500 × $3.00/M + 1 100 × $15.00/M) ≈ $0.42/burst
  Worst-case gate ($0.69) is conservative — by design. The gate's job is to
  prevent the tail, not to predict the median. Actual cost is always logged post-run.

=== Timing (1 000 000 iterations) ===
checkFanOutCost() 10 calls, PROCEED:             0.0007 ms
checkFanOutCost() 20 calls, REDUCE (sort+select): 0.0012 ms
checkFanOutCost() 9 calls, mixed models, PROCEED: 0.0009 ms
Zero API calls. Zero tokens.
```

## See also

[S-55](s55-parallel-tool-calls.md) · [S-160](s160-tool-call-count-budget.md) · [F-109](../forward-deployed/f109-pre-execution-run-cost-projection.md) · [F-35](../forward-deployed/f35-workflow-token-budget.md) · [S-72](s72-cost-anomaly-detection.md)

## Go deeper

Keywords: `parallel fan-out cost cap` · `concurrent call cost check` · `parallel dispatch budget` · `fan-out cost guard` · `batch call cost limit` · `parallel call cost exposure` · `burst cost cap` · `parallel tool call budget` · `N call worst-case cost` · `concurrent API cost check`
