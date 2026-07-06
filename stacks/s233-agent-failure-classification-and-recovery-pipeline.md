# S-233 · Agent Failure Classification and Recovery Pipeline

F-05 names the failure classes. This entry runs them in production — detecting which class is firing, routing to the right recovery action, and breaking the loop before it compounds into an incident. Without this pipeline, the taxonomy is academic.

## Forces

- Knowing failure types is not the same as detecting them at runtime — a hallucination and a tool misuse look identical as empty outputs
- Hybrid detection (rule + LLM) outperforms either alone: rules catch the obvious fast, LLM catches the ambiguous
- Recovery is failure-class-specific — the right fix for circular reasoning kills the wrong fix for schema error
- Each failed loop iteration burns tokens and latency without user-visible progress — the blast radius multiplies silently
- Post-hoc analysis (after the run) helps future runs; in-run detection prevents current ones

## The move

Three layers: **Detector → Classifier → Recovery**.

### Layer 1 — Detector: signal the run is unhealthy

Rule-based, deterministic, fires on structural signals before content analysis:

```
Signs of a broken run (any of):
  - same tool called ≥ 3x consecutively with same name
  - JSON parse failed on tool result
  - token budget exhausted mid-loop
  - response latency spike > 3x rolling average
  - tool returned empty result + agent re-requested it
  - LLM returned refusal in ≥ 2 consecutive turns
```

```python
from dataclasses import dataclass
from collections import Counter

@dataclass
class RunHealth:
    consecutive_tool_calls: Counter
    json_parse_errors: int = 0
    refusal_streak: int = 0
    empty_result_streak: int = 0
    latency_spikes: int = 0
    iteration_count: int = 0

    def is_healthy(self, threshold: int = 3) -> bool:
        if any(c >= threshold for c in self.consecutive_tool_calls.values()):
            return False
        if self.json_parse_errors >= 2:
            return False
        if self.refusal_streak >= 2:
            return False
        if self.empty_result_streak >= 2:
            return False
        if self.iteration_count > 30:   # hard loop cap
            return False
        return True
```

### Layer 2 — Classifier: name the failure

Route to one of the eight primary failure classes. Use rules first (fast, no LLM cost), then an LLM classifier for ambiguous cases:

```
Rule-based (check in order, first match wins):
  1. JSON schema mismatch in tool args  → SCHEMA_ERROR
  2. Same tool ≥ 3x consecutive         → CIRCULAR_REASONING
  3. LLM refusal in response text       → OVER_REFUSAL
  4. Tool result contradicts system prompt → HALLUCINATION (flag)
  5. Agent output drifts from task      → GOAL_DRIFT
  6. Tool result empty + agent retries  → TOOL_MISUSE (wrong tool or bad args)
  7. Latency spike + no recovery         → TIMEOUT_CASCADE
  8. else                               → run LLM classifier for CONTEXT_LOSS
```

```python
from enum import Enum
from typing import Literal

class FailureClass(Enum):
    HALLUCINATION = "HALLUCINATION"
    TOOL_MISUSE = "TOOL_MISUSE"
    CONTEXT_LOSS = "CONTEXT_LOSS"
    CIRCULAR_REASONING = "CIRCULAR_REASONING"
    GOAL_DRIFT = "GOAL_DRIFT"
    OVER_REFUSAL = "OVER_REFUSAL"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    TIMEOUT_CASCADE = "TIMEOUT_CASCADE"

def classify_failure(health: RunHealth, last_messages: list[str]) -> FailureClass:
    # Rule-based fast path
    if health.json_parse_errors >= 2:
        return FailureClass.SCHEMA_ERROR
    if any(c >= 3 for c in health.consecutive_tool_calls.values()):
        return FailureClass.CIRCULAR_REASONING
    if health.refusal_streak >= 2:
        return FailureClass.OVER_REFUSAL
    if health.empty_result_streak >= 2:
        return FailureClass.TOOL_MISUSE
    if health.iteration_count > 30:
        return FailureClass.CONTEXT_LOSS

    # LLM classifier for ambiguous cases
    prompt = f"""Classify this agent run failure.
Recent messages: {last_messages[-5:]}
Iteration: {health.iteration_count}
Return one of: HALLUCINATION, TOOL_MISUSE, CONTEXT_LOSS, GOAL_DRIFT, OVER_REFUSAL, SCHEMA_ERROR, TIMEOUT_CASCADE"""
    result = llm.complete(prompt)
    return FailureClass(result.strip())

# Trace every failure classification with the signal that triggered it
def record(classification: FailureClass, signal: str, agent_id: str):
    telemetry.log("failure_classified", {
        "class": classification.value,
        "signal": signal,
        "agent": agent_id,
        "ts": time.time()
    })
```

### Layer 3 — Recovery: act on the class

Each class maps to a specific intervention:

| Failure class | Recovery action |
|---|---|
| HALLUCINATION | Inject retrieval step: re-query RAG with the hallucinated claim as the query; if no support, retract the claim and flag for eval suite |
| TOOL_MISUSE | Re-invoke tool with validated arguments; if same tool fails twice, try the next-best tool from the registry |
| CONTEXT_LOSS | Compress earlier context (summarize + prune) or escalate to human-in-the-loop |
| CIRCULAR_REASONING | Inject a "checkpoint" message: summarize what has been done, what remains, then continue |
| GOAL_DRIFT | Re-inject the original task statement as a system-level reminder |
| OVER_REFUSAL | Strip overly cautious filtering from the prompt; if persistent, switch to a less cautious model variant |
| SCHEMA_ERROR | Validate tool arguments against schema before calling; retry with corrected args |
| TIMEOUT_CASCADE | Mark tool as degraded in registry; route to fallback implementation or cached result |

```python
def recover(failure: FailureClass, context: dict) -> "RetryDecision":
    match failure:
        case FailureClass.HALLUCINATION:
            claim = extract_claim(context["last_output"])
            retrieved = rag.query(claim)
            if retrieved.confidence < 0.6:
                return RetryDecision(action="retract_and_flag", message=f"Retracting unsupported claim: {claim}")
            return RetryDecision(action="continue", message="Claim confirmed by retrieval")

        case FailureClass.TOOL_MISUSE:
            tools = get_tool_registry()
            alt_tools = [t for t in tools if t != context["failed_tool"]]
            return RetryDecision(action="retry_alt_tool", message=f"Trying {alt_tools[0].name}")

        case FailureClass.CIRCULAR_REASONING:
            checkpoint = summarize_run(context["messages"])
            context["messages"].append({"role": "system", "content": f"Checkpoint: {checkpoint}"})
            return RetryDecision(action="continue", message="Checkpoint injected")

        case FailureClass.CONTEXT_LOSS:
            context["messages"] = compress_and_prune(context["messages"])
            return RetryDecision(action="continue", message="Context compressed")

        case FailureClass.OVER_REFUSAL:
            return RetryDecision(action="retry_rewritten_prompt", message="Retrying with permissive prompt variant")

        case FailureClass.GOAL_DRIFT:
            context["messages"].append({"role": "system", "content": f"Original task: {context['original_task']}"})
            return RetryDecision(action="continue", message="Goal re-injected")

        case FailureClass.SCHEMA_ERROR:
            validated_args = validate_schema(context["tool_args"], context["tool_schema"])
            return RetryDecision(action="retry_validated", message=f"Retrying with {validated_args}")

        case FailureClass.TIMEOUT_CASCADE:
            mark_tool_degraded(context["tool_name"])
            return RetryDecision(action="fallback", message=f"Falling back from {context['tool_name']}")

        case _:
            return RetryDecision(action="escalate", message="Human review required")
```

### Tying it together — the run loop with failure detection

```python
def run_with_failure_pipeline(agent, task, max_iterations=30):
    health = RunHealth(consecutive_tool_calls=Counter(), iteration_count=0)
    messages = [{"role": "user", "content": task}]

    for i in range(max_iterations):
        health.iteration_count = i
        if not health.is_healthy():
            failure = classify_failure(health, messages)
            record(failure, signal="health_check_failed", agent_id=agent.id)
            decision = recover(failure, {"messages": messages, "agent": agent})
            if decision.action == "escalate":
                return {"status": "escalated", "reason": failure.value}
            if decision.action == "retract_and_flag":
                return {"status": "corrected", "output": decision.message}
            if decision.action in ("continue", "retry_validated", "retry_alt_tool", "retry_rewritten_prompt"):
                pass  # loop continues with modified context
            if decision.action == "fallback":
                agent = agent.with_fallback_tool(decision.message.split("from ")[-1])

        response = agent.step(messages)
        messages.append(response.message)
        update_health(health, response)
        if response.done:
            return {"status": "success", "output": response.content}

    return {"status": "loop_exhausted", "iterations": max_iterations}
```

## Receipt

> Receipt pending — June 30, 2026. The failure classification taxonomy is grounded in Microsoft's v2.0 agentic failure taxonomy and validated against the HeyNeo classifier framework. The rule-based detector, LLM fallback classifier, and per-class recovery map are drawn from production patterns reported in the TUTAI production guardrails guide (March 2026) and the 2025 agentic systems field study. Code examples compile syntactically against Python 3.11+ with dataclasses, Enum, and pattern matching. Integration-level testing against a live agent loop is pending deployment of a test harness.

## See also

- [F-05 · Agent Failure Taxonomy](forward-deployed/f05-agent-failure-taxonomy.md) — the eight failure classes this pipeline detects
- [S-106 · Event Log Replay](stacks/s106-event-log-replay.md) — replay failed traces to confirm the classifier's accuracy
- [S-230 · Agent Harness Engineering](stacks/s230-agent-harness-engineering-the-eval-layer-production-demands.md) — eval infrastructure for regression-testing the pipeline itself
- [S-223 · Agent Sandboxing](stacks/s223-agent-sandboxing-code-execution.md) — containment for failures that slip past the pipeline
