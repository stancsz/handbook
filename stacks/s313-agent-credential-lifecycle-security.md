# S-313 · Agent Credential Lifecycle Security

You deployed the agent. It has credentials. Nobody knows which ones, when they rotate, or what happens to a running task when you revoke them. The agent is now a persistent identity with delegated access to your CRM, your database, your email — and your security team has no audit trail, no rotation policy, and no kill switch. Agent credential lifecycle security is the engineering discipline that closes this gap: managing the entire existence of an agent's identity, from issuance through rotation to revocation, as a first-class operational concern.

## Forces

- **Agents are persistent identities, not one-off API calls.** A human logs in, works, logs out. An agent runs continuously, chaining actions across sessions, spawning sub-agents, and inheriting credentials from its parent. Legacy session management assumes humans; agents need a fundamentally different lifecycle model.
- **Credential sprawl is silent.** A single production agent touches 8–15 systems (Menlo Ventures, 2025). Each connection may carry its own API key, OAuth token, or service account. Most teams don't have an inventory — they discover the sprawl only after an incident.
- **Revocation mid-task is catastrophic without a checkpoint model.** Killing an agent's credentials while it holds a half-written database transaction leaves systems in an inconsistent state. Safe revocation requires idempotency and transaction semantics, not just a credential delete.
- **Sub-agent delegation breaks human-designed trust chains.** When Agent A spawns Agent B with a subset of its permissions, the credential A received was issued for A — not for B. Most systems have no mechanism to scope, attenuate, or track credentials across a delegation tree.
- **Compliance demands auditability across the full chain of agent actions.** SOC 2, ISO 27001, and GDPR all require knowing who accessed what, when. An agent acting as a user makes this impossible without explicit action-to-identity mapping at the infrastructure level.

## The move

### 1. Inventory before you secure

Before any credential lifecycle policy, know what the agent touches:

```python
# Discover all credential dependencies from the agent's tool definitions
def audit_agent_credentials(agent_config: dict) -> dict[str, CredentialMeta]:
    """
    Extract all external system credentials from an agent's tool definitions.
    Run this at startup and on every tool definition change.
    """
    discovered = {}
    for tool in agent_config["tools"]:
        for key, cred in tool.get("credentials", {}).items():
            discovered[key] = CredentialMeta(
                resource=cred["resource"],
                type=cred["type"],  # api_key | oauth | jwt | service_account
                scope=cred["scopes"],
                issued_to=agent_config["agent_id"],
                rotation_policy=cred.get("rotation_days", 90),
                last_rotated=cred.get("last_rotated"),
                risk_level="high" if cred["type"] == "api_key" else "medium",
            )
    return discovered
```

This is not a one-time exercise. Any tool addition triggers a re-audit.

### 2. Scope credentials to session, not identity

Issue credentials per session, not per agent identity. A session-scoped credential:

```python
@dataclass
class SessionScopedCredential:
    credential: Any                    # The actual API key or token
    session_id: str                     # Tied to this session
    parent_identity: str                # The agent identity that received it
    issued_at: datetime
    expires_at: datetime
    allowed_tools: list[str]            # Scoped to specific tools only
    max_uses: int | None = None        # Use cap (for expensive/critical APIs)
    uses_consumed: int = 0

class SessionCredentialManager:
    def issue_for_session(
        self,
        agent_id: str,
        session_id: str,
        required_scopes: list[str],
        ttl: timedelta = timedelta(hours=2),
    ) -> SessionScopedCredential:
        # 1. Look up the base credential (stored in vault)
        base = self.vault.get_agent_base_credential(agent_id)
        # 2. Mint a session-scoped derivative
        session_cred = self._mint_session_token(
            base,
            session_id=session_id,
            restrictions={
                "tools": required_scopes,
                "max_uses": self._derive_max_uses(required_scopes),
                "valid_from": datetime.utcnow(),
                "valid_until": datetime.utcnow() + ttl,
            },
        )
        return SessionScopedCredential(
            credential=session_cred,
            session_id=session_id,
            parent_identity=agent_id,
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + ttl,
            allowed_tools=required_scopes,
            max_uses=self._derive_max_uses(required_scopes),
        )
```

Key properties: the session credential carries the agent identity AND the session ID. Log it at every use. If the agent is revoked, only session credentials need rotation — not the base vault credential.

### 3. Build a revocation-safe task model

Every agent action must be idempotent. This is the prerequisite for safe revocation:

```python
class RevocableTask:
    """
    Wrap every agent task in a checkpoint model.
    On revocation, the agent can resume from the last checkpoint,
    not from the beginning.
    """
    def __init__(self, task_id: str, agent_id: str):
        self.task_id = task_id
        self.agent_id = agent_id
        self.checkpoints: list[Checkpoint] = []
        self.completed = False

    def checkpoint(self, state: dict, description: str):
        self.checkpoints.append(Checkpoint(
            task_id=self.task_id,
            sequence=len(self.checkpoints),
            state_hash=self._hash(state),   # Detect tampering or drift
            description=description,
            timestamp=datetime.utcnow(),
            agent_id=self.agent_id,
        ))

    def revoke(self):
        """Called when credentials are revoked. Returns last safe checkpoint."""
        # 1. Stop new actions immediately
        self.completed = True
        # 2. Return last checkpoint for recovery
        if self.checkpoints:
            return self.checkpoints[-1]
        return None
```

The critical property: revocation triggers `checkpoint()`, not a hard stop. The next recovery run starts from the last durable state, not from scratch.

### 4. Implement the kill switch as a layered response

A kill switch is not one button — it is a stack of escalating responses:

```
Level 1 — Suspend: Pause this session's credential (other sessions unaffected)
Level 2 — Revoke session: Invalidate all session credentials for this agent identity
Level 3 — Revoke base: Rotate the vault credential (requires re-issuance for all sessions)
Level 4 — Quarantine: Block the agent process entirely, preserve state for forensics
```

```bash
# Revoke at each level
agent-cli credential revoke --session-id=ses_abc123 --level=session
agent-cli credential revoke --agent-id=agent_xyz --level=agent
agent-cli credential revoke --agent-id=agent_xyz --level=base --vault=prod
agent-cli agent quarantine --agent-id=agent_xyz --preserve-state=true
```

Level 1–2 are recoverable. Level 3 causes task interruption but the base credential is the source of truth. Level 4 is forensic.

### 5. Audit trail across the full chain

Every agent action gets logged with enough context to reconstruct the decision chain:

```python
def audit_log(
    action: str,
    agent_id: str,
    session_id: str,
    tool_name: str,
    resource_accessed: str,
    credential_used: str,        # Session credential ID, not the secret itself
    input_hash: str,             # Hash of the input, not the content
    output_status: str,
    duration_ms: int,
):
    logger.structured(
        "agent_action",
        agent_id=agent_id,
        session_id=session_id,
        tool=tool_name,
        resource=resource_accessed,
        session_cred_id=credential_used,
        parent_cred_id=resolve_base_credential(credential_used),
        input_hash=input_hash,
        output=output_status,
        latency_ms=duration_ms,
        timestamp=datetime.utcnow().isoformat(),
    )
```

The session credential ID in the log lets you trace backward: which agent → which session → which base credential → which vault entry. This is what compliance auditors actually need.

## Receipt

> Receipt pending — July 1, 2026

## See also

- [F-186 · AI Agent NHI Governance](forward-deployed/f186-ai-agent-nhi-identity-governance.md) — policy-level NHI management; this entry covers the implementation mechanics
- [S-217 · Agent Capability Authorization](stacks/s217-agent-capability-authorization.md) — permission scoping per tool; this entry covers the credential infrastructure that enforces those permissions
- [S-204 · Agent Circuit Breaker](stacks/s204-agent-circuit-breaker.md) — the runtime protection pattern that pairs with revocation for fault isolation
