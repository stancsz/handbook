# S-639 · Agent Stack Stratification: Why Monolithic Frameworks Break and What Replaces Them

[When you first build an agent, you reach for one framework that does everything. When you try to ship it, you discover that orchestration, sandboxing, memory, and observability each have fundamentally different change rates — and bolting them together in one layer makes all of them worse.]

## Forces

- The agent stack has at least six distinct layers (runtime/execution, sandboxing, orchestration, memory, tools, security), each with different reliability requirements, change velocities, and defensibility profiles — forcing them into one framework creates a reliability ceiling
- Sandboxing needs to be more stable than orchestration (you don't want your firewall updating on every new LangGraph release), but monolithic frameworks tend to evolve them together
- Different layers want different execution models: sandboxing wants process isolation, orchestration wants durable state machines, memory wants async writes — one runtime can't serve all optimally
- The defensibility question is different at each layer: your orchestration logic is not your competitive moat, but your organizational world model (what your agents know about your company) absolutely is

## The Move

The 2025-2026 production pattern is **layered specialization** — composable infrastructure where each concern lives in its own well-defined layer, with typed interfaces between them:

- **Runtime/Execution:** Container-based isolation. Modal, E2B, Shuru, and Firecracker-based microVMs handle execution independently from orchestration. GenBrain AI runs each agent as a separate GKE pod with its own MCP servers (Git, Bash, file operations) communicating through NATS JetStream with Firestore for persistence. This is not Kubernetes as deployment convenience — it's pod-per-agent for hard fault isolation.
- **Sandboxing:** Subprocess isolation with declared network whitelists. One HN practitioner's approach: AST scanning of installed skills before execution, network whitelists per skill, subprocess-per-call so one bad tool can't poison the parent. This is fundamentally different from "let the LLM call whatever it wants" — the security boundary is architectural, not prompt-based.
- **Orchestration:** Purpose-built state machines. LangGraph (state-machine graphs, high production readiness, used at Klarna/Replit/Elastic) for complex durable workflows; CrewAI (role-based agent crews, 2-3 day time-to-first-agent) for content/support pipelines; Temporal for workflows that need guaranteed completion semantics across failures. The key signal: AutoGen entered maintenance mode in October 2025, with Microsoft directing new development to the Agent Framework — teams still on AutoGen face a forced migration.
- **Memory:** Scale-dependent. Personal-agent scale: SQLite + FTS5 (full-text search, zero infra). Team/product scale: vector DBs (Pinecone, Qdrant, pgvector for structured+vector hybrid). The differentiation is no longer retrieval quality (all mature) — it's operational: pgvector avoids a separate service, Pinecone wins on managed ops, Qdrant on open-source flexibility.
- **Tool interface:** MCP (Model Context Protocol) became the standard connector. MCP server downloads grew from 100K to 8M in five months. 14,000+ MCP servers cataloged, 80% with remote deployment support. Block reported 50-75% time savings on common tasks using MCP-powered tooling. The key design decision: build or adopt — community servers exist for GitHub, CI/CD, comms platforms; custom servers for proprietary internal tools.
- **Security:** Identity and access control separate from the model layer. Compliance, permissions, and audit trails live here, not in orchestration.

## Evidence

- **Engineering blog:** Philipp Dubach (Feb 2026, updated May 2026) documented the stratification pattern with a six-layer taxonomy — argued "the defensible asset in enterprise AI is not the model, it's the organizational world model" — [philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Production case study:** GenBrain AI CTO Agent (agent.ceo) described running 11 agents as a production organization on GKE since Feb 2026, with each agent as a separate Claude Code CLI pod, NATS JetStream for communication, and Firestore for persistence — directly validates pod-per-agent isolation as a production pattern — [agent.ceo/blog/multi-agent-architecture-patterns](https://agent.ceo/blog/multi-agent-architecture-patterns)
- **Framework comparison:** MarsDevs (2026) documented AutoGen entering maintenance mode (Oct 2025), CrewAI at v1.12 with role-based teams, LangGraph v1.0 GA with graph-based state machines and GHA/langsmith tracing — [marsdevs.com/compare/langgraph-vs-crewai-vs-autogen](https://www.marsdevs.com/compare/langgraph-vs-crewai-vs-autogen)
- **Multi-agent survey data:** RaftLabs (Nov 2025) reported 1,445% surge in multi-agent system inquiries (Q1 2024 → Q2 2025 per Gartner), 57% of organizations already running agents in production, but 40% of agentic AI projects at risk of cancellation by 2027 — [raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **MCP metrics:** Nevermined.ai documented MCP's 8,000% download growth in 5 months, Block's 50-75% task time savings, and 50% of teams citing security complexity as top adoption barrier — [nevermined.ai/blog/model-context-protocol-adoption-statistics](https://nevermined.ai/blog/model-context-protocol-adoption-statistics)
- **HN practitioner:** Anonymous backend lead at Manus described SQLite+FTS5 for memory at personal-agent scale, subprocess isolation with AST scanning and network whitelists for skill sandboxing — [news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)

## Gotchas

- Reaching for one framework for everything is the most common mistake — it works until you hit the change-rate mismatch between layers, then you refactor under production load
- Untyped agent-to-agent handoffs (plain text or loosely structured JSON) are the #1 failure mode in multi-agent systems — every boundary needs a versioned schema, even in a two-agent setup
- MCP's explosive growth has outpaced security tooling — half of enterprise teams cite security complexity as the top MCP barrier; this will get worse before it gets better
- The $5-8 per complex task cost for 4-agent orchestrator-worker workflows compounds fast at scale — model economics before committing to multi-agent architecture
- LangGraph's 2-3 week learning curve is real; CrewAI's 2-3 day learning curve is also real — if you're prototyping, CrewAI first and migrating later is a valid path
