# F-176 · Agent Runbook-Driven Reliability

When your agent hits a failure in production, it retries once and returns an apology. Meanwhile, the SRE playbook for this exact failure has four steps that would recover in 30 seconds — but the agent doesn't know they exist. The fix: treat operational runbooks as first-class agent code, not tribal knowledge in a Confluence page nobody reads.

## Forces

- Agents succeed on the happy path and fail silently on edge cases — a tool timeout, a rate limit, an empty retrieval result, a partial API response — that human operators have known how to handle for years
- Every failure that reaches a human is a 10–30 minute incident; teams deploying agents at scale report that 40–60% of their on-call burden comes from agent-specific failures that have known fixes
- Hard-coding remediation logic into the agent prompt makes it brittle and context-length-consuming; hard-coding it into infrastructure makes it invisible to the agent's reasoning
- Agentic reliability (S-200) improves step quality, but doesn't give the agent *operational memory* — the institutional knowledge of what to do when step N fails
- The gap is not capability (the agent can do the task) — it's operational awareness (the agent knows how to recover from known failure modes)

## The move

**Structured runbook injection**: encode failure-condition → remediation-step mappings as a machine-readable operational knowledge base, and give the agent a lightweight reasoning layer to consult it at runtime before escalating or giving up.

### The three layers

**Layer 1 — Failure taxonomy (what can go wrong)**

Map the failure modes your agent encounters in practice. Group by trigger condition, not by error message:

```
ToolFailure
  ├── timeout          → retry with backoff (see: runbook.tool_timeout)
  ├── rate_limited     → queue + exponential backoff (see: runbook.rate_limit)
  ├── auth_expired     → refresh credentials, re-authenticate (see: runbook.auth)
  └── schema_mismatch  → re-fetch schema, re-serialize (see: runbook.schema_drift)

RetrievalFailure
  ├── no_results       → broaden query, try synonyms (see: runbook.empty_retrieval)
  ├── low_relevance    → re-rank, boost recency (see: runbook.low_relevance)
  └── stale_context    → invalidate cache, re-fetch (see: runbook.stale_context)

OutputFailure
  ├── format_violation → re-prompt with stricter schema (see: runbook.format_recovery)
  ├── confidence_low   → escalate or hedge (see: runbook.low_confidence)
  └── partial_response → retry with expanded context (see: runbook.partial_output)
```

**Layer 2 — Runbook entries (how to recover)**

Each entry is a short, imperative procedure. Aim for 3–8 steps. The agent reads this when it encounters the tagged failure:

```yaml
# runbooks/tool_timeout.yaml
trigger: tool_timeout
description: "A tool call exceeded its timeout threshold"
steps:
  - "Check if the operation is idempotent (has a GET equivalent)"
  - "Retry once with 2x original timeout"
  - "If still failing, check tool status endpoint or health check"
  - "If tool is degraded, switch to fallback provider if one exists"
  - "If no fallback, return partial result with a flagged warning — do not hallucinate a response"
recovery_signal: "tool_response received within timeout"
escalation: "failure_count > 3 in last 10 calls → page on-call"
```

**Layer 3 — Runbook executor (runtime integration)**

The agent doesn't just read runbooks — it executes them with guardrails:

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional
import time

class FailureSignal(Enum):
    TOOL_TIMEOUT = "tool_timeout"
    RATE_LIMITED = "rate_limited"
    AUTH_EXPIRED = "auth_expired"
    EMPTY_RETRIEVAL = "empty_retrieval"
    LOW_CONFIDENCE = "low_confidence"
    PARTIAL_OUTPUT = "partial_output"

@dataclass
class RunbookContext:
    failure: FailureSignal
    attempt: int
    max_attempts: int
    operation_id: str

class RunbookExecutor:
    def __init__(self, runbook_registry: dict, circuit_breaker):
        self.runbooks = runbook_registry
        self.cb = circuit_breaker  # see: S-204 Agent Circuit Breaker

    def execute(self, ctx: RunbookContext, agent, tool_registry) -> str:
        runbook = self.runbooks.get(ctx.failure.value)
        if not runbook:
            return self._escalate(ctx, reason="no runbook found")

        last_step = None
        for step in runbook["steps"]:
            step_result = self._execute_step(step, ctx, agent, tool_registry)
            if step_result.action == "retry":
                time.sleep(step_result.backoff)
                continue
            elif step_result.action == "escalate":
                return self._escalate(ctx, reason=step_result.reason)
            elif step_result.action == "continue":
                last_step = step_result
                continue

        if ctx.attempt < ctx.max_attempts:
            return f"Runbook recovered at step '{last_step}'. Retrying original task."
        else:
            return self._escalate(ctx, reason="max runbook attempts exceeded")

    def _execute_step(self, step, ctx, agent, tool_registry) -> StepResult:
        # Evaluate step in agent context — may call tools, check state, etc.
        # Returns: {action: "continue"|"retry"|"escalate", backoff?, reason?}
        # Guard: never execute destructive steps (DELETE, PATCH, WRITE) without
        #       confirming tool_registry.dry_run is False
        ...

    def _escalate(self, ctx, reason: str) -> str:
        self.cb.open()  # halt further retries per S-204
        return f"[ESCALATED] {ctx.operation_id}: {reason}"
```

**Key design principles:**

- Runbooks are data, not code — stored in YAML/JSON, versioned alongside the agent, reviewed like any other operational artifact
- Each runbook has an explicit `escalation` condition — the agent doesn't retry forever, it hands off after a defined threshold
- Destructive operations in runbook steps require explicit confirmation — prevents a runbook from compounding a failure by mutating state
- Runbook coverage is measured: after every incident, ask "was this in a runbook?" If not, add it

## Measuring runbook coverage

Track the ratio of failures that resolve via runbook vs. escalate to humans:

```
runbook_resolution_rate = runbook_resolved_failures / total_failures
mean_time_to_recovery   = avg(seconds from failure to runbook resolution)
escalation_rate          = escalations / total_failures  # target: < 10%
```

A mature agent system targets >90% runbook resolution rate on known failure categories. New failure types start at 0% coverage and get a runbook written within 24 hours of the first occurrence.

## Receipt

> Receipt pending — June 30, 2026

## See also

- [S-200 · Agent Reliability Compounding](stacks/s200-agent-reliability-compounding.md) — the math behind why step-level reliability matters
- [S-204 · Agent Circuit Breaker](stacks/s204-agent-circuit-breaker.md) — the infrastructure guardrail that stops runbook-exhausted agents from compounding damage
- [F-05 · Agent Failure Taxonomy](forward-deployed/f05-agent-failure-taxonomy.md) — classifying failures by type and severity to drive runbook prioritization
