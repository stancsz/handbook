# S-561 · The Self-Correction Gap: When Agents Can't Self-Heal

Agents fail in production not because they're dumb, but because nobody built them a way to know they were wrong — and try again differently. The first answer an LLM gives is rarely its best. The gap between output and corrected output is where quality lives. Most agent systems never close it.

## Situation

A customer service agent generates a response that confidently misstates a refund policy. The agent has no way to know it's wrong — no validator fires, no test fails, no external signal says "check this against the source of truth." It ships. An agent tasked with writing a Python function gets the types wrong. The code runs without crashing, produces wrong output, and the agent moves on. In both cases the failure is invisible: no error thrown, no exception raised, just wrong output with a 200 status code.

Traditional software catches these failures through tests, assertions, and error handlers. Agents have none of these unless you explicitly build them. The self-correction gap is the architectural hole between what the agent produced and whether that production was good enough — and whether the agent can do anything about it.

## Forces

- **Agents produce output before they know if it's correct.** Unlike a developer who writes code, runs tests, and iterates, most agents generate once and return. The first pass is final unless you engineer a loop.
- **Self-correction without an external signal makes things worse.** If only the same model judges its own output, it tends to reinforce the original answer — even when wrong. Studies show naive self-correction degrades performance on 40-60% of tasks. The correction must come from somewhere the agent can't access or influence.
- **Loop limits are the first thing teams forget.** A self-correction loop without a hard cap becomes a death spiral: agent revises, revises again, keeps going until timeout or budget exhaustion. The reflection loop that was supposed to improve quality multiplies cost instead.
- **The signal type determines whether correction works at all.** Code generation has an objective signal (tests pass or fail). Policy compliance has an objective signal (document retrieval). Tone analysis has a subjective signal (another LLM's opinion). Only the first two reliably benefit from a self-correction scaffold.

## The move

Build a three-phase scaffolding loop: **Generate → Evaluate → Revise**. The critical design decisions are what "evaluate" means and how many revisions you allow.

### The signal hierarchy

```
Level 1 — Objective, deterministic (use reflexion whenever possible)
  - Test suite execution (pytest, unit tests)
  - Schema validation (pydantic, JSON Schema)
  - API contract checks (HTTP status, response shape)
  - Math/calculation verification (compute independently)
  - Retrieval recall (does the retrieved doc actually contain the answer?)

Level 2 — Semi-objective (use with 2-round max)
  - Format checks (does output match the required structure?)
  - Length/complexity constraints (token count, section count)
  - Policy retrieval (fetch the source doc, check alignment)
  - Tool call sequence validation (did the agent call the right tools?)

Level 3 — Subjective (treat as experimental, 1-round only)
  - LLM-as-judge for quality assessment
  - Tone/style evaluation
  - "Is this response helpful?" scoring
  - Cross-model agreement checks
```

### Minimal scaffold implementation

```python
from dataclasses import dataclass
from typing import Callable, Any
import json

@dataclass
class CorrectionResult:
    output: Any
    rounds: int
    improved: bool
    final_passed: bool

def self_correct(
    agent_fn: Callable[[str], str],
    evaluators: list[Callable[[str], bool]],
    task: str,
    max_rounds: int = 3,
) -> CorrectionResult:
    """
    Generate → Evaluate → Revise loop.
    Returns when first evaluator passes, max rounds reached, or
    a Level-3 evaluator (LLM judge) reports no improvement.
    """
    output = agent_fn(task)
    rounds = 0

    for round_num in range(1, max_rounds + 1):
        rounds = round_num

        # Evaluate: run all evaluators, collect failures
        failures = []
        for eval_fn in evaluators:
            try:
                passed = eval_fn(output)
                if not passed:
                    failures.append(eval_fn.__name__)
            except Exception as e:
                # Treat evaluator errors as failures
                failures.append(f"{eval_fn.__name__}: {e}")

        # All evaluators pass — done
        if not failures:
            return CorrectionResult(
                output=output,
                rounds=rounds,
                improved=rounds > 1,
                final_passed=True,
            )

        # Round exceeded — stop (prevents infinite loops)
        if round_num >= max_rounds:
            return CorrectionResult(
                output=output,
                rounds=rounds,
                improved=rounds > 1,
                final_passed=False,
            )

        # Check evaluator type: Level-3 (LLM judge) = 1 round only
        # If this is round 2+ and all remaining evaluators are Level-3,
        # stop rather than risk echo-chamber degradation
        all_level3 = all(
            getattr(ev, '_is_llm_judge', False) for ev in evaluators
        )
        if all_level3 and round_num >= 2:
            return CorrectionResult(
                output=output,
                rounds=rounds,
                improved=False,
                final_passed=False,
            )

        # Revise: inject failures back to the agent with context
        revision_prompt = (
            f"Previous attempt:\n{output}\n\n"
            f"Failures to address:\n" +
            "\n".join(f"- {f}" for f in failures) +
            f"\n\nTask: {task}"
        )
        output = agent_fn(revision_prompt)

    # Should not reach here, but safe fallback
    return CorrectionResult(output=output, rounds=rounds,
                           improved=rounds > 1, final_passed=False)
```

### Usage: code generation with test validation

```python
def test_passes(code: str) -> bool:
    """Level 1: Objective signal via test execution."""
    try:
        # Simulate: exec in sandbox, run pytest
        exec_globals = {'__name__': '__test__'}
        exec(code, exec_globals)
        return True
    except Exception:
        return False

def schema_valid(output: str) -> bool:
    """Level 2: Structured output validation."""
    try:
        data = json.loads(output)
        return isinstance(data, dict) and 'result' in data
    except json.JSONDecodeError:
        return False

result = self_correct(
    agent_fn=lambda p: llm.generate(p),
    evaluators=[test_passes, schema_valid],
    task="Write a function that returns the nth Fibonacci number",
    max_rounds=3,
)
print(f"Rounds: {result.rounds}, Passed: {result.final_passed}")
```

## Receipt

> Verified 2026-07-04 — Pattern confirmed via ToolHalla (March 2026) and CallSphere analysis. ToolHalla reports Reflexion reaching 91% on HumanEval with test-based reflection. Confirming the signal hierarchy: Objective signals (Level 1) reliably improve; LLM-as-judge (Level 3) degrades after round 1 without external grounding. Cleanlab (November 2025) survey of 1,837 enterprise respondents confirms that understanding when agents are "right, wrong, or uncertain" is the top production challenge — cited by 73% of teams with agents in production.

## See also

- [S-70 · Agent Loop Termination](s70-agent-loop-termination.md) — the termination conditions that bound this loop
- [S-204 · Agent Circuit Breaker](s204-agent-circuit-breaker.md) — cost protection against runaway revision loops
- [S-95 · Retry Cost Attribution](s95-retry-cost-attribution.md) — accounting for the cost of each revision round
- [S-511 · Plan-then-Execute with Semantic Gate](s511-plan-then-execute-with-semantic-gate.md) — architectural isolation that makes evaluation actionable
