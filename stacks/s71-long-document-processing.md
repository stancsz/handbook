# S-71 · Long Document Processing

When a document fits in the context window, put it in and ask your question. When it doesn't fit — or when the model's attention degrades over very long contexts — use map-reduce: split the document into chunks, process each independently (map), then synthesize the results (reduce). The pattern is the same as big-data map-reduce; the unit of work is a model call, not a CPU core.

## Situation

A legal team ingests 500-page contracts for risk analysis. Each contract is ~125 000 tokens — it fits in a 200k-context model but barely, and quality degrades on content buried in the middle ([S-13](s13-context-engineering.md), lost-in-the-middle). A 2 000-page litigation archive is 500 000 tokens: it does not fit in any current context window. Map-reduce works for both cases with identical code. For the 500-page contract, it trades a 13% cost premium for more reliable attention. For the 2 000-page archive, it is the only option.

## Forces

- **Context limits are hard walls, not suggestions.** A document that exceeds the context window cannot be single-called. Map-reduce does not have this limit — you can process a document of any size by adjusting the number of chunks.
- **Long-context quality degrades non-linearly.** Models attend most strongly to content at the beginning and end of the context; content in the middle of a very long prompt receives proportionally less attention. At 33 000 tokens, the effect is minor. At 100 000+ tokens, it is measurable. Focused 6 000–8 000 token chunks each receive full model attention.
- **Map-reduce costs more for documents that fit in context.** For a 33 000-token document, single call costs $0.11 vs map-reduce $0.12. The map phase also adds a reduce step and extra latency when not parallelized. Only reach for map-reduce when (a) the document doesn't fit, or (b) quality tests on your specific task show the single-call approach is worse.
- **The map phase is embarrassingly parallel.** Chunk summaries don't depend on each other — run them concurrently with `Promise.all`. Wall-clock time for the map phase is the time of one chunk call, regardless of how many chunks you have.
- **The reduce step may need to be recursive.** If 50 map chunks produce 50 × 150-token summaries = 7 500 tokens, a single reduce call handles it easily. If 500 chunks produce 75 000 tokens of intermediate summaries, the reduce step itself needs chunking (hierarchical map-reduce).

## The move

**For documents within the context window: single call. For documents exceeding it, or when long-context quality is measurably worse: map-reduce. Parallelize the map phase; recurse the reduce if needed.**

**Map-reduce implementation:**

```js
const CHUNK_TOKENS   = 7_000; // leave headroom for system prompt + output
const CHUNK_OVERLAP  = 200;   // overlap prevents cutting sentences mid-thought
const MAP_OUTPUT_MAX = 200;   // tokens per chunk summary
const REDUCE_MAX     = 800;   // tokens for final synthesis

async function processDocument(client, document, task) {
  const chunks = splitIntoChunks(document, CHUNK_TOKENS, CHUNK_OVERLAP);

  if (chunks.length === 1) {
    // Document fits in one call — skip map-reduce overhead
    return singleCall(client, document, task);
  }

  // Map phase — parallel
  const chunkSummaries = await Promise.all(
    chunks.map((chunk, i) => mapCall(client, chunk, task, i, chunks.length))
  );

  // Recurse if reduce input itself is too large
  const totalReduceTokens = chunkSummaries.join('\n\n').length / 4; // rough estimate
  if (totalReduceTokens > CHUNK_TOKENS) {
    return processDocument(client, chunkSummaries.join('\n\n---\n\n'), task);
  }

  return reduceCall(client, chunkSummaries, task);
}

async function mapCall(client, chunk, task, index, total) {
  const resp = await client.messages.create({
    model:     'claude-sonnet-4-6',
    max_tokens: MAP_OUTPUT_MAX,
    system:    `You are processing section ${index + 1} of ${total} from a larger document. Extract what is relevant to: ${task}. Be concise.`,
    messages:  [{ role: 'user', content: chunk }],
  });
  return resp.content[0].text;
}

async function reduceCall(client, summaries, task) {
  const combinedInput = summaries.map((s, i) => `[Section ${i+1}]\n${s}`).join('\n\n');
  const resp = await client.messages.create({
    model:     'claude-sonnet-4-6',
    max_tokens: REDUCE_MAX,
    system:    `You are synthesizing analysis from ${summaries.length} document sections. Produce a coherent, complete response to: ${task}`,
    messages:  [{ role: 'user', content: combinedInput }],
  });
  return resp.content[0].text;
}

function splitIntoChunks(text, maxTokens, overlap) {
  // Split on paragraph/sentence boundaries; chunk by token count
  const paragraphs = text.split(/\n\n+/);
  const chunks = [];
  let current = '';
  let currentTokens = 0;

  for (const para of paragraphs) {
    const paraTokens = Math.ceil(para.length / 4); // rough: 4 chars/token
    if (currentTokens + paraTokens > maxTokens && current) {
      chunks.push(current.trim());
      // Keep overlap: last ~overlap chars of current as start of next
      current = current.slice(-overlap * 4) + '\n\n' + para;
      currentTokens = Math.ceil(current.length / 4);
    } else {
      current += '\n\n' + para;
      currentTokens += paraTokens;
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}
```

**When to use each strategy:**

| Document size | Context fits? | Strategy |
|---|---|---|
| < 10k tokens | Yes | Single call — no overhead |
| 10k–50k tokens | Yes | Single call, unless quality tests show degradation |
| 50k–200k tokens | Marginal | Map-reduce if quality test fails; single call if it passes |
| > 200k tokens | No | Map-reduce required |
| > 500k tokens | No | Hierarchical map-reduce (recursive) |

**Extraction tasks vs synthesis tasks:**

```
Task: extract all contract dates and deadlines
  Map: each chunk returns {deadline, section, date} list
  Reduce: merge and deduplicate lists — cheap, often no model call needed

Task: summarize the entire document
  Map: each chunk returns a paragraph summary
  Reduce: synthesize paragraphs into a coherent whole — full reduce call

Task: answer "what is the termination clause?"
  Map: each chunk answers "is there a termination clause here? quote it."
  Reduce: pick the most relevant result — short reduce call
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Latency estimates based on ~50 tok/s output generation and 200ms prefill per 10k input tokens — directional only; actual varies by load. Prices: $3.00/M input, $15.00/M output.

```
=== 100-page contract (~33 250 tokens) ===

Strategy       Calls   Wall-clock   Cost
Single call      1      10.7s       $0.107
Map-reduce (5)   6      13.2s       $0.122  ← 13% premium; better attention quality

Note: single call is faster and cheaper for this size.
Use map-reduce here only when quality tests confirm the single-call approach misses content.

=== 500-page contract (~125 000 tokens) ===

Single call: fits in 200k context — $0.383/call
Map-reduce (19 chunks, parallel map + reduce): ~$0.441/call
Single call is cheaper but attention quality is lower on deeply buried content.
Choose based on quality tests for your specific task.

=== 2 000-page legal archive (~500 000 tokens) ===

Single call: FAILS — exceeds 200k context window
Map-reduce (76 chunks): wall-clock 13.4s (parallel map) + reduce
  Map: 76 × $0.021 = $1.60
  Reduce: $0.14
  Total: $1.74

Map-reduce is the only option. No alternative at this scale.

=== Parallel map speedup ===

76 chunks × 3.1s each (serial) = 235.6s
76 chunks (parallel, all concurrent) = 3.1s map + 10.0s reduce = 13.1s wall-clock
Parallel speedup: ~18x vs serial map
```

## See also

[S-52](s52-chunking-strategy.md) · [S-07](s07-rag.md) · [S-13](s13-context-engineering.md) · [S-65](s65-multi-model-pipelines.md) · [S-55](s55-parallel-tool-calls.md) · [S-21](s21-context-compaction.md)

## Go deeper

Keywords: `map-reduce` · `long document` · `document processing` · `hierarchical summarization` · `chunk and synthesize` · `context window` · `lost in the middle` · `parallel map` · `reduce synthesis` · `document summarization`
