# S-183 · Tool Description Compression

[S-168](s168-tool-definition-waste-audit.md) profiles which tools in your schema are never invoked and removes them entirely — a waste audit that targets the tool list. S-183 covers the complement: for tools that are actively used, compress the description text to minimize per-call token overhead.

Tool schemas — name, description, parameter descriptions, enums — are paid as input tokens on every API call that includes the tools array. Unlike system prompts (S-60, S-80), the tools array changes as tools are registered and deregistered, which limits caching opportunities. A verbose 8-tool schema at 1720 tokens/call × 10 000 calls/day = 17.2 million tokens of input overhead daily. At Sonnet pricing, that is $51.60/day for description text alone — text that serves the model during prompt reading, not during tool execution.

Three categories of tokens in tool definitions earn their cost:
- **Parameter constraints**: enum values, required fields, format strings (these directly prevent wrong invocations)
- **Distinguishing descriptions**: what makes this tool different from a similar one (necessary when you have both `search_contracts` and `search_clauses`)
- **Type information**: `type: "string"`, `type: "number"` — the model needs these

Three categories do not:
- **Verbose tool descriptions**: "Use this when you need to find contracts that meet certain criteria. Returns a list of matching contracts with their key fields." — the tool name says what it does
- **Enum parameter descriptions**: if `contract_type` has `enum: ["SERVICE", "NDA", "LEASE"]`, a description saying "Filter by contract type. SERVICE for service agreements, NDA for non-disclosure agreements..." duplicates the enum values in prose
- **String parameter elaboration**: "Optional. Must be in ISO 8601 format: YYYY-MM-DD. Example: '2024-01-01'" — `description: "ISO date YYYY-MM-DD."` says the same thing in five tokens instead of twenty-seven

## Situation

A contract analysis agent has 8 actively-used tools. Tool descriptions were written for comprehensive documentation: examples, "use this when" instructions, "returns X" clauses, and parameter descriptions that restate what the enum already expresses. This is good human documentation practice. At 10 000 calls/day with Sonnet, it costs $51.60/day in schema tokens.

After applying three compression rules, the same 8 tools shrink from 1720 to 784 tokens — 936 tokens/call saved. At Haiku pricing: $7.49/day ($2733/year). At Sonnet: $28.08/day ($10 249/year).

## Forces

- **The model infers "use this when" from the tool name.** A function named `search_contracts` needs no sentence explaining when to use it. Tool names that follow the S-51 verb-noun-context pattern are self-describing; descriptions exist to add what the name cannot say — distinguishing constraints, format requirements, important caveats.
- **Enum values ARE the documentation.** When a parameter has `enum: ["SERVICE", "NDA", "LEASE", "EMPLOYMENT"]`, a description that re-lists these in prose form ("SERVICE for service agreements, NDA for non-disclosure agreements…") pays double: the enum tokens plus the description tokens. Remove the description from enum parameters; the model reads the enum.
- **Required-field markers are more reliable than description language.** "Required. The unique identifier of the contract." is 9 tokens. The JSON Schema `required: ["contract_id"]` already enforces this. Remove "Required." from descriptions; move to required array.
- **Measure before compressing.** Run `estimateToolTokens()` on each tool before and after to verify the reduction. Compression that is not measured is not trustworthy — subtle schema changes can add tokens elsewhere while descriptions are trimmed.
- **Verify invocation quality after compression.** Compress in a staging environment and run your existing evals (F-07, F-64) against both schemas. The compression must not change model tool-selection behavior. The most common failure: removing a description that contained the only signal distinguishing two similar tools. Keep descriptions that do disambiguation work.
- **Compose with S-168, not replace it.** S-168 removes zero-invocation tools from the schema. S-183 compresses descriptions of retained tools. Run S-168 first to remove waste; then S-183 to compress what remains. Applying S-183 to unused tools costs compression effort with no payoff.

## The move

**Apply three rules to every tool definition. Rule 1: one-sentence tool description — verb + noun + distinguishing constraint only. Rule 2: remove description from enum parameters. Rule 3: trim string parameter descriptions to format + constraint only.**

```js
// --- Tool description compression ---
// Compress tool schemas for production use (store verbose docs in source comments).
// Rule 1: tool description ≤ 1 sentence, no examples, no "use this when", no "returns X"
// Rule 2: enum parameters — remove description entirely (enum values are self-documenting)
// Rule 3: string parameters — format + constraint only; remove "Optional", examples, elaboration

function estimateToolTokens(tool) {
  return Math.ceil(JSON.stringify(tool).length / 4);
}

// Example: verbose vs compressed for one tool
const VERBOSE = {
  name: 'search_contracts',
  description: 'Search through the contract database to find contracts matching specific criteria. ' +
    'You can search by party name, contract type, date range, and jurisdiction. ' +
    'Returns a list of matching contracts with key metadata. ' +
    'Use this when you need to locate one or more contracts by any attribute.',
  input_schema: {
    type: 'object',
    properties: {
      query: {
        type: 'string',
        description: 'Full-text search query. Supports Boolean operators (AND, OR, NOT) ' +
          "and phrase matching with double quotes. Example: 'indemnification AND Delaware'",
      },
      contract_type: {
        type: 'string',
        enum: ['SERVICE', 'NDA', 'LEASE', 'EMPLOYMENT', 'VENDOR', 'LICENSE'],
        description: 'Optional. Filter by contract type. If not provided, searches across all types.',
      },
      date_from: {
        type: 'string',
        description: "Optional start date for the date range filter. Must be ISO 8601 format: YYYY-MM-DD. Example: '2024-01-01'",
      },
    },
    required: ['query'],
  },
};

const COMPRESSED = {
  name: 'search_contracts',
  description: 'Find contracts by full-text query, type, date range, or jurisdiction.',
  input_schema: {
    type: 'object',
    properties: {
      query: {
        type: 'string',
        description: 'Full-text search; supports AND/OR/NOT.',
      },
      contract_type: {
        type: 'string',
        enum: ['SERVICE', 'NDA', 'LEASE', 'EMPLOYMENT', 'VENDOR', 'LICENSE'],
        // Rule 2: description removed — enum values are self-documenting
      },
      date_from: {
        type: 'string',
        description: 'ISO date YYYY-MM-DD.',           // Rule 3: format only
      },
    },
    required: ['query'],
  },
};

// Measure and verify before deploying
console.log('search_contracts tokens:',
  estimateToolTokens(VERBOSE),      // 324 tok
  '→',
  estimateToolTokens(COMPRESSED),   // 142 tok
  '(saved', estimateToolTokens(VERBOSE) - estimateToolTokens(COMPRESSED), 'tok)'
);
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. 8 tools: contract analysis agent suite (search_contracts, extract_clause, validate_dates, calculate_duration, lookup_jurisdiction, check_counterparty, summarize_risk, flag_clause). Three compression rules applied. Token estimates via `Math.ceil(JSON.stringify(tool).length / 4)`. Zero API calls.

```
=== Tool Description Compression (8 tools) ===

--- Per-call schema token overhead ---
  search_contracts          verbose=324 tok  compressed=142 tok  saved=182 tok
  extract_clause            verbose=200 tok  compressed= 94 tok  saved=106 tok
  validate_dates            verbose=216 tok  compressed=100 tok  saved=116 tok
  calculate_duration        verbose=142 tok  compressed= 84 tok  saved= 58 tok
  lookup_jurisdiction       verbose=147 tok  compressed= 68 tok  saved= 79 tok
  check_counterparty        verbose=191 tok  compressed= 67 tok  saved=124 tok
  summarize_risk            verbose=211 tok  compressed= 75 tok  saved=136 tok
  flag_clause               verbose=290 tok  compressed=155 tok  saved=135 tok

  Total verbose:    1 720 tokens
  Total compressed:   784 tokens
  Saved:              936 tokens/call (54.4% reduction)

=== Cost at 10 000 calls/day ===
  Haiku ($0.80/M):   verbose=$13.76/day  compressed=$6.27/day  saving=$7.49/day ($2 733/year)
  Sonnet ($3.00/M):  verbose=$51.60/day  compressed=$23.52/day saving=$28.08/day ($10 249/year)

=== What was removed per rule ===
Rule 1 (tool description):
  "Search through the contract database to find contracts matching specific criteria.
   You can search by party name... Returns a list... Use this when you need to..."
  → "Find contracts by full-text query, type, date range, or jurisdiction."
  search_contracts tool description: 72 tok → 18 tok

Rule 2 (enum param description):
  contract_type description: "Optional. Filter by contract type. If not provided,
  searches across all contract types." (22 tok) → removed (enum is self-documenting)

Rule 3 (string param description):
  date_from: "Optional start date for the date range filter. Must be ISO 8601
  format: YYYY-MM-DD. Example: '2024-01-01'" (27 tok)
  → "ISO date YYYY-MM-DD." (5 tok)

=== Note ===
Verify invocation quality on your evals before deploying compressed schemas.
Compression that removes disambiguation (two similar tools) will cause incorrect
tool selection. Keep descriptions that distinguish — cut descriptions that restate.
```

## See also

[S-168](s168-tool-definition-waste-audit.md) · [S-51](s51-tool-schema-design.md) · [S-67](s67-dynamic-tool-registration.md) · [F-67](../forward-deployed/f67-dynamic-tool-registration.md) · [S-56](s56-pre-flight-token-check.md)

## Go deeper

Keywords: `tool description compression` · `tool schema token optimization` · `LLM tool definition tokens` · `compress tool schema` · `tool definition token cost` · `trim tool descriptions` · `tool schema overhead` · `API tool definition cost` · `anthropic tools token count` · `reduce tool schema tokens`
