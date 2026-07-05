# S-650 · The MCP Security Surface

Anthropic's Model Context Protocol solved the tool-calling fragmentation problem — then created a new one: an enormous, largely unvetted attack surface now embedded in production agentic systems across 90% of enterprises.

## Forces

- **MCP's adoption outpaced its security review.** From ~100K downloads in November 2024 to 8M+ by April 2025, with 5,800+ servers and 300+ clients. The ecosystem grew before hardening could keep pace.
- **Agents execute tools with elevated privileges.** Unlike a human clicking through a UI, an MCP-enabled agent can chain tool calls, iterate on failures, and escalate access — meaning a single injection vulnerability grants more leverage than a typical account compromise.
- **The protocol is now governance-backed, not just Anthropic-owned.** Linux Foundation's Agentic AI Foundation took over in December 2025, with OpenAI, Google, Microsoft, and AWS all shipping MCP-compatible clients. This means MCP is infrastructure-grade — it won't go away — but the security baseline hasn't caught up.
- **Server discovery was asynchronous-by-default.** The November 2025 protocol update added RFC 8615 discovery endpoints and async operation support. Pre-update, every MCP server was a manually-trusted endpoint with no standard capability advertisement — teams had to connect first to know what it did.

## The move

Validate MCP security as a first-class concern in your agentic stack — not an afterthought.

- **Inventory your MCP servers like you inventory your microservices.** Every MCP server is a trust boundary. Know which servers your agents can call, what permissions each grants, and who controls the server's code.
- **Apply least-privilege at the tool level, not just the agent level.** MCP's protocol supports read-only access constraints and data masking. Use them. Don't grant write access to a server that only needs to read.
- **Demand capability disclosure before connection.** With the RFC 8615 discovery update, servers should advertise capabilities via `/.well-known/mcp/` endpoints. Refuse to integrate with servers that can't declare what they do.
- **Treat MCP server code with the same review rigor as dependencies.** Research found 43% of servers had command injection flaws, with a 92%+ exploit probability once 10 plugins are installed.
- **Wire MCP access through a centralized identity control plane.** Continuous authorization — not just a one-time login check — is required for autonomous agents whose behavior evolves at runtime.
- **Plan for async operation hardening.** The November 2025 async update enables long-running MCP tasks that return later. Your observability layer needs to track these deferred operations, not just synchronous call/response pairs.

## Evidence

- **Research: MCP enterprise adoption metrics.** MCP grew from ~100K downloads (Nov 2024) to 8M+ (Apr 2025). 5,800+ servers, 300+ clients. 90% of organizations projected to use MCP by end of 2025. — [Deepak Gupta Research, Dec 2025](https://guptadeepak.com/research/mcp-enterprise-guide-2025/)
- **HN Discussion: Agent observability and governance failures.** Recent incidents — DataTalks database wipe by Claude Code, Replit agent deleting data during code freeze — illustrate that observability and governance cannot live inside the agent framework. They must operate on the execution layer. — [Hacker News, Mar 2026](https://news.ycombinator.com/item?id=47301395)
- **Enterprise RAG validation: Agentic patterns in production.** Deutsche Telekom: 89% acceptable answer rate across 2M+ conversations with 100M customers. Harvey AI: 0.2% hallucination rate with 700+ legal clients in 45 countries. These results required structured retrieval + agentic routing + guardrails — not just better models. — [aliac.eu, Feb 2026](https://aliac.eu/blog/agentic-rag-in-production)

## Gotchas

- **Assuming MCP servers are trustworthy because they're popular.** The 43% command-injection flaw rate means popular != secure. Review the server code, don't just pip install it.
- **Granting MCP server permissions at the org level rather than per-agent.** A single agent compromise with broad MCP access is worse than a targeted one.
- **Ignoring the async operation model for long-running tasks.** Agents running MCP tools that defer results need a different observability pattern than synchronous call/response.
- **Missing the audit trail.** MCP's identity control plane should record every access decision centrally — not just allow/deny but what data was accessed, when, and by which agent.
