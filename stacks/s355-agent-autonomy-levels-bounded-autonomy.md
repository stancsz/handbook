# S-355 · Agent Autonomy Levels: The Bounded Autonomy Pattern

The agent that booked a flight, sent the invoice, filed the expense report, and emailed the customer — all before a human knew it had started — is not a future concern. It is production. The question is not whether agents will operate autonomously, but at what level and under what constraints. Most teams deploy agents without answering this, then discover the answer when an incident happens.

The fix is explicit: map every agent to an autonomy level, define the enforcement surface at that level, and treat every escalation boundary as a machine-enforceable gate — not a policy document.

## Forces

- **Autonomy is not binary.** A chatbot is L0. A coding agent that writes and runs tests autonomously is L3+. Treating "agent" as one thing produces guardrails designed for L0 that shatter at L2.
- **Teams don't name the level.** Without explicit classification, agents drift upward — a useful prototype gains more permissions over time until it operates at L4 without anyone deciding it should. The absence of a level is not L0; it is "whatever the agent can get away with."
- **The read-to-write boundary is the critical gate.** Every escalation taxonomy from CSA to Zylos to ASDLC converges on one principle: the transition from reading information to modifying external systems is the natural, enforceable escalation point. Most governance frameworks fail because they treat this as a policy decision rather than a technical gate.
- **L5 is explicitly unsafe for enterprise.** Every major framework — CSA, ASDLC, Zylos, SAE — places full autonomy at Level 5 and designates it unsuitable for production. Production ceiling is L3-L4 with mandatory L4+ escalation. The market wants L5. The engineering discipline is knowing L4 is already pushing it.
- **EU AI Act enforcement activates August 2, 2026.** Annex III domain agents (hiring, credit, insurance, critical infrastructure) face €35M penalties for missing Article 12 audit trails. Audit trails require knowing what the agent was authorized to do — which requires knowing its autonomy level.

## The Move

### 1. Classify with the L0–L5 Scale

Inspired by SAE J3016 automotive automation, adapted for AI agents:

| Level | Name | Human Role | Agent Behavior | Production Status |
|-------|------|------------|----------------|-------------------|
| **L0** | No Automation | 100% human | Zero. Single prompt, single response. | Standard chatbots |
| **L1** | Assistive | Human decides and acts | AI recommends one action; human executes | Simple copilots |
| **L2** | Partial Automation | Human supervises, can override | AI executes bounded tasks; human monitors | Most "agent" products today |
| **L3** | Conditional Autonomy | Human on standby | AI decides and acts; human available on request | Coding agents, data pipelines |
| **L4** | High Autonomy | Human reviews post-hoc | AI operates fully within defined scope; human audits | Devin 2.0 frontier |
| **L5** | Full Autonomy | None | AI decides scope, executes, evaluates — no human in loop | Explicitly unsafe; experimental only |

The critical dividing line is **L2 vs L3**: below L2, the human is always in the decision loop. Above L2, the agent decides first and human reviews after. This boundary determines whether your agent needs pre-action approval (L0-L2) or post-action audit (L3-L4).

### 2. Map Controls to the Capability-Control Matrix

Each level requires specific controls. Do not add controls from higher levels — it adds cost and latency without benefit. Do not skip controls from the level below — it leaves a gap the agent will find.

```
L0: Input validation, output format checks, rate limiting
L1: Above + single-action confirmation prompts, tool allowlisting
L2: Above + loop detection, per-action cost caps, escalation triggers
L3: Above + pre-action human-in-the-loop (HITL) gates at read-to-write boundary,
    hard enforcement plane (S-340), undo stack
L4: Above + governance agent overlay (see below), full trajectory logging,
    autonomous privilege demotion on threshold breach
L5: Not for production. If you are reading this for a production system, you are wrong.
```

### 3. Implement the Read-to-Write Escalation Gate

The single most actionable pattern from every governance framework:

```python
# The enforcement gate — wrap every tool invocation
class ReadWriteEscalationGate:
    def __init__(self, autonomy_level: int):
        self.level = autonomy_level
        # Read tools: tools that query, summarize, search, read
        self.read_tools = {"search", "query", "read", "get", "fetch", "retrieve"}
        # Write tools: tools that modify, send, delete, update, create
        self.write_tools = {"send", "delete", "update", "create", "post", "put", "execute"}

    def classify(self, tool_name: str) -> str:
        """Classify tool as read or write at the name/permission level."""
        return "write" if tool_name in self.write_tools else "read"

    def check(self, tool_name: str, confidence: float) -> dict:
        is_write = self.classify(tool_name) == "write"
        requires_approval = is_write and self.level < 3

        if requires_approval and confidence < 0.75:
            return {
                "action": "ESCALATE",
                "reason": f"Write action '{tool_name}' at L{self.level} requires approval; confidence {confidence:.2f} below 0.75",
                "gate": "read_to_write"
            }

        if is_write and self.level >= 3:
            # L3+ can execute writes autonomously but must log
            return {"action": "LOG_AND_EXECUTE", "tool": tool_name}

        return {"action": "APPROVE", "tool": tool_name}

# Usage in agent loop
gate = ReadWriteEscalationGate(autonomy_level=3)
for step in agent_loop:
    decision = gate.check(step.tool, step.confidence)
    if decision["action"] == "ESCALATE":
        push_to_human_approval_queue(decision)
        await_human()
    elif decision["action"] == "LOG_AND_EXECUTE":
        audit_log.record(step, level=3)
        execute(step)
```

This is not a policy. It is a function. Policy lives in the function's parameters (autonomy level, confidence thresholds, tool sets), not in prose.

### 4. Deploy the Governance Agent Overlay for L4

For agents at L4 and above, the CSA's governance agent overlay pattern monitors other agents in real time:

```python
class GovernanceAgent:
    """L4+ governance overlay — watches agent behavior, not inside it."""

    def __init__(self, policy: dict, audit_store):
        self.policy = policy
        self.audit_store = audit_store  # S-340 hard enforcement plane
        self.anomaly_score = 0.0

    def monitor(self, agent_id: str, tool_call: dict):
        # Check against policy — not LLM-judged, rule-based
        violations = self.check_policy_violations(tool_call, self.policy)
        if violations:
            self.anomaly_score += sum(v["severity"] for v in violations)
            if self.anomaly_score > self.policy["demotion_threshold"]:
                self.demote_privileges(agent_id)
                self.audit_log.record_privilege_demotion(agent_id)

        # Log all actions for EU AI Act Article 12 compliance
        self.audit_log.record({
            "agent_id": agent_id,
            "tool": tool_call["name"],
            "params": tool_call["params"],
            "timestamp": utc_now(),
            "autonomy_level": self.policy["autonomy_level"],
            "decision": "autonomous",
            "escalation_triggered": bool(violations)
        })

    def check_policy_violations(self, tool_call: dict, policy: dict) -> list:
        """Deterministic — no LLM in the enforcement path."""
        violations = []
        if tool_call["name"] in policy["forbidden_tools"]:
            violations.append({"severity": 1.0, "rule": "forbidden_tool"})
        if tool_call["cost"] > policy["max_tool_cost"]:
            violations.append({"severity": 0.8, "rule": "cost_exceeded"})
        if tool_call["iteration"] > policy["max_iterations"]:
            violations.append({"severity": 0.9, "rule": "loop_detection"})
        return violations

    def demote_privileges(self, agent_id: str):
        """Autonomous privilege demotion — governance agent acts without human."""
        # Reduce autonomy level, revoke write tools, notify audit queue
        pass
```

The governance agent is not an LLM. It is a rule engine. The moment your governance agent uses an LLM to decide whether to demote an agent's privileges, you have circular LLM dependency and the same failure modes on both sides.

### 5. Build the Undo Stack for L3+

Every action at L3+ must be reversible. This is not optional — it is the mechanism that makes autonomous operation survivable:

```python
class UndoStack:
    def __init__(self):
        self.stack: list[Action] = []

    def record(self, action: Action):
        # Snapshot state before action
        self.stack.append({
            "action": action,
            "pre_state": capture_state(action.target),
            "compensation_key": hash(action.metadata),  # S-352
            "idempotency_key": action.idempotency_key
        })

    def undo_last(self) -> bool:
        """Undo most recent action using its compensation key (S-352)."""
        if not self.stack:
            return False
        entry = self.stack.pop()
        # Use compensation key — not the original action — for the undo
        # This ensures the undo itself is idempotent (S-352)
        return execute_compensation(entry["compensation_key"], idempotency_key=entry["compensation_key"])
```

### 6. Context Drift Management for L3+

Agents at L3+ accumulate context that diverges from the original intent. Compensate:

```python
class ContextDriftManager:
    def compress(self, agent_id: str, trajectory: list[Action]):
        """Every N turns: distill trajectory into compressed beliefs, archive raw."""
        if len(trajectory) % 20 == 0:  # every 20 turns
            summary = llm.summarize(f"""Summarize this agent execution into:
- Original goal
- Actions taken (one line each)
- Current state vs expected state
- Next 3 planned steps""", trajectory=trajectory)
            archive_to_external_storage(agent_id, trajectory)  # not in context
            return distill(summary)  # reinject only summary
```

## Receipt

> Verified 2026-07-02 — Researched CSA Agentic AI Autonomy Levels and Control Framework v2.0 (March 2026, 50 days operational evidence), Zylos AI Agent Autonomy Levels taxonomy (2026-03-28), ASDLC L0-L5 scale (2026-05-28), Zylos Governance and Compliance 2026 (2026-05-01), Vitalora Bounded Autonomy pattern (2026). Read-to-write escalation confirmed as the convergence point across all three independent frameworks. Governance agent overlay pattern sourced from CSA v2.0 + Zylos governance agent section. EU AI Act August 2, 2026 enforcement date confirmed — F-169 covers the audit trail requirement; this entry covers the autonomy level classification that audit trails require. L5 explicitly unsafe confirmed across all four sources. No existing handbook entry on autonomy levels, SAE taxonomy, or bounded autonomy — confirmed via full-text search of stacks/.

## See also

[S-340](s340-agent-hard-enforcement-plane.md) · [S-349](s349-agentic-guardrails-four-layer-enforcement-plane.md) · [S-78](s78-agent-to-human-escalation.md) · [S-352](s352-agentic-compensation-keys-the-autonomous-retry-era.md) · [F-169](../forward-deployed/f169-eu-ai-act-article-12-agent-trail.md)
