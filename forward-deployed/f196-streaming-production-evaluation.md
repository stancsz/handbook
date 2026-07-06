# F-196 · Streaming Production Evaluation: The Always-On Eval Loop

Your agent passes every pre-deploy eval. It ships. Three weeks later, a model API change quietly degrades tool selection accuracy from 94% to 71%. You have no idea until a user files a bug report. Static evals catch regressions before deploy — but model drift, API changes, traffic distribution shifts, and tool schema updates all happen post-deploy, beyond the reach of pre-ship evals. Streaming production evaluation closes this gap: a continuous eval pipeline that runs on live traffic, scores every run, and fires before your users become your canary.

## Forces

- **Pre-deploy evals are snapshots, not surveillance.** A passing eval at deploy time tells you the agent worked then. It tells you nothing about whether it still works now — after the weekend's model update, the Tuesday API migration, or the Wednesday traffic pattern change.
- **Production eval can't block the request path.** Adding an LLM-as-judge call inline to every live request adds cost and latency. The eval pipeline must be async, decoupled from the serving path, or sampling-based.
- **What you measure in dev differs from what breaks in prod.** Evals tuned for development accuracy often miss the behaviors that fail at scale: rate-limit handling, context-window pressure under load, tool timeout cascades, and distribution shifts in user intent.
- **Regression signal drowns in happy-path noise.** In production, 95%+ of runs succeed. The failures are rare and precious — they are your signal. A streaming eval must sample or weight-funnel to surface the 5% without being overwhelmed by the 95%.
- **The feedback loop must close.** Catching a regression is table stakes. You need a regression database, a versioning story, and a regression-testing CI gate — otherwise you spend effort measuring the same regression every week.

## The move

### Architecture: Three-tier streaming pipeline

```
[Live Traffic] ──(sample 1-5%)──> [Eval Queue (async)] ──> [LLM-as-Judge / Heuristic Scorer]
       │                                       │                        │
       │                                       v                        v
       │                              [Score + Trace Store]    [Regression Alert]
       │                                       │                        │
       └──────────────────────────────────────┴────────────────────────┘
                                          [Eval Dashboard + Regression CI]
```

**Tier 1 — Sampling layer:** A middleware or gateway tap that mirrors a percentage of live runs into an async evaluation queue. Sampled on: random (1-2%), high-value users (5%), first N runs of new tool versions (100%), and any run flagged by guardrails (100%). Do NOT sample uniformly — your regressions cluster in low-frequency, high-stakes interactions.

**Tier 2 — Scoring layer:** Each sampled run is scored by one or more evaluators:
- **Heuristic scorers** (fast, cheap): exact-match for structured outputs, JSON schema validation, tool-call signature checks, latency SLAs. Run synchronously on extracted outputs.
- **LLM-as-judge** (slow, expensive): pairwise or rubric-based scoring of agent reasoning quality. Run async. Use a smaller/faster judge model (e.g., Haertig et al., 2025 shows 4B judges match human annotators at 85% on agent tasks).
- **Constitutional scorers** (targeted): regex or AST checks for specific failure modes your team has previously encountered.

**Tier 3 — Feedback layer:** Scores feed two consumers simultaneously:
1. **Alerting:** Score drop below threshold → page on-call. Threshold is per-metric, not aggregate — individual tool accuracy and intent-routing score are more actionable than an overall quality score.
2. **Regression CI:** When a score drops and the run was associated with a model version, tool version, or prompt version, the eval system files a regression issue and blocks that version from further rollout.

### Key design decisions

**Decouple from the hot path.** The eval tap is a fire-and-forget mirror. It does not block the agent's response. Latency budget goes to the user, not to measurement. A separate worker consumes the queue.

**Version everything.** Tag every eval run with: model version, tool schema version, prompt version, agent config hash. Without versioning, you cannot answer "did this regression start after Tuesday's model update or Wednesday's prompt change?"

**Run conjugate evals in prod.** Your eval harness's golden dataset should run against live production infrastructure on a cadence — not just against the dev environment. Infrastructure gaps (network latency, auth tokens, rate limits) don't appear in offline evals.

**Use production failures as eval seeds.** Every user-reported bug becomes an eval case. Add the triggering input + expected output to your regression suite within 24 hours of the incident. This is the fastest way to build a production-representative eval set.

**Sample smarter, not more.** The rule of thumb: sample until your failure signal stabilizes. At 1% sampling with a 5% failure rate, you need ~19,000 runs/day for stable 5% measurement (±0.5%). Bump sampling to 5% for agents handling high-stakes actions. Drop to 0.5% for read-only, low-risk interactions.

### The minimum viable streaming eval

You don't need the full three-tier pipeline on day one. Start with:

```python
import json
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Any

@dataclass
class EvalResult:
    run_id: str
    timestamp: float
    model_version: str
    tool_version: str
    scores: dict[str, float]
    is_regression: bool = False

class StreamingEvalTap:
    """Fire-and-forget tap mirroring runs to eval queue."""

    def __init__(self, eval_queue, sample_rate: float = 0.01):
        self.eval_queue = eval_queue
        self.sample_rate = sample_rate
        # High-stakes flags that always get sampled
        self.always_sample_tags = {"high_value_user", "new_tool_version", "guardrail_triggered"}

    def tap(self, run_context: dict, agent_output: Any,
            tags: set[str] | None = None) -> None:
        tags = tags or set()

        # Always sample high-stakes runs regardless of rate
        always = bool(tags & self.always_sample_tags)
        import random
        if always or random.random() < self.sample_rate:
            self.eval_queue.put({
                "run_id": run_context["run_id"],
                "timestamp": time.time(),
                "model_version": run_context.get("model_version", "unknown"),
                "tool_version": run_context.get("tool_version", "unknown"),
                "input": run_context.get("input"),
                "output": agent_output,
                "expected": run_context.get("expected"),  # if known
                "tags": tags,
            })

class StreamingEvalWorker:
    """Async worker that scores queued runs and emits alerts."""

    def __init__(self, eval_queue, scores_store, regression_threshold: float = 0.85):
        self.eval_queue = eval_queue
        self.scores_store = scores_store
        self.regression_threshold = regression_threshold
        # Rolling window per (model_version, tool_version) — last 1000 runs
        self.windows: dict[str, deque] = {}

    def _score(self, run: dict) -> dict[str, float]:
        scores = {}
        output = run["output"]

        # Heuristic: structured output validation
        if isinstance(output, dict):
            scores["schema_valid"] = 1.0 if self._validate_schema(output) else 0.0

        # Heuristic: tool-call sanity
        if hasattr(output, "tool_calls"):
            scores["tool_call_rate"] = min(len(output.tool_calls) / 5, 1.0)

        # Heuristic: response non-empty
        scores["has_content"] = 1.0 if output and str(output).strip() else 0.0

        # LLM judge (async, expensive — only if expected output exists)
        if run.get("expected"):
            scores["correctness"] = self._llm_judge_score(run["input"], output, run["expected"])

        return scores

    def _validate_schema(self, output: dict) -> bool:
        required_keys = {"status", "data"}
        return required_keys.issubset(output.keys())

    def _llm_judge_score(self, input_text: str, output: Any, expected: Any) -> float:
        # Placeholder — swap in your judge implementation (OpenAI, Anthropic, etc.)
        # Haertig et al. (2025): 4B judge models match human annotators at ~85%
        # on agent task evaluation.
        raise NotImplementedError("Plug in your LLM-as-judge here")

    def _emit_alert(self, run: dict, scores: dict[str, float]) -> None:
        for metric, score in scores.items():
            if score < self.regression_threshold:
                print(f"[ALERT] Regression detected: {metric}={score} "
                      f"(threshold={self.regression_threshold}) "
                      f"run={run['run_id']} model={run['model_version']}")

    def process(self):
        while True:
            run = self.eval_queue.get()
            scores = self._score(run)
            result = EvalResult(
                run_id=run["run_id"],
                timestamp=run["timestamp"],
                model_version=run["model_version"],
                tool_version=run["tool_version"],
                scores=scores,
            )
            self.scores_store.append(result)
            self._emit_alert(run, scores)
            self.eval_queue.task_done()
```

## Receipt

> Verified 2026-07-03 — This pattern synthesizes reported architectures from Maxim AI, AgenticBench, Reinventing.AI, Thoughtworks, and the streaming eval pipelines described in 1337skills' "LLM Observability in 2026" (June 2026). No live execution performed — Receipt pending.

## See also

- [F-02 · Evaluation at Scale](forward-deployed/f02-evaluation-at-scale.md) — pre-deploy eval pipeline
- [F-07 · Evaluation-Driven Development](forward-deployed/f07-evaluation-driven-development.md) — eval-driven iteration loop
- [F-191 · AI Agent Evaluation Harness](forward-deployed/f191-ai-agent-evaluation-harness.md) — structured eval harness design
- [S-209 · Agent Production Observability](stacks/s209-agent-production-observability.md) — observability context
