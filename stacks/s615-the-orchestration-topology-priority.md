# S-615 · The Orchestration Topology Priority

When your multi-agent system is slow, expensive, or hallucinating — the instinct is to swap the LLM. But the evidence shows the topology of how agents are connected matters more than which model runs them.

## Forces

- **The model-first instinct is backwards for production.** Teams spend weeks evaluating GPT-5 vs Claude vs Llama when the real bottleneck is how tasks are routed, parallelized, and synthesized.
- **More agents ≠ more capability without the right structure.** Adding agents without a coherent orchestration pattern amplifies failure modes (cascading hallucinations, context pollution, cost explosions).
- **Framework choice is downstream of topology.** LangGraph, CrewAI, and AutoGen all support the same patterns — the pattern choice drives the framework fit, not the reverse.
- **Naive multi-agent setups fail in predictable ways.** Serial execution bottlenecks, single-agent context overflow, and undirected peer-to-peer chattiness all have known structural fixes.

## The move

**Pick your orchestration topology before picking your framework.**

1. **Supervisor + Specialists (hierarchical).** One agent decomposes the task and routes subtasks. Specialists execute. Supervisor synthesizes. Simple, debuggable, and covers ~70% of real production use cases. LangGraph implements this as a native supervisor pattern; CrewAI calls it hierarchical mode.
2. **Sequential Pipeline (fixed chain).** Agents execute in a defined order — researcher → writer → editor. Fixed contracts per agent. Predictable cost, step-by-step evaluation, low latency overhead. Best when the workflow is well-understood and does not need dynamic routing.
3. **Parallel + Fan-out.** Multiple agents work on independent sub-tasks simultaneously, results merged at a barrier. Google internal experiments used this to cut processing from **1 hour to 10 minutes (6× speedup)** on a complex task. The key is ensuring sub-task independence — correlated sub-tasks create synchronization overhead that erases the gains.
4. **Agent-as-Tool.** An agent is wrapped as a callable tool by another agent — used for complex, domain-specific reasoning that should not be decomposed further. Each agent maintains its own context window; the parent only sees the output.
5. **Agentic RAG over naive RAG.** Instead of chunk → embed → retrieve top-K → generate, embed a planning agent that decides retrieval strategy, executes it, evaluates relevance, and iterates. Naive RAG has a **~40% retrieval failure rate** in production. Agentic RAG with self-correction loops closes that gap substantially.

## Evidence

- **Production field notes:** Multi-agent systems are harder to operate than single agents by roughly the order of their agent count. The most debuggable pattern is supervisor + specialists — "most multi-agent production systems are actually this pattern." — *TURION.AI field note, March 2026* — https://turion.ai/blog/multi-agent-orchestration-infrastructure-production
- **Benchmarking orchestration topology:** Google internal experiments (Agent Bake-Off) showed distributed multi-agent cut processing from 1 hour to 10 minutes (6×). AdaptOrch research (2026) found orchestration topology delivers **12–23% gains on SWE-bench** — outperforming model selection decisions. — *MACGPU Blog, June 2026* — https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html
- **Framework + topology fit:** LangGraph (graph-based, state machines, ~12K stars, used by Klarna/Uber/Replit) suits complex state management and checkpointing. CrewAI (role-based, ~31K stars) suits fast prototyping of sequential specialist pipelines — "70% of use cases are sequential specialist pipelines." AutoGen/AG2 (conversational, ~42K stars) suits multi-party research dialogs. — *hjLabs production comparison, Pickaxe 2026 comparison* — https://pickaxe.co/post/crewai-vs-langgraph-vs-autogen
- **Agentic RAG outcomes:** Naive RAG pipelines have ~40% retrieval failure rate by mid-2026. Harvey AI reports a **0.2% hallucination rate** serving 700+ legal clients using agentic RAG with self-correction loops. Deutsche Telekom achieved **89% acceptable answers** in production. — *aliac.eu enterprise guide, February 2026* — https://aliac.eu/blog/agentic-rag-in-production
- **CrewAI production architecture:** The framework now recommends a "Flow-First mindset" — wrap crews in Flows for state management, control (loops, conditionals, branching), and observability. Production-ready systems need all three. — *CrewAI production architecture docs, v1.15.1* — https://docs.crewai.com/v1.15.1/en/concepts/production-architecture
- **MCP as the tool-calling substrate:** MCP reached 97M+ monthly SDK downloads, 10,000+ active public servers, and adoption across ChatGPT, Cursor, Claude, Gemini, VS Code, and Microsoft Copilot. — *Anthropic ecosystem update, December 2025* — https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol

## Gotchas

- **Swapping the LLM before fixing the topology is the most common wasted effort.** Evaluate and fix your orchestration pattern first. A well-structured pipeline with GPT-4o-mini will outperform a broken topology on GPT-4o.
- **Peer-to-peer agent architectures sound elegant and are operationally painful.** Unlimited agent-to-agent messaging creates non-deterministic execution paths that are nearly impossible to reproduce and debug. Use explicit routing or supervisor patterns instead.
- **CrewAI's easy onboarding is also its danger.** New teams are productive in an afternoon but then discover that the "manager agent delegates to workers" abstraction leaks when you need fine-grained control of retry logic, checkpointing, or conditional branching. That's when the migration to LangGraph happens.
- **Parallel fan-out only helps when sub-tasks are independent.** If your "parallel" agents are constantly waiting on each other's outputs, you've added orchestration overhead without the parallelism benefit.
