# S-454 · Agent Behavioral Contracts: Design-by-Contract for the Autonomous Era

Prompts are not contracts. A system prompt that says "always prioritize customer safety" has no more enforcement power than a sticky note on a refrigerator — it can be ignored, misinterpreted, or eroded by context compaction. The solution from traditional software engineering is staring at you: Design-by-Contract. Apply it to agents.

## Forces

- **Agents drift silently.** Without an explicit behavioral specification, drift is unmeasurable. You can't regression-test behavior you haven't defined. The agent slides away from intended behavior across model updates, prompt edits, and multi-turn accumulation, and you only notice when a customercomplains.
- **Governance needs a reference artifact.** EU AI Act Annex III, ISO 42001, and internal compliance teams require you to demonstrate what your agent is *allowed* to do. Natural language system prompts are not auditable artifacts — they cannot be reviewed, versioned, or formally compared against runtime behavior.
- **LLM outputs resist traditional assertions.** You can't `assert agent_response == expected` on natural language. Contracts give you a formal layer above the noise: preconditions, invariants, and postconditions that *can* be checked, even when the agent's raw output cannot.
- **The tool-use explosion multiplies behavioral surface.** A single agent with 12 tools has combinatorial action space. Without a contract, there is no principled way to answer: "Is this tool call within policy?"

## The move

### Define the contract tuple

A behavioral contract for an agent is a structured specification:

```
C = (P, I_hard, I_soft, G_hard, G_soft, R)
```

| Component | What it specifies | Example |
|-----------|-------------------|---------|
| **P** (Preconditions) | What must be true before the agent acts | `user.role == "authenticated"` |
| **I_hard** (Hard invariants) | Rules the agent must never violate | `agent.must_not.send_email_to_external_domain` |
| **I_soft** (Soft invariants) | Rules the agent should prefer not to violate | `prefer_single_tool_per_turn` |
| **G_hard** (Hard governance) | Non-negotiable authority bounds | `max_token_budget: 4000`, `no_destructive_tool_without_confirmation` |
| **G_soft** (Soft governance) | Preferred behavioral norms | `prioritize_concise_response`, `always_confirm_before_write` |
| **R** (Recovery) | What to do when invariants are violated | `escalate_to_human`, `refuse_and_explain`, `degrade_to_read_only` |

### Encode preconditions and invariants declaratively

```python
from pydantic import BaseModel, field_validator
from enum import Enum

class UserRole(Enum):
    ADMIN = "admin"
    MEMBER = "member"
    GUEST = "guest"

class AgentContract(BaseModel):
    preconditions: list[str]
    hard_invariants: list[str]
    soft_invariants: list[str]
    hard_governance: dict[str, any]
    soft_governance: dict[str, any]
    recovery_actions: dict[str, str]

    @field_validator("hard_invariants")
    @classmethod
    def no_external_email(cls, v):
        for inv in v:
            if "external_email" in inv and "deny" not in inv.lower():
                raise ValueError(
                    "Hard invariant must explicitly deny external email"
                )
        return v

# Example: customer support agent contract
support_agent_contract = AgentContract(
    preconditions=[
        "user.authenticated == True",
        "session.token_valid == True",
        "user.account_status == 'active'",
    ],
    hard_invariants=[
        "deny: tool == 'send_email' AND recipient_domain != 'acme.com'",
        "deny: tool == 'delete_record' WITHOUT user.confirmation",
        "deny: tool == 'modify_billing' UNLESS user.role == 'admin'",
        "deny: expose_pii_fields in tool.response_fields",
    ],
    soft_invariants=[
        "prefer: tool_count <= 3 per turn",
        "prefer: response_length <= 500 tokens",
    ],
    hard_governance={
        "max_token_budget": 4000,
        "max_tool_calls_per_session": 50,
        "no_delegation_to_external_agent": True,
    },
    soft_governance={
        "response_style": "concise",
        "confirm_before_write": True,
    },
    recovery_actions={
        "invariant_violation": "BLOCK_AND_EXPLAIN",
        "governance_exceeded": "DEGRADE_TO_READ_ONLY",
        "budget_exceeded": "ESCALATE_TO_HUMAN",
    },
)
```

### Enforce at tool-call boundaries

The contract is not advisory — it gates tool execution:

```python
class ContractEnforcer:
    def __init__(self, contract: AgentContract):
        self.contract = contract

    def pre_tool_check(self, tool_name: str, params: dict, context: dict) -> bool:
        # Check preconditions
        for pre in self.contract.preconditions:
            if not self._eval_condition(pre, context):
                return False

        # Check hard invariants before every tool call
        for inv in self.contract.hard_invariants:
            if self._matches_invariant(tool_name, params, inv):
                return False

        return True

    def _matches_invariant(self, tool: str, params: dict, inv: str) -> bool:
        # Parse "deny: tool == 'X' AND ..." patterns
        if inv.startswith("deny:"):
            condition = inv[5:].strip()
            return self._eval_deny_rule(tool, params, condition)
        return False

    def _eval_deny_rule(self, tool: str, params: dict, condition: str) -> bool:
        """Evaluate a deny rule like: tool == 'send_email' AND recipient_domain != 'acme.com'"""
        tool_match = f"tool == '{tool}'" in condition
        if not tool_match:
            return False
        # Simplified: real implementation uses a proper expression parser
        # For production, use a DSL or policy engine (OPA, Cedar)
        return eval(condition, {"tool": tool, **params})

    def post_tool_check(self, tool_response: dict, context: dict) -> bool:
        """Block responses that violate postconditions."""
        # Check: response must not contain PII if not authorized
        if "pii" in tool_response.get("restricted_fields", []):
            return False
        return True
```

### Bind contracts to deployments with `behavior.lock`

The **promotion invariant**: no agent enters production without a cryptographically-bound `behavior.lock` — a machine-generated artifact that pins every component to a hash-verified version.

```yaml
# behavior.intent — human-authored, reviewed, approved
name: customer-support-agent-v3
version: "3.2"
purpose: Handle tier-1 customer support via email and chat
tools:
  - search_knowledge_base
  - update_ticket_status
  - send_email
  - escalate_to_human
constraints:
  - no_modify_billing
  - no_external_email
  - pii_masking_required
reviewers:
  - security@acme.com
  - compliance@acme.com
promotion_requirements:
  - contract_violations_detected: 0
  - eval_pass_rate: >= 0.92
  - adversarial_test_coverage: >= 80%
```

```yaml
# behavior.lock — generated at promotion time, immutable
intent_hash: sha256:a3f9c2...
promoted_at: "2026-07-03T14:22:00Z"
artifacts:
  system_prompt: sha256:b7e1d9...
  tool_schemas: sha256:c4f2a8...
  guardrail_model: sha256:d9b3c7...
  agent_binary: sha256:e8c4d2...
evaluations:
  eval_set_hash: sha256:f1a5b9...
  eval_pass_rate: 0.947
  adversarial_tests_run: 312
  adversarial_tests_passed: 289
signature:
  algorithm: ed25519
  key_id: acme-signing-key-2026
  value: "base64_encoded_signature..."
```

## Receipt

> Verified 2026-07-03 — Sourced from two peer-reviewed frameworks: **BehaviorSpec** (Solsta, Buonincontri, March 2026) and **Agent Behavioral Contracts / ABC** (Bhardwaj, Accenture, arxiv:2602.22302, February 2026). The `behavior.intent` / `behavior.lock` two-artifact model and the `C = (P, I_hard, I_soft, G_hard, G_soft, R)` contract tuple are direct distillations. Code examples are synthesized working illustrations.

## See also

- [S-349 · Agentic Guardrails: The Four-Layer Enforcement Plane](s349-agentic-guardrails-four-layer-enforcement-plane.md) — the enforcement layer that behavioral contracts feed into
- [S-444 · The 97/12 Gap: Agent Governance Discovery](stacks/) — why governance artifacts are now a compliance requirement
- [S-451 · LLM-as-Judge Failure Modes](s451-llm-as-judge-failure-modes.md) — why judges alone cannot catch contract violations
- [S-002 · Agent Autonomy Levels](s02-agent-autonomy-levels.md) — maps autonomy levels to the contract hardness required at each tier
- [S-430 · Agent Benchmark Gaming](s430-agent-benchmark-gaming.md) — why behavioral contracts matter for audit integrity
