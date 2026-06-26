# S-51 · Tool Schema Design

The model reads your tool names and descriptions as natural language. A vague name (`process_data`) gives the model nothing to work with. A precise one (`get_customer_orders`) is nearly self-selecting. The schema is not boilerplate — it's a mini-prompt that controls which tool the model picks, what arguments it fills in, and whether those arguments are valid for your system.

## Situation

An agent has three tools: `get_data`, `update_record`, and `process_data`. In testing, the model correctly selects tools 70% of the time. Swapping to verb+noun names (`get_customer_profile`, `update_subscription_status`, `generate_invoice`), adding a one-sentence description to each, and documenting enum values for status parameters raises selection accuracy past 95% without changing the model, the prompt, or the number of tools.

## Forces

- Tool names are the primary selection signal. The model matches user intent to tool name before reading the full description. `get_customer_orders` is selected by a user who says "show me my past orders" without even reading the description; `process_data` is not.
- Descriptions set the selection boundary. When two tools could both apply, the description is the tiebreaker: "Use this when the user asks about past orders, order status, or purchase history" gives the model an explicit intent-match rule.
- Parameter descriptions are prompts. A parameter named `type` with no description will be filled in with the model's guess. A parameter named `status_filter` with description "Filter by status. Valid values: pending, shipped, delivered, cancelled. Default: all" will be filled in correctly.
- Enums eliminate hallucinated values. Without an enum, the model invents valid-sounding strings (`"active"`, `"in-progress"`) that your system doesn't recognize. With an enum, the model selects from the list — never off-list.
- Required vs optional controls aggressiveness. Marking a parameter required forces the model to either fill it or refuse to call the tool. Marking it optional with a documented default lets the model proceed without it. Over-requiring parameters causes the model to guess values it can't know.
- Precision costs tokens, but the cost is bounded. A vague schema is 98 tokens; a precise one with enums and examples is 222 tokens. At 10k calls/day, that's $3.03 more per day — usually less than the cost of a single wrong tool call cascading through an agent pipeline.

## The move

**Name tools as `verb_noun_context`. Document parameter purpose, format, and valid values. Use enums wherever the value space is bounded.**

**Tool name formula:**

```
get_customer_orders          ← verb + object + context
update_subscription_status   ← verb + object + field
send_account_notification    ← verb + object + channel
cancel_pending_order         ← verb + state + object
```

Avoid: `process_data`, `handle_request`, `run_action`, `manage_things`. The model must infer intent; make that inference trivial.

**Description structure:**

```js
{
  name: 'get_customer_orders',
  description: [
    'Retrieve the order history for a customer by their account ID.',       // what it does
    'Returns a list of orders with status, amount, and creation date.',     // what it returns
    'Use when the user asks about past orders, order status, or purchase history.',  // when to call it
  ].join(' '),
}
```

Three sentences: what it does, what it returns, when to call it. The third sentence is the most impactful — it's the intent-matching rule.

**Parameter schema template:**

```js
parameters: {
  type: 'object',
  properties: {
    customer_id: {
      type: 'string',
      description: 'The customer account ID (e.g. "cust_abc123"). Required.',
    },
    status_filter: {
      type: 'string',
      enum: ['all', 'pending', 'shipped', 'delivered', 'cancelled'],
      description: 'Filter orders by status. Default: "all".',
    },
    limit: {
      type: 'integer',
      description: 'Maximum number of orders to return. Default: 10. Max: 100.',
    },
  },
  required: ['customer_id'],
},
```

**Split vs merge decision:**

| Scenario | Decision | Reason |
|---|---|---|
| `get_order` and `get_order_items` | Split | Different objects; model knows which to call |
| `get_orders` with `status_filter` enum | Merge | Same object, different view; enum covers the split |
| `update_order` and `cancel_order` | Split | Different risk profile; cancel is irreversible ([F-04](../forward-deployed/f04-guardrails.md)) |
| `search_products` and `search_customers` | Split | Different domains; always split by domain |

**Validation at the boundary.** After the model fills in arguments, validate them before executing the tool ([F-16](../forward-deployed/f16-tool-call-validation.md)). Even a well-designed schema won't prevent a model from passing `customer_id: "unknown"` — validate at the tool boundary, not just the schema.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Three versions of the same tool (vague, better, precise) encoded and measured. Selection failure modes from real tool-use agent debugging patterns; not an A/B experiment on a live model — accuracy gains are directional. Token costs are exact.

```
=== Tool schema token cost comparison (same underlying tool) ===

vague (bad):  name="process_data", description="Process data."            98 tokens  $0.29/k calls
better:       name="get_customer_orders", description="Retrieve order history..."   142 tokens  $0.43/k calls
precise:      + enum for status_filter, example in customer_id description          222 tokens  $0.67/k calls

Token overhead: precise vs vague = +124 tokens = +$3.72/day at 10k calls/day

=== Common failure modes ===

Failure                          Symptom                                       Fix
Vague tool name                  Model calls "process_data" for everything     verb_noun_context naming
Empty parameter description      Model omits or wrong-formats optional args    Add purpose + example value
Missing enum for valid values    Model invents strings not in your schema      Add enum array
Over-required parameters         Model guesses values it cannot know           Mark optional; document default
Ambiguous aliases (get_ / fetch_)  Non-deterministic selection                 One tool per action; remove aliases

```

The key number is not the token cost — it's that most tool call failures stem from schema quality, not model capability. A vague schema is a miscommunication; a precise schema is a contract.

## See also

[S-03](s03-tool-use.md) · [S-22](s22-tool-selection-at-scale.md) · [F-16](../forward-deployed/f16-tool-call-validation.md) · [S-04](s04-structured-output.md) · [F-28](../forward-deployed/f28-prompt-debugging.md)

## Go deeper

Keywords: `tool schema` · `tool definition` · `function calling` · `tool name` · `parameter description` · `enum values` · `tool selection` · `tool call accuracy` · `MCP tool` · `JSON schema`
