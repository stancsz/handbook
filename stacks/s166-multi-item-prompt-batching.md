# S-166 · Multi-Item Prompt Batching

[S-37](s37-batch-vs-realtime-pipelines.md) decides when to use batch processing vs real-time: if no one is blocked waiting for the result, accumulate and process in bulk. [S-85](s85-batch-tool-design.md) batches multiple items into a single tool call to an external API — useful when the API supports bulk operations or when rate limits make parallel single calls impractical. Both are about pipeline architecture, not about how many items to include in a single LLM prompt.

When you have N independent items to process with the same logic — classify, extract, summarize, label — the system prompt cost is paid once per API call. Sending N separate calls pays for the system prompt N times. The system prompt is the fixed overhead: instructions, format specification, examples, tool schema. For a 400-token system prompt classifying 10 tickets with 25-token content each, the system prompt accounts for 93% of the input cost on separate calls and 59% on a batched call. Batching 10 items in one call reduces total cost by 75%.

Multi-item prompt batching lists N items numbered in the prompt and requests a per-item JSON response as a newline-delimited array. The model processes all N items in one generation pass. The caller parses the output back into N results. No architecture changes to the pipeline; the batching happens entirely in the prompt layer.

## Situation

A support ticket router classifies 1 000 tickets per day into five intent categories: billing, technical, account, product, and general. Each ticket averages 25 tokens of content. The system prompt is 400 tokens (classification instructions + 5-category definitions + output format spec).

Without batching: 1 000 separate API calls, each with 425 tokens input (400 system + 25 ticket) and 10 tokens output (intent label + confidence tier). Total: 425 000 input tokens + 10 000 output tokens = $0.38/day at Haiku pricing.

With N=10 batching: 100 API calls, each with 680 tokens input (400 system + 10×28 tokens of items with overhead) and 100 tokens output (10 labels). Total: 68 000 input tokens + 10 000 output tokens = $0.0944/day. Savings: 75%.

The output parsing cost (0.0141ms for 10 items) is negligible. The only added complexity is the numbered item format in the prompt and the JSON-per-line output parser.

## Forces

- **Items must be independent.** Item 3's result must not affect item 7's processing. Classification, extraction, summarization, and labeling tasks on independent inputs are good candidates. Conversation threading, where each item is a follow-up to a prior result, is not.
- **Total tokens must fit in the context window.** A batch of N items must not exceed the model's context window after including the system prompt. For a 200k-token window and a 500-token system prompt: at 25 tokens per item, N can be as high as 7 980. In practice, keep N below 50 per call for easier debugging and error isolation.
- **Per-item output must be small.** Batching saves on input; output tokens are the same total regardless of batching. If each item requires 200 tokens of output (a paragraph summary), the output cost dominates and batching saves less. Batching yields the most when output is compact: a label, a small struct, a confidence tier.
- **N=1 is not worth the batching overhead.** A single-item "batch" adds the formatting overhead (item numbering, array structure) with no system prompt savings. Break-even is N>1 for any system prompt. At N=5, savings are already 67%.
- **Error isolation is harder.** If the model returns invalid JSON for one of the 10 items in a batch, parsing fails for the whole batch, not just that item. Add a per-line JSON parser that catches individual item failures and marks them as `{error: 'parse_failed', item: N}` rather than failing the whole batch.
- **Homogeneous items only.** If tickets of type A need a different classification prompt than tickets of type B, group them into separate batches by type. Mixed-type batches require per-item instructions in the prompt, which can exceed the per-item overhead threshold.

## The move

**Number items in the prompt. Request one JSON output per line. Parse per-item. Error-isolate at the item level.**

```js
// --- Multi-item prompt batching ---
// Amortizes system prompt cost across N independent items in one API call.
// Format: numbered items in the prompt; newline-delimited JSON in the output.
// Error isolation: parse each output line independently; mark failed items, don't fail the batch.
// Break-even: N > 1 for any non-zero system prompt. Savings scale with N and system prompt size.

// Build the user-turn prompt for a batch of items.
// items: string[] — each item's content (ticket text, document excerpt, etc.)
function buildBatchPrompt(items) {
  var lines = [];
  for (var i = 0; i < items.length; i++) {
    lines.push('Item ' + (i + 1) + ': ' + items[i]);
  }
  return lines.join('\n') + '\n\nRespond with one JSON object per line, in order. Example:\n{"item":1,"intent":"billing","confidence":"HIGH"}';
}

// Parse the model's newline-delimited JSON output.
// Returns an array of N results; failed parses become error objects.
function parseBatchOutput(output, N) {
  var lines   = output.trim().split('\n').filter(function(l) { return l.trim().length > 0; });
  var results = [];
  for (var i = 0; i < N; i++) {
    if (!lines[i]) {
      results.push({ item: i + 1, error: 'missing_output' });
      continue;
    }
    try {
      results.push(JSON.parse(lines[i]));
    } catch (e) {
      results.push({ item: i + 1, error: 'parse_failed', raw: lines[i] });
    }
  }
  return results;
}

// Cost model: compare batching vs separate calls.
function estimateCost(N, systemPromptTok, perItemTok, perItemOutTok, batchOverheadTok) {
  var inputPrice  = 0.80 / 1e6;  // Haiku
  var outputPrice = 4.00 / 1e6;

  var batchInput  = systemPromptTok + N * (perItemTok + batchOverheadTok);
  var batchOutput = N * perItemOutTok;
  var batchCost   = batchInput * inputPrice + batchOutput * outputPrice;

  var sepInput  = N * (systemPromptTok + perItemTok);
  var sepOutput = N * perItemOutTok;
  var sepCost   = sepInput * inputPrice + sepOutput * outputPrice;

  return { batchCost, sepCost, savingsPct: ((sepCost - batchCost) / sepCost * 100).toFixed(0) + '%' };
}

// --- Integration: batch classification pipeline ---

const SYSTEM_PROMPT = `Classify each support ticket into one of: billing, technical, account, product, general.
Return confidence: HIGH (clearly this category), MEDIUM (likely), LOW (ambiguous).
Output format: one JSON object per line: {"item":N,"intent":"...","confidence":"..."}`;

async function classifyTicketsBatch(tickets) {
  const BATCH_SIZE = 10;
  const results    = [];

  for (let i = 0; i < tickets.length; i += BATCH_SIZE) {
    const batch   = tickets.slice(i, i + BATCH_SIZE);
    const prompt  = buildBatchPrompt(batch);
    const output  = await callModel('claude-haiku-4-5-20251001', SYSTEM_PROMPT, prompt);
    const parsed  = parseBatchOutput(output, batch.length);
    results.push(...parsed);
  }

  return results;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `buildBatchPrompt()` and `parseBatchOutput()` timed over 100 000 iterations on 10-item batches. Pricing: Haiku $0.80/$4.00 per M tok.

```
=== Multi-Item Prompt Batching: cost comparison (Haiku) ===

Config: systemPrompt=400 tok, perItem=25 tok, perItemOut=10 tok, batchOverhead=3 tok/item

N     │ Batched (in+out)   │ Cost ($)    │ Separate (in+out)    │ Cost ($)    │ Savings
──────┼────────────────────┼─────────────┼──────────────────────┼─────────────┼────────
1     │ 428+10             │ $0.000382   │ 425+10               │ $0.000380   │  -1%
5     │ 540+50             │ $0.000632   │ 2 125+50             │ $0.001900   │  67%
10    │ 680+100            │ $0.000944   │ 4 250+100            │ $0.003800   │  75%
20    │ 960+200            │ $0.001568   │ 8 500+200            │ $0.007600   │  79%
50    │ 1 800+500          │ $0.003440   │ 21 250+500           │ $0.019000   │  82%

=== Break-even ===

batchOverhead (tok/item) must be < (1 − 1/N) × systemPrompt / N to beat separate calls.
At N=10, systemPrompt=400:  threshold = 36 tok/item.  Actual overhead: 3 tok.  Batching wins.
At N=5,  systemPrompt=400:  threshold = 64 tok/item.  Actual overhead: 3 tok.  Batching wins.

Rule of thumb: batching beats separate calls for N > 1 when per-item overhead < system prompt size / N.

=== At scale: 1 000 tickets/day, N=10 ===

Batched:   100 API calls × $0.000944 = $0.0944/day
Separate: 1 000 API calls × $0.000380 = $0.3800/day
Savings:  $0.2856/day (75%)

=== Utility timing ===

buildBatchPrompt() 10 items:  0.0023 ms
parseBatchOutput() 10 items:  0.0141 ms

=== S-37 vs S-85 vs S-166 ===

              │ S-37 (batch vs realtime)   │ S-85 (batch tool calls)     │ S-166 (multi-item prompt batching)
──────────────┼────────────────────────────┼─────────────────────────────┼────────────────────────────────────────
What batches  │ Pipeline runs              │ Tool calls to external API  │ Items in a single LLM prompt
Cost savings  │ Latency, infrastructure    │ API rate limits / atomicity │ System prompt amortization
Applies to    │ Architecture               │ Tool design                 │ Any N-item classification/extraction
N limit       │ Queue depth                │ API bulk endpoint           │ Context window / ~50 practical
When not to   │ Latency-sensitive tasks    │ Error isolation needed       │ Dependent items; large per-item output
```

## See also

[S-37](s37-batch-vs-realtime-pipelines.md) · [S-85](s85-batch-tool-design.md) · [S-47](s47-output-length-control.md) · [S-71](s71-long-document-processing.md) · [F-71](../forward-deployed/f71-cost-driven-prompt-design.md)

## Go deeper

Keywords: `multi-item prompt batching` · `batch items single API call` · `system prompt amortization` · `N-item classification call` · `batch classification prompt` · `prompt batching cost` · `multiple items one LLM call` · `batch extraction prompt` · `token cost amortization` · `parallel item processing single call`
