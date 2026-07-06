# S-505 · Multi-Agent Orchestration: The Four Patterns That Work in Production

When one agent can't handle the job, teams reach for multiple — then discover that wiring agents together is where systems quietly collapse. The orchestration model matters more than the agent logic itself.

## Forces

- **Single-agent "god prompt" systems degrade 73%** when critical information lands mid-context, and persona bleed causes hallucinations — context degradation hits reasoning tasks hardest — [Comet: Multi-Agent Systems](https://www.comet.com/site/blog/multi-agent-systems)
- **65% of teams rewrite within 12 months** because their initial architecture doesn't scale — the framework choice compounds into a migration tax — [Gheware: LangGraph vs CrewAI vs AutoGen 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Typed schemas between agents are the #1 failure point** — untyped handoffs cascade failures across the system faster than any model outage — [RaftLabs: Multi-Agent Systems Guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Inference costs compound to $5–8 per complex task** on 4-agent workflows before you've accounted for orchestration overhead — model economics must precede architecture decisions — [RaftLabs: Multi-Agent Systems Guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## The move

Four production-vetted orchestration patterns. Choose by task shape, not by trend.

**1. Hierarchical (supervisor → workers)** — A supervisor agent decomposes a task and delegates to specialists. Best when task structure is unpredictable and a single decision-maker must own quality. Common failure: supervisor becomes a bottleneck; keep it stateless and task-queued.

**2. Pipeline (sequential agents)** — Output of agent A feeds directly into agent B. Best for linear transformations: research → draft → review → edit. The chain breaks if any stage lacks schema contracts with its neighbors. Async pipeline with Redis/RabbitMQ queuing between stages cuts P95 latency 45% over synchronous chaining — [Markaicode: CrewAI Production Architecture](https://markaicode.com/architecture/crewai-system-design-architecture-768).

**3. Orchestrator-worker (dispatch → fan-out → aggregate)** — A planner distributes sub-tasks to parallel workers, then aggregates results. Best for tasks with natural parallelism: research N sources, compare N products, analyze N documents. The aggregator is the hardest component to get right — it needs typed input schemas from every worker.

**4. Peer-to-peer (agents negotiate)** — Agents share a message bus and negotiate outcomes without a central coordinator. Best for multi-stakeholder scenarios (Opensoul's marketing agency: Director, Strategist, Creative, Producer, Growth Marketer, Analyst each own domain and collaborate via message passing) — [Hacker News: Opensoul Show HN](https://news.ycombinator.com/item?id=47336615). Scales well but requires typed message contracts or agents talk past each other.

**On choosing a framework:**
- **LangGraph** — graph-based state machines; 90K+ GitHub stars; strongest production control; default choice unless you have a specific reason not to. Steeper learning curve prevents painful rewrites 6–12 months in — [Gheware: Framework Comparison 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html).
- **CrewAI** — role-based team model; fastest path to working prototype; supports `async=True` in `Crew.kickoff()` for 45% P95 latency reduction. Common mistake: using LangChain under the hood adds bloat most teams don't need — [Reddit r/LocalLLaMA: LLM Agent Platforms](https://www.reddit.com/r/LocalLLaMA/comments/1bskjki/llm_agent_platforms).
- **AutoGen** — conversational collaborative pattern; strongest on Azure; best when agents need to negotiate or debate rather than execute roles.
- **Custom state machine** — if CrewAI's role model doesn't fit your task shape, build on LangGraph primitives. Most of it is simple prompt engineering achievable by string formatting — [Reddit r/LocalLLaMA: LLM Agent Platforms](https://www.reddit.com/r/LocalLLaMA/comments/1bskjki/llm_agent_platforms).

## Evidence

- **Gartner tracked 1,445% surge** in multi-agent inquiries Q1 2024 → Q2 2025, with 57% of organizations already running agents in production — [RaftLabs: Multi-Agent Systems Guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **89% of teams have observability but only 52% have evals** — the eval gap is where multi-agent failures silently compound — [RaftLabs: Multi-Agent Systems Guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- Async CrewAI with Redis task queuing between agents cuts P95 latency 45% by overlapping agent execution — [Markaicode: CrewAI Production Architecture](https://markaicode.com/architecture/crewai-system-design-architecture-768)
- Opensoul (Paperclip-based) ships 6 agents as a real marketing agency, each running on scheduled heartbeats with a work queue and peer delegation — [Hacker News: Opensoul Show HN](https://news.ycombinator.com/item?id=47336615)
- A Rust/Python local research stack (James Library) combines ZeroClaw Rust runtime for orchestration, internet access, voice conversation, and overnight memory consolidation — [Hacker News: James Library](https://news.ycombinator.com/item?id=47279088)

## Gotchas

- **Don't make every agent synchronous** — synchronous CrewAI serializes what should be parallel, collapsing throughput under 10 concurrent requests — [Markaicode: CrewAI Production Architecture](https://markaicode.com/architecture/crewai-system-design-architecture-768)
- **Typed schemas at agent boundaries are non-negotiable** — without them, the aggregator or supervisor receives unpredictable payloads and the system degrades silently — [RaftLabs: Multi-Agent Systems Guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Model economics first, architecture second** — a 4-agent orchestrator-worker workflow costs $5–8 per run; if the task value doesn't exceed that, you're over-engineering — [RaftLabs: Multi-Agent Systems Guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Memory isolation per agent** — store context in external systems (Qdrant, Redis, Chroma) so any container can serve any agent type; avoid sticky sessions or in-memory state — [Markaicode: CrewAI Production Architecture](https://markaicode.com/architecture/crewai-system-design-architecture-768)
