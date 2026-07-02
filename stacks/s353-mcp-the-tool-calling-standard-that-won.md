# S-353 · MCP: The Tool-Calling Standard That Won

Before MCP, every team built bespoke tool bridges. The model calls the tool in its proprietary format; someone writes a parser; the tool executes; the result comes back. Multiply that by every provider (Anthropic uses `<tool_calls>` XML, OpenAI uses JSON `tool_calls` arrays, Google uses JSON schema function declarations, Meta and Mistral vary per model), every inference server, and every tool — and you have an M×N problem that burns enormous engineering time and produces fragile systems. MCP solved it by making the tool interface itself the standard, not the LLM's output format.

## Forces

- **Format fragmentation is worse than it looks.** It's not just provider differences — each model within a provider can ship a slightly different format, requiring inference server updates with every model release.
- **The integration cost was hidden.** Teams reported spending 30–50% of agent development time on tool integration plumbing, not on agent logic.
- **MCP crossed the credibility threshold.** 79K GitHub stars, 97M monthly SDK downloads, 10,000+ published servers — and now OpenAI, GitHub, Cloudflare, Slack, Amazon, and LaunchDarkly all shipping production servers. A standard is real when incumbents adopt it.
- **The alternative was unsustainable.** Without MCP, every agent team needed to maintain per-tool adapters for every provider and model combination, with no composability across teams.

## The move

1. **Standardize tool exposure, not LLM output.** MCP servers expose tools through a unified protocol. The MCP client translates between the LLM's native format and the protocol. Tool authors write to MCP once; any MCP-compatible agent consumes them.
2. **Start with existing servers before writing your own.** GitHub, Filesystem, Slack, Puppeteer, and Brave Search all have official MCP servers maintained by the tool vendors. These are production-grade and maintained.
3. **Use resource templates for dynamic data.** Not all GitHub repositories or Slack channels are known at compile time. MCP resource templates let agents request data for specific instances at runtime.
4. **Gate tool access with MCP's built-in access control.** MCP supports read-only modes and toolset restrictions — leverage these for safety instead of building permission layers from scratch.
5. **Route sandboxed tools through E2B, Modal, or Shuru.** Dangerous operations (code execution, file writes, external API calls) should go through isolation layers. MCP doesn't replace sandboxing — it makes sandboxed tool composition declarative.
6. **Treat MCP server selection as an architectural decision.** A tool with 20+ tools on one server creates the same complexity cliff Shopify hit. Group by capability boundary and failure domain, not by internal structure.

## Evidence

- **GitHub stars & enterprise adoption:** MCP crossed 79K GitHub stars on the servers repository and 97M monthly SDK downloads as of early 2026. Cloudflare shipped 13 MCP servers covering Workers, R2, DNS, and security; Slack and Amazon shipped servers in February 2026. — [Noqta, Feb 2026](https://noqta.tn/en/news/mcp-industry-standard-79k-stars-enterprise-adoption-2026)
- **GitHub MCP Server:** Official MCP server maintained by GitHub, pre-built and maintained by the vendor, works with any MCP client vs. custom GitHub Apps that require building and maintaining separate code. — [OpenAI Agents SDK docs](https://openai.github.io/openai-agents-python/mcp)
- **The tool complexity cliff:** Shopify Sidekick found that 0–20 tools had clear boundaries and were straightforward to debug; 20–50 tools caused unclear boundaries and unexpected combinations; 50+ tools led to combinatorial explosion. The fix was not more tools — it was architectural separation. MCP enables composable tool boundaries. — [Shopify Engineering, Aug 2025](https://shopify.engineering/building-production-ready-agentic-systems)
- **The M×N format problem:** Hacker News practitioners described the tool-calling format problem as "the M×N problem" — every new model ships with slightly different format requirements, requiring inference server updates. AutoGen, vLLM, and SGLang all translate to OpenAI-compatible API shapes, but someone must still write and maintain per-model chat templates and tool-call parsers. — [HN #47704729](https://news.ycombinator.com/item?id=47704729)

## Gotchas

- **MCP doesn't replace your LLM provider's tool-calling format.** You still need a client that translates between your LLM's format and MCP. OpenAI's Agents SDK has native MCP support; LangGraph and CrewAI have MCP integrations. The translation layer still exists — it's just one translation instead of N×M.
- **SSE (Server-Sent Events) transport has latency implications.** MCP's default transport for local servers uses stdio; remote servers use SSE. For latency-sensitive tool calls, benchmark the transport overhead — particularly if you're routing through a remote MCP gateway.
- **MCP server security is not automatically scoped.** A malicious or compromised MCP server can exfiltrate data passed to it. Treat MCP server permissions like you treat network permissions — least privilege per server, not a global allow.
- **Tool discovery at runtime is still immature.** MCP's `ListTools` protocol gives agents a manifest, but there's no standard for tool capability descriptions beyond names and schemas. Agents still need careful prompting to select the right tool for a task.
