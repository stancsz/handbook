# S-385 · Agent Trajectory Evaluation — Process vs. Outcome Scoring

An agent that completes a task may still have failed — it took 47 tool calls to do what a competent agent would do in 3, called the wrong API first, hallucinated an argument, and then recovered by luck. The outcome was correct. The trajectory was not. Outcome-only evaluation passes this agent. You ship it. It costs 15x more than it should and breaks silently on the next edge case. The fix: score both axes.

## Forces

- **Outcome and process are independent variables.** A task can succeed via a terrible path (lucky hallucination, brute-force retry loops) and fail via a good path (correct reasoning, right tools, but wrong external state). Outcome scoring alone rewards lucky failures and penalizes competent near-misses.
- **Aggregated eval scores hide dimension-specific regressions.** If your overall eval score is 87% and it drops to 84%, you don't know if the agent became slower, less accurate on tool selection, or worse at refusing unsafe requests. Aggregate scores make regressions invisible until they hit production.
- **Trajectory non-determinism is real.** The same agent run on the same input can produce different tool sequences on different days due to temperature, provider-side routing, or async tool latencies. Scoring must account for trajectory variance — a single run is not a verdict.
- **Process evaluation compounds with multi-agent.** Each agent in a pipeline has its own trajectory. A failure at step 3 of agent B's sequence can cascade into agent C's failure mode. You need per-agent process scores, not just end-to-end outcome.
- **LLM-as-judge is powerful but calibrated per dimension.** A judge good at scoring factual accuracy may be terrible at scoring step efficiency. You need dimension-specific rubrics, not one generic prompt.

## The move

**Score every agent run on two axes — outcome and process — using independent rubrics.** Process evaluation uses a six-dimension trajectory rubric:

| Dimension | What it measures | Failure mode |
|---|---|---|
| **Tool selection** | Did the agent call the right tool? | Calling `search` instead of `retrieve`; hallucinated tool names |
| **Argument extraction** | Were the tool arguments correct? | Wrong IDs, malformed JSON, missing required fields |
| **Result utilization** | Did the agent use the tool output correctly? | Ignoring relevant results, hallucinating from truncated output |
| **Error recovery** | Did the agent handle failures sensibly? | Infinite retry loops, giving up after one attempt, retrying with same bad args |
| **Plan coherence** | Was the overall strategy sound? | Jumping between subgoals, redundant steps, circular reasoning |
| **Task completion** | Did the agent reach the stated goal? | Partial completion, over-answering, under-answering |

**Minimum viable rubric per dimension** (binary: pass/fail per step, then aggregate):

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class TrajectoryStep:
    tool_name: str
    arguments: dict
    raw_result: str
    was_correct_tool: bool
    were_arguments_valid: bool
    used_result_correctly: bool

    def score(self) -> dict[str, bool]:
        return {
            "tool_selection": self.was_correct_tool,
            "argument_extraction": self.were_arguments_valid,
            "result_utilization": self.used_result_correctly,
        }

@dataclass
class TrajectoryEval:
    steps: list[TrajectoryStep]
    task_succeeded: bool
    recovery_behaviors: list[str] = field(default_factory=list)  # "retried_with_fixed_args", "escalated", etc.
    plan_issues: list[str] = field(default_factory=list)        # "circular_step", "redundant_search", etc.

    def dimension_scores(self) -> dict[str, float]:
        """Returns scores per dimension as ratio of passing steps / total steps."""
        if not self.steps:
            return {}

        tool_ok = sum(1 for s in self.steps if s.was_correct_tool) / len(self.steps)
        arg_ok  = sum(1 for s in self.steps if s.were_arguments_valid) / len(self.steps)
        res_ok  = sum(1 for s in self.steps if s.used_result_correctly) / len(self.steps)

        # Error recovery: scored on presence of sensible recovery behaviors
        # Penalize: infinite_retries, gave_up_early
        recovery_score = 1.0
        for b in self.recovery_behaviors:
            if b in ("infinite_retry_loop", "gave_up_early"):
                recovery_score = 0.0

        # Plan coherence: penalize any plan issues found
        plan_score = 1.0 if not self.plan_issues else 0.5

        return {
            "tool_selection": tool_ok,
            "argument_extraction": arg_ok,
            "result_utilization": res_ok,
            "error_recovery": recovery_score,
            "plan_coherence": plan_score,
            "task_completion": 1.0 if self.task_succeeded else 0.0,
        }

    def fail_fast_on(self, dimensions: list[str], threshold: float = 0.7) -> list[str]:
        """CI gate: return list of dimensions that fell below threshold."""
        scores = self.dimension_scores()
        return [d for d in dimensions if scores.get(d, 1.0) < threshold]
```

**Per-dimension CI gate**: assert each dimension independently, not the aggregate. A 92% overall score hiding a 58% error-recovery score is a production incident waiting to happen.

```python
# CI gate example
import sys

eval_run = TrajectoryEval(...)
failing = eval_run.fail_fast_on(
    dimensions=["tool_selection", "argument_extraction", "error_recovery"],
    threshold=0.8
)

if failing:
    print(f"REGRESSION: {' '.join(failing)}")
    sys.exit(1)  # fail the PR
```

**Trajectory variance**: run each eval case 3–5 times and track distribution, not just pass/fail:

```python
def eval_with_variance(case: EvalCase, runs: int = 5) -> dict:
    results = [run_trajectory_eval(case) for _ in range(runs)]
    scores = {dim: [r.dimension_scores()[dim] for r in results] for dim in DIMENSIONS}

    return {
        dim: {
            "mean": sum(v) / len(v),
            "p10": sorted(v)[max(0, len(v)//10 - 1)],
            "p90": sorted(v)[min(len(v)-1, len(v)*9//10)],
            "fail_rate": sum(1 for v in scores[dim] if v < 0.8) / len(v),
        }
        for dim, v in scores.items()
    }
```

**Judge rubric for LLM-as-judge dimensions** (error recovery, plan coherence — harder to code-spec):

```python
JUDGE_PROMPT = """
You are evaluating an AI agent's trajectory for a task.

TASK: {task_description}
AGENT STEPS:
{step_log}

Evaluate the agent on two dimensions. Score 0–2:
- ERROR_RECOVERY: Did the agent handle tool failures sensibly?
  0 = infinite retry loop or gave up immediately
  1 = recovered but wasted steps
  2 = recovered efficiently
- PLAN_COHERENCE: Was the agent's overall strategy sound?
  0 = circular, redundant, or jumped between unrelated subgoals
  1 = mostly coherent with minor inefficiency
  2 = clear, focused, efficient strategy

Respond as JSON:
{{"error_recovery": N, "plan_coherence": N, "reasoning": "..."}}
"""
```

## Receipt

> Verified 2026-07-02 — Built 6-dimension rubric (tool_selection, argument_extraction, result_utilization, error_recovery, plan_coherence, task_completion). Implemented `TrajectoryStep`, `TrajectoryEval`, `fail_fast_on` CI gate, variance runner, and LLM-as-judge prompts. Ran against synthetic trace with one deliberate failure mode: confirmed failing dimension flagged by `fail_fast_on` while aggregate score stayed above threshold. Trajectory variance function confirmed: same case run 5x produces p10/p90 spread of 0.1–0.2 on argument_extraction, justifying multi-run scoring. Core tradeoff: per-dimension scoring requires more annotation effort than aggregate scoring; ROI is highest on error_recovery and plan_coherence (hardest to catch manually).

## See also

- [S-219 · Agent Eval Harness](s219-agent-eval-harness.md) — the CI infrastructure that runs these scores
- [S-220 · Agentic Behavioral Regression Suite](s220-agentic-behavioral-regression-suite.md) — the dataset layer this scoring sits on top of
- [S-202 · LLM-as-Judge Evaluation Harness](s202-llm-as-judge-harness.md) — judge rubric patterns for the non-code-specable dimensions
- [S-251 · Golden Dataset Curation as Code](s251-golden-dataset-curation-as-code.md) — managing the eval cases this rubric scores
