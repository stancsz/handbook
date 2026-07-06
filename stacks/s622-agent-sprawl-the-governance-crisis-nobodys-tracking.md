# S-622 · Agent Sprawl: The Governance Crisis Nobody's Tracking

You have 47 agents in production. Twelve teams built them. Nobody knows what four of them are doing at 3am.

## Forces

- **Agents compound faster than humans can track them.** A single enterprise team now ships an agent in a sprint. Multiply by 20 teams and you have a population nobody catalogued at birth.
- **Agent actions are invisible to traditional inventory.** Agents authenticate as service accounts, call APIs autonomously, and generate outputs that look like human work — until they don't. Your IAM system shows 45 non-human identities for every employee.
- **The sprawl is the vulnerability.** Ungoverned agents accumulate permissions across systems, operate outside approval workflows, and produce audit trails nobody can reconstruct. The risk isn't the agent — it's the 47 you don't know about.
- **Governance tooling lags deployment by 6-12 months.** Most teams discovered agent sprawl the same way they discovered SaaS sprawl: after the incident.

## The move

**The Agent Control Plane** — a centralized governance layer above the data plane where agents actually run. Not a framework, not a runtime: a policy and visibility layer.

### What it actually does

| Function | What it solves |
|----------|---------------|
| **Agent Registry** | Discovery: every agent registers on deployment with owner, capability, trust level, data access scope. No registry entry = no network access. |
| **Lifecycle Management** | Deploy, version, suspend, decommission. Agents that haven't called home in 30 days get flagged for review or auto-suspension. |
| **Policy Enforcement** | Centralized policy engine: data access constraints, human-in-the-loop gates for high-stakes actions, spend limits. Agents check policy before touching external systems. |
| **Observability Bridge** | Structured telemetry from every agent — tool calls, context windows used, outputs generated, cost accrued — flowing to a central audit log. |
| **Inter-Agent Protocol Governance** | For agents that call each other (A2A): capability negotiation, authentication, rate limits, and scope of data shared in handoffs. |

### The critical distinction: control plane vs. orchestration

**Orchestration** (LangGraph, CrewAI, AutoGen) decides *how* agents work together on a task. **The control plane** decides *who can do what, under what policy, with what visibility*. Orchestration is task-scoped; the control plane is enterprise-scoped.

MCP handles the interface between a model and its tools in a single turn. The control plane handles the interface between your organization and its agent population across months.

### Minimum viable governance: the four controls

If you're starting from zero, implement in this order:

1. **Registry + owner tagging.** Every agent gets a name, owning team, intended purpose, and data access scope on deployment. No tag, no prod access.
2. **Audit log sink.** Every agent writes structured logs to a central store: timestamp, agent ID, action taken, resources accessed, output hash. This is your incident reconstruction and compliance evidence.
3. **Policy checkpoint before external writes.** Agents that touch external systems (APIs, databases, email, code commits) pass through a policy gate. High-stakes actions require human approval or structured evidence of authorization.
4. **Auto-suspend for orphaned agents.** Agents with no owner, no recent calls, or no successful task completions in 30 days get suspended pending review.

### The 45:1 problem

McKinsey and IBM IBV research puts the average enterprise at 45 non-human identities per human employee. Most of those identities have accumulated over years of RPA, workflow automation, and now agents — with no unified view. The control plane gives you that view for the first time.

> "It is the microservices sprawl problem, except the services can think, act autonomously, and accumulate permissions without a human in the loop." — IBM Institute for Business Value, 2026

### The EU AI Act dimension

High-risk AI systems under the EU AI Act require documentation, logging, and human oversight. An agent that operates autonomously across customer data, financial systems, or HR processes is almost certainly high-risk. The control plane is the compliance infrastructure: it produces the audit trail, enforces the oversight mechanisms, and documents the decision logic that regulators will ask for.

```python
# Minimal agent control plane registry entry (pseudocode)
agent_registry.register(
    id="support-tier2-escalation-v3",
    owner="support-platform-team",
    capability="customer ticket escalation + refund authorization",
    trust_level=TrustLevel.BOUNDED_AUTONOMY,  # L3 — requires human approval for refunds > $500
    data_access=["crm:tickets:read", "billing:refunds:write"],
    policy_version="policy-v2.1",
    auto_suspend_after_days=30,  # if no activity, flag for review
    observability_sink="central-audit-log",
)
```

## Receipt

> Verified 2026-07-05 — AgentMarketCap (94% orgs report sprawl), IBM IBV (96% using agents, 45:1 non-human identity ratio), McKinsey (80% encountered risky agent behavior). IBM Think documentation confirms agent control plane as distinct from MCP. No competing handbook entry on agent sprawl governance as a named architectural pattern.

## See also

- [S-583 · The Agent Protocol Stack: MCP, A2A, and Where the Boundary Lives](s583-the-agent-protocol-stack-mcp-a2a-and-where-the-boundary-lives.md) — protocol layers that the control plane governs
- [S-532 · The Six Agent SLOs](s532-the-six-agent-slos.md) — the observability signals a control plane must capture
- [S-74 · Agent Capability Registry](s74-agent-capability-registry.md) — the discovery component at the control plane's core
- [S-527 · A2A Protocol: Agent-to-Agent Interoperability Layer](s527-a2a-protocol-agent-to-agent-interoperability-layer.md) — inter-agent communication under governance
