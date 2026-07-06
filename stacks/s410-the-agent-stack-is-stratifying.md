# S-410 · The Agent Stack Is Stratifying

The promise of a single agent framework that does everything gives way to a layered stack with distinct, swappable components. When you move past the demo and into production, the monolithic agent dissolves into specialized layers — and the seams between them are where most failures live.

## Forces

- **"Magic" frameworks collapse under real workloads.** Teams report that agents built with abstraction-layer frameworks fail silently after extended operations: tool calls stop responding, loops trigger runaway costs, and hidden errors corrupt state without surfacing. The 5-line tutorial and the production system are not the same product.
- **65% of teams that ship an agent stack rewrite it within 12 months** — often because the orchestration model (conversational, role-based, graph-based) was chosen for fit, not for the problem type. The rewrite cost is measured in months and credibility.
- **Observability is structurally misaligned with agent behavior.** Traditional APM ("tool call succeeded, 200 OK") tells you the process worked. It tells you nothing about whether the agent output was correct. Process success and output correctness are decoupled in agentic systems — a hallucination in an orchestrator can cascade incorrect decisions through every downstream agent.
- **The stack is fragmenting along defensibility lines.** Sandbox execution, memory, orchestration, tool integration, and guardrails each have different competitive moats. Monolithic approaches carry all the risk of all the layers simultaneously.

## The Move

Treat agentic systems as a layered architecture with explicit contracts between layers. Swapping one layer should not require rebuilding the others.

**Orchestration: Graph-based state machines beat conversational or role-based models for production reliability.**
- LangGraph's graph-based state machine (agents as nodes, transitions as edges) provides checkpointing, time-travel debugging via LangSmith, and parallel subgraph execution — reducing LLM overhead by ~22% versus sequential execution patterns.
- Default to LangGraph unless you have a strong reason not to. The steeper learning curve prevents painful rewrites 6–12 months in.
- Use CrewAI for fast role-based prototyping (20-minute setup vs. 2-hour LangGraph), but plan the migration path upfront.
- AutoGen entered maintenance mode in October 2025 — successor is Microsoft Agent Framework. Do not start new projects on AutoGen.

**Memory: Unified PostgreSQL (pgvector/pgvectorscale) over multi-database stacks for agent state.**
- Production teams report that managing separate vector DB + time-series DB + structured state DB adds operational complexity that outweighs the performance gains.
- pgvectorscale achieves Pinecone-level performance at ~75% lower cost, making the unified Postgres approach viable for most production workloads.
- Qdrant + GPT-4o-mini is a common lightweight combination for semantic memory in n8n and similar workflow tools.
- Use memory as a tool, not as a passive store. Active retrieval (query-time) outperforms passive context injection.

**RAG: Coverage beats ranking — combine retrievers with different failure modes.**
- RAG failures are retrieval coverage failures, not ranking failures. Pushing top-k deeper often returns more redundant chunks.
- Combine dense (embedding-based) + sparse (BM25) retrievers over different corpora. The different failure modes complement each other.
- Small-to-large chunk retrieval (retrieve small chunks, return parent/surrounding context) outperforms flat top-k retrieval for complex questions.
- Cross-encoder rerankers remain standard but plateau — diminishing returns beyond the top 20 candidates.
- Query expansion and hybrid retrieval are table stakes for production-grade RAG in 2026.

**Observability: Add semantic quality SLOs alongside system health SLOs.**
- Define separate SLOs for "system health" (latency, availability, tool call success) and "output quality" (correctness, hallucination rate, goal completion).
- Instrument at the semantic layer, not just the infrastructure layer. A tool call returning 200 OK can still produce an agent output that corrupts shared state.
- Langfuse, LangSmith, Phoenix (Arize), and W&B Weave are the primary production-grade observability tools. Datadog LLM Observability and Prometheus exporters are increasingly common in enterprise environments.

**Sandboxing: Execution sandboxing is becoming its own specialized layer.**
- E2B, Modal, Firecracker microVMs, Shuru, and similar services are separating "run code safely" from "orchestrate the agent." This is the emerging sandbox-as-a-service layer.
- Destructive action allowlists (file deletions, DB writes, deployments, external API calls that modify state) should gate on target verification before execution — confirm the target environment matches the intent before any state-modifying operation.

## Evidence

- **Framework comparison (2026, production benchmarks):** LangGraph leads on throughput (15.2 tasks/min vs. 8.7 for CrewAI), supports 50+ agents vs. ~10 for CrewAI, and enables full state-machine visualization vs. console logs. CrewAI setup takes 20 minutes vs. 2 hours for LangGraph. — [Markaicode: LangGraph Agent Stacks Compared](https://markaicode.com/best/best-ai-agent-stacks-with-langgraph/), [Gheware DevOps: LangGraph vs CrewAI vs AutoGen](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Stack stratification and sandboxing:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing." HN discussion cites Shuru, E2B, Modal, Firecracker wrappers as distinct specialized layers with different defensibility profiles. — [Hacker News on agent stack stratification](https://news.ycombinator.com/item?id=47114201)
- **RAG 2026 production patterns:** "RAG failures are often retrieval coverage failures, not ranking failures." Small-to-large chunk retrieval, hybrid dense+BM25, and cross-encoder rerankers form the 2026 baseline. — [Microsoft Azure / Ozgur Guler: 10 RAG Shifts in 2026](https://medium.com/@343544/10-rag-shifts-redefining-production-ai-in-2026-7acbdd66076c)
- **Production lessons and 5 framework iterations:** "If 2024 was the year everyone dreamed about the potential of what LLMs could do, 2025 was the year people woke up to the hard cold reality." Xpress AI built 5 agent frameworks before stabilizing — key lesson: prioritize observability and guardrails from day one. — [Xpress AI: Operationalizing AI Agents Lessons from 2025](https://xpress.ai/blog/2025-agent-lessons)
- **Observability paradox in multi-agent systems:** "The system reports 'tool call succeeded, 200 OK,' while the actual agent output was wrong or hallucinated. In AI systems, process success and output correctness are decoupled." — [Augment Code: Multi-Agent AI Operational Intelligence](https://www.augmentcode.com/guides/multi-agent-ai-operational-intelligence)
- **Unified Postgres for agent memory:** pgvectorscale achieves Pinecone-level performance at ~75% lower cost, enabling a single PostgreSQL database to handle time-series conversation history, semantic search, and structured agent state. — [Tiger Data: Building AI Agents with Persistent Memory](https://www.tigerdata.com/learn/building-ai-agents-with-persistent-memory-a-unified-database-approach)
- **35 production patterns open-source:** A curated library of 35 production-grade agentic architectures (Reflexion, LATS, GraphRAG, MemGPT, Voyager) built on LangGraph with multi-provider LLM support and 17-task benchmark leaderboard — 283 passing tests, MIT license. — [GitHub: FareedKhan-dev/all-agentic-architectures](https://github.com/FareedKhan-dev/all-agentic-architectures)
- **Enterprise adoption stats:** 80% of Fortune 500 exploring AI agents; 65% hit a wall within 12 months requiring a rewrite; 60% of Fortune 500 evaluating CrewAI; 66% productivity increase reported by organizations using agent frameworks. — [Gheware DevOps: Framework Comparison](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Gotchas

- **CrewAI to LangGraph migrations are painful but necessary.** The quick start lures teams in; the sequential-only execution model and limited observability push them out at scale. Budget the migration cost upfront, not when you hit the wall.
- **Default to first-class MCP integration.** The Model Context Protocol is increasingly the standard for tool calling across frameworks. Any framework without first-class MCP support should be treated as a migration risk.
- **Cost control is a first-class concern, not an afterthought.** Agent loops (agents calling themselves or tools in cycles) are the primary cost runaway pattern. Implement per-agent token budgets, step-count limits, and circuit breakers before going live, not after the first invoice shock.
- **Evaluation cannot be manual.** Human spot-checking is not observability. Build automated correctness assertions into your test pipeline — "did the agent accomplish the stated goal?" must be measurable, not just reviewable.
