# F-189 · Private Eval Dataset Construction

A generic benchmark tells you the agent is good at math. Your enterprise dataset tells you it correctly routes tier-3 enterprise billing disputes — which is the only thing that actually matters in production. Without a private eval dataset, every model upgrade, prompt change, or architectural shift ships blind. With a bad one, you ship confidently wrong.

## Forces

- **Public benchmarks plateau.** SWE-bench, GAIA, MMLU — these measure general capability. Your agent's actual failure modes are domain-specific: a billing agent that misclassifies refund eligibility, a legal agent that cites non-binding dicta, a support agent that escalates when it shouldn't. Generic benchmarks have zero signal on these.
- **Gold-standard labels are expensive and rot.** Getting 200 expert-annotated samples costs $5K–$20K. Three months later the product changed, the policy shifted, or the model behavior shifted — and 30% of your labels are now wrong.
- **The annotation bottleneck gates the entire quality loop.** Teams that can annotate faster ship better agents. Teams that annotate once and never update ship slowly-improving agents.
- **Synthetic labels are useful but not sufficient.** LLM-generated labels are cheap and fast but carry the model's own biases. A judge trained on the same distribution as the agent it judges produces falsely high scores.
- **Coverage is the hard part.** A dataset with 500 samples that covers 80% of failure modes beats 5,000 samples that cluster around the easy 20%.

## The move

Build a private eval dataset as a first-class engineering artifact — not a one-off annotation project. The three-phase process:

### Phase 1 — Mine failure modes from production

Extract real failure cases from live traffic, not invented ones:

```python
import json

# Extract confirmed failures from production traces
failures = []
for trace in production_traces:
    # Human override: human confirmed the agent was wrong
    if trace.get("human_correction"):
        failures.append({
            "input": trace["user_query"],
            "trajectory": trace["agent_steps"],
            "correct_output": trace["human_correction"],
            "failure_type": classify_failure(trace),
            "severity": trace.get("business_impact", "low"),
            "model": trace["model_version"],
        })

# Cluster by failure_type to find coverage gaps
from collections import Counter
failure_counts = Counter(f["failure_type"] for f in failures)
# {'wrong_tool_selection': 47, 'hallucinated_citation': 23,
#  'context_omission': 18, 'escalation_error': 12}
# → Add more cases for under-represented clusters
```

### Phase 2 — Synthesize + expand with structural diversity

Use the production failures as seeds. Generate adversarial variants that share the same failure-mode structure but differ in surface form:

```python
# Use a different model (e.g., mixtral) to generate surface variants
# of known failure cases — avoids the judge-subject circularity
def synthesize_variant(seed_case: dict, n: int = 5) -> list[dict]:
    prompt = f"""
    Original query: {seed_case['input']}
    Original failure: agent chose wrong_tool_selection
    Generate {n} semantically different queries that would likely
    trigger the same failure category (wrong_tool_selection).
    Keep the domain, difficulty, and failure-mode structure identical.
    Vary: industry jargon, query length, negation patterns.
    """
    variants = call_model("mixtral-8x7b", prompt)  # different from agent model
    return [
        {**seed_case, "input": v, "synthetic": True, "seed_id": seed_case["id"]}
        for v in variants
    ]
```

Key rule: **never generate labels with the same model you're evaluating.**

### Phase 3 — Calibrate thresholds with human spot-checks

1. Take 20 random samples from your private dataset
2. Have domain expert label them (ground truth, not review)
3. Compare expert labels to your synthetic labels
4. Measure agreement rate — if < 85%, the dataset needs work before it's a gate

```python
def calibrate_dataset(dataset: list[dict], human_labeled_subset: list[dict]) -> dict:
    """
    Returns calibration report: synthetic label accuracy by failure_type.
    """
    from sklearn.metrics import classification_report
    y_true = [d["expert_label"] for d in human_labeled_subset]
    y_pred = [d.get("synthetic_label", d.get("expected_label")) for d in human_labeled_subset]

    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
    return {
        "overall_accuracy": report["accuracy"],
        "by_failure_type": {
            k: v for k, v in report.items()
            if isinstance(k, str) and k not in ("accuracy", "macro avg", "weighted avg")
        },
        "recommendation": "use_as_gate" if report["accuracy"] >= 0.85 else "needs_review"
    }
```

### The maintenance loop

Private eval datasets rot. Treat it like a production dependency:

- **Trigger a rebuild** when: model upgrade, prompt change > 20% diff, product feature launch, policy update
- **Run delta eval** on rebuild: compare new dataset results against old on the unchanged agent — expect < 2% drift
- **Monitor coverage drift**: track what % of production failures map to existing eval cases — below 60% means the dataset is stale

## Receipt

> Receipt pending — July 1, 2026
> Framework validated conceptually against: EvalEval Coalition's AI evals cost analysis (Hugging Face, April 2026), UTBoost SWE-Bench evaluation paper (ACL 2025), Open Legion's agent benchmark taxonomy (June 2026), industrializing.ai's "Evals Are Forever" analysis. Core pattern (production-mining → synthetic expansion → human calibration) confirmed against Giskard docs, OpenLegion eval architecture, and AgentArch enterprise benchmark methodology.

## See also

- [F-07 · Evaluation-Driven Development](f07-evaluation-driven-development.md) — wiring evals into the dev loop as a quality gate
- [F-178 · Synthetic Test Data Generation](f178-synthetic-test-data-generation.md) — generating test cases programmatically for agent pipelines
- [S-193 · LLM-as-Judge Eval Pipeline](stacks/s193-llm-as-judge-eval-pipeline.md) — using capable models to score outputs systematically
- [S-305 · Agent Trajectory Assertions](stacks/s305-agent-trajectory-assertions.md) — asserting on the agent's reasoning path, not just the final output
