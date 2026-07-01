# S-319 · Agent Token Cost Engineering: From Runaway Loops to Controlled Spend

Production AI agents have become significant cost centers. Model API spend doubled from $3.5B to $8.4B between late 2024 and mid-2025, with average enterprise AI operational costs hitting $85,521/month. The problem is not that agents are expensive — it's that most teams have no cost controls until they discover one burning $47,000 over eleven days.

## Forces

- **Agents loop in ways chatbots don't.** A chatbot fails silently; an agent that calls a tool, re-reads its output, and loops can generate thousands of requests per hour. The cost compounds in multi-agent systems where each agent independently calls models.
- **Context growth is non-linear.** Every turn, every tool result, every retrieved document gets added to context. Long-horizon agents can eat 10x the tokens of the equivalent chatbot for the same task.
- **Multi-agent workflows multiply cost without obvious feedback.** A 4-agent hierarchical workflow at $5-8/complex task sounds fine in isolation; at 10,000 tasks/day it becomes a $50-80K/day budget item.
- **60-85% of token spend is recoverable** — but only if you engineer for it from the start, not after the first shock.

## The move

### Circuit breakers and hard budget limits

- **Set per-request token budgets** at the API level, not just in the prompt. Use max_tokens and context window limits as hard guards.
- **Implement iteration caps** (max 10 tool calls, max 3 re-tries) on every agent loop. This is the single highest-ROI change you can make.
- **Rate-limit at the orchestration layer** with token-per-minute ceilings. Tools like Helicone and Braintrust support budget alerts; custom implementations use Redis-based token counters.

### Model routing by task complexity

- Route trivial operations (classification, title generation, simple formatting) to cheap models: Gemini 2.0 Flash Lite ($0.08/M input) or Haiku 4.5 ($1.00/M input).
- Reserve Opus 4.6 ($5.00/M input) and GPT-4o for complex reasoning, multi-step planning, and creative synthesis.
- Self-hosted 14B-class models ($0.004/M tokens) are viable for high-volume, low-complexity tasks that don't require frontier reasoning.

### Prompt caching as first-line defense

- Anthropic's cached prompt feature provides 90% cost reduction on repeated system prompts — apply to any agent with a stable system prompt.
- Cache tool schemas and instruction blocks; only pass dynamic user context and retrieved documents as uncached tokens.
- GitHub's Copilot API and OpenAI's cached completions offer similar mechanics.

### Stopping early — teach agents to quit

- Explicitly instruct agents: "If you have sufficient information to answer, stop researching." This prevents the "one more search" spiral.
- Implement confidence thresholds: if top-3 retrieval results have >85% relevance score, stop retrieval and generate.
- Use structured output (JSON schemas) to bound output length rather than relying on the model to self-limit.

### Caching tool call results

- If the same API/resource was called within the last N minutes with identical parameters, return the cached result. This skips both LLM cost and external API cost.
- For multi-agent systems: shared tool-result caches prevent redundant calls when multiple agents query the same data source.

## Evidence

- **Engineering blog / Zylos Research:** Enterprise AI operational costs average $85,521/month as of 2025, with 60-85% of spend recoverable through prompt caching, model routing, and budget enforcement. Runaway agent loops have cost teams $15 in ten minutes to $47,000 over eleven days. — [Zylos AI Research](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)
- **AI in Production 2025 / Digits:** Open-source frameworks (LangChain, CrewAI) are great for prototyping but introduce cost unpredictability. Production-grade agents need infrastructure-level cost controls baked in from day one. Hannes Hapke (Principal ML Engineer, Digits) recommends treating agents as "process daemons" — emphasizing reliability and cost predictability over autonomy theater. — [Digits Blog](https://digits.com/blog/ai-in-production-2025-slides)
- **RaftLabs:** Four-agent multi-agent workflows cost $5-8 per complex task in inference costs. 57% of organizations already have agents in production, and 40% of agentic AI projects are at risk of cancellation by 2027 — cost overruns are a primary driver. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- **Prompt caching requires identical input prefixes.** Dynamic user content breaks the cache. Structure prompts so the stable instruction block (which gets cached) is prepended to the variable portion.
- **Max_tokens is not a budget cap.** Setting max_tokens=1000 doesn't prevent the model from using 900 tokens of context on the input side before generating. Budget enforcement needs to happen at the orchestration level, not just the API level.
- **Multi-agent cost stacks invisibly.** Each agent independently accumulates context. A "cheap" researcher agent at $0.02/task can cost $200/day at 10K tasks when multiplied across a 4-agent pipeline with shared orchestration overhead.
- **Stopping early breaks user trust if done poorly.** Agents that quit after 2 tool calls when the user expects thoroughness will be overridden. Make the stopping threshold configurable and tied to task type.
