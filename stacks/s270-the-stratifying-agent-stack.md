# S-270 · The Stratifying Agent Stack — Why the Monolithic Framework Is the Wrong Bet

The agent framework wars are over — and the winner isn't a framework. It's a topology. Teams that bet on a single monolithic agent library (LangChain, CrewAI, AutoGen as a full-stack replacement) are discovering that production agents need five independently-scaling layers: orchestration, execution environment, tool abstraction, memory/persistence, and observability. The frameworks are becoming components, not the foundation.

## Forces

- **A single framework couples every concern.** When your orchestration, sandboxing, tool schema, memory store, and tracing are all mediated through one library, a breaking change in any layer cascades everywhere. One LangChain deprecation can silence your entire fleet.
- **Different layers have different defensibility.** Sandboxing (E2B, Modal, Shuru, Firecracker wrappers) is its own category — it doesn't belong inside an orchestration framework. Vector stores have nothing to do with agent graphs. Coupling them was a 2024 prototype mistake, not a production pattern.
- **Horizontal scaling requires stateless executors.** A LangGraph agent running at 10K RPM needs its state in an external store (Redis or PostgreSQL). The graph logic itself must be stateless. This is an architectural inversion from how most teams start.
- **72% of enterprise agentic RAG implementations underdeliver in year one** — not because the LLM fails, but because the surrounding infrastructure (retrieval, evaluation, observability) wasn't treated as a first-class concern from the start.

## The Move

Split the agent stack into five independent layers, each swappable:

- **Orchestration** (LangGraph, Temporal, custom FSM) — owns state machine logic, routing, and multi-agent coordination. Not deployment.
- **Execution environment** (E2B, Modal, Docker, Shuru, raw containers) — owns code execution, sandboxing, and resource limits. Isolated from orchestration.
- **Tool abstraction** (MCP, custom schemas, REST wrappers) — owns the interface contract between agents and external services. Decoupled from both orchestration and execution.
- **Memory/persistence** (Redis, PostgreSQL/pgvector, Qdrant, Pinecone) — owns session state, semantic memory, checkpointing. External and stateful.
- **Observability** (LangSmith, Arize Phoenix, Langfuse, OpenTelemetry) — owns traces, evaluations, and cost tracking. Ambient across all layers.

For orchestration specifically: LangGraph wins for stateful, auditable, complex workflows in regulated industries (production at Uber, JP Morgan, BlackRock, Cisco, LinkedIn per multiple 2026 sources). CrewAI wins for speed-to-prototype with role-based agent metaphors. AutoGen wins for Azure-native conversational flows. Most teams use LangGraph as the backbone and drop in CrewAI concepts where they fit.

## Evidence

- **HN discussion (phil, 16 days ago):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — [HN #47114201](https://news.ycombinator.com/item?id=47114201)
- **DEV Community (Richard Dillon, 2026):** LangGraph 2.0 release (Feb 2026) marked LangGraph as the "production foundation," citing 90M monthly downloads and production deployments at Uber, JP Morgan, BlackRock, Cisco, and LinkedIn. — [DEV Community](https://dev.to/richard_dillon_b9c238186e/langgraph-20-the-definitive-guide-to-building-production-grade-ai-agents-in-2026-4j2b)
- **Gheware DevOps Blog (Mar 2026):** Comparative analysis of LangGraph, CrewAI, and AutoGen — LangGraph scores highest on production readiness, audit trails, cyclical workflows, and LangSmith observability. CrewAI leads on developer onboarding speed. — [Gheware](https://devops.gheware.com/blog/posts/langgraph-vs-autogen-vs-crewai-comparison-2026.html)
- **Google Cloud Blog (Feb 2026):** Production agent evaluation focuses on trajectories — full sequences of decisions and actions, not final answers. Recommends staged rollouts from sandbox → canary → production, with per-span latency and token cost tracking. — [Google Cloud](https://cloud.google.com/blog/products/ai-machine-learning/a-devs-guide-to-production-ready-ai-agents)
- **Alica.eu (2025):** 72% of enterprise RAG implementations underdeliver in year one. Agentic RAG with self-correction loops (plan → retrieve → evaluate → refine) consistently outperforms naive RAG. Recommended production targets: retrieval precision ≥70%, generation groundedness ≥90%, end-to-end task success ≥85%. — [Alica.eu](https://aliac.eu/blog/agentic-rag-in-production)
- **NKKTech (2026):** Survey of 10 production deployments found LangGraph in 7/10, CrewAI in 2/10, AutoGen in 1/10. Notes market consolidating around LangGraph as the default with others as situational tools. — [NKKTech](https://nkktech.com/blog/langgraph-vs-crewai-vs-autogen-2026)

## Gotchas

- **Treating orchestration as deployment.** LangGraph runs a graph of LLM calls — it doesn't sandbox code execution, doesn't persist state by default, and doesn't give you distributed tracing. Those are separate systems you must wire in yourself.
- **LangGraph state requires an external store.** The `checkpointer` mechanism is mandatory for production — it serializes agent state to Redis or PostgreSQL between steps. Without it, your agent has no memory across sessions and can't recover from restarts.
- **Over-engineering the stack from day one.** A 2-agent prototype doesn't need a five-layer topology. Teams that build for 10K RPM on day one spend 6 months on infrastructure they didn't need. Start with the layers that create failure risk at your current scale, add the rest when you hit the wall.
- **LangSmith is not optional in production.** Multi-step agent workflows create debugging challenges that don't exist in traditional software. Without per-span traces, you cannot determine whether a failure is in the LLM, the tool, the retrieval, or the state machine. The cost of tracing is lower than the cost of debugging blind.
