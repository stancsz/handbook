# S-275 · MCP Is Eating the Tool-Integration Layer

The Model Context Protocol is rapidly displacing bespoke REST integrations as the standard way agents connect to tools. The USB-C analogy isn't hype — it's an accurate description of what production teams are actually doing.

## Forces

- **The M×N integration problem is crushing teams.** Connecting M LLMs to N tools requires M×N custom implementations. MCP reduces this to M + N. For teams running 3 models across 20 tools, that's the difference between 60 integrations and 23.
- **Tool schema drift breaks agents in production.** When a SaaS API changes response shapes, custom integrations silently fail. MCP servers encapsulate this behind a stable interface, isolating agents from upstream changes.
- **Enterprise governance demands audit trails.** MCP's resource and prompt patterns make it straightforward to enforce role-based access, logging, and compliance controls at the tool layer — harder to bolt on after the fact with ad-hoc integrations.
- **First-party SDK support is arriving fast.** Microsoft (Copilot Studio, VS Code agent mode, Semantic Kernel, official C# SDK), Anthropic (Claude Desktop native MCP client, Claude for Work), and major open-source frameworks (LangGraph, CrewAI via LangChain adapters) all support MCP natively as of 2025.

## The move

MCP is now the default answer for tool integration in new agent builds. Here's how to approach it:

- **Default to MCP for all new tool integrations.** Build an MCP server for any internal API, database, or service your agents need to call. The upfront cost is ~1-2 days per server; the maintenance savings compound over time.
- **Use FastMCP (Python) or the official TypeScript SDK** for building servers — both are production-stable and have active communities. The Python SDK's `FastMCP` decorator pattern is the fastest path: annotate a function with `@mcp.tool()` and it's immediately callable by any MCP client.
- **Apply the three-pattern MCP governance model:** resources (data access with access control), tools (mutating operations requiring audit), and prompts (pre-packaged workflows). Map your internal services to these patterns explicitly rather than treating everything as a "tool."
- **Combine MCP with LangGraph for durable execution.** LangGraph's checkpointing + MCP's tool abstraction gives you stateful, observable agent runs where tool calls are logged, replayable, and auditable. This combination is emerging as the production default for serious agentic systems.
- **Deploy MCP servers as isolated services** with declared network whitelists and subprocess isolation per skill. This contains blast radius when a tool integration behaves unexpectedly — critical when agents have destructive capabilities.
- **Register MCP servers in a central registry** (e.g., Anthropic's MCP registry, or a self-hosted equivalent) so agents can discover available tools dynamically rather than having tools hardcoded at deployment time.

## Evidence

- **Framework comparison:** AutoGen, CrewAI, and LangGraph all converged on MCP as their primary tool-calling interface by mid-2025. JetThoughts' 2025 framework analysis notes LangGraph's production standing with Klarna, Replit, and Elastic — all three use MCP or equivalent patterns for tool integration. — [jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)
- **Enterprise adoption:** Microsoft shipped native MCP support across Copilot Studio (one-click server configuration, May 2025), VS Code's GitHub Copilot agent mode, and Semantic Kernel. Anthropic released an official C# MCP SDK for .NET environments. A Microsoft ISE case study documents a retail customer migrating from custom REST tool integrations to MCP servers as part of evolving from a modular monolith to microservices for their multi-agent chatbot. — [dataconomy.com/2025/09/03/top-model-context-protocol-tools-and-platforms-in-2025](https://dataconomy.com/2025/09/03/top-model-context-protocol-tools-and-platforms-in-2025/), [devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **Real code pattern:** GitHub repos show MCP clients integrated directly with LangGraph ReAct agents: `client.get_tools()` passed to `create_react_agent(model, tools)` — 4 lines to connect a LangGraph agent to any MCP server. The Agent-MCP framework repo demonstrates multi-agent coordination via MCP for parallel task execution. — [github.com/AIwithTim/mcp-client-examples](https://github.com/AIwithTim/mcp-client-examples), [github.com/rinadelph/Agent-MCP](https://github.com/rinadelph/Agent-MCP)

## Gotchas

- **MCP is not a security boundary by default.** A tool registered via MCP can still make destructive calls. You need explicit sandboxing (subprocess isolation, network whitelists, IAM policies on the underlying services) — the protocol handles discovery and schema, not authorization.
- **The MCP SDK is still moving fast.** Breaking changes in the Python and TypeScript SDKs have caused migration work for early adopters. Pin your SDK versions and treat SDK upgrades as a coordination event across all connected agents.
- **Not every tool needs an MCP wrapper.** Simple read-only integrations (e.g., a weather API called once per run) may be cheaper and simpler as direct REST calls. The M×N problem only bites when you have multiple agents calling the same tool or multiple tools being called by the same agent — evaluate per integration.
- **MCP's stdio transport is fine for local dev but adds latency in high-throughput scenarios.** For production services calling MCP servers at high frequency, evaluate HTTP/SSE transport options instead.
