# F-192 · Cost Velocity Circuit Breaker

An agent starts burning tokens at 3× the expected rate. In 12 minutes it has spent $47. Nobody notices for two hours because the session budget cap is $200. The velocity spike — the leading indicator — was visible from minute two, but no mechanism existed to read it and act. A cost velocity circuit breaker closes that gap: it watches the *rate* of spend, not just the total, and trips before the budget is gone.

## Forces

- **Static budgets are reactive.** A $200 session cap lets an agent burn $199 before it stops. At $8/min, that's 25 minutes of damage. The budget is a ceiling; it says nothing about whether you are approaching it fast.
- **Velocity is the leading indicator.** A token spiral starts fast and stays fast. A 3× rate spike at minute 2 predicts a $200 blowout by minute 15. A static cap only fires after the damage.
- **Per-task rates differ.** A 10-step research agent at $0.50/step costs $5 normally. The same agent in a loop at $0.50/step still looks like $5 total — until you count steps-per-minute, not just total steps.
- **Provider spend limits are too coarse.** OpenAI and Anthropic caps apply per-org, per-month. A runaway agent can exhaust a team's monthly budget in one workflow without triggering any per-session alert.

## The move

Layer three velocity signals on top of your existing budget caps:

**1. Spend rate gate — check before each LLM call.**
Track rolling spend rate (e.g., last 60 seconds). Before the next call, project whether the current rate will exceed budget before task completion. If projected cost exceeds the remaining budget at current velocity, fail the call with a named exception (`CostVelocityExceeded`).

```python
import time
from dataclasses import dataclass, field
from typing import List

@dataclass
class CostVelocityBreaker:
    """Detects token spirals via two conditions:
    1. Budget near-exhaustion (remaining < 2 * max_cost_per_call)
    2. Consecutive high-rate calls exceeding threshold"""

    budget_usd: float
    max_cost_per_call: float       # expected upper bound per call
    consecutive_threshold: int = 3  # trip after N consecutive above-max calls
    warmup: int = 3                # don't evaluate during warmup

    _log: List[float] = field(default_factory=list)
    _open: bool = False
    _consecutive_high: int = 0

    def track(self, prompt_tokens: int, completion_tokens: int, cost_per_1k: float):
        cost = (prompt_tokens + completion_tokens) / 1000 * cost_per_1k
        self._log.append(cost)
        if cost > self.max_cost_per_call:
            self._consecutive_high += 1
        else:
            self._consecutive_high = 0

    def check(self) -> bool:
        if self._open:
            return True
        if len(self._log) < self.warmup:
            return False
        total_spent = sum(self._log)
        remaining = self.budget_usd - total_spent
        # Condition 1: budget nearly exhausted
        if remaining < 2 * self.max_cost_per_call:
            self._open = True
            return True
        # Condition 2: consecutive high-rate calls
        if self._consecutive_high >= self.consecutive_threshold:
            self._open = True
            return True
        return False

    def reset(self):
        self._open = False
        self._log.clear()
        self._consecutive_high = 0


# Usage in agent loop
breaker = CostVelocityBreaker(budget_usd=5.0, max_cost_per_call=0.05)

def agent_step(messages):
    # ... do work ...
    response = openai.chat.completions.create(
        model="gpt-4o", messages=messages
    )
    usage = response.usage
    breaker.track(usage.prompt_tokens, usage.completion_tokens, 0.03)
    if breaker.check():
        raise CostVelocityExceeded(
            f"Budget nearly exhausted: ${sum(breaker._log):.4f} of ${breaker.budget_usd}"
        )
    return response
```

**3. Recovery.** After a trip, enter half-open: allow one test call at ≤ `max_cost_per_call`. If it succeeds, reopen. If it trips again, extend the open window exponentially (30s → 60s → 120s, cap at 5 min).

## Receipt

> Receipt pending — 2026-07-01

## See also

- [F-08 · Agent Cost Control](f08-agent-cost-control.md) — cost attribution and tracking foundation
- [F-118 · Real-Time Spend Rate Tracking](f118-real-time-spend-rate-tracking.md) — rate monitoring patterns
- [F-184 · Agent Loop Invariant Checking](f184-agent-loop-invariant-checking.md) — loop detection that pairs well with velocity enforcement
