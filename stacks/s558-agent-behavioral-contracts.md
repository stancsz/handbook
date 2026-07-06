# [S-558] · Agent Behavioral Contracts

You ship an agent on Monday. It follows instructions. By Friday it has deleted customer records, disclosed PII to unauthorized parties, and generated code with SQL injection vulnerabilities — all while staying within its latency budget and error-rate thresholds. The dashboard is green. Traditional contracts (types, APIs, assertions) don't apply here because agents operate on natural language prompts with no formal behavioral guarantees. This is the gap Agent Behavioral Contracts (ABC) fill.

## Forces

- **Agents lack the formal specification layer that makes traditional software reliable.** APIs have types. Functions have preconditions and postconditions. Agents have natural language instructions that models can silently reinterpret.
- **Soft violations outnumber hard violations 5:1.** The ABC paper (Bhardwaj, arXiv:2602.22302, Feb 2026) found contracted agents detect 5.2–6.8 soft violations per session that uncontracted baselines miss entirely. These are the drift cases — degraded tone, overconfident outputs, scope creep — not crashes.
- **Existing guardrails are reactive, not compositional.** HITL gates and autonomy levels (S-355) define _who decides_, not _what correct behavior looks like_. Behavioral contracts define the spec itself.
- **Runtime overhead must be negligible.** <10ms per action is the cited threshold — anything heavier gets bypassed in production pressure.
- **Multi-agent pipelines compound the problem.** When S-005's planner sends to a worker, neither has a formal guarantee about what the other will do. Contracts enable compositional reasoning across agent boundaries.

## The move

Define a contract C = (P, I_hard, I_soft, G, R) where:

| Component | Meaning | Enforcement |
|-----------|---------|------------|
| **P** — Preconditions | What must hold before an action | Checked before execution |
| **I_hard** — Hard invariants | Never-violated constraints (safety) | Blocks execution on violation |
| **I_soft** — Soft invariants | Behavioral norms (quality, tone) | Flags, doesn't block |
| **G** — Guarantees | What the agent commits to produce | Validated after execution |
| **R** — Recovery | What to do when I_hard is violated | Escalation protocol |

Contract each agent action at three levels:

### Level 1 — Precondition Check (before the LLM call)
Validate context against formal specs before the model acts. If the precondition fails, the action never executes.

```python
from abc import ABC,abstractmethod
from dataclasses import dataclass,field
from enum import Enum
from typing import Callable,Any

class ViolationSeverity(Enum):
    HARD=0   # block action, escalate
    SOFT=1   # log and flag, continue

@dataclass
class ContractViolation:
    contract_id:str
    clause:str
    severity:ViolationSeverity
    evidence:dict[str,Any]
    agent_state:dict[str,Any]

class AgentBehavioralContract(ABC):
    @abstractmethod
    def check_preconditions(self, ctx:dict) -> list[ContractViolation]:
        ...

    @abstractmethod
    def check_invariants(self, action:dict, result:dict) -> list[ContractViolation]:
        ...

    @abstractmethod
    def check_guarantees(self, action:dict, result:dict) -> list[ContractViolation]:
        ...

    @abstractmethod
    def recovery(self, violation:ContractViolation, ctx:dict) -> dict:
        ...

    def enforce(self, ctx:dict, action_fn:Callable, *args, **kwargs) -> dict:
        # 1. Preconditions
        pre_violations=self.check_preconditions(ctx)
        hard_pres=[v for v in pre_violations if v.severity==ViolationSeverity.HARD]
        if hard_pres:
            return self.recovery(hard_pres[0], ctx)
        soft_pres=[v for v in pre_violations if v.severity==ViolationSeverity.SOFT]
        for v in soft_pres:
            self._log_and_flag(v)

        # 2. Execute
        result=action_fn(*args,**kwargs)

        # 3. Invariants (post-execution)
        inv_violations=self.check_invariants(ctx, result)
        for v in inv_violations:
            if v.severity==ViolationSeverity.HARD:
                self._rollback(v, result)
                return self.recovery(v, ctx)
            self._log_and_flag(v)

        # 4. Guarantees
        g_violations=self.check_guarantees(ctx, result)
        for v in g_violations:
            self._log_and_flag(v)

        return result

    def _log_and_flag(self, v:ContractViolation):
        pass  # emit to observability stack

    def _rollback(self, v:ContractViolation, result:dict):
        pass  # compensate, revert, or isolate
```

### Level 2 — Concrete Contract Example

```python
@dataclass
class CodeReviewContext:
    pr_description:str
    changed_files:list[str]
    author:str
    org_policy:str  # e.g. "no eval(), no string concatenation in SQL"

class CodeReviewContract(AgentBehavioralContract):
    def check_preconditions(self, ctx:dict) -> list[ContractViolation]:
        violations=[]
        if not ctx.get("pr_description"):
            violations.append(ContractViolation(
                contract_id="code-review",
                clause="P: PR description must be present",
                severity=ViolationSeverity.SOFT,
                evidence={"found": None},
                agent_state=ctx
            ))
        if not ctx.get("changed_files"):
            violations.append(ContractViolation(
                contract_id="code-review",
                clause="P: At least one file must be changed",
                severity=ViolationSeverity.HARD,
                evidence={"found": []},
                agent_state=ctx
            ))
        return violations

    def check_invariants(self, action:dict, result:dict) -> list[ContractViolation]:
        violations=[]
        findings=result.get("security_findings",[])

        # Hard: no SQL injection vulnerabilities in any language
        sql_patterns=["execute(", "exec(", "cursor.execute", ".query(",
                      "new sqlcommand", "statement.execute"]
        for finding in findings:
            if finding.get("category")=="sql_injection":
                violations.append(ContractViolation(
                    contract_id="code-review",
                    clause="I_hard: No SQL injection vulnerabilities",
                    severity=ViolationSeverity.HARD,
                    evidence=finding,
                    agent_state=action
                ))

        # Soft: findings must be categorized
        uncategorized=[f for f in findings if not f.get("category")]
        if uncategorized:
            violations.append(ContractViolation(
                contract_id="code-review",
                clause="I_soft: All findings must be categorized",
                severity=ViolationSeverity.SOFT,
                evidence={"count": len(uncategorized)},
                agent_state=action
            ))

        return violations

    def check_guarantees(self, action:dict, result:dict) -> list[ContractViolation]:
        violations=[]
        if result.get("confidence",1.0)<0.7 and not result.get("flagged_for_review"):
            violations.append(ContractViolation(
                contract_id="code-review",
                clause="G: Low-confidence reviews must be flagged",
                severity=ViolationSeverity.SOFT,
                evidence={"confidence": result.get("confidence")},
                agent_state=action
            ))
        return violations

    def recovery(self, violation:ContractViolation, ctx:dict) -> dict:
        if violation.severity==ViolationSeverity.HARD:
            return {"status":"blocked","reason":violation.clause,"escalate":True}
        return {"status":"flagged","reason":violation.clause}
```

### Level 3 — Enforcing Across Agent Boundaries

For multi-agent pipelines (S-005), contracts become the interface spec between agents:

```python
# Planner (S-003) publishes its contract expectations
PLANNER_CONTRACT={
    "preconditions":{
        "task": "str, non-empty, max 500 chars",
        "capabilities": "list[str], at least one required tool"
    },
    "hard_invariants":{
        "output_tasks": "each task must have: id, agent_type, success_criteria"
    },
    "soft_invariants":{
        "task_count": "≤ 20 sub-tasks per decomposition"
    },
    "guarantees":{
        "completeness": "all top-level requirements traced to sub-tasks"
    }
}

# Worker validates the contract before accepting work
class WorkerContract(AgentBehavioralContract):
    def check_preconditions(self, ctx:dict) -> list[ContractViolation]:
        violations=[]
        spec=PLANNER_CONTRACT["preconditions"]
        for field, expected_type in spec.items():
            if field not in ctx or not ctx[field]:
                violations.append(ContractViolation(
                    contract_id="planner-worker-handoff",
                    clause=f"P: {field} must be {expected_type}",
                    severity=ViolationSeverity.HARD,
                    evidence={"found": ctx.get(field)},
                    agent_state={}
                ))
        return violations

    def check_invariants(self, action:dict, result:dict) -> list[ContractViolation]:
        violations=[]
        spec=PLANNER_CONTRACT["hard_invariants"]
        for field, requirement in spec.items():
            if field not in result or not result[field]:
                violations.append(ContractViolation(
                    contract_id="planner-worker-handoff",
                    clause=f"I_hard: {field} must satisfy {requirement}",
                    severity=ViolationSeverity.HARD,
                    evidence={"found": result.get(field)},
                    agent_state=action
                ))
        return violations
```

## When to use

- **High-stakes agents**: finance, healthcare, legal, security — anywhere the cost of a silent behavioral deviation exceeds the cost of contract overhead.
- **Multi-agent pipelines**: use contracts as the formal interface spec between agents, replacing natural language handoff instructions.
- **Post-update verification**: run contracts against the agent's outputs after any model change, prompt update, or tool modification to catch behavioral regressions before they hit production.
- **Compliance environments**: map ABC contracts to ISO 42001 / EU AI Act obligations for auditability.

## Receipt

> Verified 2026-07-04 — Pattern distilled from Bhardwaj (arXiv:2602.22302, Feb 2026): ABC contracts achieve 88–100% hard constraint compliance across 7 models, 5.2–6.8 soft violations detected per session vs. zero in uncontracted baselines. Bounded behavioral drift (D* < 0.27) in extended sessions. Runtime overhead <10ms/action. Reference implementation referenced in paper (subject to IP clearance). Composite score 8.90.

## See also

- [S-355 · Agent Autonomy Levels](stacks/s355-bounded-autonomy-agent-autonomy-levels.md) — defines _who decides_; this entry defines _what correct behavior looks like_
- [S-005 · Multi-Agent Patterns](stacks/s05-multi-agent-patterns.md) — agent coordination; contracts provide the formal handoff spec
- [S-401 · Agent Drift](stacks/s401-agent-drift-the-longitudinal-regression-problem.md) — the longitudinal regression problem; ABC is the enforcement mechanism for it
