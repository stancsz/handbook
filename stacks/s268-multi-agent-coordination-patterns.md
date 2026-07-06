# S-268 · Multi-Agent Coordination — The Architectural Decision That Compounds

When your agent loop grows beyond 10 steps, you hit a wall. One agent trying to do everything means a bloated context, degraded tool-calling, and a system you can't debug. Splitting into multiple agents fixes that — but introduces coordination failures that are harder to find and harder to fix. The coordination pattern you choose at the start determines your debugging surface, your cost envelope, and whether your multi-agent system holds up under production load.

## Forces

- **Cost compounds across agents.** A 4-agent orchestrator-worker workflow runs $5–8 per complex task. Each agent in the chain adds LLM calls, and inference cost stacks. Teams that don't model economics upfront cancel projects when the bill arrives.
- **Observability trails behind deployment.** 89% of teams have tracing infrastructure, but only 52% run evaluations. The gap is why debugging multi-agent systems is described as "mostly guesswork" in production.
- **Agent-to-agent boundaries are the failure surface.** Without typed schemas at handoff points, agents pass malformed outputs downstream and the error surfaces 3 steps later — invisible until it reaches the user.
- **Coordination models have fundamentally different failure modes.** An orchestrator that loops on a sub-agent is recoverable. A peer-to-peer system where two agents deadlock is not.

## The move

The four patterns that cover most production use cases — pick the one that matches your failure tolerance, not your demo complexity:

1. **Hierarchical (supervisor/worker).** One supervisor agent delegates to specialist workers. Clean error boundaries, easy to trace, natural fit for LangGraph's directed graphs. Best for: workflows where task distribution is predictable.
2. **Pipeline.** Linear chain: A → B → C → D. Each agent transforms the output of the last. Simplest to test and reason about. Best for: sequential transformations where output of step N feeds step N+1 directly.
3. **Orchestrator-worker.** A central orchestrator dynamically decomposes a task, dispatches to workers, synthesizes results. Most flexible — but $5–8/task cost makes it the most expensive. Best for: unpredictable, complex tasks requiring dynamic planning.
4. **Peer-to-peer.** Agents discover and communicate directly. Highest autonomy, lowest predictability. The A2A protocol (Anthropic/Google) is emerging as the standard for this. Best for: ecosystems of specialized agents that need to collaborate without a central coordinator.

**Non-negotiable at every handoff boundary:**
- Typed output schemas with version numbers — not "parse whatever the agent emits"
- Schema validation before the downstream agent processes the input
- Trace IDs that propagate across agent boundaries so you can reconstruct the full execution chain

**Observability minimum viable:**
- Distributed tracing (OpenTelemetry spans per agent step) + evaluation runs (not just logging)
- If you're not scoring outputs, you're flying blind when the model changes version

## Evidence

- **Analyst report:** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. 57% of organizations report agents in production (LangChain State of AI Agents 2026 Survey). 40% of agentic AI projects are at risk of cancellation by 2027, primarily due to economics failing at scale. — [RaftLabs synthesis citing Gartner + LangChain](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Engineering post:** Opensoul built a 6-agent marketing agency stack (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) on Paperclip, with each agent running autonomously on scheduled heartbeats, checking work queues and delegating to teammates. HN discussion surfaced that context-saved decision-making across agent boundaries is what separates working stacks from fragile demos. — [Hacker News Show HN, March 2026](https://news.ycombinator.com/item?id=47336615)
- **Enterprise architecture:** AI agents in regulated industries (legal, finance, healthcare) consistently prefer LangGraph's explicit graph state machines with persistent checkpoints — enabling auditability and rollback that CrewAI's role-based implicit flows don't provide. — [Turion.ai framework comparison, May 2026](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)
- **Observability gap:** Teams running 20+ simultaneous AI agents report that tracing without evaluation produces beautiful span graphs that explain what happened but not whether the output was right. The eval gap (52% evals vs 89% tracing) is the industry's dirty secret. — [QubitTool Agent Observability Guide, May 2026](https://qubittool.com/blog/agent-observability-engineering)

## Gotchas

- **Don't start with peer-to-peer.** It's the most elegant conceptually but the hardest to debug. Start hierarchical or pipeline, move to peer only when you have the observability stack to support it.
- **Schema versioning at handoffs is not optional.** When Agent A's output format changes, Agent B will silently break unless the schema is versioned and validated. This is the #1 silent failure mode in multi-agent systems.
- **Multi-agent is not free parallelism.** Adding agents does not automatically parallelize — most agentic workloads are I/O bound on LLM calls, not compute bound. Profile before you assume 4 agents = 4× throughput.
- **The framework choice is a 6-month commitment.** LangGraph, CrewAI, and Microsoft Agent Framework 1.0 (ex-AutoGen, GA April 2026) each use fundamentally different coordination models. Switching costs are high — choose based on your failure tolerance and auditability requirements, not feature lists.
