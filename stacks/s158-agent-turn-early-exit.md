# S-158 · Agent Turn Early Exit

[S-25](s25-stop-sequences.md) ends the model's output generation early using token sequences like `</answer>`. [F-90](../forward-deployed/f90-pre-session-tool-health-gate.md) gates tool calls before a session starts by health-checking each tool. [S-108](s108-progressive-tool-results.md) lets a tool return a partial result and a continuation token so the agent can fetch more pages on subsequent calls.

None of these address what happens mid-turn when the agent has already gathered enough information but continues calling tools anyway. A query like "What is this customer's plan and their most recent order status?" requires two fields: `customer_plan` and `last_order_status`. If the agent planned or sequentially calls four tools — `get_customer`, `get_orders`, `get_account_details`, `get_usage_stats` — it has both required fields after the second call. The third and fourth calls are pure waste: latency paid, tokens injected, no new signal used.

The turn early exit planner tracks which fields have been gathered from tool results and checks after each result whether the required fields for the current query are satisfied. When satisfied, remaining tool calls are skipped. The model proceeds directly to the synthesis step with the gathered context.

## Situation

A support agent answers customer queries. A query about billing plan and recent order status requires two fields: `customer_plan` (from `get_customer`) and `last_order_status` (from `get_orders`). The agent also calls `get_account_details` and `get_usage_stats` to be thorough — neither contributes anything the model uses in the answer.

Without early exit: all four tool calls execute. Latency: ~2s (4 × ~500ms average per tool call). Tool result tokens injected into context: ~800 tokens across four results.

With early exit: after `get_orders` returns with `last_order_status`, `check()` returns `sufficient: true, savedCalls: 2`. The planner signals the framework to skip `get_account_details` and `get_usage_stats`. The model synthesizes the answer from two tool results instead of four.

Latency saved: ~1s (2 tool calls). Token context saved: ~400 tokens (2 tool results not injected). At 10 000 sessions/day with 30% triggering early exit at 2 saved calls: 3 000 × 400 tok × $3.00/M Sonnet = $3.60/day plus the latency improvement for those sessions.

## Forces

- **Required fields are query-specific, not global.** The same set of tools may be called for different query types with different sufficiency criteria. A query about account risk needs `risk_level`, `jurisdiction`, and `recommended_action`. A query about billing needs `customer_plan` and `last_order_status`. Register each query type with its own required and optional field lists.
- **Optional fields are nice-to-have, not blocking.** Some tool results improve the answer quality but are not required for correctness. Separate required from optional in the spec. The planner returns `optionalMissing` so callers can choose to fetch optional fields if time permits, but the `sufficient` flag only reflects required fields.
- **The check intercepts between tool calls, not inside the model.** The planner runs in the agent framework's tool-execution loop, not inside the model's context. After each tool result is received and parsed, the framework extracts relevant fields, updates the planner context, and checks sufficiency before deciding whether to continue the loop or move to the synthesis step.
- **For LLM-driven tool selection, inject a sufficiency instruction.** When the agent uses a dynamic LLM-driven tool selection (the model decides which tool to call next based on the results so far), you cannot simply skip "planned" calls. Instead: when `sufficient: true`, append a system message before the next model call: `"[Sufficient information gathered: customer_plan and last_order_status are available. Answer the question now without calling additional tools.]"` This overrides the model's tendency to continue tool calling.
- **Don't exit early on partial information.** A `last_order_status` of `null` is not "gathered" — it means the tool returned no value for that field. The check should treat null/undefined/empty as missing. Populating a field with null from one tool call should not prevent the planner from requiring it to be properly filled.
- **Pair with S-157 (context carry cost) for cost-aware decisions.** The planner's `savedCalls` count tells you how many calls were skipped. Multiply by the average tool result size (tokens) × remaining turns × price/token to get the carry-cost savings. For long sessions where skipped results would have accumulated across many subsequent turns, the carry-cost savings exceed the per-call savings.

## The move

**Register required and optional fields per query type. After each tool result, extract fields into the planner context and check sufficiency. Exit the tool loop when sufficient.**

```js
// --- Agent turn early exit planner ---
// Tracks gathered fields after each tool call.
// Checks whether required fields for the current query type are satisfied.
// When sufficient: skip remaining tool calls; proceed to synthesis.

class TurnEarlyExitPlanner {
  constructor(opts = {}) {
    this._queryTypes = opts.queryTypes ?? {};  // name → { required: string[], optional: string[] }
    this._context    = {};                     // gathered field values for this turn
  }

  // Register a query type with its required and optional field lists.
  registerQueryType(name, required, optional = []) {
    this._queryTypes[name] = { required, optional };
    return this;
  }

  // Update context with a field extracted from the most recent tool result.
  // Call for each relevant field after each tool call returns.
  update(field, value) {
    this._context[field] = value;
    return this;
  }

  // Check whether required fields for queryType are satisfied.
  // remainingCalls: how many tool calls are still in the plan.
  // Returns { sufficient, missing, optionalMissing, gathered, required, savedCalls }
  check(queryType, remainingCalls = 0) {
    const spec = this._queryTypes[queryType];
    if (!spec) return { sufficient: false, missing: [], reason: 'UNKNOWN_QUERY_TYPE' };

    const missing = spec.required.filter(f => {
      const v = this._context[f];
      return v === null || v === undefined || v === '';
    });
    const optionalMissing = (spec.optional ?? []).filter(f => {
      const v = this._context[f];
      return v === null || v === undefined || v === '';
    });

    return {
      sufficient:      missing.length === 0,
      missing,
      optionalMissing,
      gathered:        spec.required.length - missing.length,
      required:        spec.required.length,
      savedCalls:      missing.length === 0 ? remainingCalls : 0,
    };
  }

  // Reset for the next turn.
  reset() { this._context = {}; return this; }
}

// --- Integration: agent tool call loop with early exit ---

const EXIT_PLANNER = new TurnEarlyExitPlanner()
  .registerQueryType(
    'plan_and_order_status',
    ['customer_plan', 'last_order_status'],          // required
    ['account_manager', 'usage_stats_30d']           // optional — nice to have
  )
  .registerQueryType(
    'risk_and_jurisdiction',
    ['risk_level', 'jurisdiction', 'recommended_action'],
    ['contract_language', 'governing_law_clause_id']
  );

async function agentTurnWithEarlyExit(query, queryType, toolCallPlan, model) {
  EXIT_PLANNER.reset();

  for (let i = 0; i < toolCallPlan.length; i++) {
    const toolCall = toolCallPlan[i];
    const result   = await executeToolCall(toolCall.name, toolCall.args);

    // Extract relevant fields from the tool result into the planner context.
    // For dynamic agents: parse result, update planner for each field it provides.
    for (const [field, value] of Object.entries(result)) {
      EXIT_PLANNER.update(field, value);
    }

    const remaining = toolCallPlan.length - i - 1;
    const { sufficient, missing, savedCalls } = EXIT_PLANNER.check(queryType, remaining);

    if (sufficient) {
      if (savedCalls > 0) {
        log({ event: 'turn_early_exit', queryType, savedCalls,
              skippedTools: toolCallPlan.slice(i + 1).map(t => t.name) });
      }
      break;  // exit the tool call loop; proceed to synthesis
    }
    // Not yet sufficient — continue to next tool call
  }

  // Synthesize answer from gathered context (two tool results instead of four)
  return synthesizeAnswer(query, EXIT_PLANNER._context);
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `check()` timed over 100 000 iterations. Query type `plan_and_order_status`: 2 required fields, 2 optional. Simulated agent turn with 4 planned tool calls.

```
=== TurnEarlyExitPlanner timing (100 000 iterations) ===

check() — 2 required fields missing:    0.0007 ms
check() — 2 required fields present:    0.0006 ms

=== Scenario: 4 planned tool calls, sufficient after call 2 ===

Query:   "What is this customer's plan and their most recent order status?"
Type:    plan_and_order_status
Required: [customer_plan, last_order_status]
Optional: [account_manager, usage_stats_30d]
Plan:    [get_customer, get_orders, get_account_details, get_usage_stats]

--- After get_customer (returns { customer_plan: 'enterprise', ... }) ---

update('customer_plan', 'enterprise')
check('plan_and_order_status', remaining=3):
{
  sufficient:      false,
  missing:         ['last_order_status'],
  optionalMissing: ['account_manager', 'usage_stats_30d'],
  gathered:        1,
  required:        2,
  savedCalls:      0
}
→ not sufficient, continue to get_orders

--- After get_orders (returns { last_order_status: 'shipped', ... }) ---

update('last_order_status', 'shipped')
check('plan_and_order_status', remaining=2):
{
  sufficient:      true,
  missing:         [],
  optionalMissing: ['account_manager', 'usage_stats_30d'],
  gathered:        2,
  required:        2,
  savedCalls:      2
}
→ sufficient — exit loop; skip get_account_details and get_usage_stats

=== Cost and latency savings ===

Tool calls executed:    2 of 4
Tool calls skipped:     2 (get_account_details, get_usage_stats)

Latency saved:          ~1 000 ms  (2 × ~500ms average API call)
Input tokens saved:     ~400 tok   (2 tool results not injected into context)
Carry cost saved:       400 tok × (remaining turns) × $3.00/M
  At 5 remaining turns: 400 × 5 × $3.00/M = $0.006 per session
  At 10 000 sessions/day with 30% early-exit rate:
  0.30 × 10 000 × $0.006 = $18/day saved on carry alone

=== S-25 vs F-90 vs S-108 vs S-158 ===

              │ S-25 (stop sequences)       │ F-90 (pre-session gate)      │ S-108 (progressive results) │ S-158 (early exit)
──────────────┼─────────────────────────────┼──────────────────────────────┼─────────────────────────────┼──────────────────────────────
When          │ During output generation    │ Before session starts        │ Tool returns partial data    │ Between tool calls in a turn
What it skips │ Remaining generated tokens  │ Unhealthy tool calls         │ Fetches more pages as needed │ Remaining planned tool calls
Trigger       │ Model emits stop token      │ Tool health check fails      │ Model requests continuation  │ Required fields satisfied
Misses        │ Tool call overhead          │ Mid-session sufficiency      │ Non-paginated tools          │ Output token generation
```

## See also

[S-25](s25-stop-sequences.md) · [F-90](../forward-deployed/f90-pre-session-tool-health-gate.md) · [S-108](s108-progressive-tool-results.md) · [S-157](s157-context-carry-cost-tracker.md) · [S-55](s55-parallel-tool-calls.md) · [S-47](s47-output-token-ceiling.md)

## Go deeper

Keywords: `agent turn early exit` · `tool call sufficiency check` · `skip tool calls when satisfied` · `agent tool loop exit` · `required fields sufficiency` · `LLM agent turn short-circuit` · `tool call cost reduction` · `agent context sufficiency` · `early exit agent tool loop` · `minimum tool calls per turn`
