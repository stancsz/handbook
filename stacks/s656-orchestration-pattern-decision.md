# S-656 · The Orchestration Pattern Decision

Picking an agent orchestration framework is not a one-time framework selection — it is choosing a coordination philosophy that determines how your agents think, delegate, fail, and scale. The three dominant patterns in 2025-2026 represent genuinely different worldviews, and the wrong match creates compounding costs that don't surface until production load.

## Forces

- **LangGraph, CrewAI, and Microsoft Agent Framework 1.0** (ex-AutoGen) all ship production-quality systems, but each fights you on different things. "Any can reach production" is true; "they cost the same to get there" is not.
- CrewAI's async bottleneck surfaces at 50+ concurrent requests — a p95 jump from 800ms to 12s — just when you think you've shipped.
- LangGraph's cyclical state is powerful but leaks context window budget silently. AutoGen's conversational model creates invisible looping agents.
- The stack is stratifying: MCP (5,800+ servers, 97M+ monthly SDK downloads) is now the integration layer, decoupled from orchestration choice. Pick orchestration and tool-calling independently.

## The Move

Map the problem to one of three coordination models before evaluating frameworks:

**1. Directed graph (LangGraph)** — Use when you need explicit control over agent flow, branching logic, cycles, and checkpointing. Best for complex workflows where you need to replay, inspect, or surgically modify a specific step.
- State is a typed dict; edges are explicit conditional functions
- Checkpointing enables human-in-the-loop approval mid-run
- Cycle = message accumulation — budget your context window
- Fight: writing boilerplate for simple multi-agent tasks; not worth it for flat role delegation

**2. Role-based team (CrewAI)** — Use for loosely-coupled multi-agent tasks where agents are specialists with defined inputs/outputs and don't need fine-grained orchestration.
- Fastest to scaffold; worst async bottleneck in the tier
- Fix: decouple orchestration from execution with a task queue (Redis + Celery)
- At 500 tasks/min with p95 <2s latency, requires Redis message bus + per-agent 30s timeouts
- Fight: async message bus degrades fast; visibility into agent state is thin

**3. Conversational multi-agent (Microsoft Agent Framework 1.0)** — Use when the coordination pattern is emergent rather than pre-defined and agents need to negotiate roles at runtime.
- Agents exchange messages with different skill profiles until a termination condition
- GA release (April 2026) unifies AutoGen + Semantic Kernel with stable .NET/Python APIs
- Fight: conversational agents can oscillate without a valid exit path; requires explicit max-iteration guards

**Layer the integration plane separately:** MCP (Model Context Protocol) handles tool calling and data access across all three. 97M+ monthly SDK downloads, 5,800+ servers, 300+ clients, backed by OpenAI/Google/Microsoft/AWS. Governance under Linux Foundation's Agentic AI Foundation. Security caveat: 43% of MCP servers have command injection flaws; exploit probability exceeds 92% with 10 plugins — sandbox MCP servers in isolated containers.

## Evidence

- **HN Show HN:** Opensoul — 6-agent marketing stack (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) on Paperclip orchestration, autonomous heartbeat scheduling with inter-agent work queues — [https://news.ycombinator.com/item?id=47336615](https://news.ycombinator.com/item?id=47336615)
- **Framework comparison (Turion):** LangGraph = graph nodes with explicit conditional edges; CrewAI = role-based team hierarchy; Microsoft Agent Framework = conversational chains with emergent patterns. Each wins on different production requirements — [https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)
- **Production benchmark (Markaicode):** Decoupled CrewAI topology (Redis task queue) achieves 500 tasks/min at p95 <2s on AWS c6i.4xlarge; monolithic CrewAI async bus degrades p95 from 800ms to 12s at 50+ concurrent requests — [https://markaicode.com/architecture/agent-architecture-with-crewai](https://markaicode.com/architecture/agent-architecture-with-crewai)
- **MCP market data:** 97M+ monthly SDK downloads, 5,800+ MCP servers, 300+ client apps, 90% enterprise adoption projection for 2025; 43% server command injection flaw rate — [https://guptadeepak.com/research/mcp-enterprise-guide-2025](https://guptadeepak.com/research/mcp-enterprise-guide-2025)
- **Framework failure modes (hjLabs):** CrewAI infinite retry on poorly-defined tasks; LangGraph undefined termination paths from missing conditional edges; AutoGen conversational loops without exit conditions — mitigation is architectural, not model-quality tuning — [https://hemangjoshi37a.github.io/hjLabs-AI-Engineering-Notes/04-crewai-vs-langgraph-vs-autogen-production-comparison](https://hemangjoshi37a.github.io/hjLabs-AI-Engineering-Notes/04-crewai-vs-langgraph-vs-autogen-production-comparison)
- **State of production agents (Technspire):** Developer tooling, internal ops automation, research/analysis, and customer-facing verticals shipped consistently in 2025. Gartner: 40% of agentic AI projects will be canceled by 2027 due to cost escalation and unclear value — [https://technspire.com/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **CrewAI async bottleneck is architectural, not a bug.** The fix is a separate task queue (Redis + Celery), not tuning the agents. Budget the Redis operational overhead.
- **MCP's security posture lags its adoption.** 43% of servers have injection flaws. Treat every MCP server as an untrusted service — run in isolated containers with minimal permissions.
- **Context window budgeting is the silent tax on LangGraph cycles.** Every cycle appends to the message list. For long-running agents, define explicit truncation or summarization policies.
- **Conversational agents (AutoGen/MAF) lack guaranteed termination.** Set `max_turns` explicitly. The agent will not terminate itself when done — it will keep "thinking" until told to stop.
- **Orchestration and tool-calling are now independent decisions.** MCP handles the tool plane. Don't conflate your orchestration philosophy with your tool-integration strategy.
