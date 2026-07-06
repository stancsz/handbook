# S-288 · Multi-Agent Coordination: Choose Your Topology Before It Chooses You

The moment you add a second agent, you face a topology decision that will define failure modes, observability, and cost for the lifetime of the system. Most teams pick an orchestration framework first and inherit its default topology — then discover the tradeoffs only in production.

## Forces

- **Coordination overhead scales non-linearly.** A peer-to-peer mesh of 10 agents has 45 potential communication channels. A supervisor/worker topology has 10. More channels mean more failure surfaces and harder debugging.
- **Topology constrains observability.** LangSmith traces work naturally with hierarchical trees; concurrent peer graphs require custom instrumentation. What you can see shapes what you can fix.
- **Failure domains differ by shape.** A sequential pipeline localizes failures to one step. A peer-to-peer mesh can cascade — one agent's error propagates to all its peers.
- **Teams default to peer-to-peer for "flexibility" and then regret it.** The organizational metaphor (everyone talks to everyone) feels natural but creates N² complexity as the team grows.

## The Move

Match topology to task type, not team preference. The three canonical patterns:

- **Sequential pipeline** — Use for tasks where output of agent A is the strict input of agent B. Simple, predictable, easy to trace and retry. The right choice for linear transformations (research → write → edit → publish).
- **Supervisor/worker** — Use when one agent owns the goal and others delegate sub-tasks. The supervisor maintains a shared state object; workers are stateless. Maps cleanly to LangGraph's graph model. Scales to 5–8 workers before coordination overhead dominates.
- **Peer-to-peer / marketplace** — Use only when task routing is genuinely undetermined and agents need to negotiate roles dynamically. High flexibility, high complexity. The A2A protocol (Anthropic, 2025) is emerging as the standard for this pattern. Most teams don't need this on day one.

Never mix topologies in a single workflow without explicit handoff logic. A "mostly supervisor/worker but sometimes peer" system is an undebuggable system.

### The split trigger: when to decompose into multiple agents

Decompose when agents need **different tool access, different model tiers, or different context windows**. If two agents would run the same model with the same tools on the same data, one agent with a more complex prompt is usually cheaper and more reliable.

Decompose also when the task has **independent sub-goals that can be parallelized**. A supervisor dispatching 4 research agents simultaneously to cover different dimensions of a question is a natural fit for supervisor/worker.

## Evidence

- **Gheware DevOps Blog (2026):** LangGraph's graph-based model supports all three topologies explicitly. The guide recommends defaulting to LangGraph for complex production workflows because "the steeper learning curve prevents painful rewrites 6–12 months in" when topology needs to evolve. — https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html
- **RockB Multi-Agent System Design (2026):** Documents that peer-to-peer networks of 10 agents have 45 potential communication channels vs 10 for supervisor/worker, and that LangChain's LangSmith traces "work well with hierarchical trees, struggle with concurrent peer graphs." Also notes Gartner documented a 1,445% surge in multi-agent inquiries (Q1 2024 → Q2 2025). — https://baeseokjae.github.io/posts/multi-agent-system-design-guide-2026
- **Opensoul HN Show (2025):** Production example of a 6-agent supervisor/worker hierarchy (Director → Strategist → Creative → Producer → Growth Marketer → Analyst). Built on Paperclip orchestration platform. Each agent runs on scheduled heartbeats, checks a shared work queue, delegates to teammates, and reports back. Demonstrates that role-based hierarchical decomposition maps cleanly to real organizational metaphors. — https://news.ycombinator.com/item?id=47336615

## Gotchas

- **The framework you choose imposes a default topology.** CrewAI defaults to role-based crews (a form of supervisor/worker). LangGraph defaults to graph-based (you choose). AutoGen defaults to agent-to-agent conversation (peer-like). Pick the topology first, then validate the framework supports it cleanly.
- **Checkpointing strategy must match topology.** Supervisor/worker state lives in the supervisor's shared state object — checkpoint that. Peer-to-peer state is distributed — you need a coordination store (Redis, Postgres) or you lose state on any agent crash.
- **Observability tooling has topology assumptions baked in.** LangSmith handles hierarchical traces well. Phoenix (Arize) handles concurrent graphs better. If you can't trace the communication flow, you can't debug it — instrument agent boundaries from day one, before the system gets complex enough that you dread adding it.
