# S-414 · The Protocol Convergence Thesis

Three protocols now define the agentic stack: MCP connects agents to tools, A2A connects agents to agents, and AP2 connects agents to money. Each solves one layer. Together they make autonomous commerce possible. The hard part is not understanding them individually — it is architecting the seams between them.

## Forces

- **MCP and A2A solve different directions, not competing problems.** MCP is vertical (agent → tools). A2A is horizontal (agent ↔ agent). Teams that pick only one end up with agents that work in isolation. The 2026 reference architecture uses both simultaneously — and the decision of *when to use which* is not obvious in the grey zones.
- **The convergence thesis is real but premature.** MCP servers that act as agents, A2A tool-execution extensions, joint AAIF working groups on interoperability — these patterns are emerging. But no stable spec exists yet. Betting on premature convergence introduces fragility.
- **The MCP-as-agent shift breaks the clean separation.** The MCP spec roadmap includes servers that delegate to other servers. When a tool-calling endpoint itself becomes an agent, the MCP/A2A boundary blurs inside a single protocol. Existing architectures that assume a hard line between "tool" and "agent" will need redesign.
- **AP2 completes the commerce layer but the payment primitives are immature.** Signed agent cards, verifiable credentials, and machine-readable mandates are the right primitives. But AP2 v0.2 has no settlement layer, no dispute resolution, and no standard for cost-attribution across delegated chains. Production agentic commerce today requires building the missing plumbing yourself.

## The move

### 1. Use the two-layer default until you hit its edges

The MCP + A2A two-layer model handles most enterprise use cases:

```
Orchestrator Agent (A2A client)
  └─→ dispatches task via A2A →→→ Specialist Agent (A2A server)
        └─→ calls tools via MCP →→→ MCP Server (file system, CRM, search…)
```

This is what Google ADK, Salesforce Agentforce, and ServiceNow's Now Actions implement in production. Start here.

### 2. Know the three seam cases where layers collide

**Seam A: A2A agents calling tools.** An A2A specialist agent that wraps a tool-calling interface (like a code-review service) faces the question of whether to expose itself as an MCP server or an A2A skill. Rule of thumb: if the capability is *stateless and deterministic*, MCP. If it requires *session state, negotiation, or multi-turn handoff*, A2A.

**Seam B: MCP servers that delegate.** When your MCP server internally calls other MCP servers to fulfill a request, you've built an agent that disguises itself as a tool. The MCP spec doesn't govern inter-server delegation. Treat these as hidden multi-agent systems and apply [S-05](s05-multi-agent-patterns.md) coordination logic inside the server boundary.

**Seam C: AP2 payment in delegated chains.** When Agent A delegates to Agent B, and B delegates to C, who pays whom? AP2's signed mandate model handles the A→B handshake but says nothing about chain settlement. Design cost-attribution at the A2A task-initiation level: the initiating agent embeds a budget cap in the task payload that each downstream agent respects and decrements.

### 3. Track three convergence signals

The MCP/A2A/AP2 landscape is actively evolving. Monitor:

| Signal | Source | Why it matters |
|--------|--------|----------------|
| MCP server-as-agent spec | Anthropic / AAIF roadmap | Would collapse the tool/agent distinction inside MCP |
| Joint interoperability draft | Google × Anthropic × AAIF | Formal bridge spec between MCP tool calls and A2A delegations |
| AP2 settlement layer | FIDO Alliance / AAIF | Missing piece for production agentic commerce |

### 4. Pin your protocol versions

MCP spec versioning and A2A spec versioning are governed independently by different foundations (Anthropic + Linux Foundation vs. Google + Linux Foundation). Version drift between the two is not theoretical — the MCP Tasks feature (added November 2025) overlaps with A2A's Task object in ways that are not yet harmonized. Pin major versions in your config; do not auto-upgrade either protocol SDK in production without integration testing.

## Receipt

- A2A: 50 → 150+ partner orgs in first year (Stellagent, April 2026); Linux Foundation AAIF governance
- MCP: 97M+ monthly SDK downloads within one year of launch; Anthropic donated spec to Linux Foundation
- AP2: FIDO Alliance donation April 2026, signed agent cards in A2A v1.0 (early 2026)
- Convergence: Joint Anthropic/Google AAIF working groups on interoperability expected but no official spec as of July 2026

## See also

- [S-10 · MCP](s10-mcp.md) — tool connectivity protocol
- [S-14 · A2A Protocol](s14-a2a-protocol.md) — agent coordination protocol
- [S-197 · MCP + A2A Two-Layer Orchestration](s197-mcp-a2a-two-layer-orchestration.md) — reference architecture
- [S-249 · Agentic Payment Layer — AP2](s249-agentic-payment-layer-ap2.md) — commerce layer
- [S-390 · MCP Security — The Command Injection Surface](s390-mcp-security-command-injection.md) — MCP attack surface
