# S-199 · Agent Self-Healing Loops

Agents fail silently. A traditional service crashes and surfaces an error code — you can detect it, alert on it, handle it. An agent fails by returning a wrong answer, skipping a tool call, entering a loop, or stalling indefinitely. No exception is thrown. No HTTP 500 is returned. The agent just keeps running, burning budget and producing garbage. Self-healing is the architectural pattern that closes this gap: the agent (or its infrastructure) detects that something went wrong, classifies the failure mode, and applies a recovery strategy — without human intervention.

## Forces

- Most agent failures don't throw exceptions — they produce wrong or incomplete outputs. Detection requires a semantic or behavioral check, not just a try/catch
- Recovery strategies are failure-mode-specific: a rate-limit error calls for a backoff, a loop detector calls for context compaction, a parsing failure calls for a retry with a corrected schema — you can't have one generic "try again"
- Self-healing loops add latency and cost per recovery attempt. Unbounded retry without escalation = infinite loop with a budget burn
- The agent may be the worst entity to judge its own recovery: a model that failed once may not recognize why, and may repeat the same bad strategy
- Recovery state must be managed across attempts — "we already tried approach A twice" — or the agent re-attempts the same failed strategy
- Human-in-the-loop ([F-09](../forward-deployed/f09-human-in-the-loop.md)) complicates self-healing: a paused task awaiting approval may need to heal on wake, not just on the first execution

## The move

**Three-layer architecture:**

### Layer 1 — Failure Detection

Instrument checks that fire after each step or at defined milestones:

```
# Failure detectors
- Tool call returns null / error object → detected
- Tool call result violates schema → detected
- Model output fails to parse → detected
- Agent enters same tool call 3x in a row → loop detected
- Agent consumes >N tokens without producing a final answer → stall detected
- LLM judge scores response below threshold → quality failure detected
- Latency exceeds SLO → timeout detected
```

Detection is the prerequisite. Without it, there is nothing to heal from.

### Layer 2 — Failure Classification

Route the detected failure to the correct recovery handler. Classify into tiers:

| Tier | Failure Type | Recovery Strategy |
|------|-------------|-----------------|
| T1 | Transient (rate limit, timeout, network blip) | Retry with backoff — [F-20](../forward-deployed/f20-rate-limits-and-retry.md) |
| T2 | Semantic (model ignored a constraint, wrong tool selected) | Retry with augmented prompt + explicit constraint reminder |
| T3 | Structural (context overflow, loop, parsing failure) | Compactor / replanner — [S-21](../stacks/s21-context-compaction.md) |
| T4 | Permanent (API down, tool not available, quota exhausted) | Fallback chain → partial result — [S-96](../stacks/s96-tool-fallback-chains.md) |
| T5 | Unknown | Human-in-the-loop escalation — [F-09](../forward-deployed/f09-human-in-the-loop.md) |

Do not route T2 failures to T1 handlers. A rate-limit backoff does not fix a model that hallucinated a tool argument.

### Layer 3 — Recovery with State

Track recovery history so the agent doesn't repeat failed strategies:

```python
class SelfHealingAgent:
    def __init__(self, max_t1_retries=3, max_t2_retries=2):
        self.attempt_log: list[AttemptRecord] = []
        self.failure_classifier = FailureClassifier()
        self.strategy_registry = StrategyRegistry()

    def step(self, state: AgentState) -> AgentState:
        result = self.execute_step(state)

        if not self.is_failure(result):
            return result

        tier = self.failure_classifier.classify(result, state)
        history = self.get_recovery_history(
            failure_signature=result.signature,
            max_attempts=self.max_retries_for(tier)
        )

        if history.exhausted(tier):
            return self.escalate(state, tier, history)

        strategy = self.strategy_registry.get(tier, history)
        self.attempt_log.append(AttemptRecord(
            signature=result.signature,
            tier=tier,
            strategy=strategy.name,
            attempt=history.count + 1
        ))
        return self.execute_with_strategy(state, strategy)

    def is_failure(self, result) -> bool:
        # Multi-signal: parse check, schema check, judge score, loop check
        return (
            result.parse_error
            or result.schema_violation
            or result.judge_score < self.quality_threshold
            or result.in_loop
        )
```

**Escalation budget:** Each tier has a maximum attempt count. When exhausted, move to the next tier or escalate to human. T5 is always human-in-the-loop — do not loop on unknown failures indefinitely.

**Healing on wake:** When a durable-execution agent ([F-15](../forward-deployed/f15-durable-execution.md)) resumes after a pause, run a health check on preconditions before continuing. The world may have changed: a tool's API contract may have shifted, a session token may have expired, data may have moved.

## Receipt

> Receipt pending — June 29, 2026

## See also

- [S-96 · Tool Fallback Chains](s96-tool-fallback-chains.md) — tool-level fallbacks (Tier 4 of the recovery stack)
- [F-24 · Graceful Degradation](../forward-deployed/f24-graceful-degradation.md) — service-level fault tolerance
- [S-21 · Context Compaction](../stacks/s21-context-compaction.md) — the structural recovery strategy for Tier 3 failures
- [F-15 · Durable Execution](../forward-deployed/f15-durable-execution.md) — checkpoint/resume that self-healing extends across interruptions
