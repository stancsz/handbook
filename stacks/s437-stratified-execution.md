# S-437 · Stratified Execution

You built a monolithic agent. It worked at demo. At scale it is a single point of failure — context bleeds between tasks, one tool crash takes down everything, and you cannot update the planner without redeploying the executor. Meanwhile the ecosystem has quietly split into four distinct layers: orchestration, sandboxed execution, memory, and tools. Treating them as one system is where teams get stuck.

## Forces

- **Cohesion vs. composability** — a single framework handles everything but locks you into its tool choices and update cadence
- **Prototype speed vs. production reliability** — CrewAI gets you to a working demo in minutes; LangGraph gets you to 96% task completion in production
- **Cost vs. capability** — LLM API calls are 60–80% of operating cost, yet most teams choose frameworks before designing their routing strategy
- **Tool proliferation vs. security** — MCP has 5,800+ servers published, but 43% have command injection flaws; exploit probability exceeds 92% with 10 plugins
- **State persistence vs. simplicity** — LangGraph checkpoints every node execution (time-travel debugging); CrewAI saves at method level with `@persist` (easier, but cannot replay from exact failure point)

## The move

Design the stack as four independent layers. Choose the best tool for each. Combine them deliberately.

**Layer 1 — Orchestration (brain)**
Choose based on production reliability needs, not prototyping speed:

- **LangGraph** (directed graph, typed state, per-node checkpointing, PostgreSQL/Redis/DynamoDB backends). Best for: production systems where task completion rate and auditability matter. Cost ~$0.08/task, 96% recovery. 47M+ PyPI downloads. The standard migration target when CrewAI prototypes outgrow their bounds.
- **CrewAI** (role-based agents, process flows). Best for: rapid prototyping and non-technical stakeholders who need to read the agent definitions. Common pattern: prototype in CrewAI (5-min setup), harden in LangGraph before go-live.
- **AutoGen / AG2** (Microsoft's maintained fork). Best for: collaborative multi-agent reasoning pipelines, especially on Azure. Cost ~$0.45/task, 68% recovery — highest token overhead.
- **Custom state machines** (Temporal, direct graph execution). Best for: workflows that need durable execution with built-in retry/saga semantics outside the LLM layer.

**Layer 2 — Sandboxed execution (hands)**
Execution isolation is becoming its own category:

- **E2B**, **Modal**, **Shuru**, **Firecracker-based microVMs**. Each wraps compute in isolation so a crashing tool cannot corrupt the orchestrator's state. Required when agents call untrusted code or third-party tools.

**Layer 3 — Memory / persistence**
Not a single database — a tiered memory architecture:

- **Short-term**: Redis or in-memory (current session state)
- **Long-term**: PostgreSQL + pgvector (structured data + embeddings, cost-efficient), **Qdrant** (high-dimensional dense vectors), **Pinecone** (managed scale), **Weaviate** (hybrid BM25 + vector)
- **Semantic memory**: Store agent decisions, tool results, and reasoning traces for retrieval in future sessions

**Layer 4 — Tool integration (tools)**
MCP has won the standard:

- MCP (Model Context Protocol) grew from ~100K downloads (Nov 2024) to 8M+ by April 2025. Now under Linux Foundation's Agentic AI Foundation governance. Over 5,800 servers, 300+ clients, 10,000+ published servers.
- OpenAI, Google, Microsoft, AWS all adopted MCP — it is the USB-C of AI tool integration.
- Security reality: 43% of MCP servers have command injection flaws. Always run MCP tool servers in Docker containers with resource limits. Never expose production MCP servers directly to the internet.

**Routing — the invisible layer**
Before any of the above: decide which agent or model handles each request:

- **Intent classification** → small fast model routes to specialized agent (cuts LLM spend 40–70%)
- **Model tiering**: cheap model for routing/deduplication, expensive model only for final synthesis
- Single-agent (2–3 steps): LangGraph. Multi-agent (5+ steps): CrewAI or custom fan-out

## Evidence

- **Microsoft ISE — Multi-Agent Scalability Patterns:** A retail customer's production chatbot evolved from a router-pattern modular monolith (one query → one agent) to a microservices architecture enabling agent reuse across teams. At scale, accurate agent selection and optimized LLM usage become the primary constraints. The solution: dynamic agent selection with typed state passing between agents, backed by persistent storage. — [Microsoft DevBlogs ISE, Nov 2025](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale)

- **Framework Benchmarking — Production Evaluation:** LangGraph: ~$0.08/task, 96% task recovery, 2–3 weeks prototype-to-prod. CrewAI: ~$0.15/task, 72% recovery, 2–3 days to prod. AutoGen/AG2: ~$0.45/task, 68% recovery, 1–2 weeks to prod. LangGraph's per-node checkpointing enables time-travel debugging critical for EU AI Act audit compliance. — [AlterSquare Medium, May 2026](https://altersquare.medium.com/langgraph-vs-crewai-vs-autogen-how-we-evaluated-all-three-before-recommending-one-for-a-production-51e61e9da353)

- **MCP Ecosystem Analysis:** 8M+ MCP server downloads by April 2025. Linux Foundation governance established Dec 2025. Enterprise deployments at Block, Bloomberg, Amazon, hundreds of Fortune 500. 90% enterprise adoption projected for end of 2025. Security: 43% of servers have command injection vulnerabilities; run in Docker sandbox. — [Deepak Gupta Research, 2025](https://guptadeepak.com/research/mcp-enterprise-guide-2025/)

- **Production Cost Anatomy:** Across 4 production agentic systems over 6 months, LLM API calls account for 60–80% of total operating cost. Single-agent, few tools (LangGraph): 2.4 avg steps/run, $0.02–0.04/task. Multi-agent with 3 agents (CrewAI): 8.2 avg steps/run, $0.15–0.40/task. Multi-agent fan-out cuts cost-per-task only when tasks are parallelizable. — [Inventiple, April 2026](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)

- **Stack Stratification:** The agent stack is splitting into specialized layers. Sandboxing (E2B, Modal, Firecracker) is clearly becoming its own category. Going monolithic — one framework handles everything — is the wrong call. Different layers have different defensibility profiles and different update cadences. — [Philipp Dubach / HN, 2025](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)

## Gotchas

- **Do not prototype in LangGraph if speed matters** — its graph-based model has a steeper learning curve and slower initial development. Prototype in CrewAI, migrate to LangGraph for production hardening.
- **MCP security is not a future concern** — 43% of published servers have exploitable vulnerabilities today. Treat every MCP tool server as potentially hostile; containerize and limit resource access.
- **LangGraph's checkpoint system is not free** — persisting state after every node call adds latency and storage overhead. Profile this before claiming LangGraph is "slower" than simpler alternatives.
- **CrewAI's `@persist` saves at method level, not per LLM call** — you cannot replay from an exact failure point. If auditability and exact recovery matter, use LangGraph with a persistent checkpoint backend.
- **Routing is the highest-leverage optimization** — a cheap intent classifier routing requests to the right model tier can cut LLM spend 40–70%. Most teams skip this layer entirely.
- **Naive RAG + agentic pipeline = degraded retrieval** — hybrid search with Reciprocal Rank Fusion (RRF) is now baseline for production RAG. Re-rankers help for top-5 retrieval quality but hurt latency at scale. Agentic RAG (query refinement + self-correction loops) is the pattern for high-value knowledge work.
