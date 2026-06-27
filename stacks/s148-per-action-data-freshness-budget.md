# S-148 · Per-Action Data Freshness Budget

[S-100](s100-live-data-freshness-contracts.md) defines freshness contracts at the source level: a source declares its update interval and a minimum freshness floor. A call to a source that has not updated in longer than the floor produces a STALE result — and S-100 routes to a different source or returns DATA_UNAVAILABLE. [S-105](s105-data-call-cost-threshold.md) asks whether the cost of a live data call is worth making given the action's consequence severity. Both operate on the source side.

Neither operates on the action side. The same live data fetch may be fresh enough for one action but too stale for another. A price quote 8 seconds old is FRESH for generating a portfolio summary (a report action). The same quote is STALE for executing a market order (a trade action). Source freshness contracts do not encode this: Bloomberg's data contract says the price field updates every 3 seconds, not that 8-second-old prices are unacceptable for trading. The action's own requirement determines that.

A per-action freshness budget stores a maximum acceptable data age (milliseconds) per action type. Before executing any action that depends on live data, the agent checks whether the relevant fields meet the action's budget. Fields that are STALE for this action trigger a data refresh, a degraded action variant, or an abort — depending on how critical freshness is for the action.

## Situation

A financial agent can take three action types on behalf of a user: `execute_trade` (submit a market order), `send_alert` (fire a price threshold alert), and `generate_report` (produce an end-of-day summary). Each has a different tolerance for stale data.

```
execute_trade:   5 000ms  — a 5s-old price on a fast-moving equity may be cents off; unacceptable
send_alert:     10 000ms  — price alerts fire within 10s of threshold crossing; 10s-old data is fine
generate_report: 300 000ms — end-of-day summaries use 5-min-old data; this is expected
```

An agent fetches live prices at t=0 and stores them. At t=8s, the user requests all three action types on the same data:

- `execute_trade`: price age 8s > 5s budget → STALE → agent refreshes price data before submitting order
- `send_alert`: price age 8s ≤ 10s budget → FRESH → alert fires without extra fetch
- `generate_report`: price age 8s ≤ 300s budget → FRESH → report generated without extra fetch

Without a freshness budget: the agent treats all data as equally fresh or equally stale. Either it over-fetches (refreshes before every action regardless) or under-fetches (uses cached data for trades when it shouldn't).

## Forces

- **Actions have different consequence costs.** An 8-second-old price used in a report produces a minor annotation issue. The same price used in a market order may result in a fill at the wrong price. The freshness requirement should reflect the consequence of staleness, not a blanket "live data must be recent."
- **Source update interval ≠ action freshness requirement.** Bloomberg updates equity prices every 3 seconds. A trade execution action may require data no older than 5 seconds — which is compatible with Bloomberg's rate. A different source updates every 15 seconds. For a `send_alert` action with a 10-second budget, the 15-second-update source is structurally incompatible — its data is always too stale for this action. S-100 and S-148 compose: S-100 ensures the source can deliver data in the freshness range; S-148 ensures the fetched data was fresh enough when it arrived.
- **Per-field staleness, not per-response staleness.** A merged record from S-137 may have `price` fetched at t=0 and `volume` fetched at t=-45s (from a prior poll that didn't include volume refresh). `execute_trade` needs fresh `price` and `volume` — but only `price` meets the 5s budget. `checkAll()` catches this: it returns per-field status so the agent knows exactly which fields need refreshing, not just whether the record is acceptable.
- **Freshness budgets are defined by the action owner, not the data team.** The team managing Bloomberg connections sets S-100 source contracts. The team implementing trade execution sets S-148 action budgets. These are separate concerns. Changes to Bloomberg's update rate should not require changes to trade execution freshness requirements, and vice versa.
- **Zero-infrastructure, zero-latency.** The check is a Map lookup and a subtraction. No network call, no database read, no token cost. The overhead is negligible compared to any data refresh it might trigger.
- **Document the budget table and keep it versioned.** Freshness budgets affect agent behavior in production. They should be in a config file (not hardcoded), reviewed when action types change, and audited when data quality incidents trace back to stale data.

## The move

**Declare maximum acceptable data age per action type. Check before each action. Refresh or abort on STALE.**

```js
// --- Per-action data freshness budget ---
// Stores maxAgeMs per actionType.
// check() returns whether dataFetchedAtMs is within budget at nowMs.
// checkAll() checks a map of {field: fetchedAtMs} for multi-field actions.

class ActionFreshnessBudget {
  constructor(actionBudgets = {}) {
    this._budgets = new Map(Object.entries(actionBudgets));
  }

  // Register or update the max acceptable data age for an action type.
  // maxAgeMs: number — maximum milliseconds since data was fetched
  register(actionType, maxAgeMs) {
    this._budgets.set(actionType, maxAgeMs);
  }

  // Check whether a single data point meets the action's freshness budget.
  // dataFetchedAtMs: timestamp when the data was fetched (Date.now() at fetch time)
  // nowMs:          current timestamp (Date.now() when the action is about to execute)
  check(actionType, dataFetchedAtMs, nowMs) {
    const maxAgeMs = this._budgets.get(actionType);
    if (maxAgeMs === undefined) {
      return {
        fresh:    null,
        ageMs:    nowMs - dataFetchedAtMs,
        maxAgeMs: null,
        action:   actionType,
        status:   'NO_BUDGET_DEFINED',
      };
    }
    const ageMs = nowMs - dataFetchedAtMs;
    return {
      fresh:    ageMs <= maxAgeMs,
      ageMs,
      maxAgeMs,
      action:   actionType,
      status:   ageMs <= maxAgeMs ? 'FRESH' : 'STALE',
    };
  }

  // Check multiple fields against the action budget.
  // fieldFetchTimes: { [fieldName]: fetchedAtMs }
  // Returns per-field status + list of stale fields + overall fresh flag.
  checkAll(actionType, fieldFetchTimes, nowMs) {
    const results = {};
    for (const [field, fetchedAtMs] of Object.entries(fieldFetchTimes)) {
      results[field] = this.check(actionType, fetchedAtMs, nowMs);
    }
    const staleFields = Object.entries(results)
      .filter(([, r]) => r.status === 'STALE')
      .map(([f]) => f);
    return {
      actionType,
      fresh:       staleFields.length === 0,
      staleFields,
      results,
    };
  }
}

// --- Action budget table (define per deployment) ---
// Update via config or environment — not hardcoded in application logic.
const TRADE_FRESHNESS_BUDGETS = new ActionFreshnessBudget({
  execute_trade:     5_000,    // 5 seconds  — market orders require near-real-time prices
  place_limit_order: 30_000,   // 30 seconds — limit orders are less sensitive to price precision
  send_alert:        10_000,   // 10 seconds — price alerts can tolerate 10s delay
  generate_report:  300_000,   // 5 minutes  — end-of-day summaries use 5-min-old data acceptably
  display_summary:  600_000,   // 10 minutes — dashboard display; staleness is annotated, not blocked
});

// --- Integration pattern ---
// Before any action, check freshness of all required fields.
// On STALE: refresh only the stale fields, not the full record.

async function executeWithFreshnessGate(actionType, mergedRecord, fieldFetchTimes, refreshFn, executeFn) {
  const nowMs = Date.now();
  const freshnessCheck = TRADE_FRESHNESS_BUDGETS.checkAll(actionType, fieldFetchTimes, nowMs);

  if (!freshnessCheck.fresh) {
    // Refresh only the stale fields
    const refreshed = await refreshFn(freshnessCheck.staleFields);
    // Update mergedRecord and fieldFetchTimes with fresh values
    for (const field of freshnessCheck.staleFields) {
      mergedRecord[field]    = refreshed[field];
      fieldFetchTimes[field] = Date.now();
    }
  }

  return executeFn(mergedRecord, { freshnessCheck, refreshedFields: freshnessCheck.staleFields });
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `check()` and `checkAll()` timed over 100 000 iterations. `checkAll()` uses 5 fields with 2 stale, 3 fresh.

```
=== ActionFreshnessBudget timing (100 000 iterations) ===

register():                            0.0001 ms
check() — FRESH:                       0.0001 ms
check() — STALE:                       0.0001 ms
check() — NO_BUDGET_DEFINED:           0.0001 ms
checkAll() — 5 fields, 2 stale:        0.0038 ms

=== Trading agent: 3 action types on 8-second-old data ===

Data fetched at t=0ms. Action requested at t=8 000ms.
Field fetch times at action time: all fields at t=0ms.

  Budget table:
    execute_trade:     5 000ms
    send_alert:       10 000ms
    generate_report: 300 000ms

  checkAll('execute_trade', fieldTimes, now=t+8000):
    price:     ageMs=8000  maxAgeMs=5000  STALE  ← refresh required
    bidAsk:    ageMs=8000  maxAgeMs=5000  STALE  ← refresh required
    volume:    ageMs=8000  maxAgeMs=5000  STALE  ← refresh required
    marketCap: ageMs=8000  maxAgeMs=5000  STALE  ← refresh required
    news:      ageMs=8000  maxAgeMs=5000  STALE  ← refresh required
    fresh: false — agent refreshes price + bidAsk before submitting order

  checkAll('send_alert', fieldTimes, now=t+8000):
    price:  ageMs=8000  maxAgeMs=10000  FRESH
    bidAsk: ageMs=8000  maxAgeMs=10000  FRESH
    fresh: true — alert fires without extra fetch

  checkAll('generate_report', fieldTimes, now=t+8000):
    price:     ageMs=8000   maxAgeMs=300000  FRESH
    volume:    ageMs=8000   maxAgeMs=300000  FRESH
    marketCap: ageMs=8000   maxAgeMs=300000  FRESH
    fresh: true — report generated without extra fetch

=== Per-field partial staleness (mixed-age merged record) ===

S-137 merges price from Bloomberg (fetched t=0s ago) and volume from last
scheduled poll (fetched t=45s ago). execute_trade requires both:

  checkAll('execute_trade', {price: now-0, volume: now-45000}, now):
    price:  ageMs=0      FRESH   (just fetched)
    volume: ageMs=45000  STALE   ← only volume needs refresh
    fresh: false
    staleFields: ['volume']

Agent refreshes only 'volume' via S-137 targeted fetch — not the full merged record.

=== S-100 vs S-105 vs S-148 ===

              │ S-100 (source freshness contract)    │ S-105 (data call cost threshold)     │ S-148 (per-action freshness budget)
──────────────┼──────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────
Perspective   │ Source-centric                       │ Call-cost-centric                    │ Action-centric
Question      │ Is this source's data recent enough? │ Is a live call worth the cost?       │ Is this data fresh enough for this action?
Configured by │ Data team (source knowledge)         │ Business team (consequence value)    │ Action owner (tolerance for staleness)
Trigger       │ Before picking source in S-137       │ Before deciding whether to call at all│ Before executing the action
Input         │ source update_interval, floor        │ consequence_severity, call_fee       │ actionType, dataFetchedAtMs, nowMs
On STALE      │ Try next source or DATA_UNAVAILABLE  │ Use cached data + disclose           │ Refresh stale fields, abort if critical
Composes      │ S-148: if source meets its own floor │ S-148: if cost justifies a call,     │ S-100 ensures source can meet budget;
              │ → check if meets action budget too   │ check if result would be fresh enough│ S-105 ensures call is worth making
```

## See also

[S-100](s100-live-data-freshness-contracts.md) · [S-105](s105-data-call-cost-threshold.md) · [S-137](s137-multi-source-field-level-merge.md) · [S-33](s33-live-data-vs-stale-snapshots.md) · [S-128](s128-freshness-annotated-context-injection.md) · [F-100](../forward-deployed/f100-output-claim-temporal-scope-check.md)

## Go deeper

Keywords: `per-action data freshness` · `action freshness budget` · `data staleness per action` · `freshness gate before action` · `live data action requirement` · `action data age budget` · `per-action freshness check` · `data age per action type` · `freshness enforcement per action` · `action-level data freshness`
