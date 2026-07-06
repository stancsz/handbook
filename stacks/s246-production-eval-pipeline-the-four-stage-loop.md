# S-246 · The Production Eval Pipeline — Four Stages, Zero Surprises

Your agent scores 94% on MMLU. It fails on 30% of real customer tickets. Public benchmarks lied. Internal spot checks don't catch regressions. You have no idea your latest prompt change broke the Spanish market until users complain. The production eval pipeline is the architectural pattern that closes this gap: a four-stage system that runs evals locally, in CI, in shadow mode against live traffic, and via human review — catching different failure classes at each stage.

## Forces

- **Stage 1 catches nothing that Stage 2 would.** Local unit evals catch regressions fast; they miss anything you didn't think to test.
- **Stage 2 misses anything that only appears under real load or real inputs.** CI catches deterministic regressions; it misses behavioral drift under production distribution.
- **Stage 3 catches everything Stages 1 and 2 miss** — but only if you instrument it without affecting live users.
- **Stage 4 catches everything the models miss.** Human judgment is the floor, not the ceiling.
- **Skipping any stage leaves a hole.** Teams that skip CI regression find bugs in production. Teams that skip shadow eval find their agent degraded silently for weeks. Teams that skip human calibration find their automated scores diverged from real quality by 20%.
- **Eval cost compounds.** Judging every call in production can cost 10× the agent workload. The four-stage pipeline stages the cost: cheap/fast first, expensive/slow last.

## The move

Four stages, each catching what the previous one misses. Run in sequence; each stage gates the next.

### Stage 1 — Local unit evals (fast, cheap, per-commit)

A curated golden dataset of 200–500 examples built from real production failures. Not synthetic. Not from benchmarks. Each example is a real input that broke the agent, annotated with expected output and the bug category it triggered.

Run on every commit. Target: <2 min, >100 examples, <$0.50 total cost.

```python
# eval_suite.py — stage 1, runs in CI
from deepeval import assert_test
from deepeval.metrics import FaithfulnessMetric, CorrectnessMetric

GOLDEN_CASES = [
    {
        "input": "Cancel my subscription starting next month",
        "expected": {"action": "cancel_delayed", "date": "next_month"},
        "category": "date_parsing",
    },
    {
        "input": "客户要求在本周五前退款",
        "expected": {"action": "refund", "deadline": "friday"},
        "category": "multilingual",
    },
    # ... 200+ cases from production incidents
]

@pytest.mark.parametrize("case", GOLDEN_CASES)
def test_agent_response(case):
    response = agent.run(case["input"])

    if case["category"] in ("date_parsing", "multilingual"):
        # Deterministic: check structured output fields
        assert response.action == case["expected"]["action"]
        assert response.extracted_date is not None
    else:
        # Probabilistic: use LLM judge with rubric
        metric = CorrectnessMetric(threshold=0.7)
        metric.evaluate(response, case["expected"])
        assert_test(metric)
```

The golden dataset is your most valuable asset. Curate it from production failures, not from imagined edge cases. Every confirmed bug in production → one new test case before the fix is merged.

### Stage 2 — CI regression gate (full suite, pre-release)

Triggered on every PR to main. Runs the complete golden dataset plus adversarial cases. This is where prompt changes and model upgrades face the full battery.

Key metrics to track per PR: pass rate, per-category breakdown, cost-per-case, latency p95. A 2% regression in the `multilingual` category on a PR that touches date-parsing logic is a signal — document why it happened or roll back.

```python
# ci_eval.py — stage 2, full suite pre-release
from deepeval import evaluate
from deepeval.metrics import (
    FaithfulnessMetric, CorrectnessMetric, ToxicityMetric,
    HallucinationMetric,
)
import braintrust

def full_eval_suite(agent, golden_cases):
    metrics = [
        FaithfulnessMetric(threshold=0.8),
        CorrectnessMetric(threshold=0.7),
        HallucinationMetric(threshold=0.1),
    ]

    results = evaluate(
        test_cases=[build_test_case(c) for c in golden_cases],
        metrics=metrics,
    )

    # Post results as PR comment via Braintrust
    braintrust.eval_action(
        "agent-eval",
        scores=results.scores,
        threshold=0.7,
        metadata={"pr": os.environ["PR_NUMBER"]},
    )
    return results
```

Use rubric decomposition over holistic scoring. Instead of "score the whole response 1–10," break into sub-dimensions: correctness, format, safety, helpfulness. Each sub-dimension gets its own threshold and failure flag. This makes regressions actionable — you know exactly which dimension broke.

### Stage 3 — Shadow eval against live traffic (sampling, no user impact)

Runs candidate outputs against the eval rubric on a 1–5% sample of live traffic. The agent sees real production inputs it has never trained on. This is where behavioral drift surfaces: a new model version passes CI but degrades on Spanish inputs, or on the specific phrasing patterns of your top-100 users.

```python
# shadow_eval.py — stage 3, live traffic sampling
import random

def shadow_eval(sample_rate=0.02):
    while True:
        # Receive live request (not modified — just observed)
        request = get_next_request()
        if random.random() > sample_rate:
            continue

        # Run candidate model in parallel with production model
        candidate_output = candidate_agent.run(request.input)
        production_output = production_agent.last_output  # already served

        # Score both with the eval rubric (offline, async)
        score = eval_judge.score(
            input=request.input,
            output=candidate_output,
            expected=None,  # no ground truth — rubric-based
        )

        # Log for later analysis, don't block anything
        metrics_logger.log({
            "request_id": request.id,
            "candidate_score": score,
            "production_score": request.satisfaction_score,  # if available
            "input_category": classify(request.input),
            "model": "candidate",
        })
```

Shadow eval outputs feed into a weekly scorecard: candidate vs. production distribution on each eval dimension. A >5% gap on any dimension triggers an alert. A >10% gap gates the release candidate.

### Stage 4 — Human calibration (ground truth, 1–2 week cadence)

A sample of 20–50 cases reviewed by a human annotator. The annotator doesn't see model scores — scores come after. This calibrates the automated judges against human judgment.

Track judge agreement rate: `agreement = cases_where_judge_and_human_concur / total_cases`. If agreement drops below 70%, the rubric is drifting from reality — update it before the next cycle.

```python
# human_calibration.py — stage 4, biweekly
from anthropic import Anthropic

client = Anthropic()

CALIBRATION_CASES = random.sample(production_cases, n=30)

for case in CALIBRATION_CASES:
    # Human annotator reviews blind (no model score shown)
    human_verdict = annotator.review(case["input"], case["candidate_output"])
    # Store human verdict

# After batch: compare judge scores to human verdicts
judge_agreement = sum(
    1 for c in CALIBRATION_CASES
    if abs(c["judge_score"] - c["human_verdict"]) <= 0.2
) / len(CALIBRATION_CASES)

print(f"Judge-human agreement: {judge_agreement:.0%}")
if judge_agreement < 0.70:
    print("ALERT: Rubric drift detected — update rubric before next cycle")
```

## Receipt

> Receipt pending — 2026-06-30

## See also

- [F-07 · Evaluation-Driven Development](../forward-deployed/f07-evaluation-driven-development.md) — wired evals as CI gates, this is the architectural spine that makes it possible
- [F-177 · Deterministic Agent Verification](../forward-deployed/f177-deterministic-agent-verification.md) — deterministic gates layer with probabilistic judges to eliminate sycophancy bias
- [S-235 · Production Failure → Regression Test](../stacks/s235-production-failure-to-regression-test.md) — convert every production incident into a test case that feeds Stage 1
- [S-230 · Agent Harness Engineering](../stacks/s230-agent-harness-engineering-the-eval-layer-production-demands.md) — the eval harness itself, how to structure test inputs and assertions
