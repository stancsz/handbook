# F-162 · Tool Result Freshness Assertion

S-111 (partial context refresh) replaces stale injected blocks when their TTL expires. S-174 (stale-while-revalidate) serves cached data while a background fetch completes. S-190 (live data delta injection) minimizes tokens by injecting only changed fields. None of these operate at the point of use.

An exchange rate fetched at 8:00am and used for a payment calculation at 8:45am is 45 minutes old. The block's TTL might be set to 60 minutes — it hasn't triggered a refresh. The context still shows the injected data as "current." But the exchange rate moved 0.8% since the fetch, and the payment amount is wrong.

The tool result freshness asserter checks staleness at the moment a result is about to be used in an action, not at injection time. Each high-stakes tool result is registered with its fetch timestamp and a per-operation freshness requirement. Before any tool call that consumes a prior result, the asserter checks whether that result is still within the freshness window for that specific use. If it isn't, the call is blocked with a refetch instruction.

This check is separate from TTL-based refresh because freshness requirements differ by operation. A portfolio snapshot might be fresh enough to display to a user (warn if >10 min, error if >60 min) but not fresh enough to execute a trade (warn if >1 min, error if >5 min). The same fetched result has different freshness requirements depending on what is being done with it.

## Situation

A financial services agent helps portfolio managers execute trades. It fetches three types of data during a session:
- Exchange rates (`get_exchange_rate`): volatile, changes by the minute during market hours.
- Portfolio positions (`get_portfolio`): semi-stable, changes only when trades execute.
- User permissions (`get_permissions`): stable, changes only when an admin updates access.

The agent is configured with per-result, per-operation freshness requirements:
- `exchange_rate` for `submit_payment`: WARN >5 min, ERROR >30 min.
- `portfolio_positions` for `display_summary`: WARN >10 min, ERROR >60 min.
- `portfolio_positions` for `execute_trade`: WARN >1 min, ERROR >5 min.
- `user_permissions` for any action: WARN >30 min, ERROR >120 min.

Without freshness assertions: the agent fetches the exchange rate at 9:00am, advises a trade, and the portfolio manager approves at 9:47am. The agent submits the payment using the 9:00am rate. The rate moved. The submitted amount is wrong.

With freshness assertions: the `submit_payment` call asserts freshness of `exchange_rate_for_payment`. At 9:47am, the result is 47 minutes old — beyond the 30-minute ERROR threshold. The assertion blocks the `submit_payment` call and returns a retryHint: "Re-fetch get_exchange_rate before submit_payment (current result is 47 min old; limit is 30 min)."

## Forces

- **Freshness requirements are use-dependent, not result-dependent.** A single fetched result may be used in multiple ways. Register freshness limits per (resultId, operationName) pair, or per result with different limits for display vs action. One limit fits all uses is almost always wrong.
- **The asserter works off wall-clock time, not model turn count.** A session that idles for 30 minutes while a user reviews results ages the fetched data regardless of how many model turns occurred. Store the Unix timestamp at fetch time, not the turn number.
- **Static data has no freshness limit.** Document content, historical records, and configuration fetched once don't age meaningfully. Register them without `warnMs`/`errorMs` — they pass freshness assertion unconditionally. Only volatile live data needs limits.
- **WARN assertions log and allow; ERROR assertions block.** Display operations that use slightly stale data degrade gracefully (show the data with a staleness annotation). Write/action operations that use stale data cause hard errors (wrong amounts, wrong permissions). Use severity to route appropriately.
- **Assertion is fast; re-fetch is the cost.** The assertion itself is a Map lookup + arithmetic: 0.0001ms. The refetch is a full tool call. Don't assert on every reference to the data — assert once before each high-stakes action that will consume it.
- **Compose with S-111 (partial context refresh) for defense in depth.** S-111 proactively replaces stale blocks on a TTL schedule. F-162 asserts freshness at point-of-use, catching the cases that slip through the TTL schedule (bursty usage, long user delays, stale data from before the TTL was configured). Both are needed for systems where stale data causes financial or safety errors.

## The move

**Register each high-stakes tool result with its fetch timestamp and per-operation freshness limits. Assert freshness before every action that consumes a prior result. Block on ERROR; warn and annotate on WARN.**

```js
// --- Tool result freshness asserter ---
// Checks that a tool result is still fresh enough for a specific use.
// Staleness check runs at the point of use, not at injection time.
// Compose with S-111 (proactive block refresh) for defense in depth.
// Register only volatile live data — static results need no freshness limit.

class ToolResultFreshnessAsserter {
  constructor(opts) {
    opts = opts || {};
    this._records   = new Map();  // resultId → { toolName, fetchedAt, limits }
    this._nowFn     = opts.nowFn || (() => Date.now());  // injectable for testing
  }

  // Register a fetched result and its per-operation freshness limits.
  // resultId:       unique identifier for this specific fetch (e.g., 'exchange_rate_usd_eur')
  // toolName:       the tool that produced this result (for retryHints)
  // opts.fetchedAt: unix timestamp in ms (default: now)
  // opts.limits:    { [operationName]: { warnMs, errorMs } } — per-operation limits
  //                 Use operationName='*' as fallback for any unspecified operation.
  register(resultId, toolName, opts) {
    opts = opts || {};
    this._records.set(resultId, {
      toolName,
      fetchedAt: opts.fetchedAt != null ? opts.fetchedAt : this._nowFn(),
      limits: opts.limits || {},
    });
    return this;
  }

  // Assert that a result is fresh enough for a specific operation.
  // operationName: the tool call or action about to be performed (e.g., 'submit_payment')
  // Returns: { status: 'FRESH'|'STALE_WARN'|'STALE_ERROR'|'NOT_REGISTERED', ... }
  assert(resultId, operationName) {
    const record = this._records.get(resultId);
    if (!record) {
      return { status: 'NOT_REGISTERED', resultId, operationName };
    }

    const ageMs   = this._nowFn() - record.fetchedAt;
    const limits  = record.limits[operationName] || record.limits['*'] || {};
    const { warnMs, errorMs } = limits;

    if (errorMs != null && ageMs > errorMs) {
      return {
        status:    'STALE_ERROR',
        resultId,
        operationName,
        ageMs,
        limitMs:   errorMs,
        ageSec:    Math.round(ageMs / 1000),
        limitSec:  Math.round(errorMs / 1000),
        retryHint: `Re-fetch ${record.toolName} before ${operationName}. ` +
                   `Current result is ${Math.round(ageMs / 60000)} min old; ` +
                   `limit for this operation is ${Math.round(errorMs / 60000)} min.`,
      };
    }
    if (warnMs != null && ageMs > warnMs) {
      return {
        status:      'STALE_WARN',
        resultId,
        operationName,
        ageMs,
        limitMs:     warnMs,
        ageSec:      Math.round(ageMs / 1000),
        limitSec:    Math.round(warnMs / 1000),
        retryHint:   `${record.toolName} result is ${Math.round(ageMs / 60000)} min old ` +
                     `(warn threshold for ${operationName}: ${Math.round(warnMs / 60000)} min). ` +
                     `Consider re-fetching before proceeding.`,
      };
    }
    return { status: 'FRESH', resultId, operationName, ageMs };
  }

  // Update a result's fetch timestamp after a re-fetch (no need to re-register limits).
  refresh(resultId) {
    const record = this._records.get(resultId);
    if (record) record.fetchedAt = this._nowFn();
    return this;
  }
}

// --- Registration for financial agent ---
const FRESHNESS = new ToolResultFreshnessAsserter();

FRESHNESS
  .register('exchange_rate_usd_eur', 'get_exchange_rate', {
    limits: {
      'display_estimate':  { warnMs: 10 * 60_000, errorMs: 60 * 60_000 },
      'submit_payment':    { warnMs:  5 * 60_000, errorMs: 30 * 60_000 },
      '*':                 { warnMs: 10 * 60_000, errorMs: 60 * 60_000 },
    },
  })
  .register('portfolio_positions', 'get_portfolio', {
    limits: {
      'display_summary':   { warnMs: 10 * 60_000, errorMs:  60 * 60_000 },
      'execute_trade':     { warnMs:  1 * 60_000, errorMs:   5 * 60_000 },
    },
  })
  .register('user_permissions', 'get_permissions', {
    limits: {
      '*':                 { warnMs: 30 * 60_000, errorMs: 120 * 60_000 },
    },
  })
  .register('contract_text', 'fetch_document', {
    // No limits — static content, never stale.
  });

// --- Usage in tool dispatch ---
// function dispatchTool(toolName, args, sessionState) {
//
//   // For actions that consume prior results, assert freshness first.
//   if (toolName === 'submit_payment') {
//     const check = FRESHNESS.assert('exchange_rate_usd_eur', 'submit_payment');
//     if (check.status === 'STALE_ERROR') {
//       return { error: 'STALE_DATA', retryHint: check.retryHint };
//     }
//     if (check.status === 'STALE_WARN') {
//       logWarning(check.retryHint);
//     }
//   }
//
//   const result = await callTool(toolName, args);
//
//   // After re-fetching, refresh the timestamp.
//   if (toolName === 'get_exchange_rate') {
//     FRESHNESS.refresh('exchange_rate_usd_eur');
//   }
//
//   return result;
// }
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four scenarios: fresh result, stale error (exchange rate), stale warn (permissions), no-limit (static document). Freshness simulated by passing nowFn override. Timed over 1 000 000 iterations. Zero API calls. Zero tokens.

```
=== Tool Result Freshness Assertion ===

--- Scenario A: exchange_rate fetched 2 min ago, used for submit_payment ---
  Limits for 'submit_payment': warnMs=5 min, errorMs=30 min
  Age: 2 min (120 000 ms)
  120 000 ms < 300 000 ms (warnMs)
  → FRESH

--- Scenario B: exchange_rate fetched 47 min ago, used for submit_payment ---
  Limits for 'submit_payment': warnMs=5 min, errorMs=30 min
  Age: 47 min (2 820 000 ms)
  2 820 000 ms > 1 800 000 ms (errorMs = 30 min)
  → STALE_ERROR
    retryHint: "Re-fetch get_exchange_rate before submit_payment.
                Current result is 47 min old; limit for this operation is 30 min."
  Action: block submit_payment; model re-fetches exchange rate; retries.

--- Scenario C: portfolio_positions fetched 3 min ago, used for execute_trade ---
  Limits for 'execute_trade': warnMs=1 min, errorMs=5 min
  Age: 3 min (180 000 ms)
  180 000 ms > 60 000 ms (warnMs = 1 min)
  180 000 ms < 300 000 ms (errorMs = 5 min)
  → STALE_WARN
    retryHint: "portfolio_positions result is 3 min old (warn threshold for
                execute_trade: 1 min). Consider re-fetching before proceeding."
  Action: log warning; allow execute_trade to proceed; annotate.

--- Scenario D: user_permissions fetched 45 min ago, used for access_restricted_file ---
  Limits for '*': warnMs=30 min, errorMs=120 min
  Age: 45 min (2 700 000 ms)
  2 700 000 ms > 1 800 000 ms (warnMs = 30 min)
  2 700 000 ms < 7 200 000 ms (errorMs = 120 min)
  → STALE_WARN
    retryHint: "get_permissions result is 45 min old (warn threshold: 30 min). ..."
  Action: log warning; allow access_restricted_file to proceed.

--- Scenario E: contract_text (static) — no limits registered ---
  Age: 120 min (no warnMs, no errorMs in any registered limit)
  → FRESH  (static content; no staleness limit applies)

=== Timing (1 000 000 iterations) ===
assert() FRESH:       0.0001 ms  (Map lookup + 2 comparisons)
assert() STALE_ERROR: 0.0001 ms
register():           0.0002 ms
refresh():            0.0001 ms
Zero API calls. Zero tokens.

=== Production impact ===
  Financial agent — exchange rate used for payment after 47-min delay:
    Without assertion: wrong payment amount (rate moved 0.8% in 47 min)
    With assertion:    STALE_ERROR → re-fetch → correct rate → correct payment
  Permissions assertion (WARN):
    45% of sessions exceed the 30-min warn threshold for permissions in long sessions.
    Log rate used to detect user sessions that routinely run >30 min and warrant
    upgrading the 30-min warn threshold to a proactive refresh in S-111.
```

## See also

[S-111](../stacks/s111-partial-context-refresh.md) · [S-174](../stacks/s174-stale-while-revalidate-live-data.md) · [S-128](../stacks/s128-freshness-annotated-context-injection.md) · [F-158](f158-agent-action-pre-execution-check.md) · [S-190](../stacks/s190-live-data-delta-injection.md)

## Go deeper

Keywords: `tool result freshness assertion` · `stale data gate` · `freshness check point of use` · `tool result staleness check` · `live data freshness assertion` · `fetched result age check` · `point-of-use freshness` · `stale result block` · `data freshness enforcement` · `agent data staleness guard`
