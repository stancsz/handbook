# S-537 · The Agent Stack Is Stratifying into Specialized Layers

[Your agent framework does everything — orchestration, tool calls, memory, sandboxing, observability. It works for demos. Then you hit production: sandbox escapes, cost explosions, tool-schema drift, and observability gaps you can't debug. The answer isn't a bigger framework. It's treating the agent stack as five or six independent layers with different renewal cycles, different defensibility profiles, and different winners at each.]

## Forces

- **The monolith works until it doesn't.** Single-framework agent stacks collapse under production load because the component with the highest failure rate (sandboxing, usually) drags down everything else. Fixing one layer often breaks another if they're tightly coupled.
- **Context is the only defensible layer — but it's also the most fragile.** The model layer commoditizes every 6 months. The orchestration layer is interchangeable. The context layer — your retrieval, memory, and reasoning traces — is what takes years to build and is hardest to replicate. Most teams underinvest here while over-investing in framework choice.
- **Framework selection is now a 6-12 month bet, not a 3-year commitment.** LangGraph, CrewAI, and AutoGen all look reasonable in Q1 2026. Their architectures are diverging, and migrating between them mid-production is painful. But locking into a framework that doesn't match your scaling pattern is worse.
- **Sandboxing has become its own discipline.** Code execution, file system access, network egress — these were afterthoughts in 2023 agent demos. In production, they're the primary attack surface and the primary source of reliability failures.

## The move

Treat the agent stack as six independent layers. Choose the best tool at each layer independently, and keep interfaces between them clean.

- **Orchestration layer** (LangGraph for graph/state-machine complexity; CrewAI for sequential role-based pipelines; custom FSM for simple bounded workflows) — swap this layer without touching others.
- **LLM routing layer** (route cheap/fast tasks to small models; complex reasoning to frontier models; preserve context windows by delegating to purpose-built models) — this is where cost is won or lost.
- **Tool/MCP layer** (Model Context Protocol as the standard interface for tool discovery and invocation; custom REST wrappers for legacy systems) — MCP reached 5,800+ servers and 300+ client applications by late 2025.
- **Sandbox/execution layer** (E2B or Modal for managed Firecracker microVMs; Daytona for open-source self-hosted; Docker for stateless tool execution) — isolate untrusted code, not the whole agent.
- **Memory/persistence layer** (Qdrant or Weaviate for semantic vector search; pgvector for SQL-native workloads; Redis for ephemeral conversation state; structured memory with natural decay for long-term agentic memory).
- **Observability layer** (LangSmith for LangGraph-native tracing; Arize Phoenix for OpenTelemetry-native; Langfuse for self-hosted; minimum: per-span latency, token counts, cost, retrieval scores).

## Evidence

- **Engineering blog:** Philipp D. Dubach documented the stratification thesis — 37% of enterprises now use five or more AI models in production, with context as the highest-lock-in layer and sandboxing emerging as its own specialized discipline with dedicated providers (E2B, Daytona, Modal) — [philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Industry survey:** Gartner predicted 40% of agentic AI projects would be canceled by end of 2027, with the primary failure mode being shallow context — agents retrieve correct documents but can't reconstruct human reasoning processes — corroborated by Deutsche Telekom achieving 89% acceptable answers only after deep context architecture investment — [aliac.eu](https://aliac.eu/blog/agentic-rag-in-production)
- **Framework comparison:** hjLabs documented 18 months of production deployments across LangGraph (graph-based control), CrewAI (fastest prototyping via role-based teams), and AutoGen v0.4+ (async actor group chat) — the key finding: framework choice matters less than observability, evaluation harnesses, and ops maturity at each layer — [hjLabs AI Engineering Notes](https://hemangjoshi37a.github.io/hjLabs-AI-Engineering-Notes/04-crewai-vs-langgraph-vs-autogen-production-comparison/)
- **Cost engineering:** Real per-ticket cost for a Claude Sonnet–powered support agent with RAG is ~$0.016/action (input + output + embedding). GPT-4o is ~20% cheaper for most tasks but Claude has higher quality on complex reasoning — [GitHub agentic-ai-system-design-primer](https://github.com/HimClix/agentic-ai-system-design-primer/blob/main/resources/cost-engineering/real-world-numbers.md)
- **MCP adoption:** 97M+ monthly MCP SDK downloads, 5,800+ servers, 300+ client applications by late 2025; donated to Linux Foundation's Agentic AI Foundation for vendor-neutral governance — [Deepak Gupta Research](https://guptadeepak.com/research/mcp-enterprise-guide-2025)

## Gotchas

- **Don't monolith the stack for the orchestration layer.** Choosing a framework that couples sandboxing, memory, and tools means you're stuck with all of it when one layer needs to change. Keep interfaces thin and testable.
- **MCP security is underappreciated.** Research found 43% of MCP servers have command injection flaws; with 10 plugins the exploit probability exceeds 92%. Treat MCP servers like network services — deny-by-default, allowlist explicitly.
- **Context engineering is 80% of production quality — but it's invisible until it breaks.** Teams optimize framework, model, and cost before they optimize retrieval depth, memory decay, and reasoning trace reconstruction. Reverse that priority.
- **Sandboxing cost scales differently than you expect.** E2B and similar platforms price per-second of sandbox time, not per-call. Long-running code-execution agents can surprise you. Profile actual sandbox utilization before committing to a pricing tier.
