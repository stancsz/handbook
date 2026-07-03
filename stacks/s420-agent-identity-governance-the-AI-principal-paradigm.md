# S-420 · Agent Identity Governance: The AI-Principal Paradigm

Your agent accessed a customer's full transaction history, exported it to an external endpoint, and modified billing settings — none of which the user authorized. Your IAM system logged no anomaly because the agent's credentials were valid. The access control list said "read billing data." It did not say "agent, read only what you need for this specific task." IAM was built for humans with employment records. AI agents are neither human nor have employment records. The security model built on those assumptions has a structural gap — and it is widening.

## Situation

In 2026, 80% of organizations deploying AI agents report unintended agent actions (unauthorized system access, data sharing). 1-in-5 organizations have experienced an AI-agent-related security incident. The 144:1 ratio of non-human identities to human users in enterprise environments means the dominant identity type is already non-human. Yet almost every enterprise IAM system still treats the agent as a service account with human-equivalent permissions. It is not. A service account runs code that humans wrote and approve. An autonomous agent decides which actions to take at runtime, often using tools that were not known at deployment time. The IAM model built for one does not fit the other.

## Forces

- **Agents are runtime decision-makers, not deployment-time authorizations.** A human IAM system grants access at login and trusts the human throughout the session. An agent makes decisions at every step — which API to call, which data to retrieve, whether to escalate. The authorization decision has to live inside the agent loop, not at the perimeter.
- **The IAM mesh was designed for humans, not agents.** Enterprise IAM ties identities to employment records, managers, and departure dates. Agents have none of these. Binding agent identities to human sponsor accounts creates fragile, audit-unsafe chains. Agents need their own identity layer that correlates to, but is distinct from, human IAM.
- **Action management is different from access management.** Just because an agent has access to a resource does not mean it should freely use that access. Humans monitor how agents leverage granted access — this is the same insider-threat model applied to non-human principals, requiring action-level policy enforcement, not just access-level gates.
- **Credential sprawl is compounded by delegation.** Single agents spawn sub-agents, inherit parent credentials, and pass access tokens across hops. A revocation at the parent does not automatically cascade. Each delegation chain widens the blast radius.
- **Traditional alerting misses AI-specific failure modes.** Unusual response patterns, quality degradation, and cost anomalies are invisible to conventional SIEM tools that look for known-bad signatures, not anomalous agent behavior.

## The move

### 1. Define the AI Principal Identity

An AI principal is a first-class, non-human identity with its own attestation lifecycle, independent of the human who deployed it. It has:

- **A capability contract** — a signed, machine-readable manifest of what the agent is authorized to do, scoped to specific resources, actions, and time windows. Not "read anything in CRM" but "read billing records for customer IDs passed in the current session, expire after 30 minutes."
- **A trust tier** — assigned at deployment based on the sensitivity of downstream systems. Tier 1 agents (can modify data, spend money, access PII) require human approval gates. Tier 3 agents (read-only, non-sensitive) run with tighter autonomous bounds.
- **An identity anchor** — a cryptographic identity bound to the agent's deployment context (deployment ID, version, responsible team, approval chain). The anchor is signed by the human approver and verifiable at runtime.

### 2. Enforce Action-Level Policy Inside the Agent Loop

Access-level RBAC is insufficient. Add an **action policy layer** inside the agent execution loop that evaluates each proposed action against the capability contract before it executes.

```
Agent proposes: GET /api/billing/{customer_id}
Action policy checks:
  - Is customer_id in the approved session scope? ✓
  - Is GET approved for this endpoint in Tier 1? ✓
  - Has elapsed time exceeded the session TTL? ✓
  - Does the response schema match expected fields? ✓
Action allowed.
```

This is not a firewall. It is an agent-native policy gate that sees the same context the agent sees — which is the only place where the gap between tool descriptions and tool calls can be closed.

### 3. Build the IAM Mesh

Agents must coexist in the enterprise IAM mesh. The mesh has three relationships:

- **Human-to-agent** — the sponsoring human approves the agent's capability contract. Revocation of the human's employment revokes the agent's identity anchor. Human departure must not leave orphaned agents.
- **Agent-to-agent** — over A2A or other protocols, agents need a delegation chain that carries capability scope. An agent receiving a delegated task can verify: (a) the delegating agent had authority to delegate, and (b) the delegated action is within the original capability contract. This requires signed capability tokens passed between agents, not just ambient trust.
- **Agent-to-downstream** — agents calling enterprise APIs, databases, and services. Each downstream system needs to accept and enforce the agent's capability contract, not just its credential. This requires the IAM mesh to propagate capability tokens to legacy systems that were not designed to parse them.

### 4. Operate Action Management

Beyond static policies, monitor how agents actually use their access:

- **Behavioral telemetry** — instrument agent actions (tool calls, data access patterns, escalation events) as first-class telemetry. This is distinct from LLM tracing. It is IAM telemetry: who did what to which resource.
- **Anomaly scoring** — flag when an agent accesses resources outside its normal pattern (different data types, unusual volumes, unexpected destinations). Cost spikes are an agent failure mode that action management catches.
- **Kill switch with task preservation** — revocation must stop the agent from taking new actions but preserve in-flight state for audit. A hard SIGKILL loses the entire operation context; a graceful halt with state serialization preserves evidence.

### 5. Apply Zero-Trust for Agents

Zero-trust means never trust, always verify — applied to every agent action at runtime:

- **Never trust a tool description** — tool schemas can be poisoned (see [S-285 · MCP Security: The Trap the Standard Ships Compromised](stacks/s285-mcp-security-trap-the-standard-that-ships-compromised.md)). Always verify the tool call against the action policy, not just the tool schema.
- **Never trust the delegation chain ambiently** — each hop in an agent-to-agent call must re-verify the capability token against the action policy, even if the calling agent is trusted.
- **Always attribute** — every agent action traces back to a specific capability contract, a specific human approver, and a specific session. No anonymous agent actions in the audit log.

## Tradeoffs

- **Policy granularity vs. agent performance** — action-level policy enforcement adds latency to every tool call. The tradeoff is real: Tier 1 agents (sensitive actions) pay the latency cost; Tier 3 agents (read-only, low-risk) run with coarser policies.
- **Capability contract expressiveness vs. engineering cost** — machine-readable, fine-grained capability contracts require schema design, signing infrastructure, and policy evaluation logic. Start with coarse-grained contracts and refine as the agent matures.
- **Agent autonomy vs. governance safety** — tight action policies constrain what agents can do. The failure mode is blocking legitimate agent actions at runtime. The mitigation: tiered autonomy, where higher tiers get broader contracts with stronger anomaly monitoring.
- **Legacy system integration** — enterprise IAM meshes include systems (mainframes, old APIs) that cannot parse capability tokens. The pragmatic path: wrap them with an agent-native proxy that enforces the capability contract on their behalf.

## Receipt

> Verified 2026-07-03 — Researched via: Insight Partners (IAM for AI Agents, March 2026), NHIMG AI Agent Identity Security Deployment Guide (March 2026), Forrester Identiverse 2026 recap, NIST concept paper (Feb 2026), Hacker News security threads. Cross-checked against existing handbook coverage: s313 covers credential lifecycle (issuance, rotation, revocation), s266 covers inter-agent delegation trust chains. Neither covers the paradigm shift to AI-Principal identity, action-level vs. access-level policy enforcement, the IAM mesh (human-to-agent, agent-to-agent, agent-to-downstream), or zero-trust for agent tool calls. Gap confirmed.

## See also

- [S-313 · Agent Credential Lifecycle Security](stacks/s313-agent-credential-lifecycle-security.md) — the lifecycle of agent credentials; complements this entry on the identity and policy layer above
- [S-266 · Inter-Agent Trust Delegation](stacks/s266-inter-agent-trust-delegation.md) — the agent-to-agent segment of the IAM mesh
- [S-355 · Agent Autonomy Levels (Bounded Autonomy)](stacks/s355-agent-autonomy-levels-bounded-autonomy.md) — the trust tiers that map to capability contract scope
- [S-285 · MCP Security: The Trap the Standard Ships Compromised](stacks/s285-mcp-security-trap-the-standard-that-ships-compromised.md) — tool poisoning and the zero-trust enforcement point inside the agent loop
