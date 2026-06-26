# S-84 · Tool Return Value Design

[S-51](s51-tool-schema-design.md) covers the input side of a tool: how to name it, how to describe parameters, when to use enums. [S-62](s62-tool-error-messages.md) covers the failure side: structured error results with recovery hints. Neither covers what a *successful* tool result should look like — what fields to include, how to format data for model readability, how much to return, and what makes the model more likely to use the result correctly.

## Situation

An agent calls `get_customer_orders` with `customer_id: "cust-7821"`. The tool returns a raw database row: `{ "id": 7821, "cid": "cust-7821", "status_cd": 3, "ord_dt": "2024-11-28T14:22:00Z", "tot": 248.99, "ln_items": [{"pid": "P88", "qty": 2, "prc": 124.495}] }`. The model must know that `status_cd: 3` means "shipped," that `tot` is the total price in USD, and that `pid: "P88"` is a product identifier it would need to look up separately. Every field requires translation. The model guesses some correctly, hallucinates others. A tool return designed for model readability — human-readable field names, expanded status string, price as a formatted value — costs 30 extra tokens and eliminates the translation step entirely.

## Forces

- **The model reads tool results as natural language.** A database column name like `ord_dt` or an enum integer like `status_cd: 3` are opaque to the model in the same way they are to a new developer. Use human-readable field names and expanded values. The model has no code to run on the result — it can only read.
- **Include the right amount of data.** Too little: the model asks a follow-up tool call to get what it needed. Too much: the model buries the key fact in noise, misses it, or exceeds context. Aim for the minimum that lets the model complete the task without another tool call. Include counts (total matches, pages remaining) so the model knows whether it has the full picture.
- **Consistent field names across related tools.** If `get_order` returns `customer_id` and `list_orders` returns `cust_id`, the model must hold both names in working memory and is prone to using the wrong one in subsequent calls. Standardize: same entity, same field name, always.
- **Numeric IDs alone are useless; include the readable label.** Return `{ "status": "shipped", "status_code": 3 }` not just `{ "status_code": 3 }`. The model uses the string; the code uses the integer. Both fields cost 10 tokens and prevent a lookup.
- **Pagination metadata prevents silent truncation.** If a tool returns 10 of 47 orders, include `{ "total": 47, "returned": 10, "has_more": true }`. Without this, the model thinks it has all 47 and makes decisions on incomplete data.

## The move

**Return human-readable field names and expanded values. Include metadata (count, pagination). Truncate large lists with an explicit count. Standardize field names across related tools.**

**Before (raw DB row — opaque to the model):**

```js
// Tool returns raw database fields
async function getCustomerOrders_bad(customerId) {
  const rows = await db.query(
    'SELECT id, cid, status_cd, ord_dt, tot, ln_items FROM orders WHERE cid = $1 LIMIT 10',
    [customerId]
  );
  return rows;  // raw: [{id, cid, status_cd, ord_dt, tot, ln_items}]
}
```

**After (model-readable return):**

```js
const STATUS_MAP = { 1: 'pending', 2: 'processing', 3: 'shipped', 4: 'delivered', 5: 'cancelled' };

async function getCustomerOrders(customerId, opts = {}) {
  const limit = opts.limit ?? 10;
  const rows  = await db.query(
    'SELECT id, cid, status_cd, ord_dt, tot, ln_items, COUNT(*) OVER() AS total_count FROM orders WHERE cid = $1 ORDER BY ord_dt DESC LIMIT $2',
    [customerId, limit]
  );

  if (!rows.length) {
    return { customer_id: customerId, orders: [], total: 0, has_more: false };
  }

  const total = parseInt(rows[0].total_count, 10);

  return {
    customer_id: customerId,
    orders: rows.map(r => ({
      order_id:     r.id,
      status:       STATUS_MAP[r.status_cd] ?? 'unknown',   // human-readable
      status_code:  r.status_cd,                             // keep code for programmatic use
      ordered_at:   r.ord_dt,                                // ISO 8601 — model can read this
      total_usd:    parseFloat(r.tot).toFixed(2),            // explicit currency unit in field name
      item_count:   r.ln_items?.length ?? 0,                 // count, not raw array
    })),
    total,
    returned: rows.length,
    has_more: total > rows.length,
  };
}
```

**Truncation for large nested data:**

```js
// Return summary metadata instead of full nested arrays
// Model can request details with a follow-up tool call if needed
async function getOrderDetails(orderId) {
  const order  = await db.getOrder(orderId);
  const items  = await db.getLineItems(orderId);

  return {
    order_id:       order.id,
    status:         STATUS_MAP[order.status_cd],
    total_usd:      parseFloat(order.tot).toFixed(2),
    ordered_at:     order.ord_dt,
    shipping_to:    order.shipping_address_summary,  // "Jane Doe, 123 Main St, Seattle WA"
    item_count:     items.length,
    items_preview:  items.slice(0, 3).map(i => ({    // first 3 items only
      product_name: i.product_name,                  // readable name, not pid
      quantity:     i.qty,
      unit_price_usd: parseFloat(i.prc).toFixed(2),
    })),
    items_truncated: items.length > 3,               // model knows there are more
    // Do NOT return: full items array for 50-item orders; raw pricing decimals; internal FK ids
  };
}
```

**Standard field name conventions across tools:**

```js
// Enforce shared conventions so the model doesn't have to learn per-tool naming
const FIELD_CONVENTIONS = {
  // Entity IDs — always suffixed with _id
  customer_id:  'string',   // "cust-7821"
  order_id:     'number',   // 99823
  product_id:   'string',   // "prod-P88"

  // Timestamps — always ISO 8601, always suffixed with _at
  created_at:   'ISO 8601',
  updated_at:   'ISO 8601',
  ordered_at:   'ISO 8601',

  // Money — always include currency in field name
  total_usd:    'string',   // "248.99" — formatted, not raw float
  price_usd:    'string',   // "124.50"

  // Status — always include both human and code
  status:       'string',   // "shipped"
  status_code:  'number',   // 3

  // Pagination — always these exact names
  total:        'number',   // total records matching query
  returned:     'number',   // records in this response
  has_more:     'boolean',  // true if total > returned
};
```

**What not to return:**

| Field type | Problem | Fix |
|---|---|---|
| Raw database column names (`ord_dt`, `cid`) | Model can't infer meaning | Expand: `ordered_at`, `customer_id` |
| Enum integers without labels (`status_cd: 3`) | Model guesses or hallucinates | Include label: `status: "shipped"` |
| Full nested arrays (50 line items) | Model buries key facts; large context | Truncate with count; offer detail tool |
| Raw float prices (`124.4950001`) | Model formats inconsistently | Round and label: `price_usd: "124.50"` |
| Internal FK ids without context (`pid: "P88"`) | Model can't use without lookup | Include name: `product_name: "Widget Pro"` |
| Empty response with no count | Model doesn't know if 0 or page limit | Always include `total: 0` |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Token counts measured on sample order records with gpt-tokenizer.

```
=== Token cost: raw vs model-readable ===

Raw DB response (1 order, 2 line items):
  {"id":7821,"cid":"cust-7821","status_cd":3,"ord_dt":"2024-11-28T14:22:00Z","tot":248.99,"ln_items":[{"pid":"P88","qty":2,"prc":124.495},{"pid":"P91","qty":1,"prc":0}]}
  Tokens: 68 tok

Model-readable (same order, truncated items, pagination):
  {"customer_id":"cust-7821","orders":[{"order_id":7821,"status":"shipped","status_code":3,"ordered_at":"2024-11-28T14:22:00Z","total_usd":"248.99","item_count":2}],"total":1,"returned":1,"has_more":false}
  Tokens: 76 tok

Delta: +8 tok  (12% more)
Value: model can read status directly; knows it has all orders; no guessing

At 10 000 tool calls/day: +8 tok × $0.80/M = $0.064/day — negligible
vs. cost of one wrong tool call requiring retry: 200 tok × $0.80/M = $0.00016/call
```

## See also

[S-51](s51-tool-schema-design.md) · [S-62](s62-tool-error-messages.md) · [S-03](s03-tool-use.md) · [F-16](../forward-deployed/f16-tool-call-validation.md) · [S-04](s04-structured-output.md) · [S-55](s55-parallel-tool-calls.md)

## Go deeper

Keywords: `tool return value` · `tool result design` · `tool output schema` · `model-readable` · `tool response format` · `pagination metadata` · `field naming` · `tool result format` · `function calling return` · `is_error tool_result`
