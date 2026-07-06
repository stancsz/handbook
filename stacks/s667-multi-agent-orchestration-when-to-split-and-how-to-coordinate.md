# S-667 · Multi-Agent Orchestration: When to Split and How to Coordinate

[You have a working single agent. It handles everything — research, drafting, editing, fact-checking. It works fine in the demo. Then production load hits and it starts hallucinating, timing out, or producing inconsistent output. The reflex is to prompt-engineer harder. The real answer is splitting it into a coordinated team. But splitting wrong is worse than not splitting, and the choice of coordination topology is where most teams quietly fail.]

## Forces
- [Most "agent failures" aren't model capability failures — they're orchestration and context-transfer failures at handoff points between agents, per Gartner's 1,445% surge in multi-agent inquiries Q1 2024→Q2 2025]
- [Splitting too early creates a coordination tax that outweighs the specialization benefit; splitting too late creates a context-overflow, cost-exploding monolith]
- [The three canonical topologies — hub-spoke, mesh, hierarchical — have very different failure domains, scaling curves, and failure modes]
- [Enterprise teams report 3x faster task completion and 60% better accuracy on complex workflows when splitting correctly, per Agile Soft Labs 2026 data]
- [Framework choice (LangGraph, CrewAI, custom) constrains which topologies are natural to express — picking the wrong one forces architectural workarounds]

## The move
**Split when you hit context saturation or domain boundary friction. Choose your topology by team size and failure isolation needs.**

- **When to split:** A single agent degrades when (a) context window fills mid-task, (b) two steps require different system prompts that conflict, or (c) tool count exceeds what the model can reliably route. If you find yourself writing "ignore previous instructions" in a tool description, you have a domain boundary problem.
- **Hub-spoke (star):** One coordinator agent routes tasks to 3–7 specialist spokes. Best when work is decomposable into independent subtasks. Low coordination overhead. The hub is the single failure point — if it fails, everything fails. Scales as O(n) with spokes.
- **Mesh (peer-to-peer):** Agents communicate directly with each other. Best for 2–4 agents doing tightly coupled collaborative work (e.g., writer ↔ editor ↔ fact-checker). Harder to debug — execution paths multiply combinatorially. Scales as O(n²) edges.
- **Hierarchical (tree):** Multiple hub-spoke clusters coordinated by upper-level hubs. Best for 20+ agents. The natural fit for tools like CrewAI's role-based crews, where a Director agent coordinates sub-teams. Scales as O(n log n).
- **Sequential pipeline:** Agents in strict series — output of one is input of next. Best for linear workflows where each step is a hard dependency (research → draft → edit → fact-check). Simple to debug. High latency is the cost — latency = sum of all stages.
- **Context handoff is the hard part, not the split.** Passing state between agents is where most failures occur. Be explicit about what context travels with each message, and validate at the boundary — don't let agents silently inherit state they shouldn't.
- **Framework recommendation:** LangGraph for production systems needing durable execution and observability (used at Klarna, Replit, Elastic). CrewAI for fastest prototyping with role-based teams (active v0.98+). AutoGen is in maintenance mode as of October 2025 — successor is Microsoft Agent Framework. Custom state machines when you need control the framework won't give you.

## Evidence
- **HN Show HN:** Opensoul — an open-source agentic marketing stack with 6 agents (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) running as a real marketing agency, each on scheduled heartbeats checking a shared work queue and delegating to teammates. Demonstrates hierarchical + hub-spoke hybrid at production scale — [https://news.ycombinator.com/item?id=47336615](https://news.ycombinator.com/item?id=47336615)
- **Augment Code enterprise guide:** Analysis of three canonical topologies — hub-spoke (2n edges, centralized hub state), mesh (n² edges, peer handoff), hierarchical (O(n log n) edges, layered per subtree) — with failure domain mapping and enterprise applicability per pattern — [https://www.augmentcode.com/guides/multi-agent-ai-architecture-patterns-enterprise](https://www.augmentcode.com/guides/multi-agent-ai-architecture-patterns-enterprise)
- **Agile Soft Labs enterprise survey:** 3x faster task completion, 60% better accuracy on complex workflows with multi-agent vs single-agent. Most agent failures attributed to orchestration/context-transfer issues at handoff points, not model capability. Gartner 1,445% surge in multi-agent inquiries used as market signal — [https://www.agilesoftlabs.com/blog/2026/03/multi-agent-ai-systems-enterprise-guide](https://www.agilesoftlabs.com/blog/2026/03/multi-agent-ai-systems-enterprise-guide)
- **JetThoughts framework comparison:** AutoGen (maintenance mode Oct 2025), CrewAI (active v0.98+), LangGraph (active, production-grade, used at Klarna/Replit/Elastic) — [https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)

## Gotchas
- [Splitting agents doesn't automatically improve quality — it improves parallelism and specialization. If your single agent fails because the model is weak, splitting won't fix it; you'll just have multiple weak agents]
- [Hub-spoke looks simple but the hub becomes a God object — every edge case gets routed through it, and it's easy to accidentally make the hub a bottleneck]
- [Mesh patterns are seductive because they're easy to reason about locally, but n² edge growth means observability becomes a nightmare past 4 agents — you can't trace execution paths]
- [Context handoff between agents is not free — each handoff resends context, which compounds token cost and latency. Profile the handoff frequency before committing to a topology]
