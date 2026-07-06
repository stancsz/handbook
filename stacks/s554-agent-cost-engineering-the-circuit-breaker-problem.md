# S-554 · Agent Cost Engineering: The Circuit Breaker Problem

Production AI agents are not cheap experiments — and teams that skip cost engineering discover this the expensive way. Model API spend doubled from $3.5B to $8.4B between late 2024 and mid-2025. Enterprises now average $85,521/month in AI operational costs. The problem is not the spend itself; it's that most teams have zero visibility into what's driving it until the bill arrives.

## Forces

- **Agent loops are non-obvious until they're catastrophic** — a 10-turn loop at $0.50/turn looks fine in development; it costs $450/hour in production at scale
- **Prompt caching is not free** — naive full-context caching can increase latency and cost more than a targeted approach, as a January 2026 arXiv paper documented
- **Every optimization layer is a potential failure point** — LiteLLM silently dropped cache headers, leading to a $38k AWS Bedrock bill from a "normal" local coding-agent workflow
- **60–85% of AI spend is recoverable** — but only with discipline, not just alerts
- **Alerts require humans; circuit breakers do not** — in autonomous systems, nobody is watching

## The Move

Cost control at three layers, all working together:

- **Circuit breakers at the orchestration layer** — hard token budgets and step-count limits enforced before the agent runs, not after the bill arrives. Max spend per task, max turns per workflow, kill switches that trigger on thresholds. This is the layer where most teams have nothing.
- **Prompt caching at the inference layer** — structure agent prompts so the "system personality" and shared context are cacheable. The 90% token reduction is real, but only for agents designed to earn it. Cache the persona, the tool schemas, the domain context. Don't cache the unique per-task scratch pad.
- **Model routing at the gateway layer** — route simple classification and routing decisions to cheap models (~$0.10/1M tokens), reserve expensive frontier models for actual reasoning. 37% of enterprises already run 5+ models in production for exactly this reason.

## Evidence

- **HN postmortem:** A developer using Claude Code via LiteLLM into AWS Bedrock hit $37,901.73 in charges because prompt caching silently failed across the tool chain — every layer reported caching as active, none of it worked. The lesson: verify your caching is actually working in your specific stack, not just in the docs. — [HN: $38k AWS Bedrock bill — prompt caching miss](https://news.ycombinator.com/item?id=47933355)
- **Production data:** Runaway agent loops in production cost teams documented ranges from $15 in 10 minutes to $47,000 over 11 days. An unconstrained AI agent solving a software engineering task costs $5–8 per task in API fees with no optimization; the same agent architected around prompt caching drops below $1. 60–85% of AI spend is recoverable. — [Zylos Research: AI Agent Cost Engineering](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/), [AgentMarketCap: Prompt Caching Economics 2026](https://agentmarketcap.ai/blog/2026/04/09/prompt-caching-economics-production-agent-workloads-2026)
- **Enterprise adoption:** 37% of enterprises now use 5+ AI models in production, driven by multi-model routing for cost optimization. Gartner estimates 40% of enterprise agentic AI projects will be canceled by end of 2027 due to unclear business value and runaway costs. — [Philipp Dubach: The Agent Stack Is Stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)

## Gotchas

- **Verifying caching is not optional** — test it in your actual stack (model provider → proxy layer → orchestration layer → agent), not just at the model provider level. The HN case shows that a silent failure across one link in the chain can be catastrophic.
- **Hard limits beat soft alerts** — an alert that fires while you're asleep is not a circuit breaker. Budget enforcement must be architectural, not operational.
- **Cost observability lags cost generation** — by the time you see the bill, the damage is done. Token-per-task tracking, per-agent spend dashboards, and cost attribution by workflow are the minimum viable observability stack.
- **Per-step cost modeling compounds** — a system with four reasoning steps at 95% reliability delivers only 81.5% end-to-end reliability, and each step has its own cost. Model the full chain, not just the individual calls.
