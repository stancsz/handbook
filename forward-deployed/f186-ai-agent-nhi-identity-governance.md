# F-186 · AI Agent Non-Human Identity (NHI) Governance

Every enterprise now has more AI agent identities than human employees — 45:1 on average. Most have no policies, no audits, and no revocation path for any of them. When an agent gets compromised or a sub-agent inherits permissions it shouldn't have, there is no kill switch, no trace, and no accountability. NHI governance is the infrastructure discipline that closes this.

## Forces

- **Agents outnumber human identities 45:1.** In 2021 the ratio was 10:1. By 2026 it crossed 45:1 — and most security teams still manage all of them like a single service account named `agent_pool_prod`.
- **Legacy IAM assumes humans who log in, work, and log out.** Agents operate 24/7, chain actions across platforms, spawn sub-agents, and inherit permissions that escalate without oversight. A human IAM model cannot track this.
- **78% of organizations have no AI-specific identity policies.** Yet agents already have admin-level access to production systems, customer data, and financial tools. The access was granted. The governance was not.
- **Credential sharing across agents collapses attribution.** When one agent credential is used by ten agents, you cannot tell who did what. Revocation means taking down every agent at once.
- **Breach scope scales with shared credentials.** One compromised `agent_pool_prod` token = full blast radius across every system it touches. Individual credentials per agent = containment.
- **Gartner projects 25% of enterprise breaches by 2028 will trace to AI agent abuse** — the same vector this entry defends against.

## The move

NHI governance gives every agent a first-class, auditable identity with four dimensions: **who** (principal), **why** (intent), **how** (provenance), and **when** (session). Each dimension is enforced by a separate control plane layer.

### 1. Issue per-agent credentials — never shared

```python
# Each agent gets its own scoped credential at startup
# NOT: one shared agent_pool_prod credential for all agents

def provision_agent_credential(agent_id: str, capabilities: list[str]) -> dict:
    """Issue a unique, scoped credential per agent session.
    Revocation targets one agent — not the entire fleet.
    """
    credential = {
        "agent_id": agent_id,          # unique per agent instance
        "capabilities": capabilities,   # least-privilege capability set
        "issued_at": now(),
        "expires_at": now() + timedelta(hours=8),  # short-lived
        "parent_principal": os.environ["HUMAN_INITIATOR_ID"],  # chain of trust
        "provenance": {
            "task_type": os.environ.get("AGENT_TASK_TYPE"),
            "data_sensitivity": os.environ.get("DATA_SENSITIVITY_LEVEL"),
        },
    }
    # Sign with per-agent key — not shared fleet key
    signed = agent_ca.sign(agent_id, credential, key_per_agent[agent_id])
    return signed
```

### 2. Enforce authorization with OPA/Rego — not prompt-level restrictions

Prompt instructions ("only read, don't delete") are not security boundaries. Context compression drops them. Adversarial prompts bypass them. Enforce at infrastructure level:

```rego
# policy/agent_authz.rego — evaluated at every tool call via OPA sidecar
package agent.authz

default allow := false

# Allow read operations on customer_data for agents with read_data capability
allow if {
    input.action == "read"
    input.resource_type == "customer_data"
    "read_data" in input.agent_capabilities
}

# Allow write only if: task is approved AND data_sensitivity is low
allow if {
    input.action == "write"
    "write_data" in input.agent_capabilities
    input.provenance.data_sensitivity != "high"
    input.provenance.task_type in ["customer_support", "data_correction"]
}

# Deny delete on any resource — agents delete only via human approval workflow
deny_delete if {
    input.action == "delete"
}
```

### 3. Session-scoped capability elevation — time-boxed escalation

```python
# agent_capability_manager.py
class AgentCapabilityManager:
    """
    Agent gets base permissions at spawn.
    Elevation is requested, approved, time-boxed, and auto-revoked.
    """

    def request_elevation(self, agent_id: str, capability: str, duration_minutes: int):
        """Agent requests a capability it doesn't hold."""
        assert duration_minutes <= 30, "Elevation capped at 30 minutes"
        # Route to human approval for high-sensitivity capabilities
        if capability in ["delete_data", "send_email", "financial_transaction"]:
            approval = self.human_approval_queue.submit(
                agent_id=agent_id,
                requested_capability=capability,
                duration_minutes=duration_minutes,
                task_context=self.current_task_description,
            )
            return approval  # blocks until human approves

        # Low-sensitivity capabilities auto-approved with audit log
        return self.grant_with_audit(agent_id, capability, duration_minutes)

    def revoke_all(self, agent_id: str):
        """Kill switch: revoke every credential for this agent instance."""
        self.credential_store.revoke_by_agent_id(agent_id)
        self.audit_log.log("AGENT_REVOKED", agent_id=agent_id, reason="manual_kill")
```

### 4. Audit trail with four identity dimensions

Every action logged with all four dimensions — not just "which API key":

```
timestamp=2026-07-01T09:14:22Z
principal=agent.review_summary.v3a8f   # which agent instance
intent=generate_customer_summary      # what it was asked to do
provenance={task_type: customer_report, data_sensitivity: medium, parent: user:jane_doe}
session_id=ses_8a3f2b1c
action=read
resource=customer_data.orders.2026-Q2
outcome=allowed
```

### 5. Vendor landscape — pick the control plane layer

| Vendor | Layer | Best for |
|--------|-------|----------|
| **Aembit** | Agent-to-workload identity | Ephemeral credential issuance per agent |
| **CyberArk** | Privileged access for agents | Agents accessing secrets vaults |
| **Saviynt** | Identity governance & compliance | SOC2/ISO27001 audit trails |
| **Entro** | Secrets & credential management | Per-agent secret rotation |
| **Strata** | Identity orchestration | Multi-cloud agent identity federation |
| **AppViewX** | Agent certificate lifecycle | Agent-to-service mTLS certificates |

If you are building in-house: OPA for policy enforcement + a per-agent Vault PKI backend covers 80% of the threat model at open-source cost.

### 6. 90-day implementation roadmap

- **Days 1-30:** Audit current agent credential assignments. Find every shared service account. Map every tool the agent can call to a capability.
- **Days 31-60:** Deploy per-agent credential issuance. Instrument every agent action with the four identity dimensions. Set up OPA sidecar on agent runtime.
- **Days 61-90:** Implement session-scoped elevation with human approval for high-sensitivity actions. Build revocation kill switch. Run tabletop exercise: "revoke agent X in under 60 seconds."

## Receipt

> Receipt pending — 2026-07-01

## See also

- [F-10 · Agent Identity and Access](f10-agent-identity-and-access.md) — foundational IAM for agents
- [S-217 · Agent Capability Authorization](stacks/s217-agent-capability-authorization.md) — permission scoping in infrastructure
- [S-282 · Agent Guardrails](stacks/s282-agent-guardrails.md) — runtime safety enforcement
