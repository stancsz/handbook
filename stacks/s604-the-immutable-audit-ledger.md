# S-604 · The Immutable Audit Ledger

Your agent emailed a client at 02:14 UTC, forwarded sensitive data to an external domain, and modified a financial record. When the auditor asks what happened, you have a chat log. The GDPR requires you to prove which policy authorized each action, which user triggered it, and what data it accessed. A conversation transcript does not satisfy Article 22 — it proves nothing about the actual decision logic or the data it acted on. The Immutable Audit Ledger is the architectural pattern that does: an append-only, tamper-evident record of every agent decision, tool invocation, policy reference, and data access, chain-linked for integrity and queryable for compliance.

## Forces

- **Agents make consequential actions; transcripts don't prove authorization.** A chat log shows what the agent did in natural language — not which policy authorized it, which user's identity triggered it, or what data it accessed. GDPR Article 22 and the EU AI Act Article 12 require demonstrating the logic and authorization of every automated consequential decision. Conversational logs fail this requirement structurally.
- **Logs can be retroactively edited — and auditors know it.** Once a system has mutable logs, you cannot prove a log entry was not modified after the fact. GDPR fines reach €15M or 3% of global turnover; California ADMT regulations require five-year risk assessment retention. A mutable log is not a legal defense.
- **Agent reasoning is probabilistic; the audit must be deterministic.** The agent may produce different outputs on replay due to model nondeterminism. The audit trail must record what the agent *decided*, not what a replay would produce. These are different artifacts.
- **Cross-agent workflows multiply the accountability problem.** When Agent A calls Agent B, which calls a tool, the chain of responsibility spans three identities, two policy scopes, and one set of credentials. Each agent in the chain needs its own linked entry — and the links must be auditable across boundaries.

## The Move

### The Three Immutable Record Types

Every agent action generates three linked entries in the ledger:

```
Entry 1 — Decision Record (what the agent decided and why)
  - session_id, agent_id, user_principal
  - policy_ref: "POL-2024-Q4::external-email-deny"
  - reasoning_summary: LLM-extracted rationale (not full transcript)
  - tool_calls_planned: [list of planned invocations]
  - data_accessed: [entity types + data sensitivity tier]
  - timestamp, entry_hash

Entry 2 — Tool Invocation Record (what actually happened)
  - invocation_id (links to decision record)
  - tool_name, tool_version
  - input_params (parameterized, no secrets)
  - execution_status: success | failure | blocked
  - actual_data_accessed: [full entity IDs if different from planned]
  - response_hash (hash of tool response)

Entry 3 — Outcome Delivery Record (what the user received)
  - invocation_id (links to invocation record)
  - delivery_channel: email | slack | webhook | dashboard
  - delivery_status: delivered | failed | skipped
  - recipient_identity
```

### Chain Linking with SHA-256

Each entry carries the hash of the previous entry, forming a tamper-evident chain:

```python
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone

class AuditLedgerEntry:
    def __init__(self, entry_type: str, payload: dict, prev_hash: str = "GENESIS"):
        self.entry_type = entry_type
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.prev_hash = prev_hash
        self.payload = payload
        self.entry_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        data = {
            "entry_type": self.entry_type,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "payload": self.payload,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)


class ImmutableAuditLedger:
    def __init__(self, storage_backend):
        # storage_backend: any append-only store (S3 with Object Lock,
        # PostgreSQL with append-only trigger, Kafka with retention=forever,
        # or a dedicated append-only DB like FoundationDB)
        self.storage = storage_backend
        self._tip_hash = self._load_tip_hash()

    def append(self, entry: AuditLedgerEntry) -> str:
        if not self.storage.is_append_only():
            raise PermissionError("Ledger storage must be append-only")
        # Tag entry with current chain tip
        entry.prev_hash = self._tip_hash
        entry.entry_hash = entry._compute_hash()
        self.storage.write(entry.to_dict())
        self._tip_hash = entry.entry_hash
        return entry.entry_hash

    def verify_chain(self) -> bool:
        """Re-verify the entire chain integrity. O(n) scan."""
        entries = self.storage.read_all()
        prev = "GENESIS"
        for e in entries:
            if e["prev_hash"] != prev:
                return False
            recomputed = AuditLedgerEntry(e["entry_type"], e["payload"], e["prev_hash"])
            if recomputed.entry_hash != e["entry_hash"]:
                return False
            prev = e["entry_hash"]
        return True

    def query_by_session(self, session_id: str) -> list[dict]:
        return self.storage.read_filtered(entry_type="decision", session_id=session_id)
```

### Embedding Policy References at Invocation Time

The ledger is not just a log — it is a policy-enforced record. Each decision entry must reference the authorizing policy by its canonical identifier at write time, not retrospectively:

```python
# Before the agent calls a tool, the orchestrator writes the decision record
# This is synchronous and blocks the tool call until written
policy = policy_registry.resolve(
    principal=agent_principal,
    action=tool_name,
    data_sensitivity=data_tier,
)
if not policy:
    raise PolicyBlockError(f"No policy for {agent_principal} → {tool_name}")

decision_entry = AuditLedgerEntry(
    entry_type="decision",
    payload={
        "session_id": session.id,
        "agent_id": agent.id,
        "user_principal": agent.principal,
        "policy_ref": policy.policy_id,          # e.g. "POL-2024-Q4::external-email-deny"
        "policy_version": policy.version,
        "reasoning_summary": agent.last_reasoning_summary,
        "tool_calls_planned": [tool_name],
        "data_accessed": [entity_type],
    },
    prev_hash=ledger.tip_hash(),
)
entry_hash = ledger.append(decision_entry)
```

### Storage Backend Requirements

The ledger's integrity depends entirely on the storage backend's append-only guarantee:

| Backend | Guarantee | Compliance |
|---------|-----------|------------|
| S3 + Object Lock (WORM) | Cryptographic immutability | SEC 17a-4, FINRA |
| PostgreSQL + append-only trigger | DB-level | GDPR (if WAL is immutable) |
| Kafka with infinite retention | Log-level | General compliance |
| FoundationDB | Protocol-level immutability | Enterprise |

Never store the audit ledger on a filesystem that supports `rm` or `chmod` — the moment deletion is possible, the chain is not tamper-evident.

## Receipt

> Verified 2026-07-05 — Production pattern confirmed across three regulated-industry deployments. The chain-linking approach (SHA-256 per entry) is a standard cryptographic technique; the novel element is the three-entry-per-action structure (decision/invocation/outcome) that maps cleanly to EU AI Act Art.12 and GDPR Art.22 requirements. S3 Object Lock + Lambda verification is the most common enterprise implementation (Kontext Security, 2026; Inferensys, 2026). Key insight: the ledger must be written *synchronously before* the action executes — a post-hoc log is not audit-grade because the agent may report differently than what happened. Key tradeoff: storing parameterized inputs (not full prompts) avoids logging secrets while preserving the audit record. Policy reference at invocation time is non-negotiable for GDPR Art.22 defensibility.

## See also

- [S-355 · Agent Autonomy Levels (Bounded Autonomy)](s355-agent-autonomy-levels-bounded-autonomy.md) — the autonomy levels that determine which actions need audit records
- [S-313 · Agent Credential Lifecycle Security](s313-agent-credential-lifecycle-security.md) — the credential layer the ledger traces
- [S-500 · Action Hallucination Detection](s500-action-hallucination-detection.md) — the verification that the tool invocation record catches phantom completions
- [S-106 · Event Log Replay](s106-event-log-replay.md) — the debugging use case that motivated structured logging in the first place
