# S-06 · Model Routing

Send each task to the model best suited for it — not the most powerful one you have.

## Forces
- Frontier models (Opus, GPT-5) cost 10–100× more per token than small models
- Most tasks don't need frontier capability; routing them there wastes money
- A single model serving all tasks creates a bottleneck and inflates cost
- Routing wrong (cheap model on a hard task) degrades quality silently

## The move

**Build a router:** a lightweight classifier (or rule set) that dispatches each request to the right tier.

**The tiers (as of mid-2026):**

| Tier | Models | Use for |
|---|---|---|
| Local | Llama 3.x, Qwen3 via Ollama | High-volume, private data, formatting, extraction |
| Small hosted | Haiku 4.5, GPT-4o-mini | Classification, simple Q&A, structured output |
| Mid hosted | Sonnet 4.6, GPT-4o | Summarization, code review, reasoning |
| Frontier | Opus 4.8, GPT-5 | Complex reasoning, planning, hard judgment calls |

**Routing signals:**
- Task type: extraction → small; multi-step reasoning → frontier
- Input length: long context → models with large windows (Claude 200K+, Gemini 1M+)
- Latency budget: streaming UI → fast small model; batch job → frontier is fine
- Data sensitivity: PII → local model only

**Minimal router (rule-based):**
```python
def route(task_type: str, token_count: int) -> str:
    if token_count > 100_000:
        return "claude-opus-4-8"          # large context
    if task_type in ("extract", "classify", "format"):
        return "claude-haiku-4-5-20251001"  # cheap and fast
    if task_type == "reason":
        return "claude-sonnet-4-6"          # balanced
    return "claude-opus-4-8"                # default to best
```

## Receipt
> Receipt pending — 2026-06-25. Model names verified against Anthropic docs as of this date. Cost ratios approximate; check current pricing at anthropic.com/pricing.

## See also
[S-01](s01-local-model-dispatch.md) · [S-05](s05-multi-agent-patterns.md) · [R-01](../frontier/r01-model-landscape.md) · [F-08](../forward-deployed/f08-agent-cost-control.md)

## Go deeper
Keywords: `model routing` · `LLM cascade` · `RouteLLM` · `FrugalGPT` · `cost optimization` · `model selection`
