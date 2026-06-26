# F-17 · Synthetic Eval Generation

You need 50 labeled test cases before you can ship a prompt change with confidence. Writing them by hand takes hours — and you'll write cases you've already thought of, missing the failures waiting in production. An LLM can generate edge cases you haven't imagined, on demand, at any scale.

## Forces

- Hand-crafted evals reflect what you expect to fail; edge cases you haven't thought of are exactly what you miss
- Real production traffic is sparse at launch — you don't have enough labeled examples to validate a new prompt version against
- At scale, manual labeling is impractical; an eval suite needs hundreds of cases for statistical power on small quality differences
- LLM-generated data can be mislabeled or nonsensical; adding bad cases to your suite is worse than having fewer cases
- Synthetic data should not crowd out real production failures — actual failures are the ground truth; synthetic fills the gaps

## The move

**Generate → Filter → Add to suite.**

**1. Generate with an explicit edge-case instruction.**

```
Generate 20 test cases for [task]. Label schema: [labels].
Requirements:
- At least 4 "hard" cases: ambiguous, multi-intent, or unusual phrasing
- At least 2 non-English or informal messages
- Vary length: some 1 sentence, some 3–4 sentences
Return ONLY a JSON array: [{"input": "...", "label": "...", "difficulty": "easy|medium|hard"}]
```

Temperature 0.8–1.0. Higher temperature = more diversity = more edge cases surfaced. Structure the output as JSON so filtering is mechanical.

**2. Filter each case with a second LLM call.**

```
Ticket: "{input}"  Assigned label: {label}  Valid labels: [...]
Is this case realistic and correctly labeled?
Return JSON: {"keep": true/false, "reason": "...", "corrected_label": "..."}
```

Temperature 0.1 for the filter — you want a consistent judge, not a creative one. Cases that fail or get relabeled are still useful: the relabeled ones can be corrected, the rejected ones reveal what the generation prompt needs fixing.

**3. Add to suite alongside real examples.** Keep a ratio: aim for no more than 50% synthetic. When production failures accumulate, they promote ahead of synthetic cases.

## Receipt

> Verified 2026-06-26 — llama3.2 via Ollama (localhost:11435). Task: classify customer support ticket intent (5 labels). Generate 5 cases, filter each with a second call.

```
Step 1 — Generation (temperature=0.9)
  Tokens: in=2,678  out=335
  Output: 5 cases — 2 easy, 2 medium, 1 hard
  Includes Spanish-language ticket and a hard ambiguous case
  (duplicate charge + app crash + refund consideration)

Step 2 — Filter (5 calls at temperature=0.1)
  Tokens: 13,613 across 5 calls (~2,723 per call)
  Result: 5 kept, 0 rejected, 0 corrected

Total cost ratio: filter consumed 4.5× the tokens of generation.
```

**Three findings:**

1. **Filter costs dominate.** At 5 cases, filter tokens (13,613) dwarfed generation (3,013). At scale, batch filtering or a smaller judge model is the right optimization — not cutting the filter.

2. **The hard case held up.** Case 5 ("charged twice, app crashing, considering refund") was genuinely ambiguous. The filter correctly identified `refund_request` as the primary intent. At N=5, all cases passed — in real use at N=50+, expect ~10–20% rejection or correction rate.

3. **Non-English appeared without prompting.** The Spanish ticket emerged naturally from the edge-case instruction. Without explicit instruction, diversity collapses toward the training distribution's majority language and phrasing.

## See also

[F-07](f07-evaluation-driven-development.md) · [F-12](f12-llm-as-a-judge.md) · [F-02](f02-evaluation-at-scale.md) · [S-04](../stacks/s04-structured-output.md) · [S-24](../stacks/s24-self-consistency.md)

## Go deeper

Keywords: `synthetic eval data` · `LLM test case generation` · `eval suite construction` · `Distilabel` · `DeepEval` · `model collapse` · `LLM-as-a-judge` · `temperature diversity`
