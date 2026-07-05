# S-624 · The Agent Stack Is Stratifying into Specialized Layers

[Everyone wants one framework to rule them all. The teams shipping stable agents in 2025-2026 made the opposite call: the agent stack is decomposing into six distinct layers, each with different economics, rates of change, and defensibility profiles. Fighting this stratification is how you end up with a brittle monolith. Working with it is how you get upgrade paths.]

## Forces

- **The abstraction promise breaks at layer boundaries.** Every "build an agent in 5 lines of code" framework collapses the moment you need production-grade anything — because the layers underneath have wildly different failure modes, upgrade cycles, and security profiles.
- **Each layer has a different defensibility profile.** Model providers commoditize fastest; orchestration is sticky but hard to protect; tool/infra layers are where actual product differentiation lives. A monolithic stack hides this from you until you're locked in.
- **The 40%+ agent project cancellation rate (Gartner, 2027 projection) correlates with teams fighting layer violations.** When one framework owns everything, upgrading one layer means upgrading the whole stack — and in a fast-moving space, that means falling behind.

## The move

Accept the stratification. Design layer boundaries explicitly. Choose the best tool at each layer rather than the best all-in-one framework.

**Six layers, in order of increasing stickiness:**
- **Model / Runtime** — LLM inference. Commodity at the provider level; real value is in the prompt/response layer. Anthropic for reasoning, OpenAI for broad coverage, DeepSeek/Qwen for cost-sensitive paths.
- **Orchestration** — Workflow state and agent coordination. LangGraph for graph-based state machines with checkpointing; CrewAI for role-delegation teams; AutoGen for human-in-the-loop collaborative patterns. None wins universally.
- **Tool integration** — How agents talk to the world. MCP (Model Context Protocol) now the fastest-growing standard, with 9,400+ public servers as of April 2026 (up 7.8× YoY). Anthropic donated it to the Linux Foundation in late 2025, which catalyzed enterprise governance adoption.
- **Sandboxing / Isolation** — Where agents execute. Separate from orchestration by design. Shuru, E2B, Modal, and Firecracker-based wrappers each solve this differently. This layer exists because agent code execution cannot share fate with orchestration.
- **Memory / Persistence** — Short-term state, long-term knowledge. Vector DBs (Qdrant, Weaviate, Pinecone) for retrieval; pgvector for latency-sensitive cases; knowledge graphs for hallucination-critical domains (agentic RAG with knowledge graphs cut hallucination ~62% per MLOps Community benchmark, May 2026).
- **Observability / Evaluation** — Tracing, evals, cost tracking. LangSmith, Phoenix, or custom. Non-negotiable at production scale — P95/P99 latency matters, not mean latency.

**Decision heuristic:** If your framework makes it hard to swap one layer without touching the others, you're building a monolith.

## Evidence

- **Engineering blog:** Philipp Dubach's "Don't Go Monolithic; The Agent Stack Is Stratifying" documents the six-layer decomposition and explains why "going monolithic is the wrong call" — each layer has a different defensibility profile. Heavily cited on HN across multiple agent infrastructure threads. — [https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN comment thread:** Multiple engineers corroborate the pattern — sandboxing is "clearly becoming its own thing" separate from orchestration, with Shuru, E2B, Modal, and Firecracker wrappers each targeting different isolation trade-offs (cost vs. security vs. cold-start latency). — [https://news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)
- **Enterprise operator:** Xpress AI's "fifth agent framework" journey documents hitting the layer-boundary wall repeatedly — each prior attempt collapsed because it bundled layers that needed independent upgrade paths. Their Xaibo rewrite explicitly decoupled them. — [https://xpress.ai/blog/2025-agent-lessons](https://xpress.ai/blog/2025-agent-lessons)
- **Market signal:** Y Combinator Spring 2025 batch: 67 of 144 startups (46%) self-describe as "AI agents" — a new high. As this cohort hits production, the stratification pattern will accelerate because early agents exposed exactly where monolithic stacks fail. — [https://pitchbook.com/news/articles/y-combinator-is-going-all-in-on-ai-agents-making-up-nearly-50-of-latest-batch](https://pitchbook.com/news/articles/y-combinator-is-going-all-in-on-ai-agents-making-up-nearly-50-of-latest-batch)
- **MCP adoption data:** CTO survey (May 2026) shows 78% of enterprises have MCP in production; 67% named it their default integration standard for the next 12 months. Public MCP server registry at 9,400+ (April 2026), up 7.8× YoY — adoption spiked after Linux Foundation donation. — [https://agileleadershipdayindia.org/blogs/mcp-model-context-protocol-enterprise/mcp-adoption-statistics-cto-survey.html](https://agileleadershipdayindia.org/blogs/mcp-model-context-protocol-enterprise/mcp-adoption-statistics-cto-survey.html)

## Gotchas

- **The "tutorial cliff" is a layer-confusion symptom.** Frameworks that demo beautifully collapse when production demands pull different layers in different directions. Budget for the cliff before you hit it.
- **Sandboxing is the most commonly underengineered layer.** Most teams skip it in POC and then can't retrofit it without rearchitecting. Plan for it on day one.
- **MCP governance is still immature.** 78% adoption rate but fewer than half using it for mission-critical data — gateway security and machine identity concerns are blocking production upgrades. If you're adopting MCP for production, invest in gateway controls from day one.
