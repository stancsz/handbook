# S-511 · Plan-then-Execute: The Architectural Isolation Pattern

When agents go wrong in production, the failure almost always happens at the seam — between *what the agent decided to do* and *what it actually did*. The fix is not more guardrails bolted onto the executor. It's a clean architectural separation: a planner that thinks, and an executor that acts only through a semantic gate that enforces policy before execution.

## Forces

- **Confidence ≠ correctness.** Agents produce confident action plans that look coherent but contain subtle errors — wrong IDs, inappropriate tool selection, contextually inappropriate operations. The confidence comes from the reasoning layer; the error lives in the action layer.
- **Guardrails are reactive; the plan is proactive.** Blocking a malformed tool call at the executor is a lossy filter. The executor doesn't know *why* a tool call was blocked — it just retries or escalates. You need to catch bad plans before they become bad actions.
- **Separation of concerns is not optional at production scale.** A single agent that reasons and executes in one pass cannot be audited, constrained, or selectively overridden. The moment you need a human to approve a specific class of action, you have to restructure everything.
- **Plan-then-execute (P-t-E) is the proven answer.** The pattern is well-established in robotics, autonomous vehicle systems, and industrial control. It is now the de facto security baseline for production agentic AI after the wave of 2024-2025 incidents where agents with fused planning/execution layers caused data corruption.

## The move

Separate the agent into at least two distinct processing stages with a semantic gate between them:

```
User Input → Planner LLM → Action Plan (structured) → Semantic Gate → Executor LLM → Tool Calls → Results
                                                      ↓
                                               Policy Evaluation
                                               Context Validation
                                               Risk Scoring
```

### The planner layer

The planner receives the task and produces a structured action plan — not raw tool calls. The output schema should include:

```
ActionPlan {
  goal: string           // What we're trying to accomplish
  steps: Step[]          // Ordered sequence of actions
  preconditions: string  // What must be true for this plan to succeed
  rollback_plan: Step[]  // How to undo if step N fails
  escalation_trigger: string  // When to abandon and escalate
}
```

The planner never calls external tools. It reasons and plans. This is a deliberate limitation — not a performance constraint.

### The semantic gate

The semantic gate intercepts the planner's output before the executor sees it. It runs three checks:

**1. Policy evaluation.** Does this plan violate any standing policy? (e.g., "never modify more than 100 records in one operation", "escalate before deleting user data", "never execute financial transfers above $X without HITL approval"). Policy checks are rule-based, not probabilistic.

**2. Context validation.** Does the plan's preconditions match the current context? The planner assumed certain state — verify it. If the planner planned to "update customer record" but the record was locked by another process, the plan is stale.

**3. Risk scoring.** Does the plan's risk profile match the task's trust level? A data-reporting agent and a data-mutating agent have different risk tolerances. Score the plan against the session's trust tier and reject or escalate if it exceeds the budget.

### The executor layer

The executor receives a validated plan and executes step by step. Each step goes through a lightweight execution gate — does the tool call match the planned step? — before the actual tool invocation. The executor can be a much smaller model, since it doesn't reason, it just executes.

```
[language=python]
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
import json

class RiskTier(str, Enum):
    SAFE = "safe"        # read-only, no side effects
    BOUNDED = "bounded"  # write operations within limits
    PRIVILEGED = "privileged"  # high-impact, requires escalated context
    BLOCKED = "blocked"  # never allowed regardless of plan

class ActionStep(BaseModel):
    action_type: str
    target: str
    parameters: dict
    rollback_step: Optional[int] = None

class ActionPlan(BaseModel):
    goal: str
    steps: list[ActionStep]
    preconditions: str
    risk_tier: RiskTier

class PolicyRule(BaseModel):
    rule_id: str
    description: str
    max_records: Optional[int] = None
    max_amount_usd: Optional[float] = None
    requires_hitl: bool = False
    allowed_action_types: Optional[list[str]] = None
    blocked_action_types: Optional[list[str]] = None

class SemanticGate:
    """Intercepts planner output; returns (approved, escalated, rejected)."""
    
    def __init__(self, policy_rules: list[PolicyRule], risk_threshold: RiskTier):
        self.policy_rules = policy_rules
        self.risk_threshold = risk_threshold
    
    def evaluate(self, plan: ActionPlan, context: dict) -> tuple[str, list[str]]:
        """
        Returns (decision, reasons):
          decision in {'approved', 'escalated', 'rejected'}
          reasons: list of human-readable policy notes
        """
        reasons = []
        
        # 1. Policy evaluation
        for rule in self.policy_rules:
            for step in plan.steps:
                if rule.blocked_action_types and step.action_type in rule.blocked_action_types:
                    return 'rejected', [f"Action type {step.action_type} blocked by rule {rule.rule_id}: {rule.description}"]
                if rule.max_records and self._count_affected_records(step) > rule.max_records:
                    return 'rejected', [f"Step exceeds max_records ({rule.max_records}) per rule {rule.rule_id}"]
                if rule.requires_hitl:
                    reasons.append(f"HITL required for {rule.description}")
        
        # 2. Context validation
        for step in plan.steps:
            if not self._validate_preconditions(step, context):
                return 'rejected', [f"Preconditions not met for step targeting {step.target}"]
        
        # 3. Risk tier gating
        if self._risk_tier_value(plan.risk_tier) > self._risk_tier_value(self.risk_threshold):
            return 'escalated', [f"Plan risk tier {plan.risk_tier} exceeds threshold {self.risk_threshold}"]
        
        if reasons:
            return 'escalated', reasons
        return 'approved', []
    
    def _risk_tier_value(self, tier: RiskTier) -> int:
        return {RiskTier.SAFE: 0, RiskTier.BOUNDED: 1, RiskTier.PRIVILEGED: 2, RiskTier.BLOCKED: 3}[tier]
    
    def _count_affected_records(self, step: ActionStep) -> int:
        return step.parameters.get('limit', 0) or step.parameters.get('batch_size', 0) or 1
    
    def _validate_preconditions(self, step: ActionStep, context: dict) -> bool:
        # Simplified: real implementation checks record locks, auth state, data freshness
        return True

# Usage
policy = [
    PolicyRule(rule_id="no-bulk-delete", description="No bulk deletes without approval",
               blocked_action_types=["bulk_delete", "truncate"]),
    PolicyRule(rule_id="hitl-financial", description="Financial transfers require human approval",
               requires_hitl=True, allowed_action_types=["transfer", "payment"]),
    PolicyRule(rule_id="max-record-batch", description="Max 100 records per operation",
               max_records=100),
]

gate = SemanticGate(policy_rules=policy, risk_threshold=RiskTier.BOUNDED)
plan = ActionPlan(
    goal="Archive old customer records",
    steps=[ActionStep(action_type="bulk_delete", target="customers", parameters={"older_than_days": 365})],
    preconditions="Records older than 365 days with no open tickets",
    risk_tier=RiskTier.BOUNDED,
)
decision, reasons = gate.evaluate(plan, context={"db_locked": False})
print(f"Decision: {decision}, Reasons: {reasons}")
# Decision: rejected, Reasons: ['Action type bulk_delete blocked by rule no-bulk-delete: No bulk deletes without approval']
```

## Receipt

> Verified 2026-07-03 — Pattern documented in Zylos Research (2026), Idan Habler "Building Secured Agents" (Medium, 2025), Authority Partners AI Guardrails Guide (2026). The Plan-then-Execute + semantic gate architecture is the consensus recommendation across production AI security literature. Code example is a functional prototype demonstrating the three-gate evaluation logic.

## See also

- [S-198 · Agent Tool Call Guardrails](stacks/s198-agent-tool-call-guardrails.md) — reactive guardrails at the execution layer; this entry is the proactive architectural complement
- [S-340 · Agent Hard Enforcement Plane](stacks/s340-agent-hard-enforcement-plane.md) — policy enforcement as a dedicated infrastructure layer
- [S-503 · Consequential Action Gates: Tiered HITL Architecture](stacks/s503-consequential-action-gates-tiered-hitl-architecture.md) — human-in-the-loop as a policy tier, not an afterthought
- [S-357 · Long-Running Agent Orchestration (Planner-Worker)](stacks/s357-long-running-agent-orchestration-planner-worker.md) — the broader planner-worker pattern this entry specializes
