# S-644 · The Three-Layer Agent Eval Model

[Most teams evaluate their agents at exactly one layer: the final answer. They miss the failure modes that live in the path. The three-layer eval model — final-answer, trajectory, and per-turn — is the organizing framework that shows where each type of failure hides, and why the tractable production path is per-turn classification.]

## Forces

- **Final-answer eval is necessary and insufficient.** A correct answer reached by calling the wrong tool three times, looping twice, and ignoring a safety signal is a failing agent run. Grading only the last message misses this.
- **Trajectory eval requires ground truth nobody has.** Scoring the sequence of steps requires labeled trajectories — which turns were correct, which were wasted, which recovered. Building and maintaining a trajectory dataset is expensive enough that most teams don't.
- **Per-turn eval is tractable but undervalued.** Each individual turn is self-contained: one input, one output, one tool call (or none). You can classify a turn with a fast auxiliary model in milliseconds, without needing a full trajectory label.
- **Each layer catches a different failure class.** Answer-grade misses path failures. Path-grade misses turn-level failures. Turn-grade misses systemic quality drift. You need all three, but you deploy them differently.

## The move

### Layer 1 — Final-Answer Evaluation

Score the last message against an expected result. This is what every benchmark does.

```
def grade_answer(response: str, expected: str) -> float:
    judge = LLM-as-judge(model="gpt-4o-mini")
    result = judge.invoke(
        f"Grade: {response}\n\nExpected: {expected}\n"
        "Return JSON {{\"pass\": bool, \"reason\": str}}"
    )
    return json.loads(result)["pass"]
```

**What it catches:** Wrong conclusions, hallucinated citations, off-topic responses, style violations.

**What it misses:** Everything that happened inside the trajectory. The answer can be right for the wrong reasons.

### Layer 2 — Trajectory Evaluation

Score the full execution trace — tool calls, reasoning steps, recovery events, step count vs. expected.

```
def grade_trajectory(trace: list[Turn], expected_tools: list[str],
                     max_steps: int) -> TrajectoryScore:
    tool_precision = len(set(t.tool for t in trace) & set(expected_tools)) \
                     / max(len(set(expected_tools)), 1)
    step_efficiency = expected_steps / max(len(trace), expected_steps)
    recovery = any(t.recovered for t in trace)
    return TrajectoryScore(
        tool_precision=tool_precision,
        step_efficiency=step_efficiency,
        recovered=recovery
    )
```

**What it catches:** Wrong tool sequence, looping, wasted steps, missed recovery.

**What it misses:** Turn-level failures that don't aggregate to a trajectory score (e.g., a safe-looking trajectory with one catastrophic mid-step policy violation).

### Layer 3 — Per-Turn Classification

Classify each turn independently — a fast, parallelizable, single-turn signal. This is the production workhorse.

```python
from pydantic import BaseModel

class TurnLabel(BaseModel):
    tool_correct: bool        # right tool, right arguments?
    safe: bool               # no policy violations?
    necessary: bool          # this turn added new information?
    efficient: bool          # no redundant API calls?

def label_turn(turn: Turn, max_latency_ms: int = 50) -> TurnLabel:
    # Run as async fire-and-forget on production traffic
    # Results feed dashboards, RL pipelines, and regression alerts
    return fast_classifier.invoke(turn, timeout=max_latency_ms)

# Production sampling — label 10% of turns, no latency impact on user
async def sample_and_label(traffic: list[Turn]):
    sample = random.sample(traffic, k=int(len(traffic) * 0.10))
    tasks = [label_turn(t) for t in sample]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

**What it catches:** Tool-call errors before they compound, policy drift in real time, unnecessary API calls, semantic drift in intermediate outputs.

**What it misses:** Cross-turn dependencies — whether the sequence of turns makes sense.

### The composite signal

```
Composite Agent Score = w1 × L1 + w2 × L2 + w3 × L3

# Where:
# L1 = final-answer pass rate (per-task, averaged over eval set)
# L2 = trajectory score (tool precision + step efficiency + recovery rate)
# L3 = per-turn quality rate (fraction of turns passing all TurnLabel checks)
```

The three layers are orthogonal. An agent can score 1.0 at L1 and 0.3 at L2 — correct answer, terrible execution. Another scores 0.95 at L2 and 0.4 at L3 — efficient trajectory, each step is unreliable. All three matter.

## The per-turn shortcut

The practical production path: run per-turn classifiers on sampled production traffic, use their outputs to:

1. **Drive RL reward signals** — per-turn labels are the dense, frequent feedback that fine-tuning pipelines need. Final-answer labels arrive once per run; per-turn labels arrive every turn.
2. **Trigger regression alerts** — if per-turn safety score drops 5% week-over-week, alert before the next release cycle.
3. **Feed dashboards** — aggregate per-turn rates by tool type, request category, or time window to find systemic degradation.

The per-turn classifier itself is cheap to build. You don't need a trajectory dataset — you need turn-level binary labels ("this tool call was correct: yes/no"), which domain experts can produce 10x faster than trajectory labels.

## Receipt

> Verified 2026-07-05 — Pattern synthesized from MorphLLM's three-layer eval framework (morphllm.com, 2026-06-20) + InfoQ's agent evaluation survey (infoq.com, 2026) + arXiv:2507.21504 (Mohammadi et al., 2025). Code examples are structural pseudocode illustrating the pattern, not runnable against a live system. Trajectory grading requires a labeled eval set not available in this environment.

## See also

- [S-246 · The Production Eval Pipeline — Four Stages, Zero Surprises](s246-production-eval-pipeline-the-four-stage-loop.md) — the deployment pipeline that hosts these three eval layers
- [S-351 · The Eval Gap: Tracing Without Truth](s351-the-eval-gap-tracing-without-truth.md) — why observability without ground truth is still blind
- [S-281 · Agent Evaluation Is the Missing Layer Nobody Builds Until Production Breaks](s281-agent-evaluation-the-layer-nobody-builds-until-production-breaks.md) — the organizational context that makes eval investment hard
