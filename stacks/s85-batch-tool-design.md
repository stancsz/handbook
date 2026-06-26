# S-85 · Batch Tool Design

[S-55](s55-parallel-tool-calls.md) shows how to execute multiple tool calls in parallel — the model issues three `tool_use` blocks in one response, you run them concurrently, and return all results together. [S-51](s51-tool-schema-design.md) covers single-operation tool schemas. Neither covers when to design the tool itself to accept a batch input: `get_orders(ids: [1, 2, 3])` vs three calls to `get_order(id: 1)`, `get_order(id: 2)`, `get_order(id: 3)`.

## Situation

An agent retrieves order details for 12 items in a customer's cart. With single-operation tools and S-55 parallelism, the model issues 12 `tool_use` blocks, you fire 12 concurrent requests to your orders database, and get 12 results. This works — until the database rate-limits at 10 concurrent connections. Now you're serializing in groups of 10, and 2 calls fail intermittently. Alternatively, you expose `get_orders(ids: [string[]], max 50)`: the model issues one `tool_use` block, you make one batch query (`WHERE id IN (?)`), and return all 12 records in one tool result. No rate limit issue. One error handles the whole set. The trade-off: if one of the 12 IDs is invalid, you have to decide whether to fail the batch or return partial results.

## Forces

- **Batch tools are better when downstream APIs support bulk queries.** A SQL `WHERE id IN (?)` with 50 IDs is faster than 50 single-row queries. An external API that has a `/orders/batch` endpoint is faster than 50 `/orders/{id}` calls. When the downstream has a native bulk operation, model it with a batch tool — don't lose the efficiency by pretending each item needs a separate call.
- **Parallel single-call tools are better when error isolation matters.** If item 3 of 12 fails in a batch tool, the whole result is tainted unless you implement partial success. With parallel single calls, item 3 fails with an `is_error` result, items 1-2 and 4-12 succeed, and the model sees each result independently and decides how to proceed. Error isolation is free with parallel calls; it requires design with batch tools.
- **Rate limits are the strongest argument for batch tools.** Parallel tool calls (S-55) bound fan-out to 3-5 simultaneous requests. For N=50, that's still 10 rounds of 5 calls each. A batch tool reduces N=50 to 1 call with no rate limit concern.
- **Batch tools must bound their input size.** A parameter `ids: string[]` without an upper bound lets the model request 5,000 orders in one call. Set a `max_items` in the description and enforce it in the implementation. Return pagination metadata when the request is truncated.
- **Atomic operations must be batch tools.** Some operations require all-or-nothing semantics: "update these 5 records in a transaction" cannot be split into 5 separate tool calls without losing the atomicity guarantee. Design atomic operations as a single batch tool and document the atomicity in the tool description.

## The move

**Build batch tools when the downstream supports bulk queries, when rate limits make parallel single calls impractical, or when atomicity requires all items in one transaction. Return partial success with per-item status rather than failing the whole batch on one error.**

**Single-operation tool (baseline):**

```js
// Model must issue N tool_use blocks to fetch N orders
const getOrderTool = {
  name:        'get_order',
  description: 'Retrieve a single order by ID. Returns order details or an error if not found.',
  input_schema: {
    type:       'object',
    properties: { order_id: { type: 'string', description: 'The order ID to retrieve.' } },
    required:   ['order_id'],
  },
  execute: async ({ order_id }) => db.getOrder(order_id),
};
```

**Batch tool (preferred when N > 3 and downstream supports bulk):**

```js
const getOrdersBatchTool = {
  name:        'get_orders_batch',
  description: 'Retrieve up to 50 orders by their IDs in one call. More efficient than multiple get_order calls. Returns an array of results; each result includes either the order data or an error for that specific ID.',
  input_schema: {
    type:       'object',
    properties: {
      order_ids: {
        type:        'array',
        items:       { type: 'string' },
        maxItems:    50,
        description: 'List of order IDs to retrieve. Maximum 50 per call. Use multiple calls for larger sets.',
      },
    },
    required: ['order_ids'],
  },
  execute: async ({ order_ids }) => {
    if (order_ids.length > 50) {
      return { error: 'Too many IDs. Maximum 50 per call.', received: order_ids.length };
    }

    // One bulk query — WHERE id IN (?)
    const found = await db.getOrdersBulk(order_ids);
    const foundMap = new Map(found.map(o => [o.id, o]));

    // Per-item partial success — don't fail the batch for one bad ID
    return {
      results: order_ids.map(id => {
        const order = foundMap.get(id);
        return order
          ? { id, status: 'found', order: formatOrder(order) }
          : { id, status: 'not_found', error: `Order '${id}' does not exist.` };
      }),
      total_requested: order_ids.length,
      total_found:     found.length,
    };
  },
};

function formatOrder(row) {
  return {
    order_id:   row.id,
    status:     STATUS_MAP[row.status_cd],
    total_usd:  parseFloat(row.tot).toFixed(2),
    ordered_at: row.ord_dt,
  };
}
```

**Atomic batch (all-or-nothing — use when atomicity required):**

```js
const updateOrderStatusBatchTool = {
  name:        'update_order_statuses',
  description: 'Update the status of multiple orders in a single atomic transaction. All updates succeed or all fail — no partial updates. Use when the status changes must be consistent.',
  input_schema: {
    type:       'object',
    properties: {
      updates: {
        type:  'array',
        items: {
          type:       'object',
          properties: {
            order_id:   { type: 'string' },
            new_status: { type: 'string', enum: ['processing', 'shipped', 'cancelled'] },
          },
          required: ['order_id', 'new_status'],
        },
        maxItems: 20,
        description: 'List of order ID + new status pairs. Applied atomically — if any update fails, none are applied.',
      },
    },
    required: ['updates'],
  },
  execute: async ({ updates }) => {
    try {
      await db.transaction(async (trx) => {
        for (const { order_id, new_status } of updates) {
          await trx.updateOrderStatus(order_id, new_status);
        }
      });
      return { success: true, updated: updates.length };
    } catch (err) {
      return { success: false, error: err.message, updates_applied: 0 };
    }
  },
};
```

**Decision table:**

| Scenario | Use batch tool | Use parallel single calls |
|---|---|---|
| Downstream has bulk API (SQL IN, batch endpoint) | Yes | No |
| Rate limits make fan-out risky (>5 concurrent) | Yes | No |
| Atomic all-or-nothing required | Yes | No |
| Per-item error isolation needed | No | Yes |
| N ≤ 3 items, no rate limit risk | No | Yes (simpler) |
| Model needs to react differently per item | No | Yes |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Token counts on 12-order retrieval scenarios.

```
=== Token cost: 12 parallel single calls vs 1 batch call ===

Parallel single calls (12 × get_order):
  12 tool_use blocks in one response: ~30 tok each × 12 = 360 tok model output
  12 tool_result blocks returned: ~80 tok each × 12 = 960 tok model input
  Total tool round-trip: 1 320 tok

1 batch call (get_orders_batch, 12 IDs):
  1 tool_use block: ~45 tok model output (12 IDs in array)
  1 tool_result: ~400 tok model input (12 order records)
  Total tool round-trip: 445 tok

Savings: 875 tok (66% fewer tokens for 12-item retrieval)
At Haiku ($0.80/M in + $4.00/M out): $0.000356 + $0.001440 = $0.00180 (parallel)
                                       $0.000320 + $0.000180 = $0.000500 (batch)
Savings per 12-item retrieval: $0.00130

At 1 000 agent tasks/day with 12 items each: $1.30/day savings
Plus: 0 rate limit errors vs ~5 throttles/day with parallel
```

## See also

[S-55](s55-parallel-tool-calls.md) · [S-51](s51-tool-schema-design.md) · [S-84](s84-tool-return-value-design.md) · [S-62](s62-tool-error-messages.md) · [F-20](../forward-deployed/f20-rate-limits-and-retry.md) · [S-03](s03-tool-use.md)

## Go deeper

Keywords: `batch tool` · `bulk tool` · `batch API design` · `tool batching` · `parallel tool calls` · `atomic tool` · `partial success` · `rate limit tool` · `tool fan-out` · `batch query`
