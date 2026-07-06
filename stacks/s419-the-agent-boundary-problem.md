# S-419 · The Agent Boundary Problem

Most multi-agent systems fail not because individual agents are weak, but because the boundaries between them are drawn in the wrong place. Split by workflow step and you get a pipeline that is brittle, expensive, and impossible to debug. Split by the right axis — audience, timing, or trust — and complexity becomes manageable.

## Forces

- **Complexity scales nonlinearly with agent count.** Multi-agent systems are harder to operate than single agents by roughly the order of their agent count. Two agents don't mean twice the debugging surface — they mean exponential coordination surface. (TURION.AI, "Multi-Agent Orchestration Infrastructure: Lessons from Production," March 2026)
- **The obvious split is the wrong split.** Drawing agent boundaries along workflow steps (researcher → writer → editor) feels natural but creates tight coupling, opaque handoffs, and error propagation that is hard to isolate. (FRE|Nxt Labs, "Multi-Agent System Architecture: A Practical Guide for Production," April 2026)
- **Every iteration costs tokens, time, and money — and branches introduce compounding error risk.** More agents means more LLM calls. More calls means more failure modes. A single agent with a loop is often cheaper and more reliable than three agents in sequence. (Matt Frank, DEV Community, "Building Multi-Agent AI Systems," February 2025)
- **Adding agents feels like progress; it usually isn't.** The pressure to show "multi-agent" as a feature creates premature architectural complexity. Start with one agent. Add more only when a genuine boundary appears. (FRE|Nxt Labs)

## The Move

Draw boundaries along these axes, not along workflow steps:

**By audience** — Different end users need different context, tone, and trust levels. A customer-facing agent and an internal ops agent share no meaningful context, so sharing it introduces noise and risk.

**By timing** — Agents with real-time requirements (sub-second response) and agents with deliberative requirements (minutes-long research) should be separate processes. Merging them creates latency ceilings.

**By trust** — A "helpful" agent and an "impartial assessor" agent cannot share context without the assessor losing its independence. The code reviewer that knows the coder's intent will not catch the same bugs. (FRE|Nxt Labs)

**Use supervisor + specialists as the default production pattern.** One supervisor decomposes tasks and routes to specialists. Specialists execute and return. Supervisor integrates. This is simple, debuggable, and covers most real production use cases — including Klarna, Replit, and Elastic's agent deployments. (TURION.AI; JetThoughts, "LangGraph vs CrewAI vs AutoGen," 2025)

**Use pipeline (sequential) only when the contract is fixed and the cost is predictable.** The `researcher → writer → editor` chain works when each agent has a well-defined schema for input and output, and when failures at each step can be caught independently. (TURION.AI)

**For local-only stacks, prefer Langroid over CrewAI.** CrewAI uses LangChain under the hood, which practitioners report as "too bloated, wants to be everything." Langroid offers Pydantic-based tool definitions, critic agents, and LiteLLM for model agnosticism — without LangChain's overhead. For serious use, many teams copy CrewAI's API design and implement it on top of LiteLLM directly. (r/LocalLLaMA, "LLM Agent platforms," 2024/2025)

## Evidence

- **Technical blog (TURION.AI):** Multi-agent systems in production require typed and scoped shared state with checkpointing, explicit error handling with retries/fallbacks/timeouts, and full-trace observability. Supervisor + specialists is the dominant pattern. — [https://turion.ai/blog/multi-agent-orchestration-infrastructure-production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Research report (FRE|Nxt Labs):** Agent boundaries should be drawn by audience, timing, or trust — not by workflow step. Start with one agent and add more only when a genuine boundary appears, because complexity is not free. — [https://www.frenxt.com/research/multi-agent-architecture-guide](https://www.frenxt.com/research/multi-agent-architecture-guide)
- **Comparison analysis (JetThoughts):** LangGraph (state-machine graphs) is the production choice for systems needing observability and durable execution. CrewAI (role-based crews) is for fast delivery on content and support pipelines. AutoGen entered maintenance mode October 2025. — [https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)
- **Community discussion (r/LocalLLaMA):** CrewAI's LangChain dependency is a known liability. Teams building serious local stacks extract the API concept and reimplement on LiteLLM. — [https://www.reddit.com/r/LocalLLaMA/comments/1bskjki/llm_agent_platforms](https://www.reddit.com/r/LocalLLaMA/comments/1bskjki/llm_agent_platforms)

## Gotchas

- **Supervisor becomes a god object.** If one agent routes to all others and also does final synthesis, you've built a bottleneck. Give the supervisor a narrow contract; let specialists own their domain fully.
- **Shared state without schema is chaos.** Multiple agents reading and writing unstructured context leads to inconsistent world state. Use typed schemas (Pydantic models) for all inter-agent communication. (TURION.AI)
- **Checkpointing is not optional.** Without durable state, a process restart mid-workflow loses all context. For anything beyond a single-turn task, checkpoint every major state transition. (FRE|Nxt Labs)
- **Observability at the agent level is not enough.** You need trace-level visibility into inter-agent communication — not just what each agent returned, but why it was routed there and what the routing decision was based on. (TURION.AI)
