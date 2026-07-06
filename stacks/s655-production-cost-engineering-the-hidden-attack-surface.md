# S-655 · Production Cost Engineering: The Hidden Attack Surface

AI agents that cost $200/month in demos have sent teams $47,000 bills in eleven days. Cost is not an infrastructure concern to add later — it is a correctness concern that belongs in the agent loop from day one.

## Forces

- **Agents optimize for the goal, not the budget.** A loop that re-retries a failed API call 200 times will complete the task correctly and bankrupt you doing it.
- **Context repetition is the silent cost multiplier.** Every agent turn re-sends the full conversation history. Long-horizon tasks compound token costs quadratically unless you actively truncate.
- **Enterprise AI spend is doubling yearly.** Model API spend grew from $3.5B to $8.4B between late 2024 and mid-2025. The median enterprise now spends $85,521/month on AI operations — and most have no idea where it goes.
- **Prompt caching is underused.** Anthropic, OpenAI, and Google offer prompt caching that reduces repeated prefix costs by 60–90%. Most teams discover this only after their first bill shock.
- **The circuit breaker is now standard practice.** After a wave of runaway agent incidents, the pattern has moved from optional to baseline: teams that skip it learn why the hard way.

## The Move

Treat cost as a first-class agent invariant, not a FinOps afterthought.

### 1. Instrument before you optimize

Every agent loop should emit structured cost events: input tokens, output tokens, model used, tool calls made, and cumulative session cost. This is not optional — without it, you cannot distinguish a cost anomaly from a correctness anomaly. LangSmith, Phoenix, or custom JSON logging to a time-series DB are all valid. Pick one and wire it in before the first user-facing call.

### 2. Add circuit breakers at three levels

- **Per-turn budget:** Hard cap on tokens consumed in a single LLM call (e.g., 8K output tokens max). Catches malformed responses and runaway generation.
- **Per-session budget:** Cumulative spend cap for a single agent session (e.g., $5). Catches loops and unbounded re-retries.
- **Per-tool budget:** Limits on expensive tools — API calls, document fetches, search queries. A web search tool that loops 50 times in a session is a circuit breaker problem, not a prompt problem.

### 3. Route models by task complexity

Use the right model for the step. Haiku-class models handle classification, routing, and simple extraction at roughly 1/5 the cost of Sonnet/Opus. Route boring decisions to cheap models; reserve expensive models for synthesis and judgment. This is not speculative — Zylos Research reports teams recovering 40–60% of spend through routing alone.

| Task | Recommended Model Tier | Rationale |
|---|---|---|
| Intent classification | Haiku / GPT-4o-mini | High-volume, low-stakes decisions |
| Tool selection | Sonnet / GPT-4o | Moderate reasoning cost |
| Final synthesis / judgment | Opus / GPT-4o | Expensive but non-negotiable for quality |
| Code generation | Opus / Claude 3.5 Sonnet | Reliability worth the premium |

### 4. Structure prompts for cache hits

Prompt caching works when the prefix (system prompt, instructions, retrieved context) stays identical across calls. Structure your prompts so the static parts are up front and the variable parts (user query, retrieved chunks) come later. This is a prompt architecture decision — retrofitting it costs more than designing it in.

### 5. Set hard budget enforcement, not soft alerts

A Slack alert at 80% of budget is not a circuit breaker. It assumes a human is watching. Set automatic hard stops: when a session hits its budget cap, the agent returns a graceful error, not "let me try one more time." The alert is for post-mortem analysis, not prevention.

## Evidence

- **Engineering blog (Google):** The AI Agent Clinic's "Titanium" refactor replaced a monolithic sales agent with sub-agents, each with hard timeout and failure budgets. The original had no cost controls and silently accumulated API spend across re-tries. — [Google Developers Blog, April 2026](https://developers.googleblog.com/production-ready-ai-agents-5-lessons-from-refactoring-a-monolith)
- **Research report (Zylos):** Documented runaway agent incidents ranging from $15 in 10 minutes to $47,000 over 11 days. Reports 60–85% of enterprise AI spend is recoverable through caching, routing, and budget enforcement. Enterprise median spend: $85,521/month. — [Zylos Research, May 2026](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/)
- **Developer post (Calder):** A student-matching agent demoed at 92% success rate with $200/month budget. Production reality: 55% success, $847/month actual spend, 47 distinct data format issues. — [Calder's Lab, January 2025](https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/)
- **Guardrails guide (Gheware):** Enterprise teams at Fortune 500 companies now implement cost circuit breakers at the gateway layer, with per-endpoint throttle policies and surge handling — moving cost enforcement from the application layer to infrastructure. — [DevOps Engineering, May 2026](https://devops.gheware.com/blog/posts/ai-agent-guardrails-production-enterprise-2026.html)

## Gotchas

- **Cache invalidation is subtle.** If your retrieved context changes every call, prompt caching buys you nothing. Benchmark your actual cache hit rate — teams often find it is 0% because the prefix includes timestamps or dynamic IDs.
- **Output token limits are the most common runaway vector.** Agents that hit a tool failure and retry with a longer prompt can rapidly accumulate massive output token counts. Set output token caps before you need them.
- **The demo-to-production gap is predictable, not exceptional.** A 92% → 55% success rate drop and a 4x cost overrun are now documented as the norm, not the exception. Plan for it.
- **Budget enforcement without observability is guesswork.** You cannot cut costs you cannot measure. Emit structured cost events on every call before you add any budget logic.
- **Lakera and Invariant Labs (prompt injection guardrail vendors) were both acquired in 2025** — Lakera by Check Point in November, Invariant Labs by Snyk in June. Enterprise security guardrails are consolidating into larger platforms, which may reduce individual team access to best-in-class tooling.
