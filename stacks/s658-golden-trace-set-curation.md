# S-658 · Golden Trace Set Curation

You have 50,000 agent traces. Your eval harness passes. Your agent still breaks in production. The problem: you have logs, not data. A golden trace set is not a log dump — it is a curated, annotated, versioned corpus of exemplar agent trajectories that defines what "correct" means for your specific product. It is the single source of truth that feeds behavioral evals (S-220), regression tests (S-235), trajectory replay debugging (S-222), and synthetic trajectory fine-tuning (S-295). Without it, every downstream quality process runs on handwaving.

## Forces

- **General benchmarks measure the wrong thing.** SWE-bench, WebArena, GAIA — all document behaviors on tasks the model was not built for. Your agent's correct behavior is defined by your users, your APIs, your output schemas, your business logic. A trace set curated from your production is the only eval set that measures what actually matters.
- **Production traces are noisy.** Most runs are unremarkable — routine completions that add little signal. The value lives in the edges: the near-miss, the failure mode, the edge case that almost worked. Curation means finding the traces that teach the agent something, not just the ones that finished.
- **Without versioning, your trace set rots.** A trace captured against API v1.3 is invalid against v1.4. Model upgrades change tool-selection behavior. Prompt changes alter reasoning patterns. A trace set without a versioning discipline becomes misleading faster than it becomes useful.
- **Negative examples are as important as positives.** A golden set with only success traces teaches the agent "always complete the task" without teaching "here is what failure looks like and how to recover." You need both, annotated with the failure mode.

## The move

### The four curation layers

**Layer 1 — Capture.** Instrument your agent runtime to emit structured trace events: tool calls, tool results, model outputs, context state, and outcome label (success / partial / failure). Capture everything; filter later. S-222 covers the capture infrastructure. The key discipline: include the *full* input context at each step, not just the step output.

**Layer 2 — Grade.** Score every trace across at least two dimensions:
- **Outcome grade**: task completion (pass/fail/hang) from the ground-truth signal (user feedback, API correctness, output validation).
- **Process grade**: reasoning quality, tool selection appropriateness, constraint adherence — scored by an LLM judge (S-193). Two grades let you distinguish "right answer, wrong reasoning" from "wrong answer, good reasoning."

Classify each trace into one of four buckets:

| | High Outcome | Low Outcome |
|---|---|---|
| **High Process** | ✅ **Anchor positive** — canonical success patterns | ⚠️ **Process failure** — good reasoning, bad execution (often infrastructure) |
| **Low Process** | ⚠️ **Lucky pass** — task completed, reasoning flawed | ❌ **Anchor negative** — canonical failure patterns |

Anchor positives and anchor negatives are your golden traces. Lucky passes and process failures go to infra/ops.

**Layer 3 — Annotate.** Attach metadata that makes a trace actionable:
- `failure_mode`: wrong_tool, hallucinated_param, context_omission, prompt_injection, constraint_violation, deadlock, timeout
- `trigger`: the specific input condition or context state that caused the failure
- `correct_behavior`: what the agent should have done instead (ground truth)
- `product_version`, `model_version`, `prompt_version`: versioning fields for regression tracking

Annotation can be partly automated (LLM-assisted classification) but should include human review on any trace that will seed a regression test or training data.

**Layer 4 — Version and gate.** Treat the golden set like a dataset, not a directory:

```python
# golden_trace_set/registry.json
{
  "version": "v2.3",
  "created": "2026-07-05",
  "product_version": "1.8.x",
  "model": "claude-sonnet-4-5",
  "prompt_version": "prod-prompt-v17",
  "counts": {
    "anchor_positive": 847,
    "anchor_negative": 312,
    "process_failure": 156,
    "lucky_pass": 89
  },
  "coverage": {
    "failure_modes": ["wrong_tool", "hallucinated_param", "context_omission", "constraint_violation"],
    "tool_coverage": 0.94,
    "scenario_coverage": 0.78
  }
}
```

Run a coverage check before each release: are all critical failure modes represented? Has a recent model upgrade invalidated old traces? A trace that no longer represents current behavior is worse than no trace — it trains the wrong pattern.

### The curation loop

```
Production runs → trace capture → grading → annotation →
golden set update → eval seed → regression test seed →
training data seed → model improvement → back to production
```

The loop closes when the golden set drives measurable improvement: eval scores rise, regression failures from the same root cause stop recurring, and synthetic training data from anchor traces improves task completion rates.

### Size vs. quality

A golden set of 500 well-annotated traces (balanced across failure modes, versioned, with ground-truth annotations) outperforms a dump of 50,000 raw traces. Quality signals over volume. Each trace should answer: "if the agent sees this input, does it know what correct behavior looks like?"

## Receipt
> Receipt pending — 2026-07-05. The four-layer curation framework synthesizes documented practices from agent eval literature (Cleanlab 2025 production agent survey, arXiv:2601.22607 verifiable-reward RL, Arthur.ai regression test methodology, Chronicle Labs trajectory capture platform). The code structures are composable from existing open-source components (OpenTelemetry trace ingestion, LLM judges, structured logging). Full end-to-end run on a production agent stack was not executed in this session — validate against your own runtime before deploying.

## See also
- [S-220 · Agentic Behavioral Regression Suite](s220-agentic-behavioral-regression-suite.md) — uses the golden set as its eval corpus
- [S-235 · Production Failure → Regression Test](s235-production-failure-to-regression-test.md) — failure traces feed the negative class
- [S-295 · Synthetic Trajectory Fine-Tuning Pipeline](s295-synthetic-trajectory-fine-tuning-pipeline.md) — anchor traces as training data
- [S-222 · Agent Trajectory Replay](s222-agent-trajectory-replay.md) — capture infrastructure for Layer 1
- [S-193 · LLM-as-Judge Eval Pipeline](s193-llm-as-judge-eval-pipeline.md) — process grading for Layer 2
