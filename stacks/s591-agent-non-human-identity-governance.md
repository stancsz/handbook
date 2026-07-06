# S-591 · Agent Non-Human Identity Governance

Traditional IAM was designed for humans: a person joins, gets a role, does work, leaves, and the account is deprovisioned. AI agents break every assumption in that lifecycle. An agent spawns silently, inherits credentials from a human it replaced, calls tools it was never explicitly granted access to, and operates 24/7 with no manager, no departure date, and no audit trail that maps actions to a principal. Non-Human Identity (NHI) governance treats the agent itself as a first-class security principal — with its own lifecycle, capability scope, and revocation path.

## Forces

- **NHIs outnumber human identities 45:1** in most enterprise environments; AI agents are the fastest-growing category. Guild.ai reports 56% YoY growth in NHI-to-human ratios. 78% of organizations have zero formal AI identity policies even as agents carry full-admin credentials to production systems.
- **Agents inherit human credentials by default.** The fastest path to "agent can access the tools it needs" is to give it a service account or API key with broad permissions. This makes every agent an over-privileged principal by construction.
- **Credential sprawl compounds across delegation chains.** When Agent Alpha delegates to Agent Beta over A2A, Alpha passes its credentials to Beta. One compromised agent becomes a pivot point for credential exfiltration across the entire agentic mesh.
- **Traditional RBAC maps poorly.** A "role" describes what a human job category does. An agent's capabilities are granular and task-specific. The org-admin role and the invoice-processor agent role need entirely different permission models.
- **OWASP ASI03 (Identity and Privilege Abuse)** is the #3 risk for agentic applications. MCP's open tool registry amplifies this: an agent discovering one of 40 MCP tools implicitly has access to all 40 until you enforce endpoint-level allowlists.
- **EU AI Act enforcement activates August 2, 2026.** High-risk AI systems — including agents that make consequential decisions — require documented accountability chains. A decision made by an agent using an inherited credential fails this requirement by default.

## The move

**1. Declare agents as first-class principals — not as humans in disguise.**

Every agent gets its own identity with explicit scope. The agent's credentials are not shared with the human it assists. Credentials are scoped to the minimum set of endpoints the agent needs for its defined task, not the maximum the human role allowed.

```python
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta

class NHIStatus(Enum):
    PROVISIONED = "provisioned"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DECOMMISSIONED = "decommissioned"

@dataclass
class AgentIdentity:
    nhi_id: str                    # e.g., "nhi-4f8a3c1e"
    name: str                      # e.g., "invoice-processor-prod-v2"
    agent_type: str                # e.g., "MCP", "A2A", "CLI"
    purpose: str                   # business justification (EU AI Act audit req.)
    status: NHIStatus = NHIStatus.PROVISIONED
    granted_by: str = ""          # human approver
    granted_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    capability_scope: list[str] = field(default_factory=list)
    max_token_budget_usd: float = 0.0
    max_tool_calls_per_hour: int = 0
    allowed_endpoints: list[str] = field(default_factory=list)

    def is_active(self) -> bool:
        if self.status != NHIStatus.ACTIVE:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True
```

**2. Broker credentials at the infrastructure layer — not in context.**

Instead of embedding long-lived API keys in the agent's system prompt, use short-lived, scope-limited tokens issued by a credential broker. The broker enforces per-endpoint allowlists, rate limits, and time-to-live on every call.

```python
class CredentialBroker:
    def issue_token(
        self,
        nhi: AgentIdentity,
        requested_scopes: list[str],
        ttl_seconds: int = 3600,
    ) -> str | None:
        # Enforce least-privilege: intersection of agent's declared
        # scope and the specific endpoints this invocation needs
        allowed = set(nhi.capability_scope)
        requested = set(requested_scopes)
        granted = allowed & requested

        if not granted:
            return None  # denied — does not exist in agent's declared scope

        token = self._mint_token(
            nhi_id=nhi.nhi_id,
            scopes=list(granted),
            endpoints=nhi.allowed_endpoints,
            ttl_seconds=min(ttl_seconds, 3600),  # hard cap: 1 hour max
            max_budget_usd=nhi.max_token_budget_usd,
        )
        self._audit_log(nhi=nhi, granted=list(granted), purpose="token_issue")
        return token

    def revoke_all(self, nhi_id: str) -> None:
        """Full revocation: used on agent failure, compromise, or task completion."""
        for token in self._tokens_by_nhi(nhi_id):
            self._revoke(token)
        self._audit_log(nhi_id=nhi_id, event="full_revocation")
```

**3. Bind credentials to task scope — time-limited, endpoint-gated, budget-capped.**

Credentials expire automatically. The agent's identity does not survive task completion.

```python
# On task initiation
nhi = identity_registry.get_by_name("invoice-processor-prod-v2")
if not nhi.is_active():
    raise PermissionError(f"NHI {nhi.nhi_id} not active")

token = broker.issue_token(
    nhi,
    requested_scopes=["erp:read:invoice", "db:write:invoice_status"],
    ttl_seconds=600,  # 10-minute window for one invoice task
)
if not token:
    raise PermissionError("Requested scopes exceed agent's declared capability")
```

**4. Map A2A delegation chains to the credential scope.**

When an agent delegates to another agent over A2A, the delegation chain must carry the NHI context — not just the parent's credentials. Downstream agents inherit only the intersection of their own declared scope and the delegation context's authorized scopes.

```python
def delegate_task(agent_nhi: AgentIdentity, target_agent: str, task_scope: list[str]):
    # The delegation token is the intersection of what the delegator
    # is authorized to pass and what the target is authorized to receive
    delegator_scopes = set(agent_nhi.capability_scope)
    requested = set(task_scope)
    delegatable = delegator_scopes & requested

    a2a_message = {
        "task": task_scope,
        "delegation_chain": agent_nhi.nhi_id,
        "effective_scopes": list(delegatable),
        "token": broker.issue_token(agent_nhi, list(delegatable), ttl_seconds=300),
    }
    send_a2a_message(target_agent, a2a_message)
```

**5. Audit every action to the NHI — not just to the human.**

Each log entry must include `nhi_id`, `effective_scopes_used`, `decision_reason`, and `delegation_chain`. This is the accountability chain EU AI Act Article 12 requires for high-risk AI systems.

```python
# Every tool call is logged with NHI context
def audited_tool_call(nhi: AgentIdentity, tool: str, args: dict):
    if tool not in nhi.capability_scope:
        raise PermissionError(f"{tool} not in NHI scope")
    if not broker.check_budget(nhi.nhi_id):
        raise BudgetExceededError(f"NHI {nhi.nhi_id} budget exhausted")
    result = tool_registry.invoke(tool, args)
    audit_logger.log(
        nhi_id=nhi.nhi_id,
        tool=tool,
        args_hash=hash_args(args),
        delegation_chain=nhi.nhi_id,  # extend for A2A chains
        reason="task_execution",
    )
    return result
```

## Receipt
> Verified 2026-07-05 — Architecture validated against OWASP ASI Top 10 (ASI03), Zylos Research IGA patterns, and Guild.ai NHI report. Credential broker pattern confirmed against Aembit/Entra NHI vendor documentation. EU AI Act Article 12 mapping verified against Zylos governance research (2026-05-01). IAM-to-NHI gap statistics (45:1 ratio, 78% no policy) sourced from iEnable enterprise guide (March 2026) and corroborated by Exogram SOC 2 Trust Ledgers documentation.

## See also
- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — the interception layer between proposed and executed tool calls
- [S-266 · Inter-Agent Trust Delegation](s266-inter-agent-trust-delegation.md) — A2A delegation without a native trust model; this entry fills the credential side
- [S-238 · Deterministic Guardrails Outside the LLM Loop](s238-deterministic-guardrails-outside-the-llm-loop.md) — enforcing safety outside the model's intent layer
- [S-532 · The Six Agent SLOs](s532-the-six-agent-slos.md) — SLO framework that should include NHI uptime and credential expiry rates
