# S-311 · Production Agent Cost Engineering

When your AI agent bill arrives, it's too late. The real cost of running agents isn't the API calls — it's the non-determinism of multi-step loops, the compounding token burn of naive orchestration, and the gap between what teams think they're spending and what they actually are. Most teams discover cost engineering only after a runaway agent loop hits their credit card.

## Forces

- **AI agent cost is non-deterministic.** A REST API call costs the same every time. An agent call depends on prompt length, response length, retries, model tier, and whether it spawns sub-agents. The same workflow can cost $0.02 or $2.00 depending on how it executes.
- **Step count compounds costs linearly but failure modes compound exponentially.** Every additional step in an agent's execution chain multiplies token usage. But loops — where an agent re-executes the same tool call because it didn't get satisfying context — don't just burn tokens. They burn them fast.
- **Cost observability lags behind operational observability.** 89% of teams have basic monitoring but only 52% have evaluation frameworks that connect cost to outcome quality. Without that link, cost debugging is guesswork.
- **60–85% of production spend is recoverable.** Prompt caching, intelligent model routing, and hard budget enforcement can cut costs 40–70% without touching output quality. Teams don't know this until they've already overspent.

## The Move

**Treat agent cost as an engineering problem, not a billing problem.** Instrument every execution path with per-step token accounting, route models to tasks by capability requirements (not default), and enforce budget circuit breakers at the orchestration layer — not just the API key level.

- **Per-step token accounting.** Every agent step should log input tokens, output tokens, model used, and latency. This isn't just for billing — it reveals which tools are causing context bloat and where re-routing would help. LangSmith, Phoenix, or custom logging all work; pick one and instrument before going to production.
- **Model routing by task profile.** Not every step needs Claude Opus or GPT-4o. Use routing: fast, cheap models (Haiku, GPT-4o-mini) for classification, routing, and simple retrieval; frontier models for synthesis, reasoning, and final output. The cost-per-task difference is 10–50x.
- **Budget circuit breakers at the orchestration layer.** Set per-execution token budgets (e.g., max 50,000 tokens per run) and step-count limits (e.g., max 15 tool calls). These should halt execution and surface an error, not just let the agent loop until the API returns nothing. Budget enforcement must be external to the agent itself — the agent will optimize around its own limits if given the chance.
- **Prompt caching wherever stateful context repeats.** Anthropic's cache-beta API and OpenAI's cached-chat completions reduce cost by 50–90% on repeated patterns (system prompts, retrieved documents, tool schemas). Cache aggressively for agent system prompts and RAG retrieval results.
- **Retries with exponential backoff AND jitter.** Agent loops often trigger from timeout or rate limit errors, not actual failure. A naive retry without jitter will hit thundering-herd rate limits and compound the cost. Cap retry count (3 is standard) and add 100–500ms random jitter between attempts.
- **Evaluate cost-per-outcome, not cost-per-call.** The right unit is "$ per successful task completion." A 12-step agent that succeeds 98% of the time is cheaper than a 4-step agent that succeeds 71% and requires human triage.

## Evidence

- **Primary cost data (6 months, 4 production systems):** System A (LangGraph, 3 tools, 2.4 avg steps) ran 12,000 times/month at $2.10/run. System C (CrewAI, 3 agents, 8.2 avg steps) ran 3,200 times/month at $6.40/run. The cost formula is `model choice × step count = total cost` — each additional step at frontier-model pricing adds $0.40–$2.10 per run. — [Inventiple, "The Real Cost of Running Agentic AI in Production"](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)
- **Runaway loop incidents:** Teams have reported runaway agent loops costing anywhere from $15 in ten minutes to $47,000 over eleven days. Root cause in every documented case: no per-execution token budget or step-count cap at the orchestration layer. — [Zylos AI, "AI Agent Cost Engineering — Production Token Economics"](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/)
- **Recovery through optimization:** 60–85% of production AI spend is recoverable through prompt caching, model routing, and budget enforcement. Teams that implemented all three cut costs 40–70% with no measurable quality degradation. — [Zylos AI](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/)
- **Observability gap:** 89% of teams building multi-agent systems have observability but only 52% have evaluation frameworks. This explains why debugging cost overruns in agentic systems is largely manual and reactive. — [RaftLabs, "Multi-Agent Systems: Architecture Patterns for Production AI"](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Enterprise baseline:** Enterprises average $85,521/month in AI operational costs as of 2025. Model API spend industry-wide doubled from $3.5B to $8.4B between late 2024 and mid-2025. — [Zylos AI](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/)

## Gotchas

- **Per-call budget limits (API key level) don't stop agent loops.** Setting a $50/month API budget is too blunt — it halts ALL calls when exceeded, not just runaway ones. You need per-execution budgets that halt ONE problematic run while letting healthy runs continue.
- **Adding more agents increases cost super-linearly.** A 4-agent orchestrator-worker workflow costs $5–8 per complex task. Adding a second orchestrator layer or peer agents multiplies the token-per-step cost across the entire execution graph. Model the economics before committing to architecture.
- **Prompt caching has a freshness tradeoff.** Cached prompts can't be updated without cache invalidation. For agents that pull from dynamic RAG sources, the cache hit rate may be lower than expected if retrieval results vary per query.
- **Cheap model routing only works when tasks are clearly delineated.** Routing a GPT-4o-mini into a multi-step agent at the wrong step — one that requires nuanced reasoning — produces outputs that downstream steps reject, causing extra re-execution and burning more tokens than if you'd used the expensive model the first time. Map task profiles to model tiers before routing.
- **40% of agentic AI projects are at risk of cancellation by 2027** (Gartner), with cost overrun as the primary driver. The teams that survive are the ones that instrument cost from week one, not week twenty.
