# S-216 · Multi-Agent Orchestration Pattern Selection

You have two agents. Maybe three. You're about to connect them and the question is not "how" — it's "which topology?" Supervisor chain? Peer-to-peer? Hierarchical? The pattern you choose shapes latency, failure modes, cost, and whether a third engineer can debug it at 2am.

## Forces

- Supervisor patterns are simple but create a single point of failure — if the supervisor goes off-track, the whole system drifts
- Peer-to-peer is resilient but introduces consensus overhead and token duplication that balloons costs (CAMEL: 86% token overlap, AgentVerse: 53%)
- Hierarchy scales to 20+ agents but coordination overhead grows non-linearly
- 72% of enterprise AI projects now use multi-agent systems (up from 23% in 2024), but observability remains the #1 cited barrier to production adoption
- Token cost compounds multiplicatively with agent count — every relay pass is money

## The move

Match the orchestration topology to the task structure, not the team preference.

- **Sequential chain (supervisor → worker):** Linear tasks where each step depends on the last. Minimal coordination overhead. The supervisor holds global state; workers are disposable. Best for: form-filling, document processing pipelines, compliance reviews.
- **Hierarchical (director → manager → worker):** Tasks that decompose into parallel sub-tasks. The director never touches tools directly — it decomposes, delegates, synthesizes. Best for: research agents, marketing stacks (6-agent Opensoul uses this — Director coordinates Strategist, Creative, Producer, Growth, Analyst), complex enterprise workflows.
- **Peer-to-peer (all agents equal, negotiated):** Tasks where no single agent has a global view. Agents message each other, negotiate, and converge. Best for: multi-perspective analysis, adversarial validation, distributed expertise domains.
- **Swarm (50+ agents, emergent coordination):** Tasks requiring massive parallel exploration or optimization. Each agent has a local objective; global behavior emerges. Best for: robotics, logistics optimization, simulation. Documented as "emergence complexity" is high; mostly research, not production enterprise.

**Decision heuristic from Zylos Research (2025):** If the task fits in a supervisor pattern, use it. Only escalate to hierarchy when (a) sub-tasks can run in parallel and (b) you have more than 3 distinct domain roles. Only go peer-to-peer when fault tolerance outweighs latency. Never start with swarm.

## Evidence

- **HN Show HN (2025):** Opensoul open-sourced a 6-agent marketing stack on Paperclip with a Director-thought pattern — the Director decomposes strategy and delegates to domain agents (Strategist, Creative, Producer, Growth Marketer, Analyst), each running on scheduled heartbeats. Confirmed hierarchical pattern works for marketing agency workflows at production scale.
- **Zylos Research (2026):** Surveyed enterprise multi-agent adoption. Found 72% of enterprise AI projects now involve multi-agent systems (up from 23% in 2024). Token duplication is a measurable cost: MetaGPT 72%, CAMEL 86%, AgentVerse 53% overlap when agents share context. Peer-to-peer is slower to converge but more fault-tolerant.
- **Dev Community / InfraSketch (2025):** Matt Frank's architecture guide distinguishes agent from chatbot: "A chatbot is a function: input in, output out. An agent is a loop with branching logic, tool access, and memory." Key insight: every agent iteration costs tokens, time, and money — orchestration pattern directly determines iteration count.

## Gotchas

- **Over-architecting for simplicity:** Adding hierarchy when a linear chain suffices adds coordination overhead with no benefit. Start with supervisor; escalate only when you have proof the task decomposes.
- **Ignoring token cost at design time:** Peer-to-peer with 5 agents, 10 relay rounds, and shared context windows can cost 5–10× a supervisor pattern for the same output. Model token budgets before choosing topology.
- **No failure boundaries:** Every agent in a topology needs a defined failure mode — what does the system do when a worker agent returns malformed output? LangGraph's node-level error handling provides this natively; CrewAI's delegation chain obscures it.
- **Shared state is a hidden coupling:** When multiple agents read/write shared memory, race conditions and stale context emerge silently. Use structured state channels, not shared mutable objects.
