# S-47 · Output Length Control

Output tokens cost 4–5× more than input tokens. The model's default response length is calibrated for helpfulness, not economy. Without an explicit constraint, a ticket classification that should be one word ("high") arrives as 137 tokens of reasoning and reassurance. That costs 23× more than it needs to.

## Situation

A ticket-routing system calls the model 10,000 times per day to classify priority. No length constraint is set. The model answers thoroughly — it explains its reasoning, hedges with context, and offers to clarify. Monthly cost: $636. Adding `max_tokens: 5` to the API call: $24/month. Same answer, 26× less output.

## Forces

- Output token price is asymmetric. At typical 2026 pricing, input tokens cost ~$3/M and output tokens cost ~$15/M. Every extra word in the model's response costs 5× more than the same word in the prompt. Reducing output length is the fastest cost lever for high-call-volume pipelines.
- The model cannot self-regulate output length without instruction. Instruction-tuned models are fine-tuned to be helpful, which correlates with being thorough. "Be concise" helps but does not enforce — the model may still add a preamble or closing acknowledgment.
- Three mechanisms have different enforcement characteristics. Prompt constraints are soft (the model usually complies but can deviate). `max_tokens` is a hard API-level ceiling (the model cannot exceed it — but it truncates without knowing the limit was hit, potentially mid-sentence). Structured output via tool use ([S-04](s04-structured-output.md)) is schema-bounded — the schema itself limits what can be in the response.
- Over-instruction inflates output. Adding more explanation of the desired format ("Please provide a JSON object with the following structure...") generates a longer response than a terse instruction ("Return only: {priority: ...}"). Verbosity in the prompt teaches verbosity in the response.
- LLM judges prefer longer outputs ([F-12](../forward-deployed/f12-llm-as-a-judge.md)). This creates a hidden incentive when using LLM-as-judge to evaluate your agent: longer responses score higher regardless of quality. Control for this by adding a conciseness criterion to the judge rubric.

## The move

**For each call, ask: what is the minimum output that serves the task? Constrain to that.**

**Three mechanisms — pick by task:**

| Task | Mechanism | Example |
|---|---|---|
| Classification / labeling | `max_tokens` | `max_tokens: 5` — can't exceed a single label |
| Structured extraction | Structured output (S-04) | Tool schema defines allowed keys; output is schema-bounded |
| Summarization with length target | Prompt constraint + `max_tokens` | "Summarize in ≤3 sentences" + `max_tokens: 150` |
| Open Q&A (variable length needed) | Prompt constraint only | "Answer in 2-3 sentences" |

**Prompt constraints — effective phrasing:**
- "Return only the priority label: critical, high, medium, or low." — explicit label list prevents prose
- "Answer in ≤20 words." — word count (not token count, but close enough at this scale)
- "One sentence only." — structural constraint the model understands
- Avoid: "Be concise." — too vague; model interprets differently each call

**`max_tokens` for classification and extraction:**
```js
const response = await client.messages.create({
  model: 'claude-haiku-4-5',
  max_tokens: 5,   // hard ceiling — one label or one short phrase
  messages: [{ role: 'user', content: classifyPrompt }]
});
// If output is 5 tokens exactly, check if it was truncated:
// response.stop_reason === 'max_tokens' → truncated
// response.stop_reason === 'end_turn'   → natural completion
```

**Structured output for extraction pipelines:**
Define a tool whose schema only allows the fields you need. The model cannot add prose outside the schema. Token cost = schema overhead (cacheable after first call) + field values only. See [S-04](s04-structured-output.md).

**Check `stop_reason` when using `max_tokens`.** If `stop_reason === 'max_tokens'`, the output was cut short — not complete. For critical extractions, treat this as a failure and retry with a larger budget or reformatted prompt.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Five response styles for the same ticket classification task; responses are illustrative but token counts are real measurements. Pricing: $3/M input, $15/M output (mid-market 2026).

```
=== Output length control: ticket classification (10k calls/day) ===
Prompt: 22 tokens. Correct answer: "high"

Style                            out_tok   cost/1k-calls   monthly@10k/day
No constraint (default)             137      $2.12           $636
"Be concise"                         32      $0.55           $164
"≤20 words" constraint               17      $0.32            $96
"Return the label only"               1      $0.08            $24
Structured output (JSON label)        6      $0.16            $47

Savings from no-constraint → label-only: $612/month

Mechanism comparison:
  Prompt constraint  — soft; model usually complies; zero API overhead
  max_tokens: 5      — hard; truncates at ceiling; stop_reason=max_tokens on truncation
  Tool/schema output — schema-bounded; setup cost cacheable; best for structured pipelines
```

The 137-token default vs 1-token label gap is real and observable in production. The model's training incentivizes thoroughness; the application's economics require brevity. The constraint bridges the gap.

## See also

[S-04](s04-structured-output.md) · [S-35](s35-latency-budget.md) · [F-08](../forward-deployed/f08-agent-cost-control.md) · [F-12](../forward-deployed/f12-llm-as-a-judge.md) · [S-36](s36-system-prompt-architecture.md)

## Go deeper

Keywords: `output length` · `max_tokens` · `token cost` · `response length control` · `concise output` · `stop_reason` · `output truncation` · `verbosity` · `classification prompt`
