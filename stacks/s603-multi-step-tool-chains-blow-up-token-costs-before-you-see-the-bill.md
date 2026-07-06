# S-603 · Multi-Step Tool Chains Blow Up Token Costs Before You See the Bill

Every LLM "thinks" between tool calls. When an agent chains 4 tools sequentially — scrape, extract, transform, save — it re-reasons after each result. A task that should cost 500 tokens of real work routinely costs 3,000–4,000. By the time you notice, you've already shipped it.

## Forces

- **Token overhead compounds invisibly.** The LLM's reasoning between steps is invisible in code review — it only shows up on the API bill. Teams discover 4–8x token inflation after production load testing.
- **Naive composition feels natural.** Sequential tool calls map directly to how humans describe workflows. The "obvious" implementation is the expensive one.
- **More agents = more reasoning overhead.** Multi-agent systems don't just multiply tool calls — they multiply the inter-step reasoning. Each agent re-evaluates context after every shared state change.
- **Prototype costs don't predict production costs.** At low volume, token bloat looks acceptable. At scale, it's the difference between a profitable service and a cost center.

## The Move

**Reduce tool-call count and strip per-call reasoning overhead through structured composition.**

- **Batch related tools into single composite calls.** Instead of `scrape → extract → transform → save` as four separate LLM round-trips, define a single `process_web_data(url, instructions)` tool that handles the full pipeline. One round-trip, one reasoning pause.
- **Use structured output modes aggressively.** When the LLM must produce JSON rather than freeform, reasoning tokens drop significantly. Force tool schemas to be exact rather than loosely described.
- **Route deterministic steps to code, not the LLM.** Validation, formatting, routing logic — these don't need LLM reasoning. Keep the model for decisions, not computation.
- **Implement semantic caching at the prompt level.** Cache the result of reasoning chains, not just retrieval results. Two identical reasoning paths should not recompute.
- **Add a step-count budget per task.** Cap the number of LLM round-trips per workflow. When the budget is exhausted, fall back to a deterministic path or escalate to a human. This is the only reliable guard against runaway loops.
- **Profile before optimizing.** Log token counts per tool-call sequence in staging. Any sequence exceeding 2x the theoretical minimum of real-work tokens is a candidate for refactoring.

## Evidence

- **Reddit (r/LocalLLaMA):** User reports running a 4-step sequential agent (scrape → extract → transform → save) where the actual token cost was 3–4x the expected 500 tokens due to LLM reasoning between each step. Identifies tool-call batching as the fix. — [r/LocalLLaMA · "Those of you running agents in production—how do you handle multi-step tool chains?" (6mo ago)](https://www.reddit.com/r/LocalLLaMA/comments/1qh8xj6/those_of_you_running_agents_in_productionhow_do/)
- **Digits.com (AI in Production 2025):** Hannes Hapke (Principal ML Engineer, 10yr experience across fintech/healthcare/retail) recommends implementing your own core agent loop rather than relying on OSS frameworks for production, specifically citing that LangChain and CrewAI introduce too many dependencies — and the implicit overhead that comes with them. — [Digits Blog · "Agents in Production: Lessons from AI in Production 2025" (July 2025)](https://digits.com/blog/ai-in-production-2025-slides)
- **Zylos Research:** Runaway agent loops have cost teams from $15 in 10 minutes to $47,000 over 11 days. 60–85% of AI spend is recoverable through prompt caching, model routing, and budget enforcement. Enterprise teams average $85,521/month in AI operational costs as of 2025. — [Zylos Research · "AI Agent Cost Engineering — Production Token Economics" (May 2026)](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)

## Gotchas

- **Cutting tool calls too aggressively loses the observability benefit.** When one tool does everything, you can't tell which step failed. Keep intermediate logging even if you merge the LLM calls.
- **Structured output doesn't always reduce tokens for reasoning-heavy tasks.** If the LLM genuinely needs to decide between 10 options at each step, forcing it into a JSON schema just adds validation overhead. Profile before and after.
- **The step-count budget is a blunt instrument.** A hard cap of 5 tool calls will kill legitimate complex tasks. Instead, budget per task type and escalate based on task complexity classification.
- **Token inflation hides in the prompt engineering phase too.** Adding more context to reduce errors increases input token costs on every call. The savings from better reasoning must exceed the per-call overhead.
