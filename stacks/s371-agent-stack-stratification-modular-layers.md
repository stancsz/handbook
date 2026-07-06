# S-371 · Agent Stack Stratification — Why Monolithic Agent Bundles Are the Wrong Bet

Your team built a compelling single-agent demo. You shipped it. Six months later, the LLM underneath got deprecated, your vector DB doesn't scale, and the agent's "memory" is a JSON blob you can't query. You're locked into every decision you made on week one. The pattern that keeps emerging from teams who scale past the prototype phase: the agent stack isn't one thing — it's six layers, and the teams winning in production are treating each layer as an independent decision with independent tradeoffs.

## Forces

- **The monolithic agent bundle optimizes for day-one velocity, not year-two flexibility.** Bundling orchestration, memory, tool access, sandboxing, and observability into one system makes the first demo fast and the second year painful
- **Each stack layer has a different rate of change and different competitive dynamics.** The LLM layer commoditizes fast; the organizational context layer (your proprietary knowledge, processes, relationships) is defensible long-term — mixing them into one abstraction conflates two very different assets
- **The "best agent framework" question is the wrong question.** LangGraph, CrewAI, AutoGen, and the OpenAI Agents SDK each win on different layers. Picking one for the whole stack locks you into its mental model across layers where a different tool would fit better
- **Sandboxing is its own problem that agent frameworks ignore.** Once agents execute code, call APIs, or browse the web, isolation becomes a first-class concern — not a footnote

## The move

Treat the agent stack as six independent layers, each with its own selection criteria:

- **Security** — access controls, permissions, compliance guardrails. Layer closest to data sensitivity
- **Context** (organizational world model) — proprietary knowledge, process memory, domain knowledge. The defensible asset; invest here most heavily
- **Orchestration** — workflow graphs, agent coordination, state machines. Choose based on workflow complexity needs, not tool familiarity
- **Execution** — sandboxed code execution, API calls, web browsing. Isolate aggressively; this is where agents cause real-world harm
- **Tools** — MCP (Model Context Protocol) is emerging as the standard for standardized tool communication. Anthropic open-sourced it Nov 2024; AWS, Azure, and GCP all shipped first-party integrations by mid-2025
- **Observability** — tracing, eval, cost tracking, faithfulness checks. Must be layered in from day one, not bolted on after the first production incident

**The organizational world model is the moat, not the LLM.** Every compute era stratifies into specialized layers (cloud → IaaS/PaaS/SaaS; data → ingestion/warehousing/transformation/BI). Enterprise AI is following the same pattern. The teams winning are building proprietary context layers — domain knowledge, process memory, relationship graphs — that no competitor can replicate by picking the same model.

**Default to LangGraph for orchestration unless you have a specific reason not to.** The graph-based mental model prevents painful refactoring as workflows grow complex. CrewAI for fast prototypes with role-based agents. AutoGen for Azure-native enterprise stacks. Build raw loops only when you fully understand what you're replacing.

**For tool calling, MCP over custom schemas.** The protocol standardizes the interface between agents and tools, eliminating the per-framework tool-definition churn. The failure mode isn't under-use of MCP — it's over-loading it: connecting 20 MCP servers at once bloats the context window. Target 3–5 targeted servers per specific business process.

## Evidence

- **HN / Blog post:** Philipp Dubach's "Don't Go Monolithic; The Agent Stack Is Stratifying" (Feb 2026, updated May 2026) articulates the six-layer model and the defensibility argument — "The defensible asset in enterprise AI is not the model. It's the organizational world model." — cited on HN with discussion of Shuru, E2B, Modal, Firecracker as sandboxing-layer players — [https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Engineering blog:** Essa Mamdani's "The Complete Guide to Building Production-Grade Agentic AI Systems with MCP and Multi-Agent Orchestration in 2026" — three-layer architecture (Reasoning / Protocol / Orchestration) with MCP as the cross-layer standard, migration from monolithic to distributed achieving 40% latency reduction — [https://essamamdani.com/blog/production-grade-agentic-ai-mcp-multi-agent-2026](https://essamamdani.com/blog/production-grade-agentic-ai-mcp-multi-agent-2026)
- **Framework comparison:** Beam's "Agent Orchestration Frameworks Compared: LangGraph vs CrewAI vs AutoGen vs OpenAI Agents SDK (2026)" — honest breakdown of when each wins: LangGraph for complex stateful workflows, CrewAI for fastest prototype path (with 6–12 month scalability ceiling), AutoGen for Azure shops, OpenAI SDK for narrow use cases — [https://getbeam.dev/blog/agent-orchestration-frameworks-compared-2026.html](https://getbeam.dev/blog/agent-orchestration-frameworks-compared-2026.html)
- **Production patterns:** Devstarsj's "AI Agents in Production: Architecture Patterns for Reliable, Safe, and Scalable Agentic Systems" (Apr 2026) — four-layer production stack: Agent Core, Memory/Persistence, Tools/Integration, Guardrails/Observability — and the observation that production failures stem from engineering discipline gaps, not AI capability gaps — [https://devstarsj.github.io/ai/architecture/2026/04/11/ai-agents-production-architecture-patterns-memory-safety-reliability](https://devstarsj.github.io/ai/architecture/2026/04/11/ai-agents-production-architecture-patterns-memory-safety-reliability)
- **Pitfalls / regrets:** Kieran Zhang's "4 Pitfalls of Agentic Engineering in Production" (Apr 2026) — hard-won lessons: (1) don't make the LLM do dirty work — use deterministic scripts for messy tasks, (2) skills are soft constraints not silver bullets, (3) observability makes tests actually valuable, (4) don't just supervise — think deeply about what supervision means — [https://kieranzhang.dev/blog/agentic-4-pitfalls](https://kieranzhang.dev/blog/agentic-4-pitfalls)

## Gotchas

- **Don't pick one orchestration framework and let it dictate your entire stack.** LangGraph doesn't need to own your observability or your vector DB. Use the right tool at each layer
- **Over-retrieval is the agentic RAG failure mode, not under-retrieval.** Classic RAG under-retrieves; agentic RAG over-retrieves and loops. Gate answers with a faithfulness judge and a step budget — [https://futureagi.com/blog/agentic-rag-systems-2025](https://futureagi.com/blog/agentic-rag-systems-2025)
- **MCP servers are not load-bearing architecture — they're integration plumbing.** Don't build core business logic inside MCP servers. Keep them thin and focused on translation between the agent and the external system
- **Enterprise AI projects canceled by end of 2027 will exceed 40%** (Gartner, cited in Dubach 2026). The primary cause isn't model quality — it's underestimating the engineering discipline required at each stack layer. Treat this as a software engineering problem first
