# S-594 · The Agentic Stack Is Stratifying: Infrastructure, Guardrails, and the MCP Moment

The single-prompt agent died in 2024. What replaced it is not a monolith — it's a stack of specialized layers that teams are stitching together for the first time. The result is a new class of architectural decisions: what belongs in orchestration, what belongs in tooling, and what belongs in sandboxing — with each layer having very different production characteristics.

## Forces

- **The orchestration layer is the easiest to swap.** LangGraph, CrewAI, and AutoGen compete aggressively, but the abstraction cost of switching is low — they all call the same LLMs and expose similar graph/node primitives.
- **The tool integration layer is where the real lock-in lives.** Custom tool schemas, REST wrappers, and internal API connectors are expensive to rebuild. This is where teams get stuck.
- **Sandboxing is becoming its own discipline.** Agents that write code, browse the web, or execute user-provided scripts need isolation — and off-the-shelf containers don't cut it. E2B, Modal, Shuru, and Firecracker wrappers are converging here.
- **Context management is the hidden cost center.** Agents hallucinate not because of bad models but because they lack the right context at the right time. Vector stores, graph databases, and session state are first-class production concerns.
- **40% of multi-agent pilots fail within six months of production deployment.** The failure is almost never the model — it's the handoff schemas, the lack of observability, or the missing eval loop.

## The Move

Layer the agentic stack explicitly. Treat each layer as independently deployable, with clean contracts between them.

- **Orchestration:** LangGraph for complex stateful graphs; CrewAI for role-based agent teams where task handoffs are well-defined; raw Python + asyncio for simple linear workflows. Don't reach for a framework if a loop will do.
- **Tool protocol:** Default to MCP (Model Context Protocol, Anthropic, November 2024) for new integrations. It standardizes how agents discover and invoke tools — replacing a tangled mess of custom REST wrappers per agent. Google's A2A (Agent-to-Agent) protocol handles inter-agent communication.
- **Sandboxing:** Isolate agents that execute code or external content. E2B for Python/JS execution; Modal for serverless GPU workloads; Firecracker-based microVMs for lightweight isolation. Don't give agents direct system access.
- **Memory/persistence:** Redis-based checkpointing for LangGraph state; vector stores (Qdrant, Pinecone) for semantic memory; graph databases (Neo4j) for relationship-heavy context. Keep session state separate from long-term knowledge.
- **Observability:** LangSmith for trace-first debugging (Klarna, LinkedIn, Cisco, Nvidia all use it); Arize Phoenix for open-source LLM observability with span-level tracing. The eval gap (89% of teams have observability, only 52% have evals) is the single biggest debugging bottleneck in multi-agent systems.
- **Guardrails:** Input validation at every tool boundary; output validators as deterministic contracts that fail loudly; critic agents for downstream validation. Silent failures are the most dangerous in multi-agent pipelines.

## Evidence

- **Engineering blog:** The agentic stack is stratifying into specialized layers — orchestration, tool integration, sandboxing — each with different defensibility profiles. "Going monolithic is the wrong call." — Philipp Dubach, [philippdubach.com/posts/dont-go-monolithic](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/) (HN discussion, 2025)
- **Industry survey:** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. 57% of organizations have agents in production (LangChain survey, 1,300+ professionals). A 4-agent orchestrator-worker workflow costs $5–8 per complex task. 89% of teams have observability, but only 52% have evals. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide), November 2025
- **Production case:** GenBrain AI runs 11 agents as a production organization on GKE (CEO, CTO, CSO, Backend, Frontend, Marketing, DevOps, and peers). Each agent runs in its own GKE pod with topic-based pub/sub via Redis. Untyped handoffs between agents were identified as the #1 failure mode — every agent-to-agent boundary needs a validated schema with version numbering. — [agent.ceo](https://agent.ceo/blog/multi-agent-architecture-patterns), March 2026
- **Tool protocol:** MCP (Anthropic, November 2024) described as "virtual USB-C for agents" — a universal interface standardizing how AI models connect to external systems. By 2026, MCP had become the de-facto standard for tool integration, with the Linux Foundation providing governance. Google's A2A protocol emerged for agent-to-agent communication. Together they represent the HTTP moment for AI agents. — [Omnitech Inc.](https://omnitech-inc.com/blog/model-context-protocol-mcp-for-ai-agent-integration), November 2025

## Gotchas

- **Don't put business logic in orchestration.** The graph structure is for flow control, not for complex domain rules. Business logic belongs in tools or agents — keep the orchestration layer thin.
- **Every handoff needs a schema.** The most common multi-agent failure is untyped message passing between agents. Define the contract at every boundary, version it, and validate it.
- **Observability without evals is theater.** Traces tell you what happened; evals tell you whether it was right. Teams instrument their pipelines extensively, then ship agents that produce plausible but incorrect outputs. Build the eval loop before you scale.
- **Cost compounds across agents.** A 4-agent workflow at $1–2/inference call adds up fast. Model the economics before you commit to a multi-agent architecture — for simple tasks, a single capable agent often beats a team of specialists.
