# S-524 · Multi-Agent Coordination: When to Split and How to Connect

A single agent with 50 tools does worse than five agents with 10 tools each. The split is intuitive until you have to decide *how* they communicate — and the wrong answer makes the whole system slower, more expensive, and harder to debug than the monolith you started with.

## Forces

- **Context window saturation hits before you expect.** LLM reasoning accuracy degrades up to 73% when the context window exceeds 60–70% capacity. A "god agent" that carries the entire conversation history, all tools, and all retrieval context accumulates exactly the failure mode it can't see.
- **Role bleed is real.** A single agent with a coder persona and a writer persona starts hallucinating libraries that don't exist because the persona boundaries dissolve under long-context pressure. You can't prompt-engineer your way out of this — you need structural separation.
- **The coordination overhead tax.** Every agent boundary adds latency, token cost, and a new failure mode (timeout, miscommunication, deadlock). Teams that split aggressively discover that the coordination cost exceeds the parallelism gain for most real workloads.
- **Not all splits are equal.** Dividing by "role" (researcher, writer, editor) vs. by "capability" (code executor, semantic search, external API) vs. by "domain" (customer support, billing, inventory) creates fundamentally different failure surfaces.

## The Move

**Split on task-type boundary, not role-label. Connect with structured output contracts, not message passing.**

- **Split when:** The task requires different tool sets, different context sources, or fundamentally different reasoning styles. A researcher agent that calls a web search tool should not share a process with a writer agent that calls a CMS API — not for security, but because their retry logic, timeout behavior, and quality criteria are orthogonal.
- **Keep a supervisor/router agent at the top.** The router decides which specialized agent handles a request, collects outputs, and produces the final response. LangGraph's supervisor pattern or CrewAI's crew hierarchy both implement this. The supervisor is not a bottleneck — it's the single place where you put your routing logic, audit trail, and fallback handling.
- **Use structured output as the communication protocol.** Define Pydantic schemas for every inter-agent message. Agents don't "talk" to each other via free-text; they pass typed objects with defined fields. This makes every agent boundary testable and traceable.
- **Prefer async fan-out for parallelizable sub-tasks.** If multiple agents can work independently (e.g., research three different competitors simultaneously), call them in parallel, then aggregate. CrewAI's `Process.hierarchical` and LangGraph's `Send` API both support this. Don't serialize what can run concurrently.
- **Use a shared memory store for cross-agent context, not the conversation history.** Each agent should have its own short-term context window. Shared state (customer profile, session context, retrieved documents) goes into a shared store (Redis, PostgreSQL, or a vector DB for semantic memory). The supervisor agent provides context to sub-agents, not the other way around.
- **Instrument every agent boundary.** At minimum: which agent was called, with what input, how many tokens in/out, latency, and final status. This is where multi-agent systems fail — you can't debug what you can't see. LangSmith, Phoenix, or even structured JSON logs to a filebeat pipeline are all better than nothing.

## Evidence

- **Shopify engineering blog:** Sidekick evolved from a single tool-calling system into a multi-agent platform where a supervisor agent routes to specialized sub-agents. Key lesson: "A single agent with 50 tools performs measurably worse than five agents with 10 tools each. The solution was structural separation with typed tool contracts." — [Shopify Engineering, Aug 2025](https://shopify.engineering/building-production-ready-agentic-systems)
- **Comet.ml research:** Found that LLM reasoning accuracy degrades 73% when critical information is buried mid-context. Multi-agent decomposition eliminates this by keeping each agent's context window focused. — [Comet Multi-Agent Systems, Mar 2026](https://www.comet.com/site/blog/multi-agent-systems)
- **AI Magicx field analysis:** Identified four multi-agent patterns that hold at scale: supervisor-hierarchy, peer-pools with a router, event-driven pub/sub, and pipeline (sequential with gates). The supervisor-hierarchy pattern dominates production because it limits the blast radius of agent failures and makes cost attribution tractable. — [AI Magicx, Apr 2026](https://www.aimagicx.com/blog/multi-agent-ai-production-architecture-patterns-2026)

## Gotchas

- **Splitting by role (researcher/writer/editor) sounds natural but often creates a sequential pipeline.** Sequential pipelines are just expensive chains — you get none of the parallelism benefits of multi-agent systems. Split by *capability* or *tool domain* instead, which enables parallel execution.
- **Adding more agents increases the p50-to-p95 variance.** Real production data shows 16x cost variance between p50 and p95 on identical inputs in multi-agent systems. A single slow sub-agent holding a mutex or making a network call will dominate your tail latency. Build for the p95 case, not the happy path.
- **The shared memory store becomes the new blast radius.** If your Redis/Postgres-backed shared context store goes down, every agent fails simultaneously. Treat it like a database, not a message bus — with replication, timeouts, and fallback behavior.
- **Inter-agent prompt injection is underexplored.** If one agent can produce text that another agent acts on, the attack surface is the union of both agents' tool permissions. In practice, sanitize all structured output from sub-agents before passing it to any agent with destructive tool access.
