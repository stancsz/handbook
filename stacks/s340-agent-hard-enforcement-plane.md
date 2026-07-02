# [S-340] · Agent Hard Enforcement Plane

The agent's LLM decides to call a sensitive tool, loop for 30 turns, and spend $200. The model is still returning 200 OK. Nothing stopped it. The enforcement plane — the deterministic layer between the agent's *intent* and the action's *execution* — was missing. This entry is the pattern: one wrapper that enforces hard cost caps, loop bounds, tool call restrictions, and escalation gates before any of them can compound into an incident.

## Forces

- **LLM guardrails fail at scale.** An LLM monitoring another LLM adds latency, cost, and a circular dependency. The guardian model has the same failure modes as the agent it watches.
- **Production failures compound silently.** One tool call becomes 30. 30 turns at 50k tokens each becomes $125. A forbidden tool becomes a data breach. Each escalation is individually rational — the LLM got a plausible-looking response.
- **Incremental enforcement is not enforcement.** Adding one hard limit after the first incident, then another after the second, produces a fragile stack. A unified plane means every bound is enforced together and auditably.
- **Escalation is a first-class concern, not an afterthought.** When an agent wants to send an email, exfiltrate data, or spend beyond its task budget, a human should decide — and the enforcement plane should make that a blocking gate, not a log entry.

## The move

Wrap the entire agent run in an `AgentEnforcementPlane`. It is not a prompt, not an LLM call, and not a retry — it is a deterministic execution guard that intercepts before each tool call and after each step.

### The enforcement plane

```python
from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from enum import Enum
import time

class EscalationAction(Enum):
    BLOCK = "block"          # hard stop, return error
    APPROVE = "approve"      # human approved ahead of time
    ESCALATE = "escalate"    # pause, request human decision
    ALLOW = "allow"          # proceed normally

@dataclass
class EnforcementConfig:
    max_iterations: int = 20
    max_duration_seconds: float = 300.0
    max_cost_cents: float = 500.0          # per-run hard cap
    cost_velocity_cents_per_min: float = 200.0  # circuit breaker rate
    max_tool_calls_per_tool: dict[str, int] = field(default_factory=dict)  # e.g. {"send_email": 1}
    escalation_threshold_cents: float = 50.0  # human gate above this spend
    forbidden_tools: list[str] = field(default_factory=list)

@dataclass
class RunMetrics:
    iterations: int = 0
    total_cost_cents: float = 0.0
    tool_call_counts: dict[str, int] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    cost_velocity_history: list[tuple[float, float]] = field(default_factory=list)  # (ts, cents)

class EscalationRequired(Exception):
    """Raised when a human decision is needed before the agent can continue."""
    def __init__(self, reason: str, context: dict):
        super().__init__(reason)
        self.reason = reason
        self.context = context

class EnforcementViolation(Exception):
    """Raised when a hard limit is breached."""
    def __init__(self, limit_type: str, value: Any, threshold: Any):
        super().__init__(f"{limit_type}: {value} exceeds {threshold}")
        self.limit_type = limit_type
        self.value = value
        self.threshold = threshold

class AgentEnforcementPlane:
    """
    Deterministic enforcement wrapper for an agent run.
    Wraps tool calls and step boundaries with hard limits, cost tracking,
    velocity detection, and escalation gates — outside the LLM loop.
    """

    def __init__(
        self,
        config: EnforcementConfig,
        escalate_fn: Optional[Callable[[str, dict], EscalationAction]] = None,
    ):
        self.config = config
        self.escalate_fn = escalate_fn or (lambda r, c: EscalationAction.BLOCK)
        self.metrics = RunMetrics(start_time=time.time())
        self._first_spend_ts: Optional[float] = None

    def _check_hard_limits(self):
        """Called before each step. Raises EnforcementViolation on breach."""
        now = time.time()
        elapsed = now - self.metrics.start_time
        if elapsed > self.config.max_duration_seconds:
            raise EnforcementViolation("max_duration", f"{elapsed:.1f}s", f"{self.config.max_duration_seconds}s")

        if self.metrics.total_cost_cents > self.config.max_cost_cents:
            raise EnforcementViolation("max_cost", f"${self.metrics.total_cost_cents/100:.2f}", f"${self.config.max_cost_cents/100:.2f}")

        if self.metrics.iterations >= self.config.max_iterations:
            raise EnforcementViolation("max_iterations", self.metrics.iterations, self.config.max_iterations)

    def _check_cost_velocity(self):
        """Check if spend rate exceeds the circuit breaker threshold."""
        if self._first_spend_ts is None or self.metrics.total_cost_cents == 0:
            return

        now = time.time()
        elapsed_min = max((now - self._first_spend_ts) / 60.0, 0.1)
        velocity = self.metrics.total_cost_cents / elapsed_min

        if velocity > self.config.cost_velocity_cents_per_min:
            raise EnforcementViolation(
                "cost_velocity",
                f"${velocity:.1f}/min",
                f"${self.config.cost_velocity_cents_per_min:.1f}/min",
            )

    def _check_tool_restrictions(self, tool_name: str) -> EscalationAction:
        """Check per-tool call limits and escalation thresholds."""
        # Hard forbidden list
        if tool_name in self.config.forbidden_tools:
            raise EnforcementViolation("forbidden_tool", tool_name, self.config.forbidden_tools)

        # Per-tool call cap
        cap = self.config.max_tool_calls_per_tool.get(tool_name)
        if cap is not None:
            count = self.metrics.tool_call_counts.get(tool_name, 0)
            if count >= cap:
                raise EnforcementViolation(f"max_tool_calls:{tool_name}", count, cap)

        # Escalation gate (human approval for expensive or sensitive tools)
        if self.metrics.total_cost_cents > self.config.escalation_threshold_cents:
            action = self.escalate_fn(
                f"Spend threshold reached: ${self.metrics.total_cost_cents/100:.2f}",
                {"tool": tool_name, "cost_cents": self.metrics.total_cost_cents, "metrics": self.metrics.__dict__},
            )
            return action

        return EscalationAction.ALLOW

    def on_tool_result(self, tool_name: str, cost_cents: float):
        """Called after a tool returns. Updates metrics and checks velocity."""
        if self._first_spend_ts is None and cost_cents > 0:
            self._first_spend_ts = time.time()

        self.metrics.total_cost_cents += cost_cents
        self.metrics.tool_call_counts[tool_name] = self.metrics.tool_call_counts.get(tool_name, 0) + 1

        self._check_cost_velocity()

    def on_iteration(self):
        """Called before each new agent loop iteration."""
        self.metrics.iterations += 1
        self._check_hard_limits()

    def pre_tool_call(self, tool_name: str) -> EscalationAction:
        """Called before each tool call. Returns whether to proceed."""
        self._check_hard_limits()
        return self._check_tool_restrictions(tool_name)


# --- Example: wiring into a LangGraph-style agent ---

def run_agent_with_enforcement(
    agent_fn: Callable,
    config: EnforcementConfig,
    escalate_fn: Callable[[str, dict], EscalationAction],
):
    plane = AgentEnforcementPlane(config, escalate_fn)

    # Simple escalation implementation: prompt a human via webhook/Slack/etc.
    def blocking_escalate(reason: str, context: dict) -> EscalationAction:
        action = escalate_fn(reason, context)
        if action == EscalationAction.ESCALATE:
            raise EscalationRequired(reason, context)
        elif action == EscalationAction.BLOCK:
            raise EnforcementViolation("escalation_block", reason, "policy")
        return action

    plane.escalate_fn = blocking_escalate

    try:
        state = agent_fn.initial_state()
        while True:
            plane.on_iteration()
            step = agent_fn.next_step(state)

            if step.type == "tool_call":
                action = plane.pre_tool_call(step.tool_name)
                if action == EscalationAction.BLOCK:
                    state.result = {"error": f"Tool {step.tool_name} blocked by policy"}
                    break
                # Proceed with tool execution...
                result, cost = step.execute()
                plane.on_tool_result(step.tool_name, cost)

            elif step.type == "done":
                state.result = step.result
                break

    except EnforcementViolation as e:
        return {
            "error": "enforcement_violation",
            "limit": e.limit_type,
            "detail": str(e),
            "metrics": plane.metrics.__dict__,
        }
    except EscalationRequired as e:
        return {
            "error": "human_escalation_required",
            "reason": e.reason,
            "context": e.context,
            "metrics": plane.metrics.__dict__,
        }

    return state.result
```

### Key design decisions

- **Order of checks matters.** Tool restrictions are checked first (they can fire before cost accrues). Hard limits (iteration, duration, cost) are checked before each step. Velocity is checked after each tool result.
- **Velocity is measured from first spend, not first call.** A tool that returns fast and cheap followed by a loop is the failure mode — `first_spend_ts` is the right anchor.
- **Escalation is a first-class return type, not a log.** `EscalationRequired` propagates to the caller so the orchestrator can surface a human-in-the-loop prompt or queue an approval workflow.
- **Forbidden tools are hard blocks, not warnings.** Adding a tool to `forbidden_tools` is equivalent to removing it from the agent's capability set — no LLM opinion changes this.
- **`max_tool_calls_per_tool` is additive with per-run caps.** An agent with `max_iterations=20` and `max_tool_calls_per_tool={"send_email": 1}` will stop either at 20 turns or after one email — whichever comes first.

## Receipt

> Receipt pending — July 2, 2026

## See also

- [S-070 · Agent Loop Termination](s70-agent-loop-termination.md) — four concrete termination conditions and how to wire them
- [F-192 · Cost Velocity Circuit Breaker](f192-cost-velocity-circuit-breaker.md) — rate-based spend enforcement that trips before the budget is gone
- [S-238 · Deterministic Guardrails Outside the LLM Loop](s238-deterministic-guardrails-outside-the-llm-loop.md) — pattern-matching enforcement for PII, injection, and tool-level blocks
