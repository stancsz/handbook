# S-359 · MCP Security and the Agent Protocol Convergence

MCP adoption exploded — 97M+ monthly SDK downloads, 5,800+ servers, 300+ clients. But 43% of MCP servers have command injection flaws, and exploit probability exceeds 92% with 10 plugins. Meanwhile, four competing agent protocols (MCP, A2A, ACP, ANP) are converging into complementary layers. Teams adopting MCP fast are shipping insecure tool integrations, and teams waiting for "one protocol to win" are missing the window to build the interoperability layer that's becoming the next defensible position.

## Forces

- **MCP is the USB-C moment for AI tool integration, but the security surface is wildly underappreciated.** Teams treat MCP servers like safe tool wrappers. They're not — they're executable code paths with broad system access.
- **Protocol proliferation feels chaotic but is actually converging toward distinct layers.** MCP (tool access), A2A (agent-to-agent), ACP (enterprise collaboration), ANP (decentralized) — they don't compete, they stack.
- **Security tooling for MCP is immature.** MCP Manager and similar gateways are 2026 products addressing a 2025 gap. Most production stacks have no observability or policy enforcement on their MCP traffic.
- **The organizational world model is the moat, not the model.** The real lock-in in agentic systems is process knowledge and context — not which LLM powers the orchestration.

## The move

**Adopt MCP aggressively for tool access, but gate it with security infrastructure from day one. Watch A2A for agent-to-agent collaboration — it reached Linux Foundation with 50+ partners in June 2025 and is converging toward enterprise standard. Build the interoperability layer as a first-class concern, not an afterthought.**

### MCP security (act now)

- Treat every MCP server as an attack surface. Command injection in 43% of servers means you cannot trust third-party MCP integrations without sandboxing.
- Use MCP gateways (MCP Manager or equivalent) that add observability, auth, and policy enforcement — the protocol itself has no security layer built in.
- Exploit probability with 10 plugins exceeds 92%. Keep the plugin count low and audit each one.
- Sandbox MCP servers at the process or container level. Modal, E2B, Shuru, and Firecracker wrappers are the emerging isolation layer.

### Protocol layer mapping (understand the landscape)

- **MCP (Anthropic):** Tool access, data retrieval, external system integration. 5,800+ servers, fastest-growing ecosystem.
- **A2A (Google → Linux Foundation, June 2025):** Agent-to-agent collaboration in enterprise settings. 50+ founding partners including AWS, Microsoft, Salesforce, SAP. Best bet for multi-agent coordination.
- **ACP (IBM):** Enterprise collaboration layer — heavier than A2A, designed for business process integration.
- **ANP (Community):** Decentralized agent marketplaces and discovery — speculative but gaining traction.

### Architecture implication

- Don't wait for one protocol to win. Build a thin abstraction layer that lets you swap MCP servers and eventually route across A2A/ACP.
- The defensible position is your organizational world model — the process knowledge, context, and toolchains you wire together. The protocols are commoditizing; the wiring is not.

## Evidence

- **Research report:** 97M+ monthly MCP SDK downloads, 5,800+ servers, 300+ client apps. 43% of MCP servers have command injection flaws; exploit probability >92% with 10 plugins — [Deepak Gupta Research: MCP Enterprise Adoption, Market Trends & Implementation](https://guptadeepak.com/research/mcp-enterprise-guide-2025) (December 11, 2025)
- **Technical analysis:** A2A donated to Linux Foundation June 2025 with 50+ partners (AWS, Microsoft, Salesforce, SAP). MCP and A2A described as "protocols building the AI Agent Internet" — analogous to how HTTP enabled web interoperability. Four protocols address distinct layers (tool access, enterprise collaboration, decentralized) rather than competing — [Zylos Research: Agent-to-Agent Communication Protocol Standards](https://zylos.ai/research/2026-02-15-agent-to-agent-communication-protocols) (February 15, 2026)
- **HN post:** Agent stack is "stratifying" — context, orchestration, security, execution, monitoring, infrastructure as distinct layers with different defensibility profiles. Sandboxing becoming its own discipline (E2B, Modal, Firecracker wrappers). Organizational world model identified as the highest lock-in layer — [Hacker News: phil / Don't Go Monolithic — The Agent Stack Is Stratifying](https://news.ycombinator.com/item?id=47114201) (discussion, 2026)

## Gotchas

- **No auth in MCP by default.** The protocol standardizes the interface, not the access control. You must add auth and policy enforcement at the gateway or proxy layer.
- **A2A and ACP are not production-ready equivalents of MCP yet.** MCP has the ecosystem. A2A has momentum but fewer real deployments. Don't migrate your tool integrations to A2A — use it for agent-to-agent coordination where it makes sense.
- **Silent failure is the dominant agent failure mode.** Xpress AI's fifth agent framework iteration is what it takes to get reliability. Don't assume a working demo equals production-ready code — build explicit health checks, circuit breakers, and test harnesses from the start.
