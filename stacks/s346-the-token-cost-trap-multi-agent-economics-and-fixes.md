# S-346 · The Token Cost Trap: How Multi-Agent Systems Bankrupt You and How to Fix It

Single-agent demos look cheap. Multi-agent production systems in the real world are not. A single agent solving a software engineering task costs $5–8 in API fees alone. Stack four agents together and you have $20–32 per task before infrastructure, observability, or vector DB costs. The problem is not the per-call price — it is the multiplicative compounding of LLM calls across multi-agent pipelines, and most teams discover this only after they have already shipped.

## Forces

- **Agents make 3–10x more LLM calls than chatbots.** Every tool invocation, every step in a reasoning chain, every inter-agent handoff is another API call. A workflow that looked like 10 calls becomes 100 once you trace all the tool use and agent loops.
- **Multi-agent coordination multiplies cost linearly with complexity.** A 4-agent workflow where each agent calls the orchestrator, calls peers, and loops is not 4x the cost of a single agent — it is closer to 10–20x due to context-passing and redundant reasoning.
- **Enterprise AI spending exceeded projections by 96%.** Nearly 40% of enterprises now spend over $250K/year on language models, with AI agents driving the bulk of the overage. Gartner estimates 40% of agentic AI projects face cancellation by 2027 — cost overruns are a primary driver.
- **Naive cost management ("set a max_tokens cap") doesn't work.** Hard caps cause mid-task failures that require expensive retry loops, which often cost more than if you'd just let the task complete.
- **The retrieval step amplifies everything.** Every RAG query adds embedding + vector search + LLM synthesis to every agent turn. With 4 agents each doing 10 RAG lookups per task, a single task can trigger 40 retrieval cycles.

## The Move

A layered optimization stack where each layer composes with the others. No single fix — the 60–80% reduction only comes from stacking all of them:

**1. Model routing as the first line of defense.** Route simple queries (status checks, factual lookups, format conversions) to cheap models (GPT-4o-mini, Haiku, Llama-3.1-8B). Reserve expensive models (o3, Opus, Claude 3.7) only for tasks requiring genuine reasoning. Teams report 50%+ deflection to cheap models without quality regression when routing logic is well-scoped.

**2. Semantic caching deflects the highest-value queries.** Cache LLM responses keyed by semantic similarity, not exact match. A cache hit avoids the entire downstream cost stack — model, tools, and retrieval. Deflection rates of 30% are reported for production systems with stable query distributions.

**3. Context summarization and compression inside the agent loop.** Older conversation turns should be compressed to semantic summaries before they consume context budget. Agents that manage their own context windows (summarizing rather than truncating) show 40–60% context size reduction with no loss in downstream task quality.

**4. Prefixed caching for repeated system prompts.** Most agent frameworks repeat identical system prompts across every call. Cloud provider prefix caching (Anthropic, OpenAI, Google) now handles this automatically — but only if your prompt strings are identical across calls. Fragmenting prompts across concatenation breaks cache eligibility.

**5. Token budgets with graceful degradation, not hard caps.** Budget-aware agents should stop early when a task is "good enough" rather than continuing to refine. An agent that reasons for 8 steps when 3 would suffice is burning budget on marginal output quality. Define quality thresholds per task type, not blanket budgets.

**6. Async batch scheduling for non-urgent tasks.** Many agent workloads (reporting, batch analysis, periodic synthesis) don't need immediate results. Batch scheduling captures 50% discounts from OpenAI and Anthropic for async workloads. The discount compounds with the volume multi-agent systems generate.

## Evidence

- **RaftLabs (Nov 2025):** Multi-agent systems with 4 coordinated agents incur $5–8 per complex task in inference costs alone. Teams using full-stack optimization (caching + routing + compression) report 60–80% token cost reduction. — [raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Zylos Research (Apr 2026):** AI agents make 3–10x more LLM calls than chatbots. Enterprise LLM spending reached $8.4B in H1 2025; 96% of teams report costs exceeded projections. Teams applying semantic caching (30% deflection), model routing (50% deflection), prefix caching, and batch scheduling (50% async discount) achieve 60–80% reduction from naive baseline. — [zylos.ai/research/2026-04-12-ai-agent-cost-optimization](https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing)
- **Accenture Software (Apr 2026):** Production agents face a "reliability gap" — they handle expected inputs well but fail on the 51st edge case, triggering retry loops that compound cost. Observability (89% of teams have it) and structured eval pipelines (only 52% have evals) are the gap: you cannot optimize what you cannot measure. — [accenturesoft.com/blog/ai-agents-in-production](https://www.accenturesoft.com/blog/ai-agents-in-production)

## Gotchas

- **Hard token caps cause retry storms.** An agent mid-task that hits a context limit will re-send the full prompt on retry, burning the original cost plus the retry cost. Use soft budgets with early-exit signals instead.
- **Semantic caching requires a good embedding model for the cache key.** A bad embedding model produces false negatives (missed cache hits) or false positives (returning wrong answers for semantically-similar-but-different queries). Validate your cache hit quality separately from cache hit rate.
- **Prefix caching breaks with dynamic prompt assembly.** If you concatenate system prompts from multiple modules or add timestamps/IDs, the prompt string changes and cache eligibility is lost. Keep your system prompt template stable and deterministic.
- **Model routing accuracy is a hidden eval burden.** Routing a query to a cheap model that fails and must be retried on an expensive model costs more than just using the expensive model upfront. Routing decisions need eval coverage before they save money.
- **Cost observability without behavioral evals is insufficient.** You can see that a task cost $7 — but not whether it was worth $7. The 52% of teams without evals are flying blind on quality, which means they cannot make informed routing or compression decisions.
