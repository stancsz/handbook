# S-526 · A2A Agent Card: Capability Discovery for the Agentic Web

Two agents need to collaborate. Before they exchange a single task, one of them must answer: *does the other speak my language, handle my data types, and can I trust it?* In human collaboration, you read a business card. In the A2A protocol, you read an **Agent Card** — a JSON document every A2A-compatible agent publishes describing who it is, what it can do, and how to authenticate with it. This is the handshake that makes autonomous agent-to-agent collaboration possible without manual configuration.

## Forces

- **Agents are opaque boxes.** Unlike tools (MCP), where you can inspect a manifest, an agent's capabilities are hidden until you interact with it. Without a standard self-description format, every integration requires hardcoded knowledge of the other agent's API — the service-discovery anti-pattern for an autonomous ecosystem.
- **Capability matching must happen before delegation.** A task sent to the wrong agent fails expensively (S-505's blast radius applies here). The Agent Card lets the routing agent evaluate fit *before* the task crosses the wire.
- **Trust is not optional in open agent networks.** An agent receiving a delegation needs to verify the sender's identity, its declared capabilities, and its security posture — not discover these at runtime through failure.
- **Discovery mechanisms are environment-dependent.** A global A2A registry works for open networks; an enterprise catalog behind a VPN works for internal multi-agent systems. The spec supports both, but the implementation choice has security implications.
- **S-414 covers the protocol convergence thesis** but focuses on MCP↔A2A interoperability and the three-layer stack. This entry covers the discovery and capability-matching primitives that make the horizontal A2A layer actually work.

## The move

### The Agent Card schema

Every A2A server publishes a card at `https://<base_url>/.well-known/agent.json` (the well-known convention). The card is the agent's self-description:

```json
{
  "name": "billing-intelligence-agent",
  "description": "Analyzes subscription data, predicts churn, generates billing reports.",
  "provider": {
    "organization": "acme-corp",
    "contact": "platform-team@acme.com"
  },
  "url": "https://agents.acme.com/billing/v1",
  "version": "2.1.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true
  },
  "authentication": {
    "schemes": ["Bearer", "OAuth2"]
  },
  "skills": [
    {
      "id": "churn-prediction",
      "name": "Subscription Churn Prediction",
      "description": "Predicts 30/60/90-day churn probability from usage signals.",
      "inputModes": ["application/json"],
      "outputModes": ["application/json"],
      "examples": [
        {
          "comment": "Standard churn risk query",
          "input": "{\"customer_id\": \"cust_123\", \"lookback_days\": 30}",
          "output": "{\"churn_probability\": 0.73, \"risk_tier\": \"high\"}"
        }
      ]
    }
  ]
}
```

The `skills[]` array is the actionable part. Each `AgentSkill` declares a capability with a human-readable description and machine-readable examples. This is what a routing agent parses to decide whether to delegate.

### Discovery mechanisms

**Well-known URL (DNS-based):** The client resolves `billing.acme.com` via DNS, then fetches `https://billing.acme.com/.well-known/agent.json`. Works for any agent with a public domain. Simple, zero-configuration, but requires the client to already know the agent's base URL — discovery is still a bootstrapping problem.

**Curated registry (catalog-based):** An intermediary service maintains a collection of Agent Cards. Clients query the registry by skill, tag, provider, or description. This is the enterprise pattern: private catalogs behind a VPN, organizational agent marketplaces, or the A2A Global Registry. Enables capability-based search ("find an agent that does churn prediction in the financial services domain") rather than address-based routing.

**Hybrid:** A client checks its local catalog first (low-latency), falls back to the well-known URL if the agent is unknown, and optionally queries the global registry for new agents. The A2A spec doesn't mandate a single approach — it standardizes the artifact format so all three mechanisms produce interoperable results.

### Capability matching

The `skills[]` array enables programmatic matching. A routing agent building on S-505's tiered action gates can match task requirements against skill declarations:

```
Task requirements (what the delegating agent needs)
  → Query registry/catalog for skills where:
      description matches task intent
      inputModes ⊇ task input format
      outputModes ⊇ task expected format
  → Rank by: skill examples (higher fidelity = better match),
             version stability, authentication support
  → Select: top-ranked, authenticated agent
  → Establish A2A session, delegate task
```

This is distinct from MCP's tool manifest (which describes discrete function calls) because an AgentSkill describes a *capability* — a possibly complex, stateful, multi-turn task — not a single function signature.

### Authentication and trust

The `authentication.schemes` field declares what's required. Agents accepting Bearer tokens work for closed systems. Agents requiring OAuth2 are appropriate for cross-organizational delegation. The field doesn't encode the credential itself — it declares what's needed so the calling agent can provision access.

Enterprise deployments layer certification on top: the registry operator signs Agent Cards, adds a `certifications[]` array (SOC2, ISO27001, data residency classification), and the receiving agent verifies the chain before accepting a delegation. This is the production trust model for regulated industries — see the healthcare A2A use case cited in the spec.

## Receipt

> Verified 2026-07-04 — Agent Card spec extracted from a2a-protocol.org v0.2.5 and a2a-inspector project (GitHub a2aproject). The well-known URL convention, AgentSkill schema, authentication schemes, and registry patterns are confirmed against the official A2A Protocol documentation. The registry taxonomy (DNS-based, catalog-based, hybrid) confirmed against the official spec. Enterprise certification/attestation layer is documented in the spec but implementation varies by registry operator.

## See also

- [S-414 · The Protocol Convergence Thesis](stacks/s414-the-protocol-convergence-thesis.md) — the three-layer stack (MCP↔A2A↔AP2) this entry operates within
- [S-505 · Consequential Action Gates](stacks/s505-consequential-action-gates-tiered-hitl-architecture.md) — the tiered delegation model that precedes capability-matched routing
- [S-365 · MCP Supply Chain](stacks/s365-mcp-supply-chain-from-npx-to-production-catalog.md) — parallel catalog/security patterns for MCP (tool layer vs. agent layer)
- [S-355 · Agent Autonomy Levels](stacks/s355-agent-autonomy-levels-bounded-autonomy.md) — the trust calibration required before an agent uses capability-matched delegation at L3+
