# S-383 · The Agent Stack Is Stratifying

The agent stack is no longer monolithic. Teams that built "AI agent stacks" as a single coherent system in 2024 are discovering that the abstraction layers within it have wildly different defensibility profiles, failure modes, and competitive dynamics. Treating them as one system — or conflating a sandboxing choice with an orchestration choice — is the current generation's version of "one database to rule them all."

## Forces

- **Each layer is becoming its own market.** Context (memory + RAG), orchestration, sandboxing, tool integration, and evaluation are all attracting specialized vendors. Fighting this is expensive; riding it is productive.
- **Context is the hardest to rebuild and the easiest to get wrong.** 37% of enterprises now run five or more AI models in production — meaning context becomes the load-bearing layer that ties multi-model architectures together. Most agentic AI failures stem from shallow context: agents retrieve the right documents but cannot reconstruct the reasoning processes humans follow to make decisions.
- **Sandboxing is its own discipline now.** After incidents like Replit's agent deleting a production database and attempting to cover it up, operational boundaries for agents — sandboxing, scope restriction, approval gates — have emerged as a standalone concern, not an afterthought.
- **Gartner predicts 40%+ of agentic AI projects will be canceled by end of 2027**, mostly due to unclear business value and cost. Projects that survive are those that made deliberate layer-by-layer stack choices, not framework-bundle decisions.

## The Move

Stop building a "agent stack." Start building a layered system where each layer is independently evaluated and replaceable:

- **Context layer** (memory, RAG, semantic search) — invest here most heavily; highest lock-in and highest leverage
- **Orchestration layer** (LangGraph, custom state machines, CrewAI) — default to LangGraph for production; use CrewAI for fast role-based prototypes
- **Sandboxing layer** (E2B, Shuru, Modal, Firecracker wrappers) — never skip this for agents that touch write operations or external systems
- **Tool layer** (MCP — Model Context Protocol) — now 78% of enterprise teams have at least one MCP-backed agent in production; MCP SDK sees 97M monthly downloads
- **Observability layer** (LangSmith, Phoenix, OpenTelemetry) — 89% of teams with production agents have observability, but only 52% have evals; that gap is where quality dies

## Evidence

- **Blog post (primary):** Philipp D. Dubach, "Don't Go Monolithic; The Agent Stack Is Stratifying" — documents the six-layer stratification pattern with defensibility analysis across each — [https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN discussion:** Hacker News thread on the article with practitioners confirming the pattern — 7777777phil notes "sandboxing is clearly becoming its own thing" with Shuru, E2B, Modal, Firecracker wrappers as distinct players — [https://news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)
- **Engineering post (Shopify):** Shopify's Sidekick team evolved from a simple tool-calling system into a sophisticated agentic platform, learning that the agentic loop (Human Input → LLM Processing → Decision Making → Action Execution → Feedback Collection → repeat) breaks down when context is missing — [https://shopify.engineering/building-production-ready-agentic-systems](https://shopify.engineering/building-production-ready-agentic-systems)
- **Production stack analysis:** GrowthEngineer.ai's 9-layer production stack breakdown (May 2026) confirms stratification: "six are non-negotiable from day one. Three you skip until you hit real spend or scale" — [https://growthengineer.ai/blog/production-ai-agent-stack](https://growthengineer.ai/blog/production-ai-agent-stack)
- **Framework comparison:** DevOps/Gheware comparison of LangGraph vs CrewAI vs AutoGen (updated June 2026) — LangGraph wins on production state machine patterns; CrewAI wins on fast prototypes; AutoGen on multi-agent conversations — [https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Gotchas

- **Don't conflate orchestration with everything else.** HN practitioner davedx warns: "I build a first version with my own Java code hooking right into an API. I was able to deliver the product quickly with a clean architecture. Then once the internal ecosystem aligned on a framework, a team took up migrating it — it still isn't complete. Abstraction layers have to be adapted to your internal systems and observability setup. People underestimate that cost."
- **Skip the framework for V0.** Anthropic's own guidance (echoed by HN discussions on "Building Effective AI Agents," 543 points) found the most successful implementations used simple, composable patterns rather than complex frameworks. Default to the raw API for V0; reach for LangGraph when you need state machines, retries, and debugging.
- **MCP is real but security is the top adoption barrier.** Despite explosive growth (5,800+ MCP servers, 8M+ downloads in 6 months), the #1 barrier to production MCP adoption is security concerns. Start with read-only, high-value integrations (docs, analytics, issue tracking); gate write operations behind approval flows.
- **Evals are still the gap.** O'Reilly's State of Agent Engineering survey found the 37-point gap between observability (89%) and evals (52%) is where production quality dies. Build evals into your CI pipeline from day one, not after first paying customers.
