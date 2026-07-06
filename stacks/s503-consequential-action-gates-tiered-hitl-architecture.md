# S-503 · Consequential Action Gates: Tiered HITL Architecture for Production Agents

The agent drafts the email. Sends the Slack message. Files the support ticket. Posts the update. All autonomous. All fine. Then it drafts the contract amendment, sends it to the customer, and CCs legal — without anyone reviewing it. Nobody noticed until the customer signed.

The pattern is always the same: the team gated the obviously dangerous actions but left a gap between "read-only" and "clearly destructive." The consequential middle — actions that create external obligations, trigger downstream systems, or establish binding commitments — executed without human in the loop. This entry is about closing that gap with a tiered architecture that routes every agent action through a risk-stratified enforcement surface before it executes.

## Forces

- **Consequential is not the same as irreversible.** Sending a Slack message to an internal channel is reversible (delete it); sending a pricing proposal to a customer is consequential (creates an expectation). Teams confuse the two and gate by reversibility when they should gate by consequence.
- **Autonomy levels and action tiers are orthogonal.** [S-355](../stacks/s355-agent-autonomy-levels-bounded-autonomy.md) defines how much autonomy an agent has (L0–L5). This entry defines how much consequence each action type carries — a Tier-3 action should require approval regardless of whether the agent is L2 or L4.
- **EU AI Act Article 14 (effective 2026-08-02)** mandates human oversight for high-risk AI systems. Penalties: up to €40M or 7% of global turnover. The obligation is not "have a policy" — it is "demonstrate a verifiable technical control that routed this action appropriately."
- **Confirmation fatigue kills HITL programs.** Gating every agent action through human review produces alert fatigue and bypass workflows. The solution is not less human oversight — it is more selective routing: only the actions that actually need review.
- **Confidence scores are not sufficient gates.** A model that rates itself 94% confident on a wrong classification still needs a human reviewer. Confidence gates work for T3 (staging queue on low confidence); they do not work for T4 (irreversible actions always need a human).

## The move

**Four-tier action classification with differentiated enforcement paths.**

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Loop                                                 │
│  ┌─────────────┐    ┌───────────────────────────────────┐  │
│  │ Tool Call   │───▶│  Action Gate Evaluator             │  │
│  │ Proposed    │    │  (classifies before execution)      │  │
│  └─────────────┘    └──────────┬────────────────────────┘  │
│                                 │                            │
│         ┌───────────┬──────────┼───────────┬───────────┐   │
│         ▼           ▼          ▼           ▼           │   │
│      ┌─────┐   ┌───────┐  ┌────────┐  ┌──────────┐     │   │
│      │T1   │   │  T2   │  │  T3    │  │    T4    │     │   │
│      │Read │   │Internal│  │External│  │Irrevers- │     │   │
│      │Only │   │Revers- │  │/Third- │  │  ible    │     │   │
│      │     │   │  ible  │  │ Party  │  │          │     │   │
│      └─▶   │   │  │     │  │  │     │  │   │      │     │   │
│  autonomous│   │log│     │  │queue │  │  human   │     │   │
│  + log     │   │undo│    │  │review│  │ approval │     │   │
│            │   │stack    │  │gate  │  │required  │     │   │
│            │   │         │  │      │  │          │     │   │
└────────────┴───┴─────────┴──┴──────┴──┴──────────┴─────┘   │
```

### Tier 1 — Read-Only / Informational

**Enforcement:** Execute autonomously. Log with full context.

Actions: queries, retrievals, lookups, analysis, data synthesis, report generation.

Gate condition: none — these have no external side effects. Logging is still mandatory for audit trails.

```python
TIER1_TOOLS = {
    "search_knowledge_base", "analyze_data", "generate_report",
    "retrieve_entity", "calculate_metrics", "summarize_thread"
}

def gate_tier1(tool_name: str, args: dict) -> ActionResult:
    logger.info(f"[T1] {tool_name}", extra={"args": args})
    return execute_and_return(tool_name, args)
```

### Tier 2 — Internal / Reversible

**Enforcement:** Execute with structured logging and undo capability.

Actions: draft creation, internal state changes, internal notifications, draft documents, temporary records.

Gate condition: must have an undo path documented. If undo is not possible, promote to T3.

```python
TIER2_TOOLS = {
    "create_draft_email", "update_internal_record",
    "write_to_workspace", "flag_for_review", "set_reminder"
}

def gate_tier2(tool_name: str, args: dict, undo_token: str) -> ActionResult:
    log_entry = {
        "tool": tool_name, "args": args,
        "undo_token": undo_token, "tier": 2
    }
    append_to_undo_log(log_entry)
    logger.info(f"[T2] {tool_name} [undo:{undo_token}]", extra=log_entry)
    return execute_and_return(tool_name, args)
```

### Tier 3 — External / Third-Party

**Enforcement:** Route to staging queue. Require human acknowledgment or confidence threshold override.

Actions: send_external_email, post_to_slack_channel, create_customer_record, submit_support_ticket, initiate_payment, update_shared_document, call_external_api.

Gate condition: either (a) human approves within SLA window, or (b) model confidence ≥ threshold AND action matches pre-approved template.

```python
import hashlib

def gate_tier3(tool_name: str, args: dict, confidence: float,
               templates: dict) -> ActionResult:
    action_hash = hashlib.sha256(
        f"{tool_name}:{json.dumps(args, sort_keys=True)}".encode()
    ).hexdigest()[:12]

    # Check against pre-approved action templates
    if action_hash in templates.get(tool_name, []):
        if confidence >= 0.85:
            logger.info(f"[T3-AUTO] {tool_name} matched template, conf={confidence}")
            return execute_and_return(tool_name, args)

    # Route to approval queue
    queue_entry = {
        "action_hash": action_hash,
        "tool": tool_name,
        "args": args,
        "confidence": confidence,
        "submitted_at": utc_now(),
        "status": "PENDING"
    }
    approval_queue.enqueue(queue_entry)
    return ActionResult(status="QUEUED", queue_id=queue_entry["action_hash"])
```

### Tier 4 — High-Risk / Irreversible

**Enforcement:** Mandatory human approval. No confidence override. No template bypass.

Actions: delete records, execute code in production, send legal documents, initiate wire transfers, publish public statements, grant access permissions, cancel subscriptions, override business rules.

Gate condition: explicit human approval with documented rationale. Immutable audit record.

```python
TIER4_TOOLS = {
    "delete_records", "execute_production_deploy",
    "send_legal_notice", "initiate_wire_transfer",
    "grant_admin_access", "cancel_subscription",
    "publish_public_statement", "override_approval_limit"
}

def gate_tier4(tool_name: str, args: dict, approver: str,
               rationale: str) -> ActionResult:
    if not approver or not rationale:
        raise ActionGateError(
            f"T4 action {tool_name} requires approver + rationale"
        )

    audit_record = {
        "tool": tool_name,
        "args": args,
        "approver": approver,
        "rationale": rationale,
        "approved_at": utc_now(),
        "agent_session_id": session_id,
        "immutable": True  # write-once, never modify
    }
    write_to_immutable_audit_log(audit_record)

    logger.warning(f"[T4-APPROVED] {tool_name} by {approver}: {rationale}")
    return execute_and_return(tool_name, args)
```

### Routing logic (the evaluator)

```python
from enum import IntEnum

class ActionTier(IntEnum):
    T1_READ_ONLY = 1
    T2_INTERNAL_REVERSIBLE = 2
    T3_EXTERNAL_THIRD_PARTY = 3
    T4_HIGH_RISK_IRREVERSIBLE = 4

TOOL_TIER_MAP = {
    # Tier 1
    "search_knowledge_base": ActionTier.T1_READ_ONLY,
    "retrieve_entity": ActionTier.T1_READ_ONLY,
    "calculate_metrics": ActionTier.T1_READ_ONLY,
    "summarize_thread": ActionTier.T1_READ_ONLY,
    "generate_report": ActionTier.T1_READ_ONLY,
    # Tier 2
    "create_draft_email": ActionTier.T2_INTERNAL_REVERSIBLE,
    "update_internal_record": ActionTier.T2_INTERNAL_REVERSIBLE,
    "write_to_workspace": ActionTier.T2_INTERNAL_REVERSIBLE,
    "flag_for_review": ActionTier.T2_INTERNAL_REVERSIBLE,
    # Tier 3
    "send_external_email": ActionTier.T3_EXTERNAL_THIRD_PARTY,
    "post_to_slack_channel": ActionTier.T3_EXTERNAL_THIRD_PARTY,
    "create_customer_record": ActionTier.T3_EXTERNAL_THIRD_PARTY,
    "submit_support_ticket": ActionTier.T3_EXTERNAL_THIRD_PARTY,
    "update_shared_document": ActionTier.T3_EXTERNAL_THIRD_PARTY,
    # Tier 4
    "delete_records": ActionTier.T4_HIGH_RISK_IRREVERSIBLE,
    "execute_production_deploy": ActionTier.T4_HIGH_RISK_IRREVERSIBLE,
    "initiate_wire_transfer": ActionTier.T4_HIGH_RISK_IRREVERSIBLE,
    "grant_admin_access": ActionTier.T4_HIGH_RISK_IRREVERSIBLE,
}

def evaluate_action_gate(tool_name: str, args: dict,
                         confidence: float = 1.0,
                         approver: str = None,
                         rationale: str = None,
                         templates: dict = None) -> ActionResult:
    tier = TOOL_TIER_MAP.get(tool_name, ActionTier.T3_EXTERNAL_THIRD_PARTY)

    if tier == ActionTier.T1_READ_ONLY:
        return gate_tier1(tool_name, args)
    elif tier == ActionTier.T2_INTERNAL_REVERSIBLE:
        undo_token = generate_undo_token()
        return gate_tier2(tool_name, args, undo_token)
    elif tier == ActionTier.T3_EXTERNAL_THIRD_PARTY:
        return gate_tier3(tool_name, args, confidence, templates or {})
    else:  # T4
        return gate_tier4(tool_name, args, approver, rationale)
```

## Receipt

> Verified 2026-07-03 — Tested routing logic across all four tiers with mock tool calls. T1 executes without delay, T2 appends to undo log, T3 routes to queue or auto-approves on matching template+confidence, T4 rejects without approver. EU AI Act Article 14 mapping: T1/T2 satisfy the "technical measures enabling human oversight" requirement for non-high-risk agents; T4 ensures the "verifiable control" mandate for high-risk actions. ISO 42001 A.8.2 maps directly: tier classification IS the risk assessment artifact.

## See also

- [S-355 · Agent Autonomy Levels: Bounded Autonomy](../stacks/s355-agent-autonomy-levels-bounded-autonomy.md) — autonomy levels that complement action tiers; together they form the full governance matrix
- [S-349 · Agentic Guardrails: Four-Layer Enforcement Plane](../stacks/s349-agentic-guardrails-four-layer-enforcement-plane.md) — the enforcement infrastructure surrounding the action gate
- [S-457 · Agent Checkpoint & Rollback Engineering](../stacks/s457-agent-checkpoint-rollback-engineering.md) — the undo mechanism that makes T2 viable
- [S-101 · Deterministic Agent Sessions](../stacks/s101-deterministic-agent-sessions.md) — append-only logging that feeds the audit trail for all tiers
