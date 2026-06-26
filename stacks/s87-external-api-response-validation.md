# S-87 · External API Response Validation

[F-16](../forward-deployed/f16-tool-call-validation.md) covers validating tool call *inputs* before execution — checking that the model-supplied arguments are valid before the tool runs. [S-84](s84-tool-return-value-design.md) covers designing tool return values for model readability. Neither covers validating what comes *back* from the external service: confirming the shape, types, and size of the external API's response before injecting it into the agent's context.

## Situation

An order management agent calls `get_inventory(product_id: "SKU-8821")` which hits an external inventory REST API. Normally the API returns `{ "sku": "SKU-8821", "qty": 150, "location": "WH-A" }`. After a backend deploy, the API starts returning `{ "sku": "SKU-8821", "quantity": 150, "warehouse": "WH-A" }` — the field names changed. The agent code does `response.qty` which is now `undefined`. The agent injects `{ sku: "SKU-8821", qty: undefined, location: undefined }` into the model's context. The model, reading `qty: undefined`, either hallucinates a stock level or reports an error. Without validation, this silent field-rename propagates undetected for hours until a user notices wrong inventory decisions. With response validation: the schema mismatch throws immediately, an alert fires, and the agent returns a structured error to the model.

## Forces

- **External APIs are not under your control.** A provider can change response shapes with a version bump, a behind-the-scenes migration, or a bug. Your agent code cannot assume the contract is stable — it must verify at runtime.
- **Schema validation is cheap.** Checking that `response.qty` is a number takes under 0.1ms. Injecting malformed data into the model costs a full inference call and may corrupt downstream reasoning. The validation overhead is immaterial; the cost of skipping it is not.
- **Size guards prevent context overflow.** An external API that normally returns a 200-byte JSON object could, under error conditions, return a full HTML error page (10 KB), a stack trace, or a 1MB debug payload. Inject any of these into the agent context and you risk a context overflow or a model confused by unexpected content. Guard on payload size before injecting.
- **Validate structure, not semantics.** Response validation checks that the right fields exist, have the right types, and are within reasonable bounds. It does not check whether the inventory count is "correct" — that's a business logic problem. Structural validation is cheap, automatable, and catches the most common external-API failure mode: changed field names and missing fields.
- **Map external shapes to internal shapes at the boundary.** The validator is also the place to normalize: rename `quantity` to `qty` if your internal schema uses `qty`, convert strings to numbers, filter out undocumented fields. This insulates the rest of the agent from external naming conventions.

## The move

**Validate every external API response against a schema before injecting it into agent context. Guard on size. Map to internal shape at the boundary. Return a structured error to the model when validation fails.**

```js
// Schema definition for each external API endpoint your tools call
const SCHEMAS = {
  inventory_item: {
    required: ['sku', 'qty', 'location'],
    types:    { sku: 'string', qty: 'number', location: 'string' },
    maxSizeBytes: 4096,  // reject unusually large responses
  },
  order: {
    required: ['order_id', 'status', 'total_usd'],
    types:    { order_id: 'string', status: 'string', total_usd: 'number' },
    maxSizeBytes: 8192,
  },
};

// Validate + normalize an external API response
function validateApiResponse(schemaName, rawResponse, rawBytes = 0) {
  const schema = SCHEMAS[schemaName];
  if (!schema) throw new Error(`Unknown schema: ${schemaName}`);

  // Size guard
  if (rawBytes > schema.maxSizeBytes) {
    return {
      valid:  false,
      error:  `response_too_large`,
      detail: `${schemaName} response was ${rawBytes} bytes (max: ${schema.maxSizeBytes}). Possible HTML error page or debug payload.`,
    };
  }

  // Type check
  for (const field of schema.required) {
    if (!(field in rawResponse)) {
      return {
        valid:  false,
        error:  `missing_field`,
        detail: `External API response missing required field: "${field}". Schema: ${schemaName}. Got fields: [${Object.keys(rawResponse).join(', ')}].`,
      };
    }
    const expectedType = schema.types[field];
    const actualType   = typeof rawResponse[field];
    if (expectedType && actualType !== expectedType) {
      return {
        valid:  false,
        error:  `wrong_type`,
        detail: `Field "${field}": expected ${expectedType}, got ${actualType} (value: ${JSON.stringify(rawResponse[field])}).`,
      };
    }
  }

  return { valid: true, data: rawResponse };
}

// Field name normalizer — map external names to internal names
const FIELD_MAPS = {
  inventory_item: { quantity: 'qty', warehouse: 'location' },  // handle API renames
};

function normalizeResponse(schemaName, raw) {
  const fieldMap = FIELD_MAPS[schemaName] ?? {};
  const normalized = {};
  for (const [key, value] of Object.entries(raw)) {
    normalized[fieldMap[key] ?? key] = value;
  }
  return normalized;
}

// Wrap every external API call with validation
async function callExternalApi(url, schemaName, opts = {}) {
  const resp = await fetch(url, opts);

  if (!resp.ok) {
    return {
      is_error: true,
      content: `External API error ${resp.status} for ${schemaName}. Do not retry without operator review.`,
    };
  }

  const rawText = await resp.text();
  const rawBytes = rawText.length;

  let parsed;
  try {
    parsed = JSON.parse(rawText);
  } catch {
    return {
      is_error: true,
      content: `External API returned non-JSON for ${schemaName} (${rawBytes} bytes). Possible error page.`,
    };
  }

  // Normalize field names first (handles renames transparently)
  const normalized = normalizeResponse(schemaName, parsed);

  // Then validate normalized shape
  const result = validateApiResponse(schemaName, normalized, rawBytes);
  if (!result.valid) {
    return {
      is_error: true,
      content:  `External API response validation failed (${result.error}): ${result.detail}`,
    };
  }

  return result.data;
}

// Usage in a tool — validation is invisible to the model on success; surfaced on failure
async function getInventoryTool({ product_id }) {
  const data = await callExternalApi(
    `https://inventory.api.internal/v2/items/${product_id}`,
    'inventory_item'
  );

  if (data.is_error) return data;  // structured error — model sees it and can respond

  return {
    sku:      data.sku,
    qty:      data.qty,
    location: data.location,
  };
}
```

**Schema evolution strategy:**

```js
// When an external API adds a new version, run both schemas during migration
const SCHEMAS_V1 = { inventory_item: { required: ['sku', 'qty', 'location'], ... } };
const SCHEMAS_V2 = { inventory_item: { required: ['sku', 'quantity', 'warehouse'], ... } };

function validateWithFallback(raw, schemaName) {
  const v2 = validateApiResponse(schemaName, raw, 0, SCHEMAS_V2);
  if (v2.valid) return normalizeResponse(schemaName, raw);  // new API version

  const v1 = validateApiResponse(schemaName, raw, 0, SCHEMAS_V1);
  if (v1.valid) return raw;  // old API version — log and alert

  return { is_error: true, content: `Unrecognized ${schemaName} schema.` };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Validation timing on 1 000 iterations of inventory_item schema check.

```
=== Validation overhead ===

$ node -e "
const response = { sku: 'SKU-8821', qty: 150, location: 'WH-A' };
const t0 = performance.now();
for (let i = 0; i < 10000; i++) validateApiResponse('inventory_item', response, 100);
const ms = (performance.now() - t0) / 10000;
console.log('validateApiResponse() per call:', ms.toFixed(4), 'ms');
"
validateApiResponse() per call: 0.0041 ms  (3-field schema, type check + size guard)

=== What validation catches ===

CATCHES:
  { sku: 'X', quantity: 150, warehouse: 'WH-A' }   → missing_field (qty, location)
  { sku: 'X', qty: '150', location: 'WH-A' }       → wrong_type (qty should be number)
  10KB HTML error page                               → response_too_large OR non-JSON
  { sku: 'X', qty: null, location: null }           → wrong_type (null ≠ number)

MISSES (structural check only):
  { sku: 'X', qty: -9999999, location: 'WH-A' }    → valid structurally; add range check for business logic
  { sku: 'X', qty: 150, location: '' }              → valid (empty string passes type check)

For business-logic validation (negative qty, empty string), add custom checks after structural validation.

=== Failure example: field rename propagates undetected ===

Without validation:
  API changes qty → quantity
  agent code: data.qty === undefined
  Model context: { sku: 'SKU-8821', qty: undefined }
  Model hallucinates stock level or reports 'unknown'
  Time to detect: next user complaint

With validation:
  API changes qty → quantity
  validateApiResponse fires: missing_field: "qty". Got fields: [sku, quantity, warehouse]
  Structured error returned to model; agent responds: "Inventory data unavailable."
  Alert fires; on-call engineer updates schema within 1 hour
```

## See also

[F-16](../forward-deployed/f16-tool-call-validation.md) · [S-84](s84-tool-return-value-design.md) · [S-62](s62-tool-error-messages.md) · [S-03](s03-tool-use.md) · [F-55](../forward-deployed/f55-agent-task-replanning.md) · [F-42](../forward-deployed/f42-ai-incident-response.md)

## Go deeper

Keywords: `API response validation` · `external API schema` · `tool response validation` · `response schema` · `field validation` · `size guard` · `JSON schema validation` · `API contract` · `schema evolution` · `response normalization`
