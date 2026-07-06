# S-254 · Multi-Agent Orchestration: The Pattern You Pick Before the Framework

Forty percent of multi-agent pilots fail within six months of production deployment. The failure is almost never the LLM, rarely the framework, and almost always the orchestration topology. Teams pick LangGraph or CrewAI or AutoGen and treat it as the architectural decision. It is not — the topology is.

## Forces

- **"One super-agent" works in demos but collapses under complexity.** A single agent with 15+ tools is a signal, not a performance issue — it means the agent needs peers, not more tools.
- **Every orchestration pattern has a distinct failure mode.** Choosing a peer network for a task that needs a single accountability point, or a supervisor chain for a task that needs parallelism, will break in production — not immediately, but on the second Tuesday when the load is unusual.
- **Framework choice is downstream of topology.** LangGraph's state-machine primitives, CrewAI's role-based agents, and AutoGen's group chat are all solving the same coordination problem with different idioms. Pick the pattern first.
- **The 2025-2026 transition is making this acute.** Gartner reported a 1,445% surge in multi-agent system inquiries between Q1 2024 and Q2 2025. Teams that survived the proof-of-concept are now hitting the wall where "more agents" makes coordination harder, not easier.

## The move

Six orchestration patterns have emerged from production deployments as distinct, non-interchangeable choices. The decision tree starts with one question: does the task require a single point of decomposition and accountability, or does it require parallel expertise?

**Pattern 1 — Orchestrator-Worker (hierarchy, single decomposition point)**
One agent receives the task, breaks it into subtasks, delegates to specialist workers, and assembles results. The orchestrator uses a capable model; workers use cheaper, task-specific ones.
- *Cost reduction:* 40-60% vs. single-agent-per-task via model cascading
- *Failure mode:* Bottleneck at orchestrator; poor decomposition = cascade failure
- *Use when:* Cross-functional work with clear task decomposition and a single accountability point is required

**Pattern 2 — Supervisor-Executive (hierarchy with approval gate)**
A supervisor agent validates worker outputs before assembly. Adds a review-and-correction loop.
- *Cost reduction:* Lower than orchestrator-worker due to additional passes
- *Failure mode:* Supervisor becomes a second bottleneck; over-validation adds latency without quality gain
- *Use when:* High-stakes outputs where validation is cheaper than errors (legal, compliance, financial)

**Pattern 3 — Hierarchical (multi-level supervisor chain)**
A senior agent delegates to mid-level agents, which delegate to specialists. Matches org-chart-style accountability.
- *Failure mode:* Deep chains amplify latency; errors compound at each level
- *Use when:* Large organizations with distinct domain boundaries (e.g., Opensoul's 6-agent marketing agency with a Director at the top — HN Show HN, 2025)

**Pattern 4 — Peer-to-Peer (decentralized, shared task pool)**
Agents share a message bus and pick tasks from a common queue. No single coordinator.
- *Failure mode:* Race conditions, duplicate work, no single source of truth for task state
- *Use when:* Loosely coupled tasks where independence is the goal (multi-channel publishing, parallel research)
- *Opensoul detail:* Each of their 6 agents runs on scheduled heartbeats, checking a shared work queue and delegating to teammates — https://news.ycombinator.com/item?id=47336615

**Pattern 5 — Voting/Round-Robin (consensus-based)**
Multiple agents produce independent outputs and a voting or averaging step selects the best.
- *Cost:* N agents × full execution; expensive but parallelizable
- *Failure mode:* Homogeneous agents produce homogeneous errors; diversity in agent design matters
- *Use when:* Tasks where multiple perspectives reduce error (code review, content editing, classification)

**Pattern 6 — Event-Driven (subscription model)**
Agents subscribe to events and react. Used in agentic RAG pipelines and tool-augmented systems.
- *Failure mode:* Cascading reactions are hard to debug; event storms are a real operational risk
- *Use when:* Real-time reactive pipelines (data ingestion triggers, monitoring alerts, MCP tool routing)

**The framework is not the architecture.** LangGraph (v1.0 stable Oct 2025) excels at state-machine patterns and fine-grained control. CrewAI (v0.86+) provides the fastest path to role-based teams. Microsoft Agent Framework (AutoGen + Semantic Kernel merger, GA Q1 2026) is the enterprise/Azure choice. All are model-agnostic (OpenAI, Anthropic Claude, local via Ollama/vLLM).

## Evidence

- **Gartner:** 1,445% surge in multi-agent system inquiries Q1 2024 → Q2 2025; 40% of pilots fail within six months of production deployment; average organization uses 12 agents — https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production
- **Show HN (Opensoul):** 6-agent marketing agency with hierarchical pattern — Director → [Strategist, Creative, Producer, Growth Marketer, Analyst]. Each agent on scheduled heartbeats, shared work queue, cross-channel memory. SQLite + FTS5 for memory instead of vector DB at personal-agent scale — https://news.ycombinator.com/item?id=47336615
- **Production RAG:** Agentic retrieval shifts from "retrieve then generate" to plan-execute-replan loops. Rerankers can hurt quality if they disrupt the semantic signal from hybrid search (dense + sparse with RRF). Signals when to split: agent accumulates 10-15+ tools — https://onseok.github.io/posts/building-production-rag-system
- **Framework comparison:** LangGraph: steep learning curve (2-4 weeks), production-stable. CrewAI: easy (1-2 weeks), fastest prototyping. MS Agent Framework: moderate, GA Q1 2026, Azure-ecosystem best — https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html
- **When to split agents:** The architectural trigger is not task count — it is tool accumulation and instruction complexity. When a single system prompt exceeds what the model reliably follows for the domain, split. The same signal appears in multi-agent RAG: when retrieval subtask complexity grows, separate the retriever agent from the synthesizer — https://medium.com/@shahab.sheikhbahaei/building-production-ready-ai-agents-7-architecture-patterns-that-scale-6253e397a804

## Gotchas

- **Model cascading is the cost lever, not agent count.** Giving every agent a frontier model is expensive. The orchestrator-worker pattern with a capable orchestrator and cheap task-specific workers is where 40-60% cost reduction comes from — not from fewer agents, but from right-sizing each agent's model.
- **Anti-pattern: "Let me think step by step" hardcoded in every system prompt.** Modern models do not need it for routine tasks. It inflates latency and token cost. Use it selectively for complex reasoning tasks, not as a default.
- **Voting with identical agents is not diverse.** If all agents use the same model and prompt strategy, the vote is meaningless. Diversity in agent design — different models, different tool sets, different prompt strategies — is what makes voting patterns effective.
- **Event-driven chains are operationally opaque.** Debugging a cascade of 7 agents reacting to each other's events is harder than debugging a serial pipeline. Instrument every handoff with trace events, even in development.
- **Cross-channel memory is non-trivial at scale.** Opensoul's SQLite + FTS5 approach works at personal-agent scale. At team or enterprise scale, you need either a shared vector store with namespace isolation or a purpose-built memory agent. The pattern does not scale linearly.
