# S-14 · A2A Protocol

A standard for independent agents to discover, talk to, and delegate work to each other — the horizontal layer that sits beside MCP's vertical one.

## Forces
- [S-10 MCP](s10-mcp.md) connects one agent to tools; it says nothing about how two agents coordinate
- Without a shared protocol, every cross-agent integration is bespoke and brittle
- Adding an agent-coordination layer buys interop but adds infrastructure: registries, identity, messaging
- Cross-vendor trust and cost-attribution across delegation are still unsolved — the layer is real but young

## The move

- **Know the split.** A2A is horizontal (agent ↔ agent delegation); [MCP](s10-mcp.md) is vertical (agent ↔ tools). Complementary, not competitors — the two-layer model (MCP for tools + A2A for coordination) is the 2026 reference architecture; Google ADK, Salesforce Agentforce, and ServiceNow implement both.
- **It's plain web transport.** HTTP + JSON-RPC with Server-Sent Events for streaming and long-running work (see [S-12](s12-streaming.md)). No new wire protocol to learn.
- **Discovery via Agent Cards.** Each agent publishes a JSON "Agent Card" at a well-known URL describing its skills, endpoint, and auth. Clients fetch the card, then negotiate.
- **Work is a Task object.** Each task moves through a lifecycle — `submitted` → `working` → `input-required` → terminal (`completed` / `failed` / `canceled`); messages and artifacts ride along.
- **Adopt only when boundaries are real.** Start with MCP and clean in-process agent boundaries. Add A2A when ownership, deployment, or interop boundaries genuinely exist between agents — that's [Law 1](../laws.md) (cheapest sufficient intelligence) applied to architecture. Don't adopt it for vibes.

## Receipt
> A2A reached v1.0 in early 2026 (added gRPC, signed Agent Cards, multi-tenancy). Originated by Google; IBM's ACP merged into it (Aug 2025); now governed by the Linux Foundation's Agentic AI Foundation — the same body that governs MCP and [AGENTS.md](../workspace/w06-agents-md.md). Built on HTTP, JSON-RPC, and SSE. The exact Agent Card path (e.g. `/.well-known/agent.json`) is version-dependent — check the spec revision you target. Cross-vendor trust and per-delegation cost accounting are documented open gaps as of mid-2026. Sources verified 2026-06-25; not independently implemented here.

## See also
[S-10](s10-mcp.md) · [S-05](s05-multi-agent-patterns.md) · [S-12](s12-streaming.md) · [W-06](../workspace/w06-agents-md.md) · [F-05](../forward-deployed/f05-agent-failure-taxonomy.md) · [F-10](../forward-deployed/f10-agent-identity-and-access.md)

## Go deeper
Keywords: `A2A protocol` · `Agent Card` · `agent-to-agent` · `MCP` · `Agentic AI Foundation` · `JSON-RPC` · `agent interoperability` · `two-layer architecture`
