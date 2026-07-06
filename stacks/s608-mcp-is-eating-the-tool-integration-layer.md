# S-608 · MCP Is Eating the Tool-Integration Layer

Before MCP, every team built bespoke tool-integration code for every agent. Connecting Claude to GitHub was a different prompt+API call than connecting GPT-4 to GitHub. Every new tool was N×M integration work. MCP solves this by making tool definitions host-agnostic — and 200+ servers later, it's becoming the de facto standard.

## Forces

- **N×M integration hell is real.** Without a shared protocol, adding a tool to your agent means writing custom code for each model. A 3-tool system with 4 models = 12 integrations. MCP collapses this to 3 + 4 = 7.
- **Tool discovery is broken at the agent level.** Agents have no standard way to enumerate what tools exist, what they do, or how to invoke them safely. MCP bakes discovery into the protocol itself.
- **Security and audit trails require structured tool invocation.** Bespoke tool calls produce unstructured logs. MCP's typed JSON-RPC messages give you structured, auditable traces by default.
- **The ecosystem is moving faster than the standards.** MCP's November 2024 open-sourcing triggered rapid adoption, but the ecosystem is still fragmented — not every server is production-grade, and the governance model is immature.

## The move

MCP provides a client-server protocol using JSON-RPC 2.0 over HTTP. The key insight: your LLM host (Claude Code, Cursor, VS Code Copilot, any custom agent) embeds an MCP client, and tools live behind MCP servers.

**Three capability types MCP servers expose:**
- **Tools** — active operations the model triggers (API calls, file writes, ticket creation)
- **Resources** — passive data the model retrieves into context (database rows, documents, config)
- **Prompts** — pre-defined templates guiding how the model uses specific tools

**Practical rollout sequence:**
- Start with a read-only server (file system, Slack archive) to validate the integration pattern
- Add write-capable servers only after establishing audit trails and rollback paths
- Use server-side permission scoping — give each server only what it needs, nothing more
- Pilot inside Slack or VS Code before embedding in production agent flows

**The "USB-C for AI" analogy holds for developer experience but breaks on security.** Swapping Claude for GPT without rewriting connectors is real. But unlike USB-C, MCP servers don't have a hardware-enforced permission model. Trust boundaries must be engineered in.

## Evidence

- **200+ MCP servers exist as of March 2026** — covering GitHub, Google Calendar/Sheets/Directory, database access, CRM integrations, and more. Enterprise SaaS vendors (Workato, Salesforce) are shipping MCP servers as first-class products. — [Bacancy Technology: Enterprise MCP Use Cases](https://www.bacancytechnology.com/blog/enterprise-mcp-use-cases)
- **Anthropic open-sourced MCP in November 2024 and it was rapidly adopted by OpenAI, DeepMind, and Microsoft.** The cross-vendor buy-in is unusual — it signals that the N×M integration problem was painful enough for all of them to align on a shared solution rather than compete on it. — [Rick Xie: MCP Ecosystem 2024–2025](https://rickxie.cn/archive/2025-05-20-MCP)
- **The N×M problem MCP solves is concrete.** One production team cited: connecting a single agent to Slack, GitHub, Notion, and Jira required 16 custom integration modules. With MCP, each tool gets one server; the agent client handles any server. — [Generation Digital: MCP Adoption Guide](https://www.gend.co/blog/model-context-protocol-mcp)
- **Governance and production hardening remain the gap.** Multiple sources note that while MCP servers are proliferating, production deployment requires mTLS, per-tool permission scoping, and encryption patterns for regulated data — none of which are enforced by the protocol itself. — [Generation Digital: MCP Adoption Guide](https://www.gend.co/blog/model-context-protocol-mcp)

## Gotchas

- **MCP does not provide authentication enforcement — you must add it.** The protocol defines how tools are invoked, not who can invoke them. Every production MCP deployment needs an auth layer on top.
- **Not all servers are production-grade.** The ecosystem has 200+ servers but quality variance is large. Evaluate server implementations the same way you'd evaluate any third-party dependency before using in production.
- **Context window pressure still applies.** MCP gives agents more tools, which means more temptation to call everything. Without per-call budget tracking and semantic caching (which can deflect 30% of queries entirely), MCP amplifies cost exposure.
- **Streaming and async patterns vary across servers.** Some MCP servers assume request-response; others support streaming. A multi-agent workflow that chains multiple MCP tool calls can encounter timeout and retry complexity that the protocol spec doesn't address.
