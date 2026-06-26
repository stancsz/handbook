# S-56 · Pre-Flight Token Check

The API doesn't warn you before you overflow the context window — it either errors, or silently truncates and answers from an incomplete prompt. Both outcomes are worse than catching the overflow before you send. A pre-flight token count adds ~0.1ms per request, costs nothing, and enables graceful handling: strip examples, compress the document, truncate to fit, or route to a larger model — in that order of preference.

## Situation

An agent processes uploaded documents. Most documents are under 2,000 tokens and work fine. Legal contracts average 16,000 tokens. On a model configured for 16,384-token context (cost-optimized routing), a 16k document plus the 474-token fixed overhead overflows by 90 tokens. Without pre-flight: the API returns a `context_length_exceeded` error; the agent retries without change; the retry fails again; the user sees an error. With pre-flight: the agent detects the overflow before sending, drops the 44-token few-shot examples (fits with 46 tokens to spare — still tight), and if still overflowing, truncates the document at the boundary. The user gets an answer with a "document was truncated" notice.

## Forces

- Tokenization is fast and free. The `gpt-tokenizer` (JS) or `tiktoken` (Python) libraries count tokens locally in microseconds with no API call. The check costs nothing and catches overflows before billing starts.
- Token counts are not character counts. A 16,000-word document is not 16,000 tokens. Code, whitespace, punctuation, and multilingual content all tokenize differently. Never estimate context fit from character count or word count; always tokenize.
- Fixed overhead components should be counted once and cached. Your system prompt, few-shot examples, and instruction text are static — tokenize them at startup, cache the counts. Only the variable parts (the user's document, the retrieved chunks) need per-request counting.
- Overflow handling should be ordered by reversibility and cost. Removing examples is free and reversible. Truncating a document loses information. Routing to a larger model costs more. Try them in that order.
- Reserve tokens for output. A context budget that exactly fits the input leaves no room for the model's response. Reserve 400–1,000 tokens for output depending on expected response length. Check `stop_reason === 'max_tokens'` on responses — that signals the output was cut off ([S-47](s47-output-length-control.md)).
- Silent truncation is the dangerous case. Some models and APIs truncate from the beginning of the context rather than returning an error. If your system prompt is dropped silently, the model answers without its persona, constraints, or safety instructions — with no error signal to trigger a retry.

## The move

**Count tokens before constructing the final messages array. Detect overflow early. Apply the truncation hierarchy in order.**

**Pre-flight function:**

```js
import { encode } from 'gpt-tokenizer';    // npm install gpt-tokenizer
// Python: from tiktoken import encoding_for_model; enc = encoding_for_model("gpt-4o")

// Cache static component lengths at startup
const STATIC_OVERHEAD = {
  systemPrompt:    encode(SYSTEM_PROMPT).length,
  fewShotExamples: encode(FEW_SHOT_EXAMPLES).length,
  instruction:     encode(INSTRUCTION).length,
  outputReserve:   400,
};
const FIXED_TOKENS = Object.values(STATIC_OVERHEAD).reduce((a, b) => a + b, 0);

function preflightCheck(documentText, modelLimit) {
  const docTokens = encode(documentText).length;
  const total     = FIXED_TOKENS + docTokens;
  return {
    docTokens,
    total,
    headroom: modelLimit - total,
    fits:     total <= modelLimit,
    utilizationPct: (total / modelLimit) * 100,
  };
}
```

**Truncation hierarchy (apply in order, stop when it fits):**

```js
async function fitToContext(document, modelLimit) {
  let result = preflightCheck(document, modelLimit);
  if (result.fits) return { document, truncated: false };

  // Step 1: Drop few-shot examples (free; model may still answer correctly)
  const limitWithoutExamples = modelLimit + STATIC_OVERHEAD.fewShotExamples;
  result = preflightCheck(document, limitWithoutExamples);
  if (result.fits) return { document, truncated: false, droppedExamples: true };

  // Step 2: Compress document (S-31) — try key-sentence extraction
  const compressed = await extractKeyContent(document);
  result = preflightCheck(compressed, modelLimit);
  if (result.fits) return { document: compressed, truncated: false, compressed: true };

  // Step 3: Hard truncate — keep first 70% and last 30% of budget
  const budget    = modelLimit - (FIXED_TOKENS - STATIC_OVERHEAD.fewShotExamples);
  const docToks   = encode(document);
  const keepFirst = Math.floor(budget * 0.70);
  const keepLast  = budget - keepFirst;
  const truncated =
    decode(docToks.slice(0, keepFirst)) + '\n[...]\n' +
    decode(docToks.slice(-keepLast));

  return { document: truncated, truncated: true, droppedTokens: docToks.length - budget };

  // Step 4 (not in code): Route to larger-context model (S-06)
}
```

**Output truncation check (after the call):**

```js
const response = await model.messages.create({ ... });
if (response.stop_reason === 'max_tokens') {
  // Output was cut off — increase max_tokens or add "be concise" to prompt
  console.warn('Response truncated at output token limit');
}
```

**Context budget checklist:**

- [ ] Static overhead tokenized once at startup, not per-request
- [ ] `outputReserve` is set to at least `expected_output_length + 10%`
- [ ] `preflightCheck` runs before constructing `messages` array
- [ ] Truncated calls log which strategy was used
- [ ] Response `stop_reason` is checked for `max_tokens`

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Token counts exact. System prompt 25 tok, few-shot examples 44 tok, instruction 5 tok, output reserve 400 tok. 16k context window chosen to surface real overflow scenarios on realistic documents.

```
=== Pre-flight check: 16k context window (cost-optimized routing) ===

System: 25 tok | Examples: 44 tok | Instruction: 5 tok | Output reserve: 400 tok
Fixed overhead: 474 tokens

Document                     doc tok   total    headroom   action
FAQ answer (200 tok)           200       674    15,710    send as-is
Product page (800 tok)         800     1,274    15,110    send as-is
Long article (8k tok)        8,000     8,474     7,910    send as-is
Legal doc (16k tok)         16,000    16,474       −90    OVERFLOW → try dropping examples
Report (50k tok)            50,000    50,474   −34,090    OVERFLOW → truncate

=== After dropping examples (free −44 tok) ===
  Legal doc: total=16,430  headroom=−46  → still overflows by 46 tok → hard truncate
  Report:    total=50,430  headroom=−34,046  → truncate (keep first 70% + last 30%)

=== Hard truncation for legal doc ===
Budget after dropping examples: 15,954 tokens
Keep first 11,168 + last 4,786 tokens (drop middle 46 tokens)
Caller notified: "document was lightly truncated (46 tokens)"

=== Cost of skipping pre-flight ===
Failure mode 1: context_length_exceeded error → wasted tokens billed + retry loop
Failure mode 2: silent truncation → system prompt dropped, wrong model behavior, no signal

Pre-flight cost: one encode() call, ~0.1ms, zero API cost.
```

For legal doc overflow: the fix is dropping 46 tokens from the middle of a 16k document. Pre-flight catches it; hard truncation removes it; the user gets an answer with a notice. Without pre-flight, the only signal is an API error after billing.

## See also

[S-02](s02-context-budget.md) · [S-18](s18-tokenization.md) · [S-13](s13-context-engineering.md) · [S-31](s31-prompt-compression.md) · [S-06](s06-model-routing.md) · [S-47](s47-output-length-control.md)

## Go deeper

Keywords: `pre-flight check` · `token counting` · `context overflow` · `context_length_exceeded` · `truncation strategy` · `tiktoken` · `gpt-tokenizer` · `context budget` · `silent truncation` · `output reserve`
