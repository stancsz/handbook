# S-318 · Multi-Agent Coordination: When to Split Agents and How to Wire Them

Single-agent architectures hit a ceiling once a pipeline needs to handle multiple domains, expertise areas, or concurrent tasks simultaneously. The answer most teams arrive at is multi-agent — but the coordination topology matters more than any individual agent's capability. The choice between hierarchy, peer networks, and pipeline patterns determines failure modes, latency, and how hard it is to debug.

## Forces

- **LLMs degrade in long contexts, not just from length but from persona bleed.** When one agent handles research, code, and creative writing, the model "leaks" personas into each other's outputs. Splitting by role doesn't just parallelize — it reduces interference.
- **Hierarchical coordination adds latency but prevents runaway loops.** A director-agent bottleneck is real; so is an uncontrolled peer network where agents spiral into redundant tool calls. The cost of coordination must be explicit.
- **Framework choice encodes your coordination topology.** LangGraph, CrewAI, and AutoGen don't just differ in syntax — they enforce different mental models (state machine, role-based hierarchy, conversation). Picking the wrong one means retrofitting your architecture to the framework.
- **The team-structure analogy is seductive but limited.** Real organizations have shared context, institutional memory, and managers with veto power. Agents sharing a work queue don't automatically get that — it has to be designed.

## The move

**Split agents by cognitive domain, not by task.** A marketing stack with Director + Strategist + Creative + Producer + Growth + Analyst works because each maps to a distinct expertise area, not a linear pipeline stage. The Coordinator pattern (one orchestrator routing to specialists) dominates early-stage systems; peer networks emerge for tasks where multiple agents must contribute simultaneously.

**Use heartbeat scheduling for autonomous agents rather than request-response.** Opensoul's approach — agents run on scheduled heartbeats, check their work queue, execute, delegate, and report — decouples execution from user requests and prevents the "one user = one agent run" bottleneck.

**Choose your framework by coordination topology:**
- **LangGraph** when you need explicit state machines, complex branching, or audit trails through the graph (production systems, Klarna/Uber/Replit adoption)
- **CrewAI** for role-based hierarchies that map cleanly to org charts — fastest path to a working prototype, but teams report hitting scalability ceilings within 6–12 months
- **AutoGen (AG2)** for multi-party conversations, debate patterns, or research synthesis — most flexible conversation model, but the Microsoft→AG2 transition created real confusion in tutorials

**Implement budget gates as first-class infrastructure, not afterthoughts.** Paperclip's architectural insight: agents succeeding too well run up API bills with no human oversight. Budget caps per agent, per task type, or per time window belong at the platform layer, not the prompt layer.

## Evidence

- **HN Show HN:** Opensoul — 6-agent marketing stack built on Paperclip, agents run autonomously on heartbeat scheduling, organized as a real marketing agency with Director/Strategist/Creative/Producer/Growth/Analyst roles. The creator (iamevandrake) built it after a year of autonomous agent systems work, citing the need for organizational structure around agents to prevent runaway costs. — https://news.ycombinator.com/item?id=47336615
- **Dev blog (Gheware):** Framework comparison — LangGraph adopted by Klarna, Uber, Replit for production; CrewAI's role-based model fastest to prototype; AutoGen's conversation model most flexible for multi-party scenarios but highest learning curve. All three are model-agnostic (OpenAI, Anthropic, local via Ollama/vLLM). — https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html
- **Reddit r/LocalLLaMA:** AI Developer Tools Map 2026 — clarification that the full stack shouldn't be composed as LangChain + CrewAI + Dify together ("recipe for confusion and dependency pain"), with explicit mapping of agent frameworks by maturity and use case fit. — https://www.reddit.com/r/LocalLLaMA/comments/1r47a79/
- **Microsoft ISE blog:** Multi-agent system at scale (e-commerce voice assistant) — identified agent selection accuracy, LLM usage optimization, and orchestration as three core production requirements; found that CrewAI fit their described requirements well for role-based workflows. — https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale

## Gotchas

- **Agent-to-agent delegation without a shared memory layer produces inconsistent context.** If the Director tells the Strategist to research X, and the Strategist's context window doesn't include prior conversation history, outputs diverge. Shared vector stores or a persistent work queue with full context are not optional.
- **CrewAI's role-based model looks like an org chart but has no actual chain of command.** Agents can be instructed to delegate, but nothing enforces that delegation. Expect teams to implement ad-hoc handoff protocols when agents start ignoring their assigned roles.
- **Heartbeat-based autonomy needs watchdog budgets.** Without per-agent spend limits and task-timeouts, a misbehaving agent can make unbounded API calls. This isn't theoretical — the Paperclip/Opensoul creator explicitly cites runaway costs as the problem this architecture was designed to solve.
- **LangGraph's graph-based state is powerful but verbose.** The explicit state management that makes it production-stable also means more boilerplate. Teams prototyping with CrewAI often hit a wall when they try to add the conditional branching and error recovery that LangGraph makes first-class.
