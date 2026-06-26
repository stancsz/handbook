# R-01 · Model Landscape

What models exist, what they cost, and what they're actually good for. **Last verified: 2026-06-25. This entry decays fast — check current pricing before using these numbers.**

## Forces
- The model landscape changes monthly; any fixed list is out of date
- Marketing claims and benchmark scores don't predict performance on your task
- Cost per token has fallen ~90% since 2023 — yesterday's pricing is misleading
- Picking the wrong tier wastes money or quality; the right tier depends on the task

## The move

**The categories (mid-2026):**

### Frontier hosted (best reasoning, highest cost)
| Model | Provider | Strength |
|---|---|---|
| Claude Opus 4.8 | Anthropic | Complex reasoning, long context (200K+) |
| GPT-5 | OpenAI | General frontier, strong tool use |
| Gemini 2.x / 3.x | Google | Very large context window (1M+), multimodal |

### Mid-tier hosted (best value for most tasks)
| Model | Provider | Strength |
|---|---|---|
| Claude Sonnet 4.6 | Anthropic | Balanced quality/cost, 200K context |
| GPT-4o | OpenAI | Fast, multimodal, strong reasoning |
| Gemini 2.0 Flash | Google | Fast, cheap, large context |

### Small/fast hosted (cheapest, good for extraction/classification)
| Model | Provider | Strength |
|---|---|---|
| Claude Haiku 4.5 | Anthropic | Fastest Claude, very cheap |
| GPT-4o-mini | OpenAI | Cheap, fast |

### Open-source frontier (self-hostable, no per-token cost)
| Model | Strength |
|---|---|
| Llama 4.x (Meta) | Strong open-source general model |
| Qwen3 (Alibaba) | Strong code and reasoning |
| DeepSeek-V3.x | Competitive with frontier on benchmarks |

**How to pick:** See [S-06 Model Routing](../stacks/s06-model-routing.md).

**Reality check:** Benchmarks measure benchmark performance. Run your actual task on 20–50 representative examples before committing to a model for production. A model that tops MMLU may underperform on your specific use case.

## Receipt
> Sourced from public documentation, Anthropic/OpenAI/Google release notes, and the web research performed 2026-06-25. Model names and capabilities are accurate as of that date. Pricing: check anthropic.com/pricing, openai.com/pricing, cloud.google.com/vertex-ai/pricing directly — do not use numbers from this entry for budgeting.

## See also
[S-06](../stacks/s06-model-routing.md) · [R-02](r02-reasoning-models.md) · [R-03](r03-fine-tuning-vs-prompting.md) · [F-14](../forward-deployed/f14-reading-agent-benchmarks.md)

## Go deeper
Keywords: `LLM leaderboard` · `LMSYS Chatbot Arena` · `Hugging Face Open LLM Leaderboard` · `model benchmarks` · `MMLU` · `HumanEval`
