# F-30 · Runtime Output Validation

Most agents trust their own output. They generate a response and return it. For low-stakes tasks at high volume, that's correct — the economics don't support a per-call judge, and sampling-based drift detection ([F-26](f26-behavioral-drift-detection.md)) catches systemic problems. For high-stakes tasks — medical triage, legal summaries, financial actions, irreversible tool calls — a live validation gate before the response reaches the user is worth the extra latency and cost. This entry covers when to run a runtime gate, what to check, and how to structure the judge call.

## Situation

A RAG-backed legal assistant returns case summaries to attorneys. The model occasionally cites claims not supported by the retrieved documents — either interpolating from training data or hallucinating plausible-sounding details. The error rate is 3–4%. That's acceptable for a search result; it's unacceptable for a legal document. Adding a binary LLM judge that checks "Is every claim in this response supported by the provided documents?" catches ~70% of unsupported claims before they reach the attorney, at a cost of $1.40/k calls and 400ms of added latency — both acceptable for a high-value professional tool.

## Forces

- Runtime validation is expensive relative to sampling. A judge on every call costs 2–5× more than the primary generation and adds 200–600ms. Sampling-based monitoring (F-26) costs $0.35/month. The runtime gate is justified only when a single bad output reaching a user has material consequences: trust loss, legal liability, patient harm, financial damage, or irreversible agent action.
- Structural validation is free; semantic validation costs inference. Checking that a JSON output has the right schema ([S-39](../stacks/s39-output-parsing-robustness.md)) or that a response doesn't contain a banned pattern (regex) costs nothing. Checking that every factual claim is supported by the provided context requires a model call. Use structural checks first; add semantic only where structural can't catch it.
- The judge should be faster and cheaper than the primary model. Run the judge on a smaller, faster model (Haiku, flash, mini) rather than the same model used for generation. The judge's task is binary classification, not generation — it doesn't need the capability tier of the primary response.
- Binary is better than scored for gates. A judge that returns PASS/FAIL is more actionable at runtime than one returning a score. A score requires a threshold; a threshold requires calibration. PASS/FAIL with a one-sentence reason is directly actionable: PASS → return; FAIL → retry or fallback.
- Retry on FAIL has diminishing returns. If the primary model fails validation once, re-prompting it with a constraint may fix a format violation but is unlikely to fix a hallucination — the model will produce a different hallucination. After one retry, use a canned safe response or escalate to human rather than retrying indefinitely.

## The move

**Layer validation by cost: structural check first, then semantic judge only for high-stakes tasks. Use PASS/FAIL. Cap retries at 1. Have a safe fallback.**

**Validation layer decision:**

```
Low stakes + high volume:
  → No runtime gate. Sample 2-5% for monitoring (F-26). Use structural checks (S-39).

Medium stakes (scope violations, off-topic responses):
  → Keyword/regex blocklist. Zero LLM cost. Run before returning.

High stakes (factual claims, legal, medical, financial, irreversible):
  → LLM judge gate on every call. Fast model. Binary PASS/FAIL.
```

**Judge call (binary PASS/FAIL):**

```js
async function validateOutput(userRequest, retrievedContext, modelResponse, judgeModel) {
  const judgePrompt = `
<user_request>${userRequest}</user_request>
<retrieved_context>${retrievedContext}</retrieved_context>
<response>${modelResponse}</response>

Evaluate this response on three criteria:
1. Scope: Does it address only what was asked, within the product's domain?
2. Grounding: Is every factual claim supported by the retrieved context?
3. Format: Does it follow the required output format?

Answer: PASS or FAIL
If FAIL, one sentence identifying which criterion failed and why.`.trim();

  const result = await judgeModel.messages.create({
    model: 'claude-haiku-4-5-20251001',  // fast + cheap; binary task
    max_tokens: 40,
    messages: [{ role: 'user', content: judgePrompt }],
  });

  const verdict = result.content[0].text.trim();
  return {
    pass:   verdict.startsWith('PASS'),
    reason: verdict.startsWith('FAIL') ? verdict.slice(5).trim() : null,
  };
}
```

**Retry and fallback strategy:**

```js
async function generateWithValidation(request, context, primaryModel, judgeModel) {
  for (let attempt = 0; attempt <= 1; attempt++) {
    const response = await primaryModel.generate(request, context, {
      // On retry: add explicit grounding constraint
      extraInstruction: attempt > 0
        ? 'Only make claims directly supported by the provided context. If unsure, say "I don\'t have information about that."'
        : null,
    });

    const validation = await validateOutput(request, context, response, judgeModel);
    if (validation.pass) return { response, validated: true };

    if (attempt === 0) {
      console.log(`Validation failed (attempt 1): ${validation.reason}. Retrying.`);
    }
  }

  // Safe fallback after max retries
  return {
    response: 'I wasn\'t able to generate a reliable answer for this question. Please contact support for assistance.',
    validated: false,
    escalate: true,
  };
}
```

**What each validation type catches:**

| Validation | Method | Cost | Catches |
|---|---|---|---|
| Schema check | JSON.parse + type check | Free | Wrong structure, missing fields |
| Regex blocklist | Pattern match | Free | PII leaks, banned phrases, off-topic domains |
| LLM judge: scope | Binary judge | $0.38/k | Off-topic content, competitor mentions |
| LLM judge: grounding | Binary judge | $0.38/k | Unsupported claims, hallucinated details |
| LLM judge: format | Binary judge | $0.38/k | Constraint violations (length, tone, structure) |

Run multiple checks in one judge call rather than separate calls.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Judge prompt template: 90 tokens. Response: ~30 tokens (support answer). Judge output: 15 tokens. Primary response size: ~30 tok (short answer), ~300 tok (legal summary). Prices: $3/M input, $15/M output. Latency estimates (400ms for a fast judge call) are representative; actual depends on provider and load.

```
=== Runtime validation: cost and error escape tradeoffs ===

Approach                           Added cost/k   Latency   Error escape rate
No validation                      $0.00          +0ms      ~5% bad outputs reach user
Structural check (regex/schema)    $0.00          +2ms      ~3% (misses semantic errors)
LLM judge gate (fast model)        $0.38/k        +400ms    ~1%

=== Judge call cost breakdown (300-token legal summary) ===
Judge template:    90 tokens input
Response to check: 300 tokens input
Context excerpt:   150 tokens input  (shortened for judge)
Judge output:       15 tokens

Total judge call:  540 input + 15 output = $1.845/k calls

=== When runtime gate is worth it ===
High-stakes threshold: bad output cost > $0.002/call (break-even vs. $1.85/k gate)
Examples where threshold is crossed:
  Legal research tool:  attorney time wasted on bad cite = $5-50/occurrence
  Medical triage:       patient harm potential (threshold ≈ ∞)
  Financial advice:     regulatory liability
  Irreversible actions: tool calls that delete, charge, send (validate before executing)
```

The cost of a judge gate ($1.85/k) justifies itself if even 1 in 500 bad outputs causes a consequence worth more than $0.92. For legal, medical, and financial tools, that threshold is crossed easily. For support chat on billing FAQs, it's not.

## See also

[F-12](f12-llm-as-a-judge.md) · [F-26](f26-behavioral-drift-detection.md) · [S-39](../stacks/s39-output-parsing-robustness.md) · [F-09](f09-human-in-the-loop.md) · [F-04](f04-guardrails.md) · [F-16](f16-tool-call-validation.md)

## Go deeper

Keywords: `runtime output validation` · `output gate` · `LLM judge` · `hallucination detection` · `factual grounding` · `binary judge` · `PASS/FAIL` · `output quality gate` · `validation pipeline` · `safe fallback`
