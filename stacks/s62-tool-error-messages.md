# S-62 · Tool Error Messages

When a tool call fails, the model gets a `tool_result` back. What's in that result determines whether the model recovers in one attempt, retries blindly three times, or escalates to the user. The content of the error message is the model's only signal about what went wrong and what to do next. "Error" tells it nothing. "File not found: /reports/q4_2025.csv. Available files in /reports/: q3_2025.csv, q2_2025.csv" tells it exactly what to try next.

## Situation

An agent tries to read `/reports/q4_2025.csv`. The file doesn't exist — the user said "q4" but the file is named `q4_2025_final.csv`. The tool returns `{ is_error: true, content: "Error" }`. The model has no idea what went wrong. It retries the same call. Fails again. Retries. After three failures it asks the user "what should I do?" — four API calls to reach a question that a 41-token error message would have avoided entirely.

## Forces

- **`is_error: true` is a signal, not a solution.** The Anthropic API supports `is_error: true` on `tool_result` content blocks. Setting it tells the model a tool call failed. What's in `content` tells the model *why* and *what to do*. The flag without useful content is noise.
- **Three retry modes, one error field.** Some errors are recoverable (transient timeout — retry works); some are self-correctable (wrong filename — model can try the right one); some are unrecoverable (auth error — model cannot fix it). All three arrive via the same `tool_result`. The error message must carry the recovery hint, because the model has no other channel.
- **Vague errors cost 3–4× more than specific ones.** A model receiving "Error" will regenerate a new tool call attempt (output tokens), wait for the same failure (latency), and repeat. A model receiving "File not found: X. Did you mean Y?" adapts immediately. The 38-token error message costs four cents per thousand tool failures; the retry loop costs dollars.
- **Unrecoverable errors must say so explicitly.** "Permission denied" without a "do not retry" signal leads to retry loops on a call that will never succeed. Saying "Do not retry — escalate to the user" in the error text short-circuits the loop.
- **Parameter errors need the schema.** If the model passed the wrong parameter shape, the error message should include what the correct schema looks like. Without it, the model guesses at the fix.

## The move

**Return structured, actionable error content in every `tool_result` with `is_error: true`. Classify the error in the message so the model knows how to respond.**

**The `is_error` tool_result shape:**

```js
// Correct shape (Anthropic API)
const errorResult = {
  type: 'tool_result',
  tool_use_id: toolUseBlock.id,   // must match the tool_use block's id
  is_error: true,
  content: errorMessage,           // string; this is what the model reads
};
```

**Error message patterns by type:**

```js
function buildToolError(type, details) {
  switch (type) {
    case 'not_found':
      // Recoverable by model: include what IS available
      return `${details.resource} not found. Available options: ${details.available.join(', ')}`;

    case 'permission_denied':
      // Unrecoverable by model: explicit stop signal
      return `Permission denied: ${details.resource}. Required role: ${details.requiredRole}. Do not retry — request the user to provide access or an alternative resource.`;

    case 'timeout':
      // Transient: model should retry
      return `Timeout: ${details.operation} did not complete within ${details.limitMs}ms. The operation may have partially completed. Retry once.`;

    case 'invalid_params':
      // Model-error: include the correct schema
      return `Invalid parameters: ${details.message}. Expected schema: ${JSON.stringify(details.expectedSchema, null, 0)}. Retry with corrected parameters.`;

    case 'rate_limit':
      // Transient but delayed: don't let model retry in a tight loop
      return `Rate limit reached. Wait at least ${details.retryAfterSeconds} seconds before retrying.`;

    case 'api_error':
      // Upstream failure: retry once; escalate if persistent
      return `External service error (${details.statusCode}): ${details.message}. Retry once; if this fails again, inform the user that the service is unavailable.`;

    default:
      return `Tool error: ${details.message}`;
  }
}
```

**Retry budget in the agent loop:**

```js
const MAX_TOOL_RETRIES = 2;
const retryCount = {};

async function handleToolCall(toolUseBlock, tools) {
  const key = `${toolUseBlock.name}:${JSON.stringify(toolUseBlock.input)}`;
  retryCount[key] = (retryCount[key] ?? 0) + 1;

  if (retryCount[key] > MAX_TOOL_RETRIES) {
    // Hard stop: return escalation message instead of retrying
    return {
      type: 'tool_result',
      tool_use_id: toolUseBlock.id,
      is_error: true,
      content: `Tool ${toolUseBlock.name} has failed ${MAX_TOOL_RETRIES + 1} times. Inform the user and stop retrying.`,
    };
  }

  try {
    const result = await tools[toolUseBlock.name](toolUseBlock.input);
    return { type: 'tool_result', tool_use_id: toolUseBlock.id, content: JSON.stringify(result) };
  } catch (err) {
    return {
      type: 'tool_result',
      tool_use_id: toolUseBlock.id,
      is_error: true,
      content: buildToolError(err.type, err),
    };
  }
}
```

**Error message taxonomy:**

| Error type | Recovery hint | Do not retry? |
|---|---|---|
| `not_found` | List available alternatives | No — model self-corrects |
| `permission_denied` | State required role; say do not retry | Yes — unrecoverable |
| `timeout` | Say retry once | No — one retry is fine |
| `invalid_params` | Include correct schema | No — model self-corrects |
| `rate_limit` | Include `retryAfterSeconds` | Delayed retry only |
| `quota_exceeded` | Say do not retry; escalate | Yes — unrecoverable |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Cost model: $3.00/M input, $15.00/M output. Tool failure rate 5%, 10k calls/day. Recovery attempt cost includes re-sending accumulated context + model generation per retry.

```
=== Tool error message quality ===

Message type    Tokens   Content summary
vague           3        "Error"
specific        41       "File not found: /reports/q4_2025.csv. Available files in /reports/: ..."
actionable      36       "Permission denied... Do not retry — request the user to provide..."

=== Recovery cost at 10k calls/day, 5% failure rate (500 failing calls/day) ===

Error type    Retries   Cost/failure   Monthly cost
Vague         3         $0.011490      $172.35
Specific      1         $0.005664      $84.96
Actionable    0         $0.002505      $37.57

→ Specific error saves $87.39/month vs vague at this scale
→ Actionable (unrecoverable with stop signal) saves $134.78/month
→ 41-token error message pays back in the first 10 failed calls
```

The vague error is 3 tokens. The specific one is 41 tokens. The retry loop it prevents costs roughly 400 tokens of accumulated context re-sends plus generation. The 38-token investment returns 10× in token savings when the model self-corrects on the first attempt instead of retrying to exhaustion.

## See also

[S-03](s03-tool-use.md) · [F-16](../forward-deployed/f16-tool-call-validation.md) · [S-55](s55-parallel-tool-calls.md) · [S-51](s51-tool-schema-design.md) · [F-20](../forward-deployed/f20-rate-limits-and-retry.md) · [F-31](../forward-deployed/f31-structured-call-logging.md)

## Go deeper

Keywords: `tool error` · `is_error` · `tool_result` · `tool retry` · `error message crafting` · `agent recovery` · `retry budget` · `tool call failure` · `unrecoverable error` · `actionable error message`
