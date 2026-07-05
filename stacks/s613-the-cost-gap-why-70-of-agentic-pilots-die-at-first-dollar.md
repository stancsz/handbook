# S-613 · The Cost Gap: Why 70% of Agentic Pilots Die at First Dollar

Agentic AI demos work. Production billing destroys budgets. The gap between development economics and production economics is the single biggest killer of agentic pilots — and most teams discover it only after the demo already convinced stakeholders to fund a rollout.

## Forces

- **Token cost compounds across agents.** A 4-agent orchestrator-worker workflow costs $5–8 per complex task. A ReAct loop with a single agent might cost $0.02. The cost difference is 250–400x, and it compounds with retries, re-rankers, and context re-building.
- **Production data is adversarial to your assumptions.** One team tracked 47 different data format issues in production that never appeared in testing. Success rate dropped from 92% (test) to 55% (production) for a student-matching agent — and monthly costs hit $847 against a $200 budget.
- **LLM spend is the dominant cost driver at scale**, ranging from $1,800 to $10,500/month for real production deployments. Infrastructure is secondary. Teams that budget for compute infrastructure and treat LLM API costs as marginal get blindsided.
- **The eval gap amplifies cost waste.** 89% of teams have observability but only 52% have evals. Without evals, you can't distinguish expensive failures from expensive successes — so you pay for both equally.
- **Production token volume is structurally different from dev.** Real users trigger edge cases, complex inputs, and multi-turn interactions that never appear in controlled testing. Token-per-request ratios in production routinely exceed dev estimates by 3–10x.

## The Move

Model the full cost stack before you commit to architecture. Cost engineering is architecture.

- **Budget LLM API as your primary line item**, not an afterthought. At production scale, it's 60–80% of your bill. Infrastructure is secondary.
- **Count tokens per task type in development**, then multiply by your real user traffic projections — not your test traffic. Include retries, fallback models, and re-ranking passes.
- **Set per-task cost ceilings.** Implement hard aborts when a task exceeds a token or dollar threshold. The cost of one runaway multi-turn conversation can equal a month of normal operation.
- **Choose orchestration patterns with cost awareness.** Supervisor/Worker adds coordinator overhead on every task. Pipeline (sequential) has minimal overhead but doesn't parallelize. Model the tradeoff for your task mix.
- **Evaluate the eval gap on day one.** If you can't measure success vs. failure automatically, you're paying full price for every outcome including the broken ones. Invest in evals before scaling.

## Evidence

- **Blog post (Calder's Lab):** A student-matching agent went from 92% success in test to 55% in production, with costs jumping from ~$200/month budgeted to $847 actual — driven by 47 unanticipated data format issues. "We had built something that looked revolutionary in demos but was hemorrhaging money in production." — [Calder's Lab, $847/month production cost post](https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/)
- **Blog post (Island AI):** Cloud infrastructure for production agents ranges from $200 to $2,000/month depending on data volume and model size. LLM API costs at scale range from $1,800 to $10,500/month. "The $50–60/month infrastructure narrative is real for demos and MVPs. It's not real for production." — [Island AI, Production AI Agent Costs](https://www.islandshq.xyz/blog/the-real-cost-of-production-ai-agents-infrastructure-apis-and-hidden-operational-expenses)
- **Blog post (Dataa.dev):** ~70% of GenAI projects never progressed past pilot in 2025. Root causes: hallucination in production, cost explosion, data governance, and compliance failures. "What seemed affordable in dev/test became prohibitive at scale." — [Dataa.dev, AI Pilots to Production 2026](https://www.dataa.dev/2026/01/01/from-ai-pilots-to-production-reality-architecture-lessons-from-2025-and-what-2026-demands)
- **Blog post (RaftLabs):** A 4-agent orchestrator-worker workflow costs $5–8 per complex task. 89% of teams have observability but only 52% have evals. — [RaftLabs, Multi-Agent Architecture Patterns](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- **Demo success rates are misleading.** Clean, predictable test data produces 90%+ success rates. Production data is adversarial. Budget for a 30–50% success rate drop in production and validate early.
- **Context length is a cost multiplier.** Long context windows look free — they aren't. Every document you stuff into context costs per-token on every generation pass. RAG with retrieval + generation is usually 5–20x cheaper than pure context stuffing for large knowledge bases.
- **Retry logic is a cost trap.** Agents that retry on failure can spend 2–5x the base cost on a single failed task. Budget retries explicitly and set hard ceilings.
- **Per-user costs don't scale linearly.** Multi-agent systems with shared context don't enjoy the per-request marginal cost curve of single-agent APIs. Adding users compounds token usage in non-obvious ways.
