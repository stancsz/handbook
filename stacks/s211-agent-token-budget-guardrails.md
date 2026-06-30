# S-211 · Agent Token Budget Guardrails

You deployed an agent loop on a Friday afternoon. By Monday it had cost $4,200 in API calls, sent 847 emails to the wrong recipients, and triggered three downstream incidents. The agent never crashed — it returned 200s and kept working. It was producing the wrong output fast, and nothing stopped it until someone read the bill. This is the failure mode token budget guardrails close: deterministically cutting off agents before cost compounds beyond a threshold you chose.

## Forces

- LLM calls are non-deterministic in cost — a web search, a longer-than-expected generation, a retrieval with high chunk counts — each multiplies the price of a single turn unpredictably
- Agent loops compound cost exponentially: 20 turns at 50k tokens each × $2.50/1M = $2.50 per run; 20 turns with a 5-token retry loop at the same rate = $125
- Multi-tenant SaaS amplifies the tail risk: one bad customer prompt can generate 100× the expected spend on your infrastructure budget
- Provider-level rate limits (OpenAI TPM, Anthropic AUC) don't map to your business logic — a limit of 1M tokens/minute tells you nothing about whether customer X should be allowed to spend $500/month
- The circuit breaker pattern (S-204) handles reliability failures; budget guardrails handle cost failures, which often occur without any reliability failure at all

## The move

Layer three independent controls — each catches a different failure mode:

**1. Per-turn token cap** — hard ceiling on input + output tokens per single LLM call. Catches runaway context extension and unexpectedly verbose models.

**2. Per-task budget pool** — a shared token quota across all turns of one task. Catches multi-turn loops. Track `used_tokens` cumulatively; abort and escalate when `used_tokens + projected_next_call > budget`.

**3. Per-agent periodic quota** — sliding window (1h / 24h / 30d) tracking spend per agent instance or per customer. Catches slow leaks and coordinated abuse.

On budget exceeded: log the event with full trace context, return a typed `BudgetExceeded` result to the orchestrator, and trigger the escalation path (fallback model, human-in-the-loop, or graceful failure) rather than silently continuing.

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
import time

class EscalationAction(Enum):
    FALLBACK_MODEL = "fallback_model"
    HUMAN_IN_THE_LOOP = "human_in_the_loop"
    GRACEFUL_FAIL = "graceful_fail"
    CIRCUIT_OPEN = "circuit_open"

@dataclass
class TokenBudget:
    per_turn_tokens: int = 128_000      # input + output cap per call
    per_task_tokens: int = 512_000       # cumulative across all turns
    per_agent_1h: int = 2_000_000        # sliding window, tokens/hour
    cost_per_1m_tokens_usd: float = 2.50  # your blended rate

@dataclass
class BudgetState:
    used_task_tokens: int = 0
    agent_1h_tokens: list[tuple[float, int]] = field(default_factory=list)
    total_spend_usd: float = 0.0
    budget_hits: int = 0

class BudgetExceeded(Exception):
    def __init__(self, level: str, used: int, budget: int, action: EscalationAction):
        self.level = level
        self.used = used
        self.budget = budget
        self.action = action
        spend = (used / 1_000_000) * 2.50
        super().__init__(
            f"Budget exceeded at {level}: {used:,} tokens used, "
            f"{budget:,} budget (~${spend:.2f}). Escalation: {action.value}"
        )

def _evict_stale_window(state: BudgetState, window_seconds: float = 3600):
    now = time.time()
    state.agent_1h_tokens = [
        (ts, t) for ts, t in state.agent_1h_tokens if now - ts < window_seconds
    ]

class TokenBudgetGuard:
    def __init__(self, budget: TokenBudget, escalation: EscalationAction = EscalationAction.GRACEFUL_FAIL):
        self.budget = budget
        self.escalation = escalation
        self.state = BudgetState()

    def _check_turn(self, input_tokens: int, output_tokens: int):
        total = input_tokens + output_tokens
        if total > self.budget.per_turn_tokens:
            raise BudgetExceeded("per_turn", total, self.budget.per_turn_tokens, self.escalation)

    def _check_task(self, new_tokens: int) -> int:
        projected = self.state.used_task_tokens + new_tokens
        if projected > self.budget.per_task_tokens:
            raise BudgetExceeded("per_task", projected, self.budget.per_task_tokens, self.escalation)
        self.state.used_task_tokens = projected
        return projected

    def _check_agent_window(self, new_tokens: int) -> int:
        _evict_stale_window(self.state)
        window_tokens = sum(t for _, t in self.state.agent_1h_tokens)
        if window_tokens + new_tokens > self.budget.per_agent_1h:
            raise BudgetExceeded("per_agent_1h", window_tokens + new_tokens, self.budget.per_agent_1h, self.escalation)
        self.state.agent_1h_tokens.append((time.time(), new_tokens))
        return window_tokens + new_tokens

    def _record_spend(self, tokens: int):
        cost = (tokens / 1_000_000) * self.budget.cost_per_1m_tokens_usd
        self.state.total_spend_usd += cost

    def wrap(self, llm_call: Callable, input_tokens: int) -> Callable:
        """
        Returns a guarded version of an LLM call.
        Call with: guarded_call(output_callback=my_handler)
        """
        def guarded(output_callback: Optional[Callable] = None, **kwargs):
            self._check_turn(input_tokens, 0)  # rough check; update post-call
            self._check_task(input_tokens)
            self._check_agent_window(input_tokens)

            result = llm_call(**kwargs)

            # Post-call: charge actual tokens
            actual_tokens = (input_tokens or 0) + (result.usage.total_tokens or 0)
            self._record_spend(actual_tokens)
            self.state.used_task_tokens += (result.usage.completion_tokens or 0)

            # If output is large, check per-turn after the fact
            if (result.usage.total_tokens or 0) > self.budget.per_turn_tokens:
                self.state.budget_hits += 1
                raise BudgetExceeded(
                    "per_turn_post", result.usage.total_tokens,
                    self.budget.per_turn_tokens, self.escalation
                )

            if output_callback:
                output_callback(result)
            return result

        return guarded

    def reset_task(self):
        """Call between independent tasks; preserves agent-window state."""
        self.state.used_task_tokens = 0

    def report(self) -> dict:
        _evict_stale_window(self.state)
        return {
            "task_tokens": self.state.used_task_tokens,
            "task_budget": self.budget.per_task_tokens,
            "agent_1h_tokens": sum(t for _, t in self.state.agent_1h_tokens),
            "agent_1h_budget": self.budget.per_agent_1h,
            "total_spend_usd": round(self.state.total_spend_usd, 4),
            "budget_hits": self.state.budget_hits,
        }
```

**Key decisions:**

- **Count input tokens before the call** — estimate from a fast tokenizer (tiktoken, HuggingFace) rather than waiting for the API response to know if you're over the per-turn cap
- **Post-call validation** — the per-turn cap is checked after output too, because you can't know output length in advance; this catches verbose generations
- **Sliding window** — agent 1h quota uses `_evict_stale_window` to keep the list bounded; O(n) per call is fine for realistic window sizes
- **Escalation is configurable** — `FALLBACK_MODEL` lets you swap to a cheaper provider mid-task; `HUMAN_IN_THE_LOOP` surfaces the context for review; `CIRCUIT_OPEN` (S-204) halts the agent entirely
- **Reset task state between tasks** — `reset_task()` clears the cumulative task counter but preserves the agent sliding window, so slow leaks are still caught

## Receipt

> Receipt pending — 2026-06-30. The pattern is validated across production implementations at multiple teams (documented in TokenFence's production checklist, llmeter.org budget guard research, and Lakera's agent cost-control benchmarks). Code above is a reference implementation — not yet run against a live trace.

## See also

- [S-204 · Agent Circuit Breaker](s204-agent-circuit-breaker.md) — complements budget guardrails; circuit breaker halts on reliability failures, budget guardrails halt on cost failures
- [S-208 · Per-Tenant LLM Cost Attribution](s208-per-tenant-llm-cost-attribution.md) — budget guardrails are the enforcement layer on top of the attribution data
- [S-205 · Agent Sandbox Isolation](s205-agent-sandbox-isolation.md) — containment prevents a budget-exceeded agent from doing further damage while it escalates
