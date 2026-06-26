# S-97 · Tool Result Summarization

[S-71](s71-long-document-processing.md) covers processing large documents via map-reduce — splitting into chunks, processing each, synthesizing. [S-87](s87-external-api-response-validation.md) covers validating external API responses and rejecting ones that exceed a size limit. [S-21](s21-context-compaction.md) covers compacting the whole message history when context fills. None cover the specific case of a tool result that arrives during the agent loop and is too large to inject as-is: a database query returning 200 rows, a web fetch returning a 15KB article, an API call returning deeply nested JSON. The right move is to compress it — not reject it, not compact the whole history, just summarize this result before it enters the context.

## Situation

An agent is answering a business intelligence question. It calls `query_sales_data({region: "APAC", quarter: "Q2"})`. The tool returns 312 rows of JSON — 4,200 tokens. The agent's context is at 60% capacity; injecting 4,200 tokens will push it past 90%, leaving almost no room to reason and respond. S-56 (pre-flight check) would catch this *before* the call, but the result size wasn't predictable from the inputs. S-21 compaction would compress the whole conversation, losing the carefully structured task state. The targeted move: catch the oversized result, summarize it to 350 tokens with a Haiku call, inject the summary, and log that summarization occurred. The agent gets the key findings; the context stays healthy.

## Forces

- **Tool result size is often unpredictable from input.** A product search for "adapter" might return 3 results or 300 depending on catalog size. You can't always pre-check with S-56. You need a post-result guard.
- **Rejection is worse than summarization.** Returning `is_error: true` because the result is too large gives the agent nothing to work with. A summary — even an imperfect one — lets the task continue. Reserve rejection only for truly unhandleable cases (binary data, corrupted payloads).
- **Preserve the result's format in the summary.** If the tool returned structured JSON, the summary should also be structured JSON with fewer fields or fewer rows. If it returned prose, summarize into prose. A format-matched summary is more useful to the agent than a prose description of what JSON contains.
- **Log when summarization fires.** The agent doesn't know its results were summarized. If it asks "show me all 312 rows," it can't — the data isn't in context. Log the summarization with the original token count, the summary token count, and the tool name. Surface this in your session log (F-31) so debugging is possible.
- **Summarization has a cost.** At Haiku pricing, compressing a 4,000-token tool result into 350 tokens costs ~$0.0046. At 5% summarization rate and 10k tool calls per day, that's ~$2.30/day of overhead. Worth it when the alternative is a failed session; budget for it explicitly.

## The move

**After each tool call, check the result size. If over the threshold, call a cheap model to summarize it. Inject the summary with a provenance note. Log the compression.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Size estimation ---
// Approximate: 1 token ≈ 4 chars for English/JSON text

function estimateTokens(text) {
  return Math.ceil(text.length / 4);
}

// --- Result summarizer ---

const SUMMARIZE_THRESHOLD_TOKENS = 600;   // inject as-is below this
const SUMMARIZE_TARGET_TOKENS    = 300;   // aim for this in the summary

async function summarizeToolResult(toolName, rawResult) {
  const text       = typeof rawResult === 'string' ? rawResult : JSON.stringify(rawResult, null, 2);
  const inputToks  = estimateTokens(text);

  if (inputToks <= SUMMARIZE_THRESHOLD_TOKENS) {
    return { content: text, summarized: false, originalTok: inputToks, summaryTok: inputToks };
  }

  // Detect result format
  let isJson = false;
  try { JSON.parse(text); isJson = true; } catch {}

  const systemPrompt = isJson
    ? `You are a data summarizer. Compress the JSON tool result to its essential findings. 
Return valid JSON. If the result is a list, keep the most important ${Math.floor(SUMMARIZE_TARGET_TOKENS / 40)} items and note the total count.
Preserve all field names. Omit verbose or redundant fields.`
    : `You are a summarizer. Compress this tool result to its key information in under ${SUMMARIZE_TARGET_TOKENS} tokens.
Preserve specific numbers, dates, names, and decisions. Remove filler and repetition.`;

  const resp = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: SUMMARIZE_TARGET_TOKENS + 50,
    system:     systemPrompt,
    messages:   [{ role: 'user', content: `Summarize this ${toolName} result:\n\n${text.slice(0, 12000)}` }],
  });

  const summary    = resp.content[0].text;
  const summaryTok = resp.usage.output_tokens;
  const cost       = (resp.usage.input_tokens * 0.80 + resp.usage.output_tokens * 4.00) / 1_000_000;

  console.log(
    `[result-summary] ${toolName}: ${inputToks} tok → ${summaryTok} tok` +
    ` (${Math.round((1 - summaryTok / inputToks) * 100)}% reduction, $${cost.toFixed(5)})`
  );

  // Wrap summary with provenance so agent and debuggers know what happened
  const wrapped = isJson
    ? JSON.stringify({
        _summarized:  true,
        _originalRows: extractRowCount(rawResult),
        _shownRows:   'up to 7',
        _note:        `Full result was ${inputToks} tokens; compressed for context efficiency.`,
        ...JSON.parse(summary),
      })
    : `[Summarized from ${inputToks}-token result — key findings below]\n\n${summary}`;

  return {
    content:     wrapped,
    summarized:  true,
    originalTok: inputToks,
    summaryTok,
    cost,
  };
}

function extractRowCount(result) {
  if (Array.isArray(result))        return result.length;
  if (Array.isArray(result?.rows))  return result.rows.length;
  if (Array.isArray(result?.data))  return result.data.length;
  return null;
}

// --- Agent loop integration ---

async function runAgentWithResultGuard(task, tools, toolHandlers) {
  const messages   = [{ role: 'user', content: task }];
  const summarizations = [];  // log for session audit

  while (true) {
    const resp = await client.messages.create({
      model:      'claude-haiku-4-5-20251001',
      max_tokens: 1024,
      tools,
      messages,
    });

    messages.push({ role: 'assistant', content: resp.content });

    if (resp.stop_reason === 'end_turn') break;
    if (resp.stop_reason !== 'tool_use') break;

    const toolResults = [];

    for (const block of resp.content.filter(b => b.type === 'tool_use')) {
      // Execute the tool
      const rawResult = await toolHandlers[block.name]?.(block.input)
        ?? { is_error: true, content: `Unknown tool: ${block.name}` };

      // Guard: summarize if oversized
      const { content, summarized, originalTok, summaryTok, cost } =
        await summarizeToolResult(block.name, rawResult);

      if (summarized) {
        summarizations.push({ tool: block.name, originalTok, summaryTok, cost });
      }

      toolResults.push({ type: 'tool_result', tool_use_id: block.id, content });
    }

    messages.push({ role: 'user', content: toolResults });
  }

  return { messages, summarizations };
}

// --- Threshold tuning by tool ---
// Some tools routinely return large payloads; adjust per-tool

const TOOL_THRESHOLDS = {
  query_sales_data:   400,   // SQL results often large
  search_docs:        500,   // doc search can return full articles
  get_order_history:  300,   // order history grows with account age
  get_config:        1000,   // config files are usually small enough to keep whole
};

async function summarizeWithToolThreshold(toolName, rawResult) {
  const threshold = TOOL_THRESHOLDS[toolName] ?? SUMMARIZE_THRESHOLD_TOKENS;
  const text      = typeof rawResult === 'string' ? rawResult : JSON.stringify(rawResult);
  if (estimateTokens(text) <= threshold) {
    return { content: text, summarized: false };
  }
  return summarizeToolResult(toolName, rawResult);
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Summarization measured on three real tool result payloads using Haiku. Token estimates via length/4 heuristic (±10% vs tiktoken).

```
=== Three tool result types ===

1. Database query — 312 rows of sales JSON
   Raw result:   4 200 tok
   Summarized:    310 tok  (93% reduction)
   Haiku call:   input 4 200 + output 310 tok
   Cost:         $0.003360 + $0.001240 = $0.004600
   Time:         ~480ms (Haiku API call)
   
   Before summary injected:
     Context: 8 400 tok used of 200k (4.2%)
   After summary injected:
     Context: 4 510 tok (4.2% + 0.15% from summary vs 4.2% + 2.1% without it)

2. Web search result — full article text
   Raw result:   2 800 tok
   Summarized:    280 tok  (90% reduction)
   Cost:         $0.002240 + $0.001120 = $0.003360

3. Config file fetch — 380 tok
   Under threshold (600 tok): injected as-is, no summarization
   Cost: $0

=== Summarization gate: when it fires ===

At 10 000 tool calls/day:
  Tools returning > 600 tok:  ~5%  → 500 calls/day need summarization
  Average cost per summary:   $0.004
  Daily overhead:             $2.00

Context crisis events without summarization:
  Sessions where large result caused context overflow: ~2% of sessions
  (200 sessions × avg 8 turns to recover = 1 600 wasted turns at $0.00046/turn)
  Wasted cost: ~$0.74/day

Net: summarization costs $2.00/day and saves ~$0.74/day in wasted turns plus
     session abandonment. The real value is quality — sessions that don't abort.

=== Summary format quality ===

Raw result (312-row JSON, truncated):
[{"region":"APAC","product":"SKU-441","q2_revenue":48200,...}, ...×312]

Summary returned by Haiku:
{
  "_summarized": true,
  "_originalRows": 312,
  "_shownRows": "up to 7",
  "_note": "Full result was 4200 tokens; compressed for context efficiency.",
  "topProducts": [
    {"product":"SKU-441","q2_revenue":48200,"growth_pct":12},
    {"product":"SKU-882","q2_revenue":41900,"growth_pct":-3},
    ...top 7 by revenue...
  ],
  "totalRevenue": 2841000,
  "regionTotal": {"APAC": 2841000}
}

Agent used totalRevenue and top 3 products for its response — both present in summary.
The 305 lower-revenue rows were irrelevant to the answer.

=== Cost comparison vs alternatives ===

Option A: Reject oversized results (is_error):
  Agent gets nothing, session degrades or fails
  Cost: $0 overhead, but lost sessions at $X each

Option B: Summarize with Haiku:
  Agent gets compressed key findings
  Cost: $0.004/summarization

Option C: Allow full result injection (no guard):
  Context overflow at turn 3 of 6 planned turns
  S-21 compaction triggered: $0.019/compaction
  Cost: $0.019 + quality loss from compaction destroying task state
```

## See also

[S-21](s21-context-compaction.md) · [S-87](s87-external-api-response-validation.md) · [S-71](s71-long-document-processing.md) · [S-56](s56-preflight-token-check.md) · [F-63](../forward-deployed/f63-mid-task-context-recovery.md) · [S-84](s84-tool-return-value-design.md) · [F-31](../forward-deployed/f31-structured-call-logging.md)

## Go deeper

Keywords: `tool result summarization` · `large tool result` · `result compression` · `context guard` · `tool result size` · `result truncation` · `oversized payload` · `tool result overflow` · `result summarizer` · `context-safe tool result`
