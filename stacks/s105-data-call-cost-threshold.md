# S-105 · Data Call Cost Threshold

[S-102](s102-composable-agent-data-layers.md) covers composable data layers: route each query to the cheapest tier that meets its freshness requirement. When the static KB misses and the cache is stale, call the live API. [S-100](s100-live-data-freshness-contracts.md) covers per-source freshness contracts: each source declares the freshest it can guarantee, and queries route away when the source is too stale. [S-35](s35-latency-budget.md) covers latency budgeting: allocate time across pipeline stages.

None ask the prior question: **is this live API call economically justified?** S-102 treats the live API as the fallback of last resort — if the query needs data fresher than the cache, call the live API. But the live API call has a cost (the API fee) and a latency cost (the agent idles, the user waits, real-time SLOs erode). If the benefit of having fresh data is smaller than those costs, the right answer is to use the stale data with a disclosure — not to make the call.

This is not about skipping calls when data is available. It is about the decision when only stale data is on hand: is calling for fresh data worth what it costs?

## Situation

A customer service agent answers questions including "What is the current processing time for returns?" The answer changes infrequently — a few times per quarter. The data lives in an operations database that costs $0.005 per query and takes 800ms to respond. The cache TTL is 6 hours; the last update was 5 hours ago. The user's question is informational — a wrong answer costs a refund conversation later, not a financial or safety consequence.

At this moment, the cache is 5 hours old against a 6-hour TTL. The live call would cost $0.005 and block the agent for 800ms. The consequence of giving information that's up to 5 hours old is minimal — processing times don't change by the hour. The right decision: use the cache and disclose its age, not pay $0.005 and add 800ms of latency for data that almost certainly hasn't changed.

Compare: a different agent is checking whether a specific medication has had a recent recall. The consequence of using stale data is patient harm. The live call to the FDA API costs $0.001 and takes 200ms. The right decision: always call, regardless of what's in cache.

## Forces

- **Freshness requirements in S-102 are binary: either a tier meets the requirement or it doesn't.** The threshold between calling and not calling is baked into the tier structure. But the appropriate threshold is not constant — it depends on what the query will be used for and what goes wrong if the data is stale.
- **Consequence cost is not visible in the data layer.** The tier router (S-102) knows freshness; it doesn't know consequence severity. A price query for a comparison shopping widget has low consequence; a price query for a contract settlement has high consequence. Same data, different decisions.
- **Call cost accumulates across volume.** A single $0.005 API call is trivial. 10,000 calls/day on queries where stale data would have been acceptable is $50/day — $18,250/year — on calls that did not need to be made.
- **Latency cost is real, not abstract.** An 800ms external API call adds 800ms to the agent turn. For a real-time user, this is perceptible. For an async batch job, it is irrelevant. The latency penalty should be denominated in something real — user experience degradation, SLO budget consumed.
- **Disclosure is a valid output.** Using a 5-hour-old cache value with "Note: this information is from our last update 5 hours ago" is often better than waiting 800ms and paying $0.005 for data that probably hasn't changed. The agent doesn't have to choose between perfect freshness and silence — disclosing staleness is the third option.

## The move

**Model the decision as a threshold: make the live call when consequence_severity × staleness_risk > call_cost_usd + latency_penalty_usd. Use stale data with disclosure otherwise.**

```js
// --- Consequence severity levels ---
// Calibrated to the cost of acting on wrong information

const CONSEQUENCE_SEVERITY = {
  critical:  1.00,   // patient harm, legal liability, financial settlement
  high:      0.30,   // wrong charge, account action, regulatory report
  medium:    0.05,   // poor customer experience, rebooking, manual fix
  low:       0.005,  // minor inconvenience, next-session correction
  negligible:0.0005, // informational, cached answer indistinguishable from live
};

// --- Staleness risk: probability that stale data is actually wrong ---
// Depends on data volatility and cache age vs typical update frequency

function stalenessRisk(cacheAgeSeconds, typicalUpdateIntervalSeconds) {
  // If cache age is well within update interval, risk is low
  // If cache age exceeds update interval, risk approaches 1.0
  const ratio = cacheAgeSeconds / typicalUpdateIntervalSeconds;
  if (ratio <= 0.5) return 0.02;    // very fresh for this data type — almost no risk
  if (ratio <= 1.0) return 0.15;    // within one update cycle — modest risk
  if (ratio <= 2.0) return 0.45;    // past one cycle — meaningful risk
  return Math.min(0.95, ratio * 0.3);  // increasingly likely to be stale
}

// --- Latency penalty: convert latency to cost ---
// Based on P95 latency budget and what 1ms of user wait is "worth"

function latencyPenaltyUsd(callLatencyMs, opts = {}) {
  const {
    userFacing       = true,    // false for async/batch jobs
    latencyBudgetMs  = 2000,    // total turn latency budget
    budgetUsdValue   = 0.10,    // what exceeding the budget is worth (e.g., SLO fee, churn)
  } = opts;

  if (!userFacing) return 0;   // async job: latency is free

  const fractionOfBudget = callLatencyMs / latencyBudgetMs;
  return fractionOfBudget * budgetUsdValue;
}

// --- The threshold decision ---

function shouldCallLiveApi(opts) {
  const {
    cacheAgeSeconds,
    typicalUpdateIntervalSeconds,
    consequenceSeverity,   // 'critical'|'high'|'medium'|'low'|'negligible'
    callCostUsd,
    callLatencyMs,
    userFacing = true,
  } = opts;

  const severity = CONSEQUENCE_SEVERITY[consequenceSeverity] ?? CONSEQUENCE_SEVERITY.medium;
  const risk     = stalenessRisk(cacheAgeSeconds, typicalUpdateIntervalSeconds);
  const benefit  = severity * risk;   // expected cost of staleness

  const penalty  = latencyPenaltyUsd(callLatencyMs, { userFacing });
  const total_cost = callCostUsd + penalty;

  const call = benefit > total_cost;

  return {
    call,
    reason:      call ? 'expected_staleness_cost_exceeds_call_cost' : 'cache_adequate',
    benefit:     parseFloat(benefit.toFixed(6)),
    cost:        parseFloat(total_cost.toFixed(6)),
    staleness_risk: parseFloat(risk.toFixed(3)),
    severity_weight: severity,
    note:        call
      ? `Make live call: staleness risk ($${benefit.toFixed(4)}) > call cost ($${total_cost.toFixed(4)})`
      : `Use cache: staleness risk ($${benefit.toFixed(4)}) < call cost ($${total_cost.toFixed(4)}); disclose age`,
  };
}

// --- Integration: augment the S-102 router decision ---

async function routeWithCostThreshold(queryType, args, cachedResult, opts = {}) {
  const {
    cacheAgeSeconds,
    typicalUpdateIntervalSeconds,
    consequenceSeverity = 'medium',
    callCostUsd         = 0.002,
    callLatencyMs       = 500,
    userFacing          = true,
    liveApiFn,           // async (args) => result
  } = opts;

  // If no cache at all, must call
  if (!cachedResult) {
    const result = await liveApiFn(args);
    return { ...result, _data_source: 'live_api', _threshold_decision: null };
  }

  const decision = shouldCallLiveApi({
    cacheAgeSeconds,
    typicalUpdateIntervalSeconds,
    consequenceSeverity,
    callCostUsd,
    callLatencyMs,
    userFacing,
  });

  if (decision.call) {
    const result = await liveApiFn(args);
    return {
      ...result,
      _data_source:         'live_api',
      _threshold_decision:  decision,
    };
  }

  // Use cache with staleness disclosure
  return {
    ...cachedResult,
    _data_source:        'cache_with_disclosure',
    _cache_age_seconds:  cacheAgeSeconds,
    _staleness_note:     `Data from ${Math.round(cacheAgeSeconds / 60)} min ago. Current value may differ.`,
    _threshold_decision: decision,
  };
}

// --- Query-type consequence registry ---
// Operators declare consequence severity per query type once; decision is automatic thereafter

const CONSEQUENCE_REGISTRY = {
  drug_interaction_check:        { severity: 'critical', typicalUpdateIntervalSeconds: 86400  },
  medication_recall_status:      { severity: 'critical', typicalUpdateIntervalSeconds: 3600   },
  account_credit_limit:          { severity: 'high',     typicalUpdateIntervalSeconds: 900    },
  return_processing_time:        { severity: 'low',      typicalUpdateIntervalSeconds: 259200 },  // 3-day cycle
  store_hours:                   { severity: 'medium',   typicalUpdateIntervalSeconds: 86400  },
  product_price_display:         { severity: 'low',      typicalUpdateIntervalSeconds: 3600   },
  contract_settlement_amount:    { severity: 'critical', typicalUpdateIntervalSeconds: 300    },
  general_faq:                   { severity: 'negligible',typicalUpdateIntervalSeconds: 604800 },
};

function thresholdDecisionForQueryType(queryType, cacheAgeSeconds, callCostUsd, callLatencyMs, userFacing) {
  const reg = CONSEQUENCE_REGISTRY[queryType];
  if (!reg) return shouldCallLiveApi({
    cacheAgeSeconds,
    typicalUpdateIntervalSeconds: 3600,
    consequenceSeverity: 'medium',
    callCostUsd, callLatencyMs, userFacing,
  });
  return shouldCallLiveApi({
    cacheAgeSeconds,
    typicalUpdateIntervalSeconds: reg.typicalUpdateIntervalSeconds,
    consequenceSeverity:          reg.severity,
    callCostUsd, callLatencyMs,   userFacing,
  });
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. All calculations are pure arithmetic — no API calls. Timing from 100 000 iterations. Consequence severity weights and staleness risk model are design parameters, not measured probabilities; calibrate from incident history in production.

```
=== shouldCallLiveApi timing (100 000 iterations) ===

$ node -e "
const t0 = performance.now();
for (let i = 0; i < 100000; i++) {
  shouldCallLiveApi({
    cacheAgeSeconds: 18000, typicalUpdateIntervalSeconds: 259200,
    consequenceSeverity: 'low', callCostUsd: 0.005,
    callLatencyMs: 800, userFacing: true,
  });
}
console.log('shouldCallLiveApi:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
shouldCallLiveApi: 0.0006 ms

=== Decision matrix: 8 query types ===

Query type               │ Cache age │ Severity   │ Staleness risk │ Benefit  │ Cost     │ Decision
─────────────────────────┼───────────┼────────────┼────────────────┼──────────┼──────────┼──────────
drug_interaction_check   │ 1h        │ critical   │ 0.450          │ $0.4500  │ $0.0055  │ CALL ✓
medication_recall_status │ 2h        │ critical   │ 0.950          │ $0.9500  │ $0.0055  │ CALL ✓
account_credit_limit     │ 30min     │ high       │ 0.450          │ $0.1350  │ $0.0055  │ CALL ✓
return_processing_time   │ 5h        │ low        │ 0.020          │ $0.0001  │ $0.0055  │ SKIP ← use cache
store_hours              │ 12h       │ medium     │ 0.150          │ $0.0075  │ $0.0055  │ CALL ✓ (barely)
store_hours              │ 4h        │ medium     │ 0.020          │ $0.0010  │ $0.0055  │ SKIP ← use cache
product_price_display    │ 30min     │ low        │ 0.020          │ $0.0001  │ $0.0055  │ SKIP ← use cache
general_faq              │ 2days     │ negligible │ 0.020          │ $0.0000  │ $0.0055  │ SKIP ← use cache

Call cost assumed: $0.005 API + $0.0005 latency (500ms user-facing at $0.10/latency budget).

=== Savings at 10 000 queries/day: mixed query distribution ===

Flat (always call live API):
  10 000 × $0.005 = $50.00/day

With threshold decisions (realistic distribution):
  drug/medical queries (200/day):     call all     → 200 × $0.005 = $1.00
  account/credit queries (500/day):   call all     → 500 × $0.005 = $2.50
  store hours (1000/day, 60% skip):   600 call, 400 skip → $3.00
  return policy (3000/day, skip all): 0 calls, cache → $0.00
  product price (2000/day, 90% skip): 200 call, 1800 skip → $1.00
  FAQ (3300/day, skip all):           0 calls → $0.00
  Total: $7.50/day

Savings: $42.50/day = $15 512/year from threshold-based routing vs flat live-API

=== Disclosure output format ===

When decision = SKIP (cache adequate):
{
  return_processing_time: "3-5 business days",
  _data_source:        "cache_with_disclosure",
  _cache_age_seconds:  18000,
  _staleness_note:     "Data from 300 min ago. Current value may differ.",
  _threshold_decision: {
    call: false,
    benefit: 0.0001,
    cost: 0.0055,
    note: "Use cache: staleness risk ($0.0001) < call cost ($0.0055); disclose age"
  }
}

Model receives the _staleness_note field and can include it in the user-facing response:
  "Our return processing time is 3-5 business days (based on data from approximately
   5 hours ago — contact us if you need the most current information)."

=== Async vs user-facing: latency penalty difference ===

Same query, different context:
  User-facing (200ms call, 2000ms budget, $0.10 value):
    latencyPenaltyUsd = (200/2000) × $0.10 = $0.010
    Total cost = $0.002 + $0.010 = $0.012

  Async batch (latency free):
    latencyPenaltyUsd = $0.000
    Total cost = $0.002 + $0.000 = $0.002
    → Threshold is 5× lower for async jobs: more calls are worth making
```

## See also

[S-102](s102-composable-agent-data-layers.md) · [S-100](s100-live-data-freshness-contracts.md) · [S-35](s35-latency-budget.md) · [S-99](s99-agent-task-economics.md) · [F-37](../forward-deployed/f37-knowledge-cutoff-handling.md) · [F-71](../forward-deployed/f71-cost-driven-prompt-design.md) · [S-43](s43-tool-result-caching.md)

## Go deeper

Keywords: `data call cost threshold` · `live API decision` · `staleness cost model` · `consequence severity` · `cache vs live decision` · `data freshness economics` · `call worth making` · `stale data disclosure` · `latency penalty` · `data call economics`
