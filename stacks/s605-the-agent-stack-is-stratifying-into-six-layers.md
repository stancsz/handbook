# S-605 · The Agent Stack Is Stratifying into Six Layers

Every major compute era decomposes into specialized layers with different winners at each level. Cloud split into IaaS, PaaS, and SaaS. The data stack fragmented into ingestion, transformation, warehousing, and BI. The AI agent stack is doing the same thing now — and teams that treat it as a monolith are building on the wrong abstraction.

## Forces

- **Monolithic agent frameworks promise coherence but deliver lock-in at the wrong layer.** Bundling orchestration, tool execution, sandboxing, memory, and state into one system means you're committed to the tradeoffs of every layer simultaneously — even when a better tool exists for one of them.
- **The defensible asset is context, not models.** Anyone can swap in GPT-5 or Claude 4. The organizational world model — the accumulated context, tooling, and institutional knowledge your agents operate with — is what takes years to build and cannot be replicated by switching a model provider.
- **Sandboxing and orchestration have fundamentally different defensibility profiles.** Sandboxing (E2B, Modal, Shuru, Firecracker) is a commodity infrastructure play. Orchestration (LangGraph, CrewAI, Temporal) is an application-layer play. Conflating them creates architectural debt.
- **Tool selection accuracy drops below 90% at ~12+ tools** in single-agent setups — the complexity wall forces architectural decomposition before you intentionally choose it.

## The move

Treat the agent stack as six independent layers. Evaluate and replace each on its own merits:

- **Layer 1 — Model runtime:** Ollama, vLLM, or cloud APIs (OpenAI, Anthropic). Swap independently based on quality/cost tradeoffs.
- **Layer 2 — Orchestration:** LangGraph for production graph-based control, CrewAI for fastest team-based prototyping, Temporal for workflow durable execution. OpenAI Swarm for simple handoff patterns.
- **Layer 3 — Tool execution / sandboxing:** E2B, Modal, Shuru, or Firecracker-based solutions. This layer is separating because sandboxed code execution has entirely different failure modes than orchestration logic.
- **Layer 4 — Memory and state:** Vector DBs (Qdrant for local-first, Pinecone for managed cloud), pgvector for Postgres-native, or knowledge graphs for relational reasoning. Semantic memory (stored embeddings) vs. short-term context window vs. session state are separate concerns with separate tools.
- **Layer 5 — Tool protocols:** MCP (Model Context Protocol) is consolidating as the standard for agent-to-tool communication. Anthropic's November 2025 update added server discovery via .well-known URLs, async operations, and scalability improvements — cementing MCP as production infrastructure, not a prototype toy.
- **Layer 6 — Context and domain knowledge:** The highest-lock-in, hardest-to-rebuild layer. This is your RAG corpus, your internal document store, your customer data — the organizational world model that makes agents actually useful in your domain. Treat this as the strategic asset.

## Evidence

- **Engineering blog:** The agent stack is stratifying — Phil Dubach argues that "context, not models, sits in the highest lock-in and hardest-to-rebuild zone," and that the six layers each have different defensibility profiles. Teams going monolithic sacrifice the ability to upgrade one layer independently. — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN discussion:** Commenters on a Show HN for a multi-agent research stack confirmed the pattern — ZeroClaw (Rust runtime) handles orchestration and tool policies separately from James Library (Python tools), and both can be swapped independently. — [HN](https://news.ycombinator.com/item?id=47279088)
- **Industry survey:** 37% of enterprises now use five or more AI models in production — direct evidence that teams are already decomposing the model layer independently. 40% of enterprise apps will feature AI agents by end of 2026 (Gartner), but >40% of agentic AI projects will be canceled by 2027 due to unclear business value — suggesting architectural confusion is a root cause. — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)

## Gotchas

- **Going monolithic is the wrong call when the layers have very different defensibility profiles.** If you build your orchestration, sandboxing, and memory on one framework, you're betting that the framework will be best-in-class at all three. History says that's unlikely.
- **The "we'll swap later" assumption breaks down at Layer 6.** You can swap the model runtime without too much pain. Swapping your organizational context layer requires re-indexing years of domain knowledge — that's not a codebase migration, that's a knowledge migration.
- **MCP adoption is accelerating but the ecosystem is still fragmenting.** MCP (November 2024 launch, now at ~1 year old) is consolidating as the tool protocol standard, but not all frameworks support it equally. Check LangGraph, CrewAI, and AutoGen MCP integration maturity before committing.
