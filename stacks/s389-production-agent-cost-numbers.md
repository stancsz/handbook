# S-389 · Production Agent Cost — The Numbers That Actually Matter

Estimating agentic AI costs for production is notoriously opaque. Most teams start with toy benchmarks or napkin math, then get blindsided by the gap between single-call pricing and a system that loops 8 steps per execution. The real multiplier is step count — and teams that learn this late pay in wasted spend.

## Forces

- **Step count is the hidden cost multiplier.** Each agent step is an LLM call. A 3-tool agent averaging 2.4 steps/run vs. an 8-step multi-agent crew costs an order of magnitude differently at scale — not because of model prices, but because of execution paths.
- **Infrastructure overhead is non-obvious.** When teams budget "just API costs," they forget inference infrastructure (15–40% of total), vector DB hosting, observability tools, and the engineering hours spent chasing runaway loops.
- **Naive RAG kills budgets silently.** Returning 50 chunks where 5 would suffice multiplies context costs and degrades answer quality — you're paying more for worse output.

## The Move

**Model choice × step count = total cost.** The primary levers are step reduction and model routing — not swapping providers.

- **Profile before optimizing.** Track steps/run and cost/execution per agent before touching anything. The system that's 8.2 steps/run is a different problem than the one that's 2.4.
- **Route by task complexity.** Simple classification or extraction → small/fast model (GPT-4o-mini, Haiku). Reasoning, multi-tool, or ambiguous → frontier model (o3, Claude Sonnet). Real teams see 40–70% cost reduction from routing alone.
- **Cap execution steps at the orchestration layer.** A hard max_steps prevents runaway loops that burn budget on meaningless re-planning cycles. Set per-task limits, not global ones.
- **Batch non-time-sensitive tool calls.** When multiple tools are independent (e.g., fetching 3 data sources), call them in parallel rather than sequentially — reduces wall-clock time and often reduces total token volume.
- **Cache repeated embeddings and semantically identical queries.** For RAG-heavy agents, hybrid retrieval (dense + BM25) with a reranker returns higher precision in fewer chunks, cutting context costs by 30–50% over naive top-k.

## Evidence

- **Primary research — 6-month cost tracking across 4 production systems:** Monthly costs ranged $636–$1,996/system. All-in cost per execution: $0.05–$0.51. Infrastructure (vector DBs, inference, observability) consumed 15–40% of total spend on top of API costs. Step count was the primary driver: System A (2.4 steps/run, 12k runs/month) vs. System C (8.2 steps/run, 5k runs/month) had comparable monthly spend despite different volumes. — [Inventiple, April 2026](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)
- **Framework comparison — orchestration cost implications:** LangGraph: explicit graph state management, easier to enforce step limits and human-in-the-loop checkpoints, lowest overhead per step. CrewAI: role-based multi-agent teams, fastest to prototype, but shared memory overhead scales with agent count. AutoGen: collaborative conversation patterns, native Azure integration, highest per-step overhead. — [Gheware DevOps, March 2026](https://devops.gheware.com/blog/posts/langgraph-vs-autogen-vs-crewai-comparison-2026.html)
- **RAG cost reduction through retrieval quality:** Adding hybrid search (dense embeddings + BM25) and a reranker (e.g., Cohere Rerank v3) fixes the majority of retrieval failures before adopting more exotic patterns. Late chunking and hierarchical search further reduce chunk count without losing context. Teams report 30–50% context cost reduction vs. naive top-k retrieval. — [AI Thinker Lab, June 2026](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns)

## Gotchas

- **Per-token pricing misleads without step tracking.** A system using GPT-4o at $2.50/1M tokens can be cheaper than GPT-4o-mini at $0.15/1M tokens if the cheaper model loops 3× more steps due to weaker tool-calling.
- **Vector DB hosting costs are easy to underestimate.** A production Pinecone or Qdrant instance can run $200–$500/month — comparable to the LLM spend for moderate-volume systems.
- **Cold start on multi-agent crews is expensive.** Adding a second or third agent typically doubles infrastructure overhead immediately; the cost-per-step optimization payoff takes 2–4 weeks of tuning.
- **Rerankers can hurt if applied naively.** Reranking retrieved chunks before generation improves precision but adds latency and cost per query. Only apply reranking to queries where top-k recall is known to be poor.
