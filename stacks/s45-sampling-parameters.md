# S-45 · Sampling Parameters

Temperature, top-p, and top-k control how the model picks the next token from its predicted probability distribution. They do not change what the model knows or how it reasons — they change which of the possible completions the model actually produces. Getting them right takes one minute; leaving them at defaults and wondering why outputs are inconsistent or repetitive takes much longer.

## Situation

An extraction pipeline ships at temperature 0.7 (the common default). Two calls on the same document return "critical" and "high" for the same ticket — not because the model is uncertain about the right answer, but because 0.7 is a sampling temperature appropriate for conversational chat, not classification. Changing to 0.0 makes the output deterministic and consistent. No prompt change required.

## Forces

- Temperature controls sharpness of the distribution, not the quality of the most likely token. At T=0.1, the model almost always picks the top token. At T=1.5, alternatives are sampled frequently even when the top token has high logit. The model's "best answer" is the same — what changes is how often you get it vs alternatives.
- T=0 (greedy) is deterministic but brittle: the same input always produces the same output. This is desirable for extraction and classification; it is a problem for self-consistency ([S-24](s24-self-consistency.md)) and eval generation ([F-17](../forward-deployed/f17-synthetic-eval-generation.md)), both of which require distinct samples.
- Higher temperature does not mean better quality for most tasks. For creative or divergent tasks it does. For structured output, summarization, and factual Q&A, it adds variance — which means inconsistency, not richness.
- Top-p (nucleus sampling) is a complementary safety net for high-temperature sampling. It restricts the token pool to the smallest set whose cumulative probability exceeds p. At T=1.0 with top-p=0.9, even a token with a 0.01% probability can be sampled if it falls within the nucleus. With top-p=0.9, the model only samples from tokens that together account for 90% of the distribution — blocking the long tail of rare/incoherent tokens.
- Temperature and top-p are orthogonal. You can set T=1.0 and top-p=0.9 (full temperature, restricted nucleus). You can set T=0.3 and top-p=1.0 (sharpened distribution, no nucleus restriction). Default: set temperature for the task, add top-p as a guardrail only at T > 0.8.
- Sampling parameters do not affect token cost. A call at T=1.5 costs the same as T=0.0 with the same input and output length.

## The move

**Set temperature based on how much output variation is acceptable for the task.**

| Task | Temperature | Rationale |
|---|---|---|
| Data extraction (JSON fields) | 0.0 | Identical output required; any variation is a bug |
| Code generation | 0.1 | Mostly deterministic; small variance allows minor rephrasings |
| Classification / labeling | 0.0–0.2 | Label consistency; variation = inconsistency, not creativity |
| Summarization | 0.3–0.5 | Paraphrase variation acceptable; facts must stay stable |
| Chat / Q&A | 0.5–0.7 | Natural variation; higher adds rambling |
| Creative writing | 0.8–1.0 | Diversity valued; higher = more unexpected choices |
| Brainstorming / divergent | 1.0–1.3 | Maximum diversity; reduce if outputs become incoherent |
| Self-consistency ([S-24](s24-self-consistency.md)) | 1.0 | Must produce distinct reasoning chains; T=0 makes k identical copies |
| Eval case generation ([F-17](../forward-deployed/f17-synthetic-eval-generation.md)) | 0.9 (generate) / 0.1 (judge) | High for edge-case diversity; low for consistent judging |

**Add top-p only at high temperature:**
- T ≤ 0.7: leave top-p at 1.0 (disabled) — the distribution is already shaped by temperature
- T > 0.8: add top-p = 0.9–0.95 to prevent rare-token sampling from the long tail
- Never use top-p < 0.5 — you're collapsing the distribution more than temperature alone would

**Top-k** (restrict to k most likely tokens) is rarely needed alongside top-p. If you find yourself tuning both, you're over-engineering: pick one. Top-p is usually the right choice since it adapts to the distribution shape rather than imposing a fixed count.

**Do not use temperature to "improve quality."** Temperature does not make the model smarter. The model's best prediction is the same at any temperature — temperature only controls how often you get the best vs other predictions. If quality is the problem, fix the prompt, add examples ([S-44](s44-few-shot-example-selection.md)), or upgrade the model.

**Reasoning models ignore temperature.** Claude Opus with extended thinking, o3, and similar reasoning models perform internal sampling during their reasoning step. Setting temperature on the final output has little effect. Leave at default.

## Receipt

> Verified 2026-06-26 — Node.js. Temperature effect modeled from the softmax formula (exact, no LLM calls): logits for a 5-token distribution, softmax applied at each temperature. Token costs are identical at any temperature (sampling happens after the logit computation; it does not change input/output count).

```
=== Softmax temperature effect on next-token distribution ===
(Illustrative logits for tokens: "42"=3.8, "forty-two"=2.1, "unknown"=1.2, ...)

Token        T=0.1    T=0.7    T=1.0    T=1.5
42           100.0%   88.1%    74.5%    57.5%   ← top token
forty-two      0.0%    7.8%    13.6%    18.5%
unknown        0.0%    2.1%     5.5%    10.2%
unclear        0.0%    1.4%     4.1%     8.3%
N/A            0.0%    0.6%     2.2%     5.6%

At T=0.1: top token wins 100% — functionally greedy
At T=1.0: top token wins 74.5% — alternatives sampled ~1 in 4 calls
At T=1.5: top token wins 57.5% — alternatives sampled ~4 in 10 calls

Top-p at T=1.0: top 2 tokens cover 88% of probability mass.
  top-p=0.9 → sample from top 2 tokens only (blocks the low-prob tail)
  top-p=1.0 → any token eligible (including N/A at 2.2%)
```

The practical takeaway: for extraction at T=0.7, the "wrong" label is sampled 1 in 4 calls. Dropping to T=0.0 makes it deterministic. For brainstorming, T=0.0 gives the same starting point every time — not what you want. Temperature is the dial; the task determines where to set it.

## See also

[S-24](s24-self-consistency.md) · [S-16](s16-prompting.md) · [F-17](../forward-deployed/f17-synthetic-eval-generation.md) · [S-04](s04-structured-output.md) · [R-02](../frontier/r02-reasoning-models.md)

## Go deeper

Keywords: `temperature` · `top-p` · `nucleus sampling` · `top-k` · `sampling strategy` · `greedy decoding` · `softmax temperature` · `LLM sampling` · `stochastic generation`
