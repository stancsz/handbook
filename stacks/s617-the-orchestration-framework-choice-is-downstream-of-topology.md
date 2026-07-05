# S-617 · The Orchestration Framework Choice Is Downstream of Topology

Teams new to agentic systems spend weeks evaluating LangGraph vs CrewAI vs AutoGen when the evidence shows: the choice of orchestration framework matters far less than having the right topology first. Pick your coordination pattern, then pick the tool that best implements it — not the other way around.

## Forces

- **Framework marketing creates false equivalence.** LangGraph, CrewAI, and Microsoft's new Agent Framework 1.0 (ex-AutoGen) are all production-viable as of mid-2026 — but they implement fundamentally different coordination models. Choosing based on GitHub stars or blog post polish leads to square-peg deployments.
- **The demo-to-production gap in agentic systems is catastrophic.** One real-world case: 92% success in testing, 55% in production, $847/month actual vs $200/month budgeted, 47 different data format issues — all from topology and data quality problems, not model problems.
- **Multi-agent cost compounds super-linearly.** CrewAI's own community data shows multi-agent token costs run 5× a single-agent equivalent. Framework overhead can multiply costs before you even hit LLM API pricing.
- **AutoGen is deprecated.** Microsoft's December 2024 HN post confirmed AutoGen was merging into Semantic Kernel, now shipping as Microsoft Agent Framework 1.0 GA (April 2026). Choosing AutoGen means a forced migration is already on your roadmap.
- **CrewAI ships with LangChain under the hood.** Reddit consensus: the LangChain dependency is "fine for playing around but way too bloated for production." Teams building serious systems copy the API design and implement their own orchestration.

## The move

**First, pick your coordination topology. Then, pick your framework.**

| Coordination Model | Best Mental Model | Best Framework |
|---|---|---|
| Directed graph with explicit state, breakpoints, retries | "I build the flowchart, the framework executes it" | LangGraph |
| Role-based team with tasks and delegation | "I hire a team, assign roles, they figure out coordination" | CrewAI |
| Conversational agents with emergent coordination | "I put agents in a room, let them talk until solved" | Microsoft Agent Framework 1.0 |
| Simple prompt-pipe chains | "My LLM calls another LLM in a pipeline" | Build it yourself (too simple for a framework) |

**Specific decisions that actually matter:**

- Start with one agent. Add a second only when a genuine boundary appears — conflicting concerns (e.g., a coder and a security assessor), different timing cadences, or trust/separation requirements. Do not add agents for parallelism that a single agent with tools can handle.
- CrewAI's multi-agent token cost is 5× a single-agent equivalent. If your workflow can be handled by one agent with tools, use one agent.
- If you use CrewAI in production, implement your own orchestration layer on top rather than depending on the CrewAI task delegation system directly — the API design is the valuable part, not the framework internals.
- For production: LangGraph gives the most explicit control over state, retries, breakpoints, and human-in-the-loop. This matters when your agentic workflow needs to pause, resume, and be audited.
- Microsoft Agent Framework 1.0 is now the GA production path for teams already on Azure/Semantic Kernel. It is not a greenfield choice unless you're already in that ecosystem.

## Evidence

- **HN post (Dec 2024):** After a week researching frameworks, danfuya concluded AutoGen was not production-ready due to rapid changes and a pending merge into Semantic Kernel. Key HN advice: "Popular frameworks aren't always the most stable. Don't base your decision on GitHub stars." — https://news.ycombinator.com/item?id=42449741
- **Production cost reality check:** One builder's 18-month, $103,913 invested system went from 92% test success to 55% production success. Root causes: data quality and topology problems, not model choice. Monthly cost hit $847 vs $200 budget. — https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/
- **Multi-agent architecture guide:** FRENXT Labs (April 2026, updated May 2026) lays out the four foundations for production multi-agent: agent boundaries by audience/timing/trust (not workflow step), typed shared state with checkpointing, explicit error handling, and full-trace observability. Golden rule: start with one agent. — https://www.frenxt.com/research/multi-agent-architecture-guide
- **Framework comparison (May 2026):** AIStackHub benchmarks show all three open-source frameworks are free (cost is API calls + infra), CrewAI has lowest learning curve but 5× token cost multiplier, LangGraph best for durable enterprise workflows. Microsoft Agent Framework 1.0 GA released April 2026. — https://aistackhub.ai/ai-agent-orchestration-platforms

## Gotchas

- **LangGraph's complexity is front-loaded.** It's more verbose than CrewAI but pays off when you need to inspect, debug, and resume long-running agentic workflows. If you need quick prototyping and your workflow is stable, CrewAI may be the better starting point — but be aware of the LangChain dependency and token cost multiplier.
- **Human-in-the-loop is not optional in production.** Any framework you choose needs explicit support for pausing and letting a human approve, correct, or redirect. LangGraph has this as a first-class concept. Verify it exists in your choice before committing.
- **Observability must be a first-class concern from day one.** Multi-agent failures cascade silently. You need full-trace logging (LangSmith, Phoenix, or equivalent) before you go to production — not after the first incident.
- **Framework longevity matters.** AutoGen teams are now forced into a migration. Before choosing any framework, check the project's roadmap and who controls it. Microsoft Agent Framework 1.0 is backed by a major cloud vendor; CrewAI and LangGraph are community-driven.
