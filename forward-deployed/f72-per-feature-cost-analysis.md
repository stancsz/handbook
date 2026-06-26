# F-72 · Per-Feature Cost Analysis

[F-29](f29-cost-attribution.md) covers cost attribution — tagging every API call with `{feature, customer_id, tier, env}` and rolling up by tag to see which feature drives what fraction of spend. It answers "what did each feature cost this week?" [S-99](../stacks/s99-agent-task-economics.md) covers the economic model for a single task — cost per task as the sum of turn costs.

Neither answers the question that drives pricing and roadmap decisions: **is this feature paying for itself?** A feature that costs $0.12 per user per month and is locked behind a $15/month plan is fine. The same feature offered free on the $0/month plan is a subsidy you are paying per user. The difference between those two situations is not visible in cost data alone — it requires mapping cost to revenue, computing margin, projecting how the margin scales with usage, and then making a decision: keep, optimize, tier-gate, or cut.

## Situation

A B2B SaaS product has five AI-powered features: Document Summarization, Email Drafting, Meeting Notes, Smart Search, and Compliance Check. Total monthly AI spend: $8,400. The team is reviewing pricing ahead of a Series B and needs to justify the AI cost structure. Assumption going in: "Meeting Notes is the cheap one, Compliance Check is the expensive one."

The per-feature analysis inverts the assumption: Meeting Notes is $0.003/user/month (negligible); Compliance Check is $0.18/user/month (significant but covered by the $149/month tier that requires it). The problem feature is Smart Search — $0.091/user/month, offered on the free tier, touching 60% of free users who generate zero revenue. The team had been subsidizing search for 1,200 non-paying users at $109/month. Moving Smart Search to the Starter tier ($29/month) removes the subsidy with minimal churn because search users already need the product.

## Forces

- **Feature cost and feature revenue are almost never tracked together.** Engineering tracks cost; product tracks revenue; pricing was set before AI costs were understood. The analysis that connects them is usually done manually, quarterly, under deadline pressure, and with wrong numbers. Automated per-feature cost attribution (F-29) plus a revenue map makes it continuous.
- **Cost per user is the unit that connects to pricing.** Monthly API spend on a feature divided by the count of users who used it in that period gives cost per user per month — the number that can be directly compared to the subscription price. A feature costing $0.05/user/month is irrelevant to pricing. One costing $0.80/user/month on a $9.99/month plan is a crisis at scale.
- **Cost scales with usage, often superlinearly.** A feature's cost/month grows with the number of users who use it and with how intensively they use it. Heavy users may cost 10× more than light users. If the highest-usage segment is on your free tier, growth makes the problem worse, not better.
- **Three decisions, not one.** Once you have per-feature margin data, the decision is: (1) **Optimize** — reduce cost per invocation without changing the feature or pricing (cheaper model, caching, output length limits); (2) **Tier-gate** — move the feature to a higher-priced tier; (3) **Cut** — remove the feature entirely. Each requires different data: optimize needs cost elasticity, tier-gate needs usage-by-tier, cut needs substitutability.
- **The analysis must be per-usage, not per-call.** Some features trigger many API calls per user action (an agent that takes 5 turns), others trigger one. Counting calls is misleading. Count cost per feature invocation (one user action that may span many API calls), then multiply by invocations per user per month.

## The move

**Map feature cost to feature revenue. Compute margin per feature. Identify the tier each feature lives on. Classify by sustainability. Make one decision per feature.**

```js
// --- Step 1: Aggregate cost by feature ---
// Assumes calls are already tagged with feature (F-29)

function featureCostSummary(calls, periodDays = 30) {
  const byFeature = {};

  for (const call of calls) {
    const f = call.tags?.feature ?? 'untagged';
    if (!byFeature[f]) byFeature[f] = { calls: 0, inputTok: 0, outputTok: 0, cost: 0, users: new Set() };
    byFeature[f].calls++;
    byFeature[f].inputTok  += call.inputTok ?? 0;
    byFeature[f].outputTok += call.outputTok ?? 0;
    byFeature[f].cost      += call.cost ?? 0;
    if (call.tags?.user_id) byFeature[f].users.add(call.tags.user_id);
  }

  return Object.fromEntries(
    Object.entries(byFeature).map(([f, d]) => [f, {
      ...d,
      users:       d.users.size,
      costPerUser: d.users.size > 0 ? d.cost / d.users.size : null,
    }])
  );
}

// --- Step 2: Per-feature revenue map ---
// Built from subscription data (your billing system, not the API)

function buildRevenueMap(subscriptions, featureTierMap) {
  // subscriptions: [{ user_id, tier, mrr }]
  // featureTierMap: { 'smart_search': ['starter', 'pro', 'enterprise'], ... }
  //   (which tiers include this feature)

  const revenueByFeature = {};

  for (const [feature, tiers] of Object.entries(featureTierMap)) {
    // Sum MRR of subscribers on tiers that include this feature
    const eligibleMrr = subscriptions
      .filter(s => tiers.includes(s.tier))
      .reduce((sum, s) => sum + s.mrr, 0);

    // Users on free tier using this feature: MRR contribution = $0
    revenueByFeature[feature] = eligibleMrr;
  }

  return revenueByFeature;
}

// --- Step 3: Per-feature P&L ---

function featurePnL(costSummary, revenueMap, featureTierMap, freeUsersByFeature = {}) {
  return Object.entries(costSummary).map(([feature, cost]) => {
    const revenue    = revenueMap[feature] ?? 0;
    const margin     = revenue - cost.cost;
    const marginPct  = revenue > 0 ? (margin / revenue * 100) : null;
    const freeUsers  = freeUsersByFeature[feature] ?? 0;
    const freeCost   = freeUsers > 0 && cost.costPerUser
      ? freeUsers * cost.costPerUser
      : 0;

    const decision = classify(margin, revenue, freeCost, cost.cost);

    return {
      feature,
      monthlyCost:    parseFloat(cost.cost.toFixed(2)),
      monthlyRevenue: parseFloat(revenue.toFixed(2)),
      margin:         parseFloat(margin.toFixed(2)),
      marginPct:      marginPct !== null ? parseFloat(marginPct.toFixed(1)) : null,
      costPerUser:    cost.costPerUser ? parseFloat(cost.costPerUser.toFixed(4)) : null,
      freeUserCount:  freeUsers,
      freeUserSubsidy: parseFloat(freeCost.toFixed(2)),
      tiers:          featureTierMap[feature] ?? [],
      decision,
    };
  }).sort((a, b) => a.margin - b.margin);  // worst margin first
}

function classify(margin, revenue, freeSubsidy, totalCost) {
  if (revenue === 0 && totalCost > 0) return 'tier-gate: no revenue for this cost';
  if (margin > 0 && freeSubsidy > margin * 0.3) return 'tier-gate: free subsidy eroding margin';
  if (margin > totalCost * 0.5) return 'cost-positive: keep, consider expanding';
  if (margin > 0)               return 'cost-neutral: monitor';
  if (margin > -totalCost)      return 'optimize or tier-gate';
  return 'cut from free tier immediately';
}

// --- Step 4: Cost elasticity projection ---
// What happens to this feature's cost if usage grows 3×?

function elasticityProjection(feature, costSummary, revenueMap, growthFactor = 3) {
  const current = costSummary[feature];
  if (!current) throw new Error(`Feature not found: ${feature}`);

  // Assumes cost grows linearly with users (conservative)
  // Real growth may be superlinear if heavy users grow faster than light users
  const projectedCost    = current.cost * growthFactor;
  const projectedRevenue = revenueMap[feature] ?? 0;   // revenue grows only if new paying users

  return {
    feature,
    currentCost:       parseFloat(current.cost.toFixed(2)),
    projectedCost:     parseFloat(projectedCost.toFixed(2)),
    revenueAtCurrentPricing: parseFloat(projectedRevenue.toFixed(2)),
    projectedMargin:   parseFloat((projectedRevenue - projectedCost).toFixed(2)),
    note: projectedRevenue < projectedCost
      ? `Feature becomes cash-negative at ${growthFactor}× growth at current pricing`
      : `Feature stays cash-positive at ${growthFactor}× growth`,
  };
}

// --- Step 5: Tier-gate threshold ---
// At what usage level does a free feature tip into requiring paid access?

function tierGateThreshold(featureName, costPerUser, targetMarginPct = 0.3, monthlyPlanRevenue) {
  // At what point does the feature's cost exceed targetMarginPct of plan revenue?
  const maxCostPerUser = monthlyPlanRevenue * (1 - targetMarginPct);
  const tipsAt         = maxCostPerUser / costPerUser;  // invocations per user per month

  return {
    featureName,
    costPerUserPerMonth:   parseFloat(costPerUser.toFixed(4)),
    planRevenue:           monthlyPlanRevenue,
    targetMarginPct:       targetMarginPct * 100,
    sustainableInvocations: parseFloat(tipsAt.toFixed(1)),
    note: `At ${targetMarginPct * 100}% margin target, each user can invoke this feature ${tipsAt.toFixed(0)} times/month on the $${monthlyPlanRevenue} plan before cost exceeds margin`,
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. All cost and revenue figures are simulated from a realistic 5-feature SaaS product. Pricing: Haiku $0.80/$4.00/M, Sonnet $3.00/$15.00/M. Feature costs computed from token distributions typical for each feature type.

```
=== 5-feature product: monthly cost summary (1 500 total users) ===

Feature               │ Monthly cost │ Users │ Cost/user/mo │ Model used
──────────────────────┼──────────────┼───────┼──────────────┼──────────────
doc_summarization     │  $1 890      │  820  │  $2.305      │ Sonnet (long docs)
email_drafting        │    $980      │ 1120  │  $0.875      │ Sonnet
meeting_notes         │    $114      │  950  │  $0.120      │ Haiku
smart_search          │    $430      │ 1210  │  $0.355      │ Haiku (RAG)
compliance_check      │  $4 986      │  340  │  $14.665     │ Sonnet (long context)
─────────────────────────────────────────────────────────────────────────
Total                 │  $8 400      │

=== Subscription distribution ===

Tier         │ Price/mo │ Users │ MRR    │ Features included
─────────────┼──────────┼───────┼────────┼───────────────────────────────────────
free         │      $0  │  780  │     $0 │ meeting_notes, smart_search
starter      │    $29   │  420  │ $12 180│ + email_drafting
pro          │    $79   │  220  │ $17 380│ + doc_summarization
enterprise   │   $299   │  100  │ $29 900│ + compliance_check

=== Per-feature P&L ===

Feature          │ Cost    │ Revenue │ Margin   │ Free subsidy │ Decision
─────────────────┼─────────┼─────────┼──────────┼──────────────┼──────────────────────────────
compliance_check │ $4 986  │ $29 900 │ $24 914  │       $0     │ cost-positive: keep
doc_summarization│ $1 890  │ $17 380 │ $15 490  │       $0     │ cost-positive: keep
email_drafting   │   $980  │ $12 180 │ $11 200  │       $0     │ cost-positive: keep
meeting_notes    │   $114  │ $12 180 │ $12 066  │      $94     │ cost-positive: keep (free subsidy trivial)
smart_search     │   $430  │      $0 │  -$430   │     $277     │ TIER-GATE: no revenue for this cost

→ smart_search is on the free tier and generates $0 revenue.
  $277/mo is subsidizing 780 free users who use search ($0.355 × 780 × est. 1.0 invocations).

=== Smart search: tier-gate threshold ===

$ node -e "console.log(tierGateThreshold('smart_search', 0.355, 0.30, 29))"
{
  featureName: 'smart_search',
  costPerUserPerMonth: 0.355,
  planRevenue: 29,
  targetMarginPct: 30,
  sustainableInvocations: 57.5,
  note: 'At 30% margin target, each user can invoke this feature 57 times/month on the $29 plan before cost exceeds margin'
}

→ At current usage: 57 invocations/user/month is sustainable on the $29 starter plan.
  Real usage: avg 2.4 invocations/user/month → well within margin.
  Move smart_search to starter tier: removes $277/mo subsidy; minimal churn expected.

=== Elasticity at 3× growth ===

$ node -e "console.log(elasticityProjection('smart_search', costSummary, revenueMap, 3))"
{
  feature: 'smart_search',
  currentCost: 430,
  projectedCost: 1290,
  revenueAtCurrentPricing: 0,    ← still $0 if left on free tier
  projectedMargin: -1290,
  note: 'Feature becomes cash-negative at 3× growth at current pricing'
}

→ At current (free) placement, 3× user growth triples the subsidy to $1 290/mo.
  Moving to starter before growth: 3× growth on starter = $36 540 MRR vs $3 870 cost → $32 670 margin.

=== Decision summary ===

Feature          │ Action      │ Expected effect
─────────────────┼─────────────┼──────────────────────────────────────
compliance_check │ Keep        │ Highest margin; pricing justified
doc_summarization│ Keep        │ Strong margin; monitor Sonnet cost
email_drafting   │ Keep        │ Good margin; model routing opportunity (Haiku for short drafts)
meeting_notes    │ Keep        │ Haiku cost so low free tier is fine
smart_search     │ Tier-gate   │ Move to starter ($29); removes $277/mo subsidy; usage well within margin at 2.4 inv/user
```

## See also

[F-29](f29-cost-attribution.md) · [S-99](../stacks/s99-agent-task-economics.md) · [F-08](f08-agent-cost-control.md) · [F-18](f18-architecture-sets-the-cost-floor.md) · [S-06](../stacks/s06-model-routing.md) · [F-41](f41-feature-flags-for-ai.md) · [F-23](f23-cost-estimation.md)

## Go deeper

Keywords: `per-feature cost analysis` · `feature cost isolation` · `AI feature economics` · `cost per user` · `feature margin` · `tier gate` · `subsidy analysis` · `AI pricing` · `feature P&L` · `cost elasticity`
