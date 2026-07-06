# S-643 · The Coordination Layer Is the Product

[Multi-agent systems promise specialization and parallelism, but the thing that kills them isn't the agents — it's the untyped, unversioned handoffs between them. The coordination layer is where agentic systems succeed or silently fail.]

## Forces
- **The ceiling isn't the model — it's the boundary.** Single agents hit limits on expertise breadth, parallelism, and workflow complexity. But splitting into multiple agents introduces coordination costs that are invisible in demos and brutal in production.
- **Untyped handoffs kill multi-agent workflows faster than any other issue.** Every agent-to-agent boundary without a validated schema with version numbering is a silent failure mode waiting to trigger at 3 AM.
- **Inference cost compounds across agents.** A 4-agent orchestrator-worker workflow costs $5–8 per complex task. The economics need modeling before architecture commit.
- **Observability exists, evals don't.** 89% of teams have distributed tracing; only 52% have evaluation frameworks. Multi-agent debugging without evals is guesswork.
- **The orchestration framework is a philosophy, not a feature matrix.** Choosing LangGraph vs CrewAI vs AutoGen is choosing how much of the coordination logic you want to own vs. outsource.

## The move

1. **Model the handoff schema before you model the agents.** Define the exact input/output contract at every agent boundary. Version it. Treat it like an API contract, because it is one.

2. **Route on intent, not on role.** The most common mistake in multi-agent design is splitting by job title (researcher, writer, editor) rather than by decision type (routing, execution, validation). Intent-based routing scales better under complexity.

3. **Instrument every handoff with a validator, not a logger.** Validators enforce schema, policy constraints, and cost limits before output is consumed. Validators should be deterministic and fail loudly — silent failures are the most dangerous in multi-agent pipelines.

4. **Default to hierarchical until you have evidence for peer-to-peer.** A supervisor/manager agent routing to specialists is easier to debug, reason about, and cost-control than a mesh of equal agents negotiating outcomes. Peer-to-peer only when the problem genuinely has no natural root.

5. **Budget the coordination overhead.** Add 20–40% token overhead for context-passing and summarization between agents. A naive 4-agent pipeline will cost 2–3x more than the sum of individual agent costs.

6. **Build the eval framework before the agents.** The observability gap (89% tracing, 52% evals) is not a tooling problem — it's a sequencing problem. Teams add evals after the agents are built, which means they're flying blind during development.

7. **Design for graceful degradation, not perfect success.** A multi-agent system where one agent failure cascades is worse than a single-agent system. Every agent boundary needs a defined failure action (retry, escalate, degrade, halt).

## Evidence
- **RaftLabs engineering post (Nov 2025):** 89% of teams have observability but only 52% have evals; 4-agent orchestrator-worker workflows cost $5–8 per complex task; Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025; teams reporting success (3x faster, 60% better accuracy) run multi-agent architectures, not overstretched single agents. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **NKKTech production comparison (2026):** LangGraph dominates enterprise with 43% adoption; crews with specialized roles (research → write → edit → publish) outperform monolithic agents on complex workflows; AutoGen's conversational pattern creates debugging overhead at scale. — [NKKTech](https://nkktech.com/blog/langgraph-vs-crewai-vs-autogen-2026)
- **TURION.AI pattern analysis (Dec 2024):** Peer-to-peer patterns have no natural coordinator, making cost control and failure recovery harder; hierarchical patterns enable explicit priority and deadline enforcement; hybrid patterns work best for variable-complexity tasks where cheap fast-path and expensive thorough-path coexist. — [TURION.AI](https://turion.ai/blog/multi-agent-collaboration-patterns)
- **DevStarSJ production lessons (Apr 2026):** 2026 agents handle real customer interactions, execute code, and manage workflows — the engineering shift is from "can we build agents?" to "how do we build agents that are reliable, safe, and cost-effective at scale?" The production agent stack needs: orchestration (planning/execution), context (RAG/memory), tool integration (MCP), guardrails (input/output validation), and observability as a first-class layer. — [DevStarSJ](https://devstarsj.github.io/ai/architecture/2026/04/11/ai-agents-production-architecture-patterns-memory-safety-reliability)

## Gotchas
- **The "we'll add schemas later" trap.** Multi-agent systems with untyped handoffs work fine in demos. They fail silently and expensively in production when agents receive subtly wrong data shapes from upstream failures.
- **Prompt-caching is not free but it's load-bearing.** Cross-agent context passing without caching re-embeds the same document fragments repeatedly. For agentic RAG with 4+ agents, caching can reduce cost by 40–60%.
- **Framework lock-in is real.** LangGraph gives you graph primitives you own and can migrate. CrewAI gives you role abstractions that are fast to start but harder to deviate from. Choose based on how much of your logic is standard vs. novel.
- **Version your agent prompts like you version your code.** A model update can silently change agent behavior at a boundary. Pin prompt versions and validate against the eval framework on every change.
