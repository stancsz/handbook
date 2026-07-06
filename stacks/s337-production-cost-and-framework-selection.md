# S-337 · The Cost-First Agent: How Real Production Numbers Are Rewriting Architecture Decisions

Your agent works on a demo. Then it hits 10,000 monthly runs and your invoice looks like a car payment. The frameworks, model choices, and orchestration patterns you picked "because they're best" may be 5–10x more expensive than necessary for your workload. Production cost data is now abundant enough to drive architecture — not just theoretical benchmarks.

## Forces

- **LLM API calls dominate cost at 60–80% of total spend.** The math is simple: model choice × step count = cost. Everything else is noise until you optimize those two variables.
- **Agentic RAG costs 8x more per query than naive RAG.** For simple factual lookups, the additional accuracy may not justify the cost. Teams are discovering this too late.
- **Framework lock-in is a real cost.** LangGraph's state-machine approach enables granular step counting and optimization. CrewAI's role-based crews are fast to scaffold but harder to cost-profile at the step level.
- **Step count is the hidden lever.** Most teams optimize model tier before they optimize step count. A 4-step agent using Claude Haiku often costs less than a 2-step agent using GPT-4o.

## The move

**Measure cost-per-execution before choosing your stack. Then design backwards from that number.**

- **Profile your workload before choosing a framework.** If 80% of your queries are simple factual lookups, a LangGraph graph with conditional branching (and early-exit on simple cases) dramatically reduces average step count. If you need rapid scaffolding for complex multi-role workflows, CrewAI wins on development time.
- **Use the right model per step, not per task.** A routing agent (cheap, fast) determines task complexity. A specialist agent (expensive, capable) handles only complex cases. This "tiered inference" pattern cuts costs 40–70% in documented production systems.
- **Cache semantically, not exactly.** Exact-prompt cache hits are rare. Semantic caching (embedding similarity) hits ~40% of production inputs at much lower cost than recomputing.
- **AutoGen is effectively deprecated.** Microsoft's successor is the Microsoft Agent Framework. If you're starting a new project, don't begin with AutoGen — its community and documentation are shrinking.
- **Track cost-per-step at the instrumentation level.** Every agent step should log its model, tokens, and cost. Without this, you can't find where 80% of your spend goes.

## Evidence

- **Inventiple (April 2026):** 6-month cost tracking across 4 production agentic systems (October 2025 – April 2026). Key findings: LLM API calls = 60–80% of total operating cost; "model choice × step count" is the cost formula; tiered inference (routing agent → specialist) cut costs 40–70% in one system; System A (LangGraph, single agent, 3 tools, 2.4 avg steps/run) cost $0.023/run at 12,000 runs/month. — [https://www.inventiple.com/blog/agentic-ai-production-cost-analysis](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)

- **JetThoughts (2025):** Framework comparison — LangGraph used at Klarna, Replit, Elastic for production systems needing observability and durable execution; CrewAI active at v0.98+ for content/support pipelines; AutoGen in maintenance mode (October 2025) with Microsoft Agent Framework as successor. — [https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)

- **Jahanzaib Ahmed (April 2026):** Agentic RAG achieves 78% accuracy on complex queries vs 34% for traditional RAG — but costs 8x more per query. Based on 38 production deployments out of 109 total AI systems built. Recommends tiered approach: cheap naive RAG first, agentic only on complex queries. — [https://www.jahanzaib.ai/blog/agentic-rag-production-guide](https://www.jahanzaib.ai/blog/agentic-rag-production-guide)

- **Camunda (October 2025):** 50+ enterprise customers across banking, insurance, healthcare, telecom. Key lesson: "most AI projects will stall or be scrapped" without measurable business outcomes. Cost control and observability cited as primary failure points. — [https://camunda.com/blog/2025/10/hype-to-impact-lessons-learned-making-agentic-orchestration-work](https://camunda.com/blog/2025/10/hype-to-impact-lessons-learned-making-agentic-orchestration-work)

## Gotchas

- **The demo-to-production step-count explosion.** A demo agent might complete a task in 2 steps. Production reality with retries, error recovery, and context replenishment often runs 4–8 steps. Cost models built on demo data will be catastrophically wrong.
- **CrewAI hides step complexity.** Its role-based abstraction makes it easy to add agents without counting steps. At scale, this leads to agents calling agents calling agents — and runaway costs that are hard to attribute.
- **Semantic caching has a latency trade-off.** Adding an embedding lookup before each LLM call adds 50–150ms. For latency-sensitive applications, the cache hit rate needs to justify the overhead.
- **Gartner predicts 40% of agentic AI projects cancelled by end of 2027** due to escalating costs, unclear ROI, and inadequate risk controls. Cost-first architecture is defensive as well as efficient.
