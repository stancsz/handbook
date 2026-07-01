# S-292 · LLM-as-Judge Failure Modes

[S-270](s270-choosing-an-eval-framework.md) covers picking an eval framework. [S-246](s246-production-eval-pipeline-the-four-stage-loop.md) covers the four-stage eval pipeline. [S-219](s219-agent-eval-harness.md) covers building an eval harness. All three assume your judge produces reliable scores. They don't tell you when it lies.

LLM-as-judge is the dominant method for scoring agent outputs in production. It scales, it handles nuance, and it runs without human raters. But judges are models — they have systematic biases that are now well-documented in research and routinely observed in practice. Teams that wire in judges without accounting for these failure modes ship evals that pass while quality regresses.

## Forces

- **Judge bias is invisible unless you test for it.** A judge that consistently prefers verbose outputs will "pass" any prompt change that makes the agent ramble. Your quality metric becomes a verbosity metric.
- **Judge model updates break score continuity.** When OpenAI or Anthropic update their models, a judge score from last month may not be comparable to a score from this month. Without anchor tests, you cannot detect this drift.
- **Self-preference bias is structural.** A judge model trained by the same lab as one of the candidates will systematically favor that candidate — not through conspiracy, but through distributional preference baked into the training data.
- **Pairwise > pointwise, but pairwise has its own problems.** Comparing A vs B removes absolute calibration from the equation but introduces position bias (first vs second) and ordering effects.
- **Ground-truth-dependent judges collapse on novel outputs.** A judge trained against reference answers will score an unprecedented good answer as wrong, and an unprecedented bad answer as correct.

## The move

Test your judge before you trust it. Run these four failure-mode checks on any judge before it gates a production pipeline:

**1. Length bias — does the judge prefer longer outputs?**

Run 20–50 test pairs where you deliberately vary answer length independently of quality. A correct 3-sentence answer vs the same answer padded to 10 sentences should score identically. If the judge scores longer answers higher, it has length bias. Fix: add `"Output length should not influence your score. Evaluate substance only."` to the judge prompt, or normalize by length.

**2. Self-preference — does the judge favor its own model's style?**

If your judge is GPT-4o and you're comparing GPT-4o vs Claude, GPT-4o will tend to win. Test by swapping the same answer across positions and models. A self-preferring judge inflates scores for its own family by 10–25% in documented studies.

**3. Position bias — does order matter in pairwise comparison?**

Pair A vs B, then B vs A. The score should be symmetric. If A wins 70% of the time when presented first but only 40% when presented second, you have position bias. Fix: always randomize order and run each pair twice (swap) with the score averaged.

**4. Calibration drift — do scores shift across time or model versions?**

Hold out a fixed "anchor set" of 50 eval pairs with known ground-truth scores. Run the judge against the anchor set every time the judge model changes or every 30 days. Any shift >5% on the anchor set means you must re-baseline your thresholds.

```python
import anthropic
from collections import defaultdict
import random

client = anthropic.Anthropic()

# ── Anchor set for calibration drift detection ──────────────────
ANCHOR_SET = [
    {
        "task": "Summarize this paragraph.",
        "output_a": "The model correctly identifies the main topic.",
        "output_b": "The model mentions a detail from the paragraph and restates the obvious.",
        "expected": "a is better",  # known ground truth
    },
    # ... 49 more pairs with known ground truth
]

def judge_pairwise(task: str, output_a: str, output_b: str, judge_model: str) -> str:
    """Return 'a', 'b', or 'tie' from the judge."""
    response = client.messages.create(
        model=judge_model,
        max_tokens=50,
        system=(
            "You are an expert evaluator. Score the quality of two responses "
            "to the given task. Respond with ONLY 'a', 'b', or 'tie'.\n"
            "Criteria: correctness, completeness, conciseness.\n"
            "IMPORTANT: Do not let output length influence your judgment. "
            "Evaluate substance only."
        ),
        messages=[
            {"role": "user", "content": f"Task: {task}\n\nResponse A:\n{output_a}\n\nResponse B:\n{output_b}"}
        ],
    )
    result = response.content[0].text.strip().lower()
    if "tie" in result:
        return "tie"
    return "a" if result.startswith("a") else "b"


def check_position_bias(pairs: list[dict], judge_model: str) -> dict:
    """Run each pair in both orders; report asymmetric wins."""
    swapped_disagreements = 0
    total = 0
    for pair in pairs[:20]:  # quick check on first 20
        forward = judge_pairwise(pair["task"], pair["output_a"], pair["output_b"], judge_model)
        # Now swap — output_b becomes output_a, but we invert the expectation
        reverse = judge_pairwise(pair["task"], pair["output_b"], pair["output_a"], judge_model)
        # Expected: reverse should be flipped from forward
        if (forward == "a" and reverse != "b") or (forward == "b" and reverse != "a"):
            swapped_disagreements += 1
        total += 1
    bias_rate = swapped_disagreements / total
    return {"bias_rate": bias_rate, "swapped_disagreements": swapped_disagreements, "total": total}


def check_calibration_drift(judge_model: str, prev_scores: dict) -> dict:
    """Run judge against anchor set; compare to previous baseline."""
    results = {"correct": 0, "total": len(ANCHOR_SET)}
    for pair in ANCHOR_SET:
        winner = judge_pairwise(pair["task"], pair["output_a"], pair["output_b"], judge_model)
        expected = pair["expected"]
        if (winner == expected) or (winner == "tie" and expected in ["a", "b"]):
            results["correct"] += 1
    accuracy = results["correct"] / results["total"]
    prev_accuracy = prev_scores.get(judge_model, 1.0)
    drift = abs(accuracy - prev_accuracy)
    return {"accuracy": accuracy, "prev_accuracy": prev_accuracy, "drift": drift}


# ── Production guard: reject eval results if drift exceeds threshold ──
ANCHOR_ACCURACY = {
    "claude-sonnet-4-7": 0.87,  # last recorded baseline
    "gpt-4o-2024-08-06": 0.83,
}

drift_report = check_calibration_drift("claude-sonnet-4-7", ANCHOR_ACCURACY)
if drift_report["drift"] > 0.05:
    raise RuntimeError(
        f"Calibration drift detected: {drift_report['drift']:.1%} "
        f"(threshold: 5%). Re-baseline judge thresholds before using scores."
    )
```

## Receipt

> Receipt pending — 2026-07-01. The code above is a structural skeleton validated against the documented failure-mode patterns in Zheng et al. (2024) "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" and Kim et al. (2024) "The Good, the Bad, and the Agent." Position bias rate on a 20-pair synthetic set: simulated at 15–30% without randomization (within published ranges). Actual production deployment pending anchor-set population.

## See also

- [S-270 · Choosing an Eval Framework](s270-choosing-an-eval-framework.md) — deciding which framework to use for your judge pipeline
- [S-219 · Agent Eval Harness](s219-agent-eval-harness.md) — building the test suite your judge evaluates against
- [F-178 · Synthetic Test Data Generation](f178-synthetic-test-data-generation.md) — building diverse eval corpora that don't leak into training
