# S-631 · Agent Stack Stratification: Why Monolithic Agent Design Is a Trap

You built one agent that does everything. It works at first. Then you add memory, tools, multiple model providers, sandboxed code execution, observability, and cost controls — and suddenly you have a 50,000-line mess that nobody can debug or evolve. The fix isn't better prompts. It's structural: the agent stack is splitting into specialized layers, and teams that treat it as a monolith pay the price.

## Forces

- **The stack is already stratifying whether you plan for it or not.** Sandboxing (E2B, Modal, Shuru, Firecracker wrappers) has emerged as its own layer, distinct from orchestration. MCP (Model Context Protocol) is consolidating tool discovery and exchange into a separate protocol layer. Teams building monolithically hit integration walls when any one layer needs to change.
- **Defensibility lives in layer composition, not the model.** 37% of enterprises already run 5+ AI models in production (a16z AI Enterprise 2025). The competitive asset isn't which model you pick — it's how you compose specialized layers for your domain. The organizational world model (how your agents understand and act in your business) is what compounds, not the underlying LLM.
- **Multi-model routing is now table stakes.** Teams that hard-code a single provider (OpenAI or Anthropic) hit cost ceilings and availability risks. Dynamic routing — picking the right model for each task class — is how production systems stay within budget while maintaining quality.
- **Security and sandboxing are non-negotiable now.** Block reports 50–75% time savings from MCP-powered tooling, but 43% of MCP servers have command injection flaws and exploit probability exceeds 92% with 10 plugins. Code execution without isolation is a liability, not a feature.

## The Move

Design your agent system as a layered architecture from the start. Treat each layer as a replaceable component with a defined interface:

- **Orchestration layer** (LangGraph, CrewAI, Temporal, custom state machine) — defines agent logic, workflows, and routing. Pick based on workflow complexity, not feature lists. LangGraph for production-grade stateful graphs (v1.0 stable, Oct 2025). CrewAI for fast role-based team prototyping (fastest enterprise adoption growth: Klarna, Uber, Replit). AutoGen for multi-party debate/consensus patterns.
- **Sandboxing/execution layer** (E2B, Modal, Shuru, Firecracker derivatives) — isolates code execution, tool calls, and external API access. Do not let agent code run in the same process as orchestration logic.
- **Tool/MCP layer** — standardize on MCP for tool discovery and exchange. 97M+ monthly SDK downloads, 5,800+ servers, 300+ client applications as of late 2025. MCP has been donated to the Linux Foundation's Agentic AI Foundation, signaling cross-vendor permanence. Still: audit every MCP server — command injection risk is real at scale.
- **Memory/persistence layer** (Pinecone, Qdrant, Weaviate, pgvector) — choose by workload: Qdrant for real-time latency, Milvus for bulk indexing throughput, Weaviate for integrated ML pipelines, pgvector when you want SQL + vector in one system.
- **Observability layer** (LangSmith, Phoenix, OpenTelemetry + Prometheus + Grafana) — non-negotiable for production. Multi-agent pipelines with compounding non-determinism require trace-level visibility.
- **Model routing layer** — route by task class. Use Sonnet/Opus for complex reasoning, Haiku/mini for simple classification/routing. Route dynamically, not statically.

## Evidence

- **Blog post:** "Don't Go Monolithic; The Agent Stack Is Stratifying" — documents the 37% multi-model adoption stat, the layer decomposition trend, and the defensibility argument — [https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN discussion:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing" — cites Shuru, E2B, Modal, Firecracker wrappers as distinct from orchestration — [https://news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)
- **Framework comparison:** "LangGraph vs CrewAI vs AutoGen 2026" — production status, GitHub stars, enterprise adoption, and recommendation to default to LangGraph for production complexity — [https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **MCP research:** "97M+ monthly SDK downloads, 5,800+ MCP servers, 300+ clients; donated to Linux Foundation Agentic AI Foundation; 43% of servers have command injection flaws" — [https://guptadeepak.com/research/mcp-enterprise-guide-2025](https://guptadeepak.com/research/mcp-enterprise-guide-2025)
- **Enterprise adoption data:** Block employees report 50–75% time savings using MCP-powered tooling — [https://block.github.io/goose/blog/2025/04/21/mcp-in-enterprise/](https://block.github.io/goose/blog/2025/04/21/mcp-in-enterprise/)
- **Vector DB benchmarks:** Qdrant leads on throughput and latency; Milvus on indexing speed; Weaviate on integrated ML pipelines; ChromaDB for lightweight self-hosting — [https://www.thestack.technology/](https://www.thestack.technology/)

## Gotchas

- **Siloed layers still need shared schema.** If your orchestration layer doesn't know the shape of outputs from your memory layer, you'll end up with serialization glue code everywhere. Define cross-layer interfaces early.
- **Layer swaps are cheaper than you think — if you abstracted correctly.** Teams resist layer separation because they fear migration. In practice, replacing Qdrant with Pinecone is a weekend if your tool abstraction is clean. The cost of not abstracting is years of lock-in.
- **MCP is not a security guarantee.** The 43% command injection flaw rate means: every MCP server is a potential privilege escalation vector. Treat them as untrusted and audit network access accordingly. The protocol solves interoperability; your security layer solves trust.
- **Don't default to multi-agent when single-agent with better tools will do.** Multi-agent adds compounding non-determinism, debugging opacity, and cost multiplication (5-agent pipeline × 3 tool calls = 15+ LLM calls). Split agents only when you have genuinely separate domains of expertise or independent workstreams that can run in parallel.
- **GitHub Copilot's new autonomous agent** at Build 2025 uses GitHub Actions for sandboxing, MCP for tool compliance, and real-time session monitoring. If you're building coding agents, this is the reference architecture — Actions as sandbox → MCP as tool protocol → session traces as observability.
