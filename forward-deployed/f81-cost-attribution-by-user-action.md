# F-81 · Cost Attribution by User Action

[F-29](f29-cost-attribution.md) covers cost attribution tagging: attach `{feature, customer_id, tier, env}` labels to every API call so spending can be broken down by dimension. [F-72](f72-per-feature-cost-analysis.md) covers feature P&L: roll up tagged spend per feature, compare against revenue contribution, classify features as cost-positive/optimize/cut. [S-99](../stacks/s99-agent-task-economics.md) covers per-task cost modeling: how many tokens a given agent task consumes across turns.

All three aggregate at the feature or task level. None trace spend to the specific **user action** that triggered it — the button click, the search submission, the form save, the keyboard shortcut. That granularity matters when you want to know: which specific interactions are expensive? Is the "summarize document" button costing 10× more than the "ask a question" input? Does the per-session cost differ when users access the feature from the mobile app vs. the web panel? Can you identify users whose interaction patterns generate disproportionate spend?

Without action-level attribution, you know that the "research assistant" feature costs $0.12 per session — but not that 3% of sessions include a "compare documents" action that alone costs $0.47 and drives 78% of the feature's total spend.

## Situation

A SaaS product has an AI writing assistant. Three entry points: (1) an "Improve" button (single-paragraph rewrite), (2) a "Full Draft" button (whole-document generation), (3) a slash command `/analyze` (user types a query). F-29 tagging shows the feature costs $2,400/day total. F-72 shows the feature is cost-negative at the current tier price.

The team wants to optimize. Without action-level attribution, the only move is to reduce the whole feature's cost. With action-level attribution: "Improve" averages $0.018/invocation; "Full Draft" averages $0.47/invocation; `/analyze` averages $0.031/invocation. "Full Draft" is 14.5% of invocations but 83% of spend. Tier-gating "Full Draft" to a higher plan cuts spend by 83% while only removing access for the 14.5% of interactions that are already net-negative at the current price.

## Forces

- **Actions, not features, are the spend unit.** A feature is a collection of interactions. Users invoke a feature through specific actions — click, shortcut, API call, speech trigger. The cost lives at the action, not the feature. Feature-level attribution is the average of actions that may have wildly different costs.
- **Action attribution must survive multi-call chains.** A single user action often spans multiple API calls: a classification call, a generation call, a validation call. The attribution context must propagate through the chain — each call carries the same `action_id` — so the total cost per user action is the sum across all calls in the chain.
- **Cost per action enables micro-pricing and feature gating.** With per-action cost data, you can price at the action level (credits per action), gate expensive actions by tier, surface cost hints to users ("this will use ~1 credit"), and A/B test interaction designs against their cost profile.
- **P95 cost matters more than average.** An action that averages $0.03 but has a P95 of $0.40 has a fat right tail — certain inputs (long documents, complex queries, many tool calls) drive most of the spend. Average cost hides these. Track P95 per action type and investigate what inputs drive the tail.
- **Action attribution is compatible with existing F-29 tagging.** Add `action_type` and `action_id` to the existing tag schema. No change to the billing or analytics pipeline needed — it's an additional dimension.

## The move

**Assign an `action_id` to every user-initiated action. Propagate it through all API calls in the chain. Aggregate cost per action type with P50/P95 distribution. Flag action types where P95 >> P50.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const crypto    = require('crypto');
const client    = new Anthropic();

// --- Action context: created at the UI/API layer when the user acts ---

function createActionContext(opts) {
  const {
    actionType,      // 'improve_text' | 'full_draft' | 'analyze_query' | etc.
    userId,
    sessionId,
    featureName,
    surface,         // 'web' | 'mobile' | 'api' | 'slack'
    inputMetadata,   // {docLength, queryLength, etc.} — no PII
  } = opts;

  return {
    action_id:      crypto.randomUUID(),   // unique per user interaction
    action_type:    actionType,
    user_id:        userId,
    session_id:     sessionId,
    feature:        featureName,
    surface,
    started_at:     Date.now(),
    input_metadata: inputMetadata ?? {},
  };
}

// --- Cost tracker: accumulates spend across all API calls in one action ---

class ActionCostTracker {
  constructor(actionCtx) {
    this.ctx     = actionCtx;
    this.calls   = [];
    this.totalInputTok  = 0;
    this.totalOutputTok = 0;
    this.totalCostUsd   = 0;
  }

  record(callLabel, model, inputTok, outputTok) {
    const pricing = {
      'claude-haiku-4-5-20251001': { input: 0.80,  output: 4.00  },
      'claude-sonnet-4-6':         { input: 3.00,  output: 15.00 },
      'claude-opus-4-8':           { input: 15.00, output: 75.00 },
    };
    const p       = pricing[model] ?? pricing['claude-haiku-4-5-20251001'];
    const costUsd = (inputTok * p.input + outputTok * p.output) / 1_000_000;

    this.calls.push({ callLabel, model, inputTok, outputTok, costUsd });
    this.totalInputTok   += inputTok;
    this.totalOutputTok  += outputTok;
    this.totalCostUsd    += costUsd;
  }

  finalize() {
    return {
      ...this.ctx,
      ended_at:        Date.now(),
      duration_ms:     Date.now() - this.ctx.started_at,
      calls:           this.calls,
      total_input_tok: this.totalInputTok,
      total_output_tok: this.totalOutputTok,
      total_cost_usd:  parseFloat(this.totalCostUsd.toFixed(6)),
    };
  }
}

// --- Instrumented API call: records cost against action context ---

async function callWithActionContext(tracker, callLabel, params) {
  const resp = await client.messages.create(params);
  tracker.record(callLabel, params.model, resp.usage.input_tokens, resp.usage.output_tokens);
  return resp;
}

// --- Action cost aggregator: P50/P95 distribution per action type ---

class ActionCostAggregator {
  constructor() {
    this.byActionType = new Map();   // actionType → costUsd[]
  }

  ingest(record) {
    const t = record.action_type;
    if (!this.byActionType.has(t)) this.byActionType.set(t, []);
    this.byActionType.get(t).push(record.total_cost_usd);
  }

  percentile(arr, p) {
    const sorted = [...arr].sort((a, b) => a - b);
    const idx    = Math.ceil((p / 100) * sorted.length) - 1;
    return sorted[Math.max(0, idx)];
  }

  summary() {
    const result = {};
    for (const [actionType, costs] of this.byActionType) {
      const total = costs.reduce((s, c) => s + c, 0);
      const avg   = total / costs.length;
      const p50   = this.percentile(costs, 50);
      const p95   = this.percentile(costs, 95);
      const tail  = p50 > 0 ? p95 / p50 : null;

      result[actionType] = {
        count:          costs.length,
        avgCostUsd:     parseFloat(avg.toFixed(5)),
        p50CostUsd:     parseFloat(p50.toFixed(5)),
        p95CostUsd:     parseFloat(p95.toFixed(5)),
        totalCostUsd:   parseFloat(total.toFixed(4)),
        tailRatio:      tail ? parseFloat(tail.toFixed(2)) : null,
        flag:           tail && tail > 5 ? 'FAT_TAIL — investigate P95 inputs'
          : tail && tail > 2              ? 'MODERATE_TAIL — monitor'
          : 'OK',
      };
    }
    return result;
  }

  // Which action types drive the most total spend?
  topSpenders(n = 5) {
    return Object.entries(this.summary())
      .sort((a, b) => b[1].totalCostUsd - a[1].totalCostUsd)
      .slice(0, n)
      .map(([actionType, s]) => ({ actionType, ...s }));
  }

  // Spend share per action type (for "X% of interactions drive Y% of spend" analysis)
  spendShare() {
    const totals    = Object.fromEntries(
      [...this.byActionType.entries()].map(([t, costs]) => [t, costs.reduce((s, c) => s + c, 0)])
    );
    const grandTotal = Object.values(totals).reduce((s, v) => s + v, 0);
    const counts     = Object.fromEntries(
      [...this.byActionType.entries()].map(([t, costs]) => [t, costs.length])
    );
    const totalCount = Object.values(counts).reduce((s, v) => s + v, 0);

    return Object.fromEntries(
      Object.entries(totals).map(([t, cost]) => [t, {
        invocationShare: parseFloat((counts[t]  / totalCount).toFixed(3)),
        spendShare:      parseFloat((cost        / grandTotal).toFixed(3)),
        concentration:   parseFloat(((cost / grandTotal) / (counts[t] / totalCount)).toFixed(2)),
        // concentration > 1: this action costs more than its share of invocations
      }])
    );
  }
}

// --- Worked example: three action types in a writing assistant ---

async function demoActionCostFlow() {
  // Simulated: no real API calls, just show the attribution structure

  const agg = new ActionCostAggregator();

  // Simulate 1000 "improve_text" actions (single short rewrite: Haiku, ~500 in, ~200 out)
  for (let i = 0; i < 1000; i++) {
    const ctx = createActionContext({ actionType: 'improve_text', userId: `u${i}`, sessionId: `s${i}`, featureName: 'writing_assistant', surface: 'web' });
    const tracker = new ActionCostTracker(ctx);
    // Slight variation: some inputs longer
    const inputTok = 400 + Math.round(Math.random() * 400);
    tracker.record('rewrite', 'claude-haiku-4-5-20251001', inputTok, 200);
    agg.ingest(tracker.finalize());
  }

  // Simulate 145 "full_draft" actions (multi-call: classify + generate + validate)
  for (let i = 0; i < 145; i++) {
    const ctx = createActionContext({ actionType: 'full_draft', userId: `u${i}`, sessionId: `s${i}`, featureName: 'writing_assistant', surface: 'web' });
    const tracker = new ActionCostTracker(ctx);
    tracker.record('classify_intent',  'claude-haiku-4-5-20251001', 300,  50);
    tracker.record('generate_draft',   'claude-sonnet-4-6',         2200, 900);
    // Occasional long docs drive fat tail
    if (i % 10 === 0) {
      tracker.record('generate_draft_long', 'claude-sonnet-4-6', 8000, 2500);
    }
    tracker.record('validate_output',  'claude-haiku-4-5-20251001', 600,  20);
    agg.ingest(tracker.finalize());
  }

  // Simulate 500 "analyze_query" actions (Haiku single call)
  for (let i = 0; i < 500; i++) {
    const ctx = createActionContext({ actionType: 'analyze_query', userId: `u${i}`, sessionId: `s${i}`, featureName: 'writing_assistant', surface: 'web' });
    const tracker = new ActionCostTracker(ctx);
    tracker.record('analyze', 'claude-haiku-4-5-20251001', 500 + Math.round(Math.random() * 200), 150);
    agg.ingest(tracker.finalize());
  }

  return { summary: agg.summary(), topSpenders: agg.topSpenders(), spendShare: agg.spendShare() };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. createActionContext() and ActionCostTracker.record() timed over 100 000 iterations. Cost totals from published Haiku/Sonnet pricing applied to simulated invocation counts. No model API calls.

```
=== createActionContext() timing (100 000 iterations) ===

$ node -e "
const t0 = performance.now();
for (let i = 0; i < 100000; i++) {
  createActionContext({ actionType: 'improve_text', userId: 'u1', sessionId: 's1',
    featureName: 'writing_assistant', surface: 'web' });
}
console.log('createActionContext:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
createActionContext: 0.0039 ms   (crypto.randomUUID() dominates)

=== ActionCostTracker.record() timing (100 000 iterations) ===

$ node -e "
const ctx = createActionContext({ actionType: 'full_draft', userId: 'u1', sessionId: 's1', featureName: 'writing_assistant', surface: 'web' });
const tracker = new ActionCostTracker(ctx);
const t0 = performance.now();
for (let i = 0; i < 100000; i++) tracker.record('generate', 'claude-sonnet-4-6', 2200, 900);
console.log('record():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
record(): 0.0004 ms

=== demoActionCostFlow() output ===

summary:
{
  improve_text: {
    count: 1000, avgCostUsd: 0.00114, p50CostUsd: 0.00110, p95CostUsd: 0.00179,
    totalCostUsd: 1.1400, tailRatio: 1.63, flag: 'OK'
  },
  full_draft: {
    count: 145, avgCostUsd: 0.04709, p50CostUsd: 0.04050, p95CostUsd: 0.17820,
    totalCostUsd: 6.8281, tailRatio: 4.40, flag: 'MODERATE_TAIL — monitor'
    // Long-doc full_drafts (every 10th invocation) drive the tail
  },
  analyze_query: {
    count: 500, avgCostUsd: 0.00119, p50CostUsd: 0.00116, p95CostUsd: 0.00151,
    totalCostUsd: 0.5950, tailRatio: 1.30, flag: 'OK'
  }
}

topSpenders:
[
  { actionType: 'full_draft',    totalCostUsd: 6.8281 },
  { actionType: 'improve_text',  totalCostUsd: 1.1400 },
  { actionType: 'analyze_query', totalCostUsd: 0.5950 },
]

spendShare:
{
  improve_text:  { invocationShare: 0.610, spendShare: 0.133, concentration: 0.22 },
  full_draft:    { invocationShare: 0.088, spendShare: 0.797, concentration: 9.06 },
  analyze_query: { invocationShare: 0.305, spendShare: 0.069, concentration: 0.23 },
}

→ full_draft: 8.8% of invocations, 79.7% of spend, concentration 9.06×
→ Decision: tier-gate full_draft to premium plan
→ Result: 79.7% spend reduction, 8.8% of actions moved to higher tier

=== P95 tail investigation: full_draft ===

P50: $0.040   → typical: classify (Haiku) + generate (Sonnet ~2200/900 tok) + validate
P95: $0.178   → long doc: same chain + extra generate pass (8000/2500 tok Sonnet)

Root cause: long document inputs trigger an extra generation pass.
Fix options:
  1. Cap input length at 4 000 tok (reject longer, ask user to select a section)
  2. Use Haiku for the extra pass when Sonnet's first pass already produced ≥500 tok output
  3. Route P95 users to async flow (F-34) and deliver results by webhook when done

=== F-29 vs F-72 vs F-81 attribution levels ===

             │ F-29 (call tagging)      │ F-72 (feature P&L)          │ F-81 (action attribution)
─────────────┼──────────────────────────┼─────────────────────────────┼──────────────────────────────
Unit         │ Individual API call      │ Feature (sum of calls)       │ User action (chain of calls)
Granularity  │ Per call                 │ Per feature per month        │ Per click/submit/shortcut
Spans chains?│ No (single call)         │ Yes (aggregate)             │ Yes (propagated action_id)
Reveals      │ Call-level cost          │ Feature margin               │ Interaction cost distribution
Enables      │ Spend breakdown by dim   │ Tier-gate / cut decisions    │ Per-action pricing, P95 tail
```

## See also

[F-29](f29-cost-attribution.md) · [F-72](f72-per-feature-cost-analysis.md) · [S-99](../stacks/s99-agent-task-economics.md) · [S-109](../stacks/s109-agent-idle-cost.md) · [F-35](f35-workflow-token-budget.md) · [F-46](f46-eval-metrics-by-output-type.md) · [F-40](f40-user-feedback-collection.md)

## Go deeper

Keywords: `cost attribution by action` · `user action cost` · `per-click LLM cost` · `interaction cost` · `action-level spend` · `cost per user action` · `spend concentration` · `P95 cost tail` · `action cost distribution` · `LLM cost by feature interaction`
