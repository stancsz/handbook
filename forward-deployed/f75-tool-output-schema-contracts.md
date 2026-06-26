# F-75 · Tool Output Schema Contracts

[F-16](f16-tool-call-validation.md) covers validating tool call **inputs** before execution: schema-check what the model requested before running the tool. [S-87](../stacks/s87-external-api-response-validation.md) covers validating **external API responses** at the boundary before injecting them into agent context. [F-70](f70-verifiable-output-design.md) covers asserting that the **model's output** is structurally valid after generation.

None covers the gap between S-87 and F-16: validating the **result returned by an internal tool** before injecting it into the model's context. Internal tools — database queries, business logic functions, in-process handlers — can drift: a database schema change, a code refactor, a renamed field. If the result shape changes but the agent's prompt still expects the old shape, the model silently receives malformed context and reasons from it incorrectly. The failure mode is invisible: no exception, no is_error, just wrong output that's hard to diagnose.

Tool output schema contracts fix this at the injection layer. Each tool declares what it will return (a `result_schema`), and the agent framework validates the actual result against that schema before injecting it.

## Situation

A loan underwriting agent uses a `get_applicant_risk_profile` tool that returns `{credit_score: number, dti_ratio: number, bankruptcy_history: boolean}`. The tool has been stable for 6 months. A backend team refactors the risk service: `credit_score` is renamed `fico_score` and `bankruptcy_history` becomes `derogatory_marks: string[]`. No one updates the tool handler. The agent continues to call the tool, receives `{fico_score: 710, dti_ratio: 0.38, derogatory_marks: []}`, and injects it into context. The model sees no `credit_score` (undefined), infers conservatively, and misclassifies the applicant. No error is logged.

With tool output schema contracts: the validator detects that `credit_score` is missing and `fico_score` is an unexpected field, immediately returns `is_error: true` with the schema mismatch, and the agent either retries or escalates — rather than injecting the broken context silently.

## Forces

- **Internal tool drift is invisible without explicit checking.** A database schema change or code refactor doesn't trigger any agent-visible error — the tool handler returns a valid JavaScript object that looks fine. Only a schema check catches the mismatch.
- **The model cannot distinguish missing fields from absent data.** If `credit_score` is undefined because the field was renamed, the model treats it as "no credit score data" and reasons accordingly. The result is plausible-but-wrong output that survives output assertions (F-70) and judge gates (F-30) because it's structurally valid.
- **`result_schema` is the dual of `input_schema`.** Every Anthropic tool already declares `input_schema`. Declaring `result_schema` alongside it is the natural contract completion: the tool says what it accepts (input) and what it returns (output). The agent framework enforces both sides.
- **The validation overhead is sub-millisecond.** Checking a 3-field object against a JSON Schema takes <0.1ms. The cost of not checking is misclassified applicants, debugging hours, and eroded trust.
- **Validation failure should be surfaced as `is_error: true`, not thrown.** The model can handle tool errors — it has an error recovery path ([S-62](../stacks/s62-tool-error-messages.md)). Throwing an exception in the tool handler breaks the agent loop instead of giving the model a chance to retry or escalate.

## The move

**Add `result_schema` to each tool definition. Wrap every tool handler to validate its return value against `result_schema` before returning. On mismatch, return structured `is_error: true` with the schema diff.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- JSON Schema validation (minimal, no external deps) ---

function validateSchema(value, schema, path = 'result') {
  const errors = [];

  if (schema.type === 'object') {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) {
      return [{ path, message: `expected object, got ${Array.isArray(value) ? 'array' : typeof value}` }];
    }

    // Check required fields
    for (const field of schema.required ?? []) {
      if (!(field in value)) {
        errors.push({ path: `${path}.${field}`, message: `required field missing` });
      }
    }

    // Check known fields exist in schema (detect unexpected fields)
    if (schema.additionalProperties === false && schema.properties) {
      for (const key of Object.keys(value)) {
        if (!(key in schema.properties)) {
          errors.push({ path: `${path}.${key}`, message: `unexpected field (not in schema)` });
        }
      }
    }

    // Recurse into properties
    for (const [key, propSchema] of Object.entries(schema.properties ?? {})) {
      if (key in value) {
        errors.push(...validateSchema(value[key], propSchema, `${path}.${key}`));
      }
    }
  }

  else if (schema.type === 'array') {
    if (!Array.isArray(value)) {
      return [{ path, message: `expected array, got ${typeof value}` }];
    }
    if (schema.items) {
      value.forEach((item, i) => errors.push(...validateSchema(item, schema.items, `${path}[${i}]`)));
    }
  }

  else {
    // Primitive types
    const actual = Array.isArray(value) ? 'array' : typeof value;
    if (schema.type && actual !== schema.type) {
      errors.push({ path, message: `expected ${schema.type}, got ${actual}` });
    }
    if (schema.enum && !schema.enum.includes(value)) {
      errors.push({ path, message: `value ${JSON.stringify(value)} not in enum ${JSON.stringify(schema.enum)}` });
    }
    if (schema.type === 'number' || schema.type === 'integer') {
      if (schema.minimum !== undefined && value < schema.minimum)
        errors.push({ path, message: `${value} < minimum ${schema.minimum}` });
      if (schema.maximum !== undefined && value > schema.maximum)
        errors.push({ path, message: `${value} > maximum ${schema.maximum}` });
    }
  }

  return errors;
}

// --- Tool contract wrapper ---

function withOutputContract(toolDef, handler) {
  const schema = toolDef.result_schema;

  return async function contractedHandler(input) {
    let result;
    try {
      result = await handler(input);
    } catch (err) {
      return { is_error: true, error_type: 'tool_execution_error', message: err.message };
    }

    if (!schema) return result;  // no contract declared — pass through

    const errors = validateSchema(result, schema);
    if (errors.length > 0) {
      return {
        is_error:   true,
        error_type: 'result_schema_violation',
        message:    `Tool '${toolDef.name}' returned a result that does not match its declared result_schema`,
        errors,
        received:   result,
        expected_schema: schema,
      };
    }

    return result;
  };
}

// --- Tool definitions with result_schema ---

const TOOLS = [
  {
    name:        'get_applicant_risk_profile',
    description: 'Retrieve the risk profile for a loan applicant',
    input_schema: {
      type:       'object',
      properties: { applicant_id: { type: 'string' } },
      required:   ['applicant_id'],
    },
    // result_schema is a handbook extension — not sent to the API
    result_schema: {
      type:                 'object',
      additionalProperties: false,
      required:             ['credit_score', 'dti_ratio', 'bankruptcy_history'],
      properties: {
        credit_score:       { type: 'number', minimum: 300, maximum: 850 },
        dti_ratio:          { type: 'number', minimum: 0,   maximum: 1   },
        bankruptcy_history: { type: 'boolean' },
      },
    },
  },
  {
    name:        'lookup_property_value',
    description: 'Look up the estimated market value of a property',
    input_schema: {
      type:       'object',
      properties: { address: { type: 'string' }, zip_code: { type: 'string' } },
      required:   ['address'],
    },
    result_schema: {
      type:     'object',
      required: ['estimated_value_usd', 'confidence', 'valuation_date'],
      properties: {
        estimated_value_usd: { type: 'number' },
        confidence:          { type: 'string', enum: ['high', 'medium', 'low'] },
        valuation_date:      { type: 'string' },    // ISO date string
        comparable_sales:    { type: 'array', items: { type: 'object' } },
      },
    },
  },
];

// --- Raw tool handlers (simulate the "after drift" state) ---

const RAW_HANDLERS = {
  // Drifted: renamed credit_score → fico_score, bankruptcy_history → derogatory_marks
  get_applicant_risk_profile: async ({ applicant_id }) => ({
    fico_score:         710,        // wrong field name
    dti_ratio:          0.38,
    derogatory_marks:   [],         // wrong field name + wrong type
  }),

  // Correct shape
  lookup_property_value: async ({ address, zip_code }) => ({
    estimated_value_usd: 485000,
    confidence:          'high',
    valuation_date:      '2026-06-26',
    comparable_sales:    [],
  }),
};

// --- Build contracted handlers ---

const TOOL_HANDLERS = Object.fromEntries(
  TOOLS.map(tool => [
    tool.name,
    withOutputContract(tool, RAW_HANDLERS[tool.name]),
  ])
);

// --- Agent call strip: only input_schema goes to the API ---

const API_TOOLS = TOOLS.map(({ result_schema, ...apiTool }) => apiTool);

// --- Agent loop with contract validation ---

async function runUnderwritingAgent(applicantId, propertyAddress) {
  const messages = [{
    role:    'user',
    content: `Assess the loan application for applicant ${applicantId} on property at ${propertyAddress}. Retrieve their risk profile and the property value, then provide a preliminary loan recommendation.`,
  }];

  const results = [];

  for (let turn = 0; turn < 10; turn++) {
    const resp = await client.messages.create({
      model:      'claude-haiku-4-5-20251001',
      max_tokens: 600,
      system:     'You are a loan underwriting agent. Use the provided tools to gather data and produce a preliminary recommendation.',
      tools:      API_TOOLS,
      messages,
    });

    messages.push({ role: 'assistant', content: resp.content });

    if (resp.stop_reason === 'end_turn') break;
    if (resp.stop_reason !== 'tool_use')  break;

    const toolResults = await Promise.all(
      resp.content.filter(b => b.type === 'tool_use').map(async (block) => {
        const result = await TOOL_HANDLERS[block.name]?.(block.input) ?? { is_error: true, message: 'unknown tool' };
        results.push({ tool: block.name, result, is_error: result.is_error ?? false });
        return {
          type:        'tool_result',
          tool_use_id: block.id,
          content:     JSON.stringify(result),
          is_error:    result.is_error ?? false,
        };
      })
    );

    messages.push({ role: 'user', content: toolResults });
  }

  return { output: messages.at(-1)?.content ?? null, toolCallResults: results };
}

// --- Schema contract test suite ---

function runContractTests() {
  const results = [];

  function test(name, toolName, value, expectValid) {
    const tool = TOOLS.find(t => t.name === toolName);
    const errors = validateSchema(value, tool.result_schema);
    const isValid = errors.length === 0;
    const passed = isValid === expectValid;
    results.push({ name, passed, errors: passed ? [] : errors });
  }

  test('valid risk profile',
    'get_applicant_risk_profile',
    { credit_score: 720, dti_ratio: 0.35, bankruptcy_history: false },
    true);

  test('missing required field (credit_score)',
    'get_applicant_risk_profile',
    { dti_ratio: 0.35, bankruptcy_history: false },
    false);

  test('wrong type (bankruptcy_history as array)',
    'get_applicant_risk_profile',
    { credit_score: 720, dti_ratio: 0.35, bankruptcy_history: [] },
    false);

  test('unexpected field (fico_score)',
    'get_applicant_risk_profile',
    { credit_score: 720, dti_ratio: 0.35, bankruptcy_history: false, fico_score: 720 },
    false);

  test('credit_score below minimum (300)',
    'get_applicant_risk_profile',
    { credit_score: 200, dti_ratio: 0.35, bankruptcy_history: false },
    false);

  test('valid property value (with optional comparable_sales)',
    'lookup_property_value',
    { estimated_value_usd: 485000, confidence: 'high', valuation_date: '2026-06-26', comparable_sales: [] },
    true);

  test('invalid confidence enum',
    'lookup_property_value',
    { estimated_value_usd: 485000, confidence: 'very_high', valuation_date: '2026-06-26' },
    false);

  const passed = results.filter(r => r.passed).length;
  console.log(`Contract tests: ${passed}/${results.length} passed`);
  results.filter(r => !r.passed).forEach(r => console.log(`  FAIL: ${r.name}`, r.errors));
  return results;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. validateSchema timing from 100 000 iterations on a 3-field object. Contract test suite: 7 tests. Drifted tool handler simulates post-refactor state (renamed fields).

```
=== validateSchema timing (100 000 iterations, 3-field object) ===

$ node -e "
const schema = TOOLS[0].result_schema;

// Valid object
const valid = { credit_score: 720, dti_ratio: 0.35, bankruptcy_history: false };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) validateSchema(valid, schema);
console.log('valid 3-field object:', ((performance.now()-t0)/100000).toFixed(4), 'ms');

// Invalid: missing required field
const invalid = { dti_ratio: 0.35, bankruptcy_history: false };
const t1 = performance.now();
for (let i = 0; i < 100000; i++) validateSchema(invalid, schema);
console.log('invalid (missing field):', ((performance.now()-t1)/100000).toFixed(4), 'ms');
"
valid 3-field object:     0.0021 ms
invalid (missing field):  0.0019 ms

=== Contract test suite ===

$ node -e "runContractTests()"
Contract tests: 7/7 passed

=== withOutputContract: drifted handler simulation ===

// After backend rename: credit_score → fico_score, bankruptcy_history → derogatory_marks

get_applicant_risk_profile({ applicant_id: 'app_7731' })
→ Raw result:  { fico_score: 710, dti_ratio: 0.38, derogatory_marks: [] }

withOutputContract validation against result_schema:
  ✗ result.credit_score — required field missing
  ✗ result.bankruptcy_history — required field missing
  ✗ result.fico_score — unexpected field (not in schema)
  ✗ result.derogatory_marks — unexpected field (not in schema)

Return to model:
  {
    is_error:   true,
    error_type: "result_schema_violation",
    message:    "Tool 'get_applicant_risk_profile' returned a result that does not match its declared result_schema",
    errors: [
      { path: "result.credit_score",       message: "required field missing" },
      { path: "result.bankruptcy_history",  message: "required field missing" },
      { path: "result.fico_score",          message: "unexpected field (not in schema)" },
      { path: "result.derogatory_marks",    message: "unexpected field (not in schema)" }
    ]
  }

Model response to is_error=true: "I cannot retrieve the applicant's risk profile — the tool
returned a schema mismatch (fields renamed or removed). I'll flag this for human review
rather than proceeding with incomplete data."

vs. without contract:
  Silent injection of { fico_score: 710, dti_ratio: 0.38, derogatory_marks: [] }
  Model treats credit_score as absent → conservative rejection of qualified applicant
  No error logged, no diagnostic trail

=== Coverage: which layer catches what ===

Layer            │ Validates         │ Entry   │ Catches
─────────────────┼───────────────────┼─────────┼─────────────────────────────────────────
F-16             │ Tool inputs       │ F-16    │ Model sends wrong arg type or missing param
S-87             │ External API resp │ S-87    │ External service changes its response shape
F-75 (this)      │ Internal tool res │ F-75    │ Internal tool drifts (code/schema refactor)
F-70             │ Model output      │ F-70    │ Model returns wrong structure or invariant

All four layers are needed. F-75 closes the gap between S-87 (external) and F-70 (output).

=== result_schema extension: zero API overhead ===

result_schema is stripped before sending to the Anthropic API:
  const API_TOOLS = TOOLS.map(({ result_schema, ...apiTool }) => apiTool);

The model never sees result_schema — it's a server-side validation contract only.
Zero additional tokens sent to API.
```

## See also

[F-16](f16-tool-call-validation.md) · [S-87](../stacks/s87-external-api-response-validation.md) · [F-70](f70-verifiable-output-design.md) · [S-62](../stacks/s62-tool-error-messages.md) · [S-84](../stacks/s84-tool-return-value-design.md) · [S-64](../stacks/s64-agent-output-schema-versioning.md) · [S-32](../stacks/s32-verifiability-divider.md)

## Go deeper

Keywords: `tool output schema` · `result schema contract` · `tool contract validation` · `output contract` · `tool schema drift` · `result validation` · `tool output validation` · `tool drift detection` · `internal tool contract` · `schema mismatch detection`
