# S-638 · Agent Spend Guardrails: The Multiplication Problem

[An agent without hard cost limits will bankrupt its operator — not through one bad prompt, but through the silent compounding of retries, loops, escalations, and fallback chains.]

## Forces
- An agent's actual cost bears no obvious relationship to the input token count — retries multiply calls, tool loops expand context, fallback chains add sequential model calls, and long-running sessions accumulate charges across every turn
- A $0.01 request can silently become a $5 multi-step loop — the multiplication effect is invisible without instrumentation, and catastrophic without hard caps
- Provider dashboards show account-level spend after the fact; by the time the invoice arrives, the damage is already done
- The agent loop has no natural ceiling — unlike a workflow with defined stages, the model decides how many tool calls and turns to make, unbounded by any cost constraint unless explicitly enforced
- Every existing cost entry (S-105, S-107, S-160, F-88, F-08) covers a specific dimension (per-call threshold, per-stage output budget, tool call count, session dollar ceiling, cost attribution) — none addresses the structural multiplication problem as a unified design pattern requiring deterministic stop conditions

## The move

Agent spend guardrails are hardcoded, non-overrideable caps placed at the execution layer — not in the prompt, not in an observability dashboard, but as infrastructure-level policy that fires before the agent can loop again.

**Five guardrail types that address the multiplication problem:**

### 1. Per-request dollar cap
Hard ceiling on cost per user request. Enforced in the orchestration layer before each model call. Fires as a deterministic stop — the agent terminates cleanly and returns a partial result with a cost-exceeded notice.

```python
class SpendGuardrail:
    def __init__(self, per_request_cap_usd: float, global_cap_usd: float):
        self.per_request_cap = per_request_cap_usd  # e.g. 0.50
        self.global_daily_cap = global_cap_usd     # e.g. 100.00
        self.request_costs: dict[str, float] = {}
        self.daily_costs: float = 0.0

    def before_model_call(self, request_id: str, estimated_cost: float) -> bool:
        """Returns True if the call is allowed. Called BEFORE every LLM call."""
        current = self.request_costs.get(request_id, 0.0)

        if current + estimated_cost > self.per_request_cap:
            return False  # Hard stop — cannot be overridden by prompt
        if self.daily_costs + estimated_cost > self.global_daily_cap:
            return False  # Global ceiling reached

        return True

    def after_model_call(self, request_id: str, actual_cost: float):
        self.request_costs[request_id] = (
            self.request_costs.get(request_id, 0.0) + actual_cost
        )
        self.daily_costs += actual_cost
```

### 2. Step count budget
Caps the number of agent turns (model calls) per task. Catches the repetitive search loop failure mode where a tool fails to satisfy the model's internal quality bar and the model keeps calling it. Independent of dollar cost — a step budget fires even when each call is cheap.

```python
MAX_STEPS = 20  # Hard cap — not adjustable by prompt instruction

class StepBudgetGuardrail:
    def __init__(self, max_steps: int):
        self.max_steps = max_steps
        self.step_counts: dict[str, int] = {}

    def before_tool_call(self, request_id: str) -> bool:
        steps = self.step_counts.get(request_id, 0)
        if steps >= self.max_steps:
            return False
        self.step_counts[request_id] = steps + 1
        return True

    def reset(self, request_id: str):
        self.step_counts.pop(request_id, None)
```

### 3. Retry circuit breaker
Limits retry attempts per tool. Without this, a failing tool call (network timeout, rate limit, 500) triggers exponential backoff retries that silently multiply cost. The breaker also prevents the fallback chain problem — when tool A fails, tool B fires; if B also fails, a third fallback fires, and the cumulative cost exceeds what any single call would have cost.

```python
MAX_RETRIES_PER_TOOL = 2

retry_counts: dict[str, int] = defaultdict(int)

def call_with_breaker(tool_name: str, fn, *args, **kwargs):
    if retry_counts[tool_name] >= MAX_RETRIES_PER_TOOL:
        raise CircuitOpen(f"Tool '{tool_name}' exceeded retry cap ({MAX_RETRIES_PER_TOOL}). Stopping.")
    try:
        result = fn(*args, **kwargs)
        retry_counts[tool_name] = 0  # Reset on success
        return result
    except ToolError as e:
        retry_counts[tool_name] += 1
        raise CircuitOpen(f"Tool '{tool_name}' failed after {retry_counts[tool_name]} retries: {e}")
```

### 4. Escalation budget
In planner-worker architectures (S-357), the supervisor model's cost is often 2–4× the worker's. Without an escalation cap, a planner that delegates aggressively can rack up significant spend through repeated supervisor calls. Track escalation depth and cap it.

```python
MAX_ESCALATION_DEPTH = 3  # Supervisor → sub-supervisor → sub-sub-supervisor

def should_escalate(depth: int, estimated_cost: float) -> bool:
    if depth >= MAX_ESCALATION_DEPTH:
        return False  # Cap escalation depth
    return True
```

### 5. Multiplier audit log
Guardrails that only stop are half the solution — you also need to track *why* they fired. A multiplier audit log records the chain of events that produced the cost: initial request → tool call 1 → retry 1 → retry 2 → fallback → tool call 2 → success. Without this trace, you can't distinguish a legitimate multi-step task from a retry loop.

```python
import time, json

multiplier_log: list[dict] = []

def log_call(request_id: str, event: str, cost: float, metadata: dict):
    multiplier_log.append({
        "ts": time.time(),
        "request_id": request_id,
        "event": event,
        "cost_usd": cost,
        **metadata
    })
    # Post to observability platform (Langfuse, AgentOps, custom)
    post_to_langfuse(request_id, event, cost, metadata)
```

**Deployment rule:** Guardrails must be implemented as infrastructure-level policy, not prompt instructions. A model cannot be trusted to respect a budget instruction embedded in its own prompt — it will reason around it when the task is incomplete. The cap fires at the orchestration layer, before the model call is made.

## Receipt
> Verified 2026-07-05 — Pattern documented from LLM CFO research (2026-05-04), UData blog (2026-06-12), and Production AI Institute post-incident analysis of the DN42 network scan. DN42 incident: autonomous agent with no hard cap scanned an experimental network and accumulated $6,531 in API charges before the operator intervened. Root cause: five missing controls (spend caps, oversight checkpoints, boundary definitions, real-time auditability, deployment readiness gate). The multiplication effect — retries × fallback chains × escalations × tool loops — was not visible at any single step.

## See also
- [S-160 · Tool Call Count Budget](s160-tool-call-count-budget.md) — count budget catches the repetitive search loop that dollar ceilings miss
- [F-88 · Session Cost Ceiling](f88-session-cost-ceiling.md) — dollar-denominated session ceiling; S-638 complements it with step, retry, and escalation budgets
- [F-08 · Agent Cost Control](f08-agent-cost-control.md) — cost attribution and per-task measurement; guardrails are the enforcement layer for those measurements
- [S-105 · Data Call Cost Threshold](s105-data-call-cost-threshold.md) — per-API-call economic justification gate; guardrails prevent threshold-flooding via retries
