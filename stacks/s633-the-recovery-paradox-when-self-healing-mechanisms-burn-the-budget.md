# S-633 · The Recovery Paradox: When Self-Healing Mechanisms Burn the Budget

Your agent has retry logic, context compaction, and a watchdog. You feel prepared. Then a subtle edge case triggers the retry. The retry fails. Compaction kicks in to handle the context. Compaction fails too. Each failure fires the next recovery layer, which fires the next, which fires the next — until 250,000 API calls are consumed in a single day and nobody noticed until the invoice arrived. This is the Recovery Paradox: the mechanisms designed to keep agents running are the mechanisms most likely to run them off a cliff.

## Forces

- **Agents compound failure in ways services don't.** A crashed microservice stops consuming resources. A looping agent accelerates consumption. Every recovery layer that fires without a ceiling adds another multiplicative factor to the blast radius.
- **Recovery logic is written when the system is healthy.** Engineers implement retry loops, compaction triggers, and spawn caps during calm conditions — when they can't anticipate the edge case that will make all three fire simultaneously.
- **LLM-based recovery is non-deterministic.** A retry loop backed by an LLM decision can decide to retry again. A compaction routine backed by an LLM can decide the context isn't compactable yet. Without a deterministic outer bound, the recovery layer feeds the failure.
- **The ceiling is always the last thing added.** Every incident post-mortem finds the same sentence: "The recovery logic had no maximum." The ceiling is never the exciting part to implement.
- **Silent failure is the default.** An agent consuming $8,000/hour with no progress looks identical to one making meaningful progress — until the bill arrives.

## The move

### 1. Name the five failure modes the recovery paradox amplifies

| Mode | What it looks like | Recovery layer it triggers |
|------|-------------------|--------------------------|
| **F1: Loop** | Same tool called with same args ≥3× in a row | Retry → re-planning → re-contextualization |
| **F2: Deadlock** | Two agents blocked on each other's output | Timeout → respawn → fan-out |
| **F3: Resource contention** | Multiple tools grabbing shared state | Retry → backoff → re-acquisition |
| **F4: Silent corruption** | Task claims success; environment state disagrees | Self-verify → re-verify → re-execute |
| **F5: Irreversible action** | Destructive call made on bad context | Rollback → compensating action → re-plan |

Each layer has its own trigger, its own retry budget, and — critically — its own ceiling requirement.

### 2. Apply the ceiling principle to every recovery layer

Every recovery mechanism needs an explicit, deterministic outer bound that is not an LLM call:

```python
from dataclasses import dataclass
from typing import Callable
import time

@dataclass
class RecoveryCeiling:
    """Every recovery layer gets one of these. No exceptions."""
    max_attempts: int          # e.g., 3 retries
    max_token_budget: int      # hard stop regardless of progress
    max_dollar_budget: float   # same, in dollars
    max_wall_time_seconds: float  # runaway in real time
    escalation_threshold: float # fraction of budget at which to alert

@dataclass
class RecoveryLayer:
    name: str
    ceiling: RecoveryCeiling
    execute: Callable           # the actual recovery action
    on_ceiling_hit: str = "ESCALATE"  # ESCALATE | ABORT | DEGRADE

# The five recovery layers, each with a ceiling
LOOP_RECOVERY = RecoveryLayer(
    name="loop_recovery",
    ceiling=RecoveryCeiling(
        max_attempts=2,           # retry 2×, then escalate
        max_token_budget=8_000,    # ~$0.02 at Claude Haiku pricing
        max_dollar_budget=0.05,
        max_wall_time_seconds=30,
        escalation_threshold=0.7,
    ),
    execute=retry_with_backoff,
    on_ceiling_hit="ESCALATE",
)

COMPACTION_RECOVERY = RecoveryLayer(
    name="compaction_recovery",
    ceiling=RecoveryCeiling(
        max_attempts=1,            # compaction fails mean context is toxic
        max_token_budget=2_000,    # one compaction call budget
        max_dollar_budget=0.01,
        max_wall_time_seconds=5,
        escalation_threshold=0.5,
    ),
    execute=compact_context,
    on_ceiling_hit="ABORT",       # don't retry — abort the task
)

SPAWN_RECOVERY = RecoveryLayer(
    name="spawn_recovery",
    ceiling=RecoveryCeiling(
        max_attempts=0,            # spawning is not a recovery attempt
        max_token_budget=0,
        max_dollar_budget=0,
        max_wall_time_seconds=0,
        escalation_threshold=0.0,
    ),
    execute=None,                 # never auto-spawn; only human approval
    on_ceiling_hit="ABORT",
)
```

### 3. Run the watchdog as a deterministic process, not an LLM

The supervisor that enforces ceilings must not itself use an LLM. If the watchdog is an LLM, it can decide to continue — defeating the purpose. Use a deterministic process (a simple Python loop, a finite state machine, a rule engine):

```python
class SupervisorWatchdog:
    """Deterministic. No LLM in the enforcement path."""

    def __init__(self, layers: list[RecoveryLayer], agent_fn: Callable):
        self.layers = layers
        self.agent_fn = agent_fn
        self.state = "CLOSED"   # CLOSED | HALF_OPEN | OPEN
        self.metrics = {"tokens": 0, "dollars": 0.0, "attempts": {}, "start": time.time()}

    def step(self, prompt: str) -> str:
        self._check_ceiling_hits()
        self._check_state_transitions()

        if self.state == "OPEN":
            raise BudgetExhaustedError(
                f"Agent budget exhausted: ${self.metrics['dollars']:.4f} "
                f"spent, {self.metrics['tokens']} tokens, "
                f"{time.time() - self.metrics['start']:.1f}s elapsed. "
                f"State={self.state}"
            )

        # HALF_OPEN: allow one probe call
        if self.state == "HALF_OPEN":
            result = self._probe()
            if result.success:
                self.state = "CLOSED"
            else:
                self.state = "OPEN"
            return result

        # CLOSED: run the agent, track spending
        result = self.agent_fn(prompt)
        self.metrics["tokens"] += result.tokens_used
        self.metrics["dollars"] += result.cost
        return result

    def _check_ceiling_hits(self):
        for layer in self.layers:
            tokens = self.metrics["tokens"]
            dollars = self.metrics["dollars"]
            elapsed = time.time() - self.metrics["start"]

            # Check each ceiling
            if tokens >= layer.ceiling.max_token_budget:
                self.state = "OPEN"
                log_circuit_breaker_event(
                    trigger="token_budget",
                    layer=layer.name,
                    value=tokens,
                    ceiling=layer.ceiling.max_token_budget,
                )
            if dollars >= layer.ceiling.max_dollar_budget:
                self.state = "OPEN"
                log_circuit_breaker_event(
                    trigger="dollar_budget",
                    layer=layer.name,
                    value=dollars,
                    ceiling=layer.ceiling.max_dollar_budget,
                )
            if elapsed >= layer.ceiling.max_wall_time_seconds:
                self.state = "OPEN"
                log_circuit_breaker_event(
                    trigger="wall_time",
                    layer=layer.name,
                    value=elapsed,
                    ceiling=layer.ceiling.max_wall_time_seconds,
                )

    def _check_state_transitions(self):
        # HALF_OPEN after 60s cooldown
        if self.state == "OPEN" and time.time() - self._last_open > 60:
            self.state = "HALF_OPEN"

    def _probe(self) -> ProbeResult:
        """Lightweight health check — deterministic, no LLM."""
        return ProbeResult(
            success=(self.metrics["tokens"] < 1000),
            tokens=self.metrics["tokens"],
        )
```

### 4. Implement graceful degradation on budget hit

When the ceiling fires, don't kill the task silently. Return a structured failure that the calling system can act on:

```python
@dataclass
class AgentResult:
    content: str | None
    status: str              # SUCCESS | PARTIAL | CEILING_HIT | FAILURE
    error_code: str | None   # TOKEN_EXHAUSTED | DOLLAR_EXCEEDED | TIMEOUT | DEADLOCK
    checkpoint: dict | None # Resumable state for follow-up attempts
    metrics: dict            # tokens, cost, duration, attempts


def run_with_ceiling(agent_fn, prompt, ceiling: RecoveryCeiling) -> AgentResult:
    watchdog = SupervisorWatchdog([LOOP_RECOVERY, COMPACTION_RECOVERY], agent_fn)
    try:
        result = watchdog.step(prompt)
        return AgentResult(
            content=result.content,
            status="SUCCESS",
            error_code=None,
            checkpoint=result.state_snapshot,
            metrics=watchdog.metrics,
        )
    except BudgetExhaustedError as e:
        return AgentResult(
            content=None,
            status="CEILING_HIT",
            error_code=e.code,          # e.g., "DOLLAR_EXCEEDED"
            checkpoint=e.last_checkpoint,
            metrics=watchdog.metrics,
        )
```

### 5. The one-question audit

Before shipping any recovery mechanism, answer this: **"If this recovery layer fires every time for the next 24 hours, what is the maximum cost?"**

If the answer is more than your weekly budget for this agent, the recovery layer needs a ceiling added before it ships.

## Receipt

> Verified 2026-07-05 — Case documented by Zylos Research (2026-05-06): Claude Code compaction recovery loop without ceiling burned ~250,000 API calls in one day. Trigger: consecutive compaction failures. Recovery logic had no attempt ceiling. Pattern confirmed across agentic FinOps reports (Cordum, TokenFence, AgentMarketCap, 2026).

## See also

- [S-362 · Budget-Aware Agents](s362-budget-aware-agents-cost-self-regulation.md) — cost as a behavioral dimension; this entry is about the recovery layer specifically
- [S-109 · Agent Idle Cost](s109-agent-idle-cost.md) — idle agents are symptoms of failed recovery loops
- [S-561 · The Self-Correction Gap](s561-the-self-correction-gap-when-agents-cant-self-heal.md) — signal quality for self-correction; this entry is about why ceiling beats signal
- [I-048 · Signal Hierarchy for Self-Correction](s561-the-self-correction-gap-when-agents-cant-self-heal.md) — Level 1–3 signal types; ceiling principles apply to all three
