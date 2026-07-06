# S-550 · Agent Stack Stratification: The Six-Layer Architecture

When you first build an agent, it's tempting to pick a single framework, bind everything together, and ship. Within months — when the model provider changes pricing, the sandbox vendor goes under, or a new tool integration becomes critical — you're refactoring the whole thing. The teams that don't hit this wall are the ones who built stratified stacks from day one.

## Forces

- Each layer of the agent stack evolves at a different pace and has a different defensibility profile — binding them together means the slow layer drags the fast one down
- Model providers (OpenAI, Anthropic, open-source) compete fiercely on price and capability, making vendor lock-in a real cost
- The tool integration problem is N×M — N AI clients × M data sources — and ad-hoc integrations collapse under that weight
- Sandboxing, once an afterthought, is now a critical isolation boundary for agents with filesystem and network access
- The defensible asset in enterprise AI is not the model — it's the organizational world model, which lives in the memory layer

## The Move

Structure the agent stack as six independent, swappable layers. Each layer has a clear interface to its neighbors, its own selection criteria, and its own upgrade cadence.

1. **Sandbox/Execution layer** — Isolated runtime for agent code execution (Firecracker MicroVMs, E2B, Modal, Shuru). Agents run here with filesystem, network, and process boundaries. Swap this independently of everything else.
2. **Model layer** — Abstraction over LLM providers. Use a proxy or adapter (LiteLLM, OpenRouter) so routing logic stays decoupled from provider. Route by task type: fast/cheap models for triage, frontier models for synthesis.
3. **Orchestration layer** — Workflow and state management. LangGraph for graph-based control flow, CrewAI for role-based multi-agent delegation, AutoGen for conversational negotiation. Choose based on control granularity needed — not feature count.
4. **Memory layer** — Short-term (conversation context), long-term (vector store), and structured (SQL) persistence. Keep the interface abstract so you can migrate from Pinecone to pgvector without touching agent code.
5. **Tools/MCP layer** — Standardized tool definitions via MCP (Model Context Protocol). 17,000+ community servers as of late 2025. Build or consume MCP servers; do not write custom tool integrations.
6. **Guardrails layer** — Input validation, output filtering, cost circuit breakers, hallucination checks. Plumb these as middleware between layers, not inside agents.

## Evidence

- **HN Discussion / Engineering Blog:** The agent stack is splitting into specialized layers; sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers are each evolving independently with different defensibility profiles. — [HN: The agent stack is splitting into specialized layers](https://news.ycombinator.com/item?id=47114201)
- **Engineering Blog (Philipp D. Dubach, Feb 2026):** The six-layer enterprise AI agent stack decomposes into distinct layers with different defensibility. 37% of enterprises use 5+ AI models in production (up from 29%). The defensible asset is not the model — it's the organizational world model in the memory layer. — [Don't Go Monolithic; The Agent Stack Is Stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **MCP Ecosystem Report (Digital Applied, Dec 2025):** MCP grew from ~50 servers (Jan 2024) to 17,000+ community servers (Dec 2025). Anthropic donated MCP to the Agentic AI Foundation under the Linux Foundation, co-founded with Block and OpenAI. Monthly SDK downloads hit 97M+. MCP resolves the N+M integration problem — build one server per data source, connect to all MCP-aware AI clients. — [MCP Ecosystem Complete Guide](https://www.digitalapplied.com/blog/mcp-ecosystem-complete-guide-2025)
- **MCP Ecosystem Update (ToolBoost.dev, Sep 2025):** Most deployed MCPs: GitHub (45k), PostgreSQL (32k), Filesystem (28k). 25,000+ GitHub repos with MCP, 2.5M NPM downloads/month. — [MCP Ecosystem Update 2025](https://blog.toolboost.dev/mcp-ecosystem-2025-update)
- **Show HN (Evan, 2025):** Opensoul — open-source agentic marketing stack with 6 specialized agents (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) each running autonomously on scheduled heartbeats with delegation to teammates. Explicit organizational metaphor as architecture. — [Show HN: Opensoul](https://news.ycombinator.com/item?id=47336615)

## Gotchas

- **Binding orchestration to tool definitions** — If your agent's system prompt directly encodes which REST endpoints to call, you're stuck rewriting both when either changes. MCP decouples this, but you still need a clean interface.
- **Treating the model layer as a detail** — Teams that hard-code `gpt-4o` everywhere discover the upgrade tax when the next pricing change hits. An abstraction layer costs 30 minutes to add initially and saves days of migration later.
- **Picking orchestration by feature count** — LangGraph offers the most control, CrewAI the fastest initial development, AutoGen the richest conversational primitives. The right choice depends on how often your workflow changes and how deeply you need to debug agent failures. A production team debugging agent failures weekly should weight observability over development speed.
- **Ignoring the sandbox layer** — Giving agents filesystem or network access without isolation is a security and stability risk. The sandbox is not optional infrastructure; it's the blast radius limiter.
