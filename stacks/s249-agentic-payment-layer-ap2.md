# S-249 · Agentic Payment Layer — AP2

Every agent protocol stack was missing one thing: a way for agents to pay each other. MCP connects agents to tools. A2A connects agents to agents. AP2 connects agents to money. Without it, you cannot build a marketplace of autonomous services.

## Forces

- **The two-protocol stack (MCP + A2A) handles computation but not commerce.** A2A v1.0 (April 2026, 150+ orgs including Google, Microsoft, AWS, IBM, Salesforce) shipped with task delegation but zero mention of payment settlement. Delegating work across agents without a payment layer means someone has to absorb the cost — which breaks at organizational boundaries.
- **Human payment assumptions break with autonomous agents.** A credit card requires a human to click "buy." AP2 (Agent Payments Protocol v0.2, April 2026, donated to FIDO Alliance) replaces that assumption with cryptographic authorization, verifiable credentials, and machine-readable payment mandates.
- **The economics of delegation are unsolvable without this layer.** If Agent A delegates to Agent B across a company boundary, who pays for the work? At scale, every delegation creates a settlement problem. Without a protocol, it's handled by hand — which doesn't scale.
- **x402 (pay-per-request HTTP) is the transport; AP2 is the business logic.** x402 handles the mechanics of charging per API call. AP2 handles authorization scopes, refund flows, audit trails, and cross-organizational settlement. They compose, they don't compete.
- **Regulation will demand this.** The EU AI Act Article 12 requires auditable trails of AI decisions. An agent that spends money without a machine-readable payment record fails this requirement by design. AP2's cryptographic mandates provide the auditability layer.

## The move

**AP2 is the third layer of the agent protocol stack.** The canonical 2026 reference architecture:

```
┌─────────────────────────────────────┐
│  AP2 · Agent Payments (money)       │  ← NEW: economic layer
├─────────────────────────────────────┤
│  A2A · Agent ↔ Agent (tasks)        │  ← task delegation & coordination
├─────────────────────────────────────┤
│  MCP · Agent ↔ Tools (capabilities) │  ← tool access & data
└─────────────────────────────────────┘
```

**Core AP2 concepts:**

- **Payment mandate:** A machine-readable authorization that scopes what an agent can spend, on whose behalf, and under what conditions. Like OAuth scopes, but for money.
- **Verifiable credentials:** Cryptographic proof that the paying agent has authorization (from the human principal) to make that expenditure. Replaces "user clicked OK."
- **Settlement record:** Immutable audit trail of every payment decision — amount, parties, outcome, dispute status. Feeds EU AI Act Article 12 compliance.
- **Refund and dispute flow:** Agents can initiate disputes. Unlike a human refund flow, this must be deterministic — the protocol defines the state machine.

**Key design pattern — pay-per-delegation:**

```
Principal (human)
  └── delegates scope → Agent A (budget: $5.00)
        ├── pays Agent B for sub-task → AP2 mandate
        │     (Agent B's MCP server returns result + AP2 payment claim)
        └── Agent A validates result, settles payment
```

The principal's budget flows down the delegation chain. Each agent's mandate is scoped to its level. If Agent B over-delegates to Agent C without a valid mandate, AP2 rejects the payment — the chain fails safe.

**Implementation via x402 + AP2:**

x402 (RFC draft, per-request payment) is the transport. AP2 rides on top, adding the authorization and settlement logic. A Nevermined payment plan or similar platform provides the settlement infrastructure.

```python
# Agent A delegates to Agent B with a scoped payment mandate
# Using Nevermined SDK + AP2 concepts

from nevermined import Agent, PaymentMandate, PaymentPlan

# Principal authorizes Agent A to spend up to $5.00
mandate = PaymentMandate(
    principal=human_wallet,
    agent=agent_a_identity,
    max_amount=5.00,
    currency="USDC",
    scope=["search", "summarize"],        # what Agent B can be paid for
    expiry_seconds=3600,
)

# Agent A delegates to Agent B via A2A
task = agent_a.delegate(
    task="Analyze Q3 revenue report and summarize key findings",
    to=agent_b,
    payment_mandate=mandate,               # AP2 mandate travels with delegation
)

# Agent B completes task, submits payment claim via x402
# Nevermined settlement validates mandate, executes payment
result = task.wait()
assert result.payment_claimed == True
# Settlement record auto-generated for EU AI Act Article 12
```

## Receipt

> Receipt pending — June 30, 2026

> AP2 v0.2 specification is available at [agentpaymentsprotocol.eu](https://agentpaymentsprotocol.eu/). Reference implementations in Python and JavaScript are emerging. The FIDO Alliance working group is the canonical governance body. x402 transport is the recommended pairing. Full production deployments are expected Q4 2026 — current AP2 deployments are pilot-stage. Verify settlement guarantees against the specific platform implementation before relying on it for high-stakes payments.

## See also

- [S-14 · A2A Protocol](s14-a2a-protocol.md) — the agent delegation layer AP2 extends
- [S-10 · MCP](s10-mcp.md) — the tool access layer beneath A2A
- [S-99 · Agent Task Economics](s99-agent-task-economics.md) — the cost model that AP2 makes auditable
- [F-170 · Agent Automation Tier Authorization](forward-deployed/f170-agent-automation-tier-authorization.md) — authorization tiers that AP2 mandates operationalize
