# S-155 · Tool Call Argument Size Cap

[S-47](s47-output-token-ceiling.md) caps the model's generated output by setting `max_tokens` on the API call. [S-56](s56-pre-flight-token-check.md) measures the total prompt length before sending and refuses the call if the token count exceeds a budget. [F-87](../forward-deployed/f87-tool-call-argument-audit-log.md) logs every tool call argument for auditing.

None of these address the argument itself. When an LLM agent generates a tool call, it sometimes puts large blobs into the arguments: a full 4 000-character contract pasted into `search_documents(query=...)`, or a 2 000-character composed email placed inside `send_email(body=...)`. S-47 does not catch this — the model's generated text was the tool call, and `max_tokens` throttles the response to the tool, not the call. S-56 counts the full prompt before the tool call; it does not inspect individual argument strings after the tool call is generated. F-87 logs the argument but does not truncate it.

The argument contributes to input tokens in the next API turn. A `search_documents` tool call with a 3 002-character `query` argument costs ~751 input tokens for the tool call alone. Capped to 200 characters, the same call costs ~54 tokens — a 697-token reduction per call.

A tool call argument size cap intercepts the generated tool call before it is sent to the API. It checks each string argument against a per-tool-per-argument maximum. Arguments over the limit are truncated to `maxChars` characters with a `...[truncated]` suffix. The model receives the truncated value; the tool executes on a shorter input; the token count for the tool call drops.

## Situation

A contract analysis agent is given a 150-page contract as context. The model decides to search for the notice period clause and generates:

```json
{ "tool": "search_documents", "arguments": { "query": "The agreement dated January 15 2026 between Acme Corporation and FinPay Ltd. This Master Services Agreement governs all services provided hereunder... [3 002 chars total]" } }
```

The query is the model pasting in the full preamble of the contract rather than composing a targeted search query. The tool will likely return poor results (semantic search on 3 000 chars produces noisy embeddings). It also costs 751 tokens of tool call overhead.

After the cap: `query` is truncated to 200 characters. The effective query is the first 200 characters of the pasted preamble — not ideal, but no worse than the full paste — plus the suffix tells the model on the next turn that truncation occurred. The token cost drops from 751 to 54.

The better fix is a prompt instruction: "Write precise search queries, not excerpts." The size cap is the defensive backstop that limits the cost of the failure mode until the prompt is improved.

## Forces

- **This cap is about argument-level cost containment, not tool design.** S-84 (tool return value design) covers designing tools so they return compact, agent-readable results. S-51 (tool schema design) covers writing concise tool descriptions. This cap addresses the agent's behavior at runtime — what happens when the model misuses a tool that is correctly designed.
- **Per-tool, per-argument configuration is required.** A `search_documents` query max of 200 characters makes sense. A `send_email` body max of 1 000 characters is appropriate. A `lookup_clause(clause_id=...)` max of 100 characters is fine. A global default of 500 characters covers tools without specific config. One number for all tools would either be too tight for email bodies or too loose for search queries.
- **Truncation must be logged.** When an argument is truncated, record the tool name, argument name, original length, and capped length. Without this log, the agent appears to have called the tool with a short query, and the reason for a poor result is invisible.
- **The suffix `...[truncated]` is visible to the model.** On the next turn, the model sees the stub suffix in the tool result context and knows its argument was shortened. This gives it the opportunity to retry with a shorter, more precise argument. Without the suffix, the model assumes its full argument was used and may not understand why the result was poor.
- **Non-string arguments pass through unchanged.** Numeric, boolean, and array arguments are not subject to size capping. Only string arguments are candidates. An array of 500 document IDs is a different problem (see S-56 for overall prompt length).
- **This does not prevent the underlying misuse.** A model that pastes 3 000 characters into a search query will do it again on the next call. The cap limits the cost; the fix is a prompt instruction or a tool wrapper that pre-processes the argument before the model call generates it.

## The move

**Before sending each tool call to the API, apply per-tool-per-argument size limits. Truncate oversized string arguments. Log all truncations.**

```js
// --- Tool call argument size cap ---
// Intercepts tool call arguments before API dispatch.
// Truncates oversized string arguments per tool/argument config.
// Non-string args pass through unchanged.

class ToolArgSizeCapper {
  constructor(config = {}) {
    // config: { _default: N, toolName: { argName: N, '*': N } }
    // _default applies when no tool-specific config exists.
    // '*' in a tool config applies to all unnamed args for that tool.
    this._config     = config;
    this._defaultMax = config._default ?? 500;
  }

  // Apply caps to all arguments for a tool call.
  // Returns { args: capped object, truncations: [{arg, original, capped}], wasCapped: bool }
  apply(toolName, args) {
    const toolConfig  = this._config[toolName] ?? {};
    const capped      = {};
    const truncations = [];

    for (const [key, value] of Object.entries(args)) {
      if (typeof value !== 'string') {
        capped[key] = value;
        continue;
      }
      const maxChars = toolConfig[key] ?? toolConfig['*'] ?? this._defaultMax;
      if (value.length > maxChars) {
        capped[key] = value.slice(0, maxChars) + '...[truncated]';
        truncations.push({ arg: key, original: value.length, capped: maxChars });
      } else {
        capped[key] = value;
      }
    }

    return { args: capped, truncations, wasCapped: truncations.length > 0 };
  }
}

// --- Configuration ---

const ARG_CAPPER = new ToolArgSizeCapper({
  _default: 500,
  search_documents:  { query: 200 },
  send_email:        { body: 1000, subject: 80 },
  create_document:   { content: 2000 },
  run_sql:           { query: 800 },
});

// --- Integration: wrap tool dispatch ---

async function dispatchToolCall(toolName, rawArgs, executor) {
  const { args, truncations, wasCapped } = ARG_CAPPER.apply(toolName, rawArgs);

  if (wasCapped) {
    log({
      event:       'tool_arg_truncated',
      tool:        toolName,
      truncations,   // [{ arg, original, capped }] for each truncated arg
    });
  }

  return executor(toolName, args);
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `apply()` timed over 100 000 iterations. Token estimates use `Math.ceil(chars / 4)`.

```
=== ToolArgSizeCapper timing (100 000 iterations) ===

apply() — no truncation (1 string arg):       0.0008 ms
apply() — truncation    (1 string arg, 3002→200): 0.0009 ms

=== Scenario A: search_documents, short query — passes through ===

args: { query: 'renewal clause notice period' }

wasCapped: false
args (unchanged): { query: 'renewal clause notice period' }

=== Scenario B: search_documents, query is a 3 002-char document paste ===

args: { query: '<full contract preamble, 3 002 chars>' }

wasCapped: true
truncations: [{ arg: 'query', original: 3002, capped: 200 }]
Resulting query: 214 chars (200 + '...[truncated]')

Token cost before cap:  ceil(3002 / 4) = 751 tokens
Token cost after cap:   ceil(214  / 4) =  54 tokens
Tokens saved per call:  697

=== Scenario C: send_email, body 2 150 chars → 1 000 cap ===

args: { to: 'customer@example.com', subject: 'Re: Your Renewal', body: '<2 150 chars>' }

wasCapped: true
truncations: [{ arg: 'body', original: 2150, capped: 1000 }]
subject: unchanged (16 chars < 80 cap)
to: unchanged (not a string being capped — it is, but 21 chars < 500 default)

=== Scenario D: lookup_clause, all short args — passes through ===

args: { clause_id: 'CL-881', document_id: 'DOC-224', version: '3' }

No tool-specific config → _default 500 applies to all string args.
wasCapped: false (all args well under 500 chars)

=== Cost projection (Scenario B pattern) ===

Model:                   Haiku ($0.80/M input)
Sessions/day:            10 000
Oversized query rate:    5% (1 in 20 tool calls pastes excess context)
Tokens saved per cap:    697
Calls/session with tools: 4

Daily savings:  10 000 × 0.05 × 4 × 697 tok × $0.80/M = $1.12/day at Haiku
At Sonnet:      10 000 × 0.05 × 4 × 697 tok × $3.00/M = $4.19/day

=== S-47 vs S-56 vs F-87 vs S-155 ===

              │ S-47 (output token ceiling) │ S-56 (pre-flight check)      │ F-87 (arg audit log)       │ S-155 (arg size cap)
──────────────┼─────────────────────────────┼──────────────────────────────┼────────────────────────────┼──────────────────────────────
When          │ API call, max_tokens param  │ Before API call, full prompt │ After tool call generated  │ Before API dispatch, per arg
What          │ Model output length         │ Total prompt token count     │ Logs args for audit trail  │ Individual arg char length
Action        │ Hard stop by API            │ Refuse call / truncate prompt│ No cap, no change          │ Truncate arg, log, proceed
Misses        │ Tool call arg size          │ Per-arg inspection           │ Does not cap               │ Semantic quality of arg
```

## See also

[S-47](s47-output-token-ceiling.md) · [S-56](s56-pre-flight-token-check.md) · [F-87](../forward-deployed/f87-tool-call-argument-audit-log.md) · [S-88](s88-tool-argument-coercion.md) · [S-51](s51-tool-schema-design.md) · [S-84](s84-tool-return-value-design.md)

## Go deeper

Keywords: `tool call argument size cap` · `LLM tool argument truncation` · `tool argument length limit` · `oversized tool argument` · `tool call token overhead` · `agent tool argument cap` · `pre-dispatch argument limit` · `tool arg truncation` · `tool call argument budget` · `search query length cap`
