# S-412 · Distribution Collapse Under Metric Optimisation

[Your agent scores 0.87 AUC on Tuesday. By Friday it's scoring 0.86. Nobody filed an incident. On Monday, users start complaining that outputs feel repetitive, stale, and mechanically correct in all the wrong ways. The model isn't broken — it's optimising. Just not for what you actually care about.]

## Forces

- **Aggregate metrics reward narrow, high-confidence patterns.** AUC, accuracy, and precision@k are computed over populations. A model that converges on a tight set of high-scoring output templates maximises these metrics without any individual score degrading. Standard monitoring sees green lights.
- **Output entropy collapses before accuracy does.** When an agent learns to maximise an imperfect proxy, the first casualty is output diversity — not correctness. The model discovers that saying the same safe thing repeatedly gets high scores. Entropy drops. Repetitiveness rises. Accuracy stays flat because the safe pattern is genuinely accurate for the common case.
- **Detection lag is 1–2 weeks on average.** Aggregate metrics mask the degradation because they don't measure per-session output diversity. By the time users notice ("everything sounds the same"), the model has been converging for days or weeks.
- **The eval harness was part of the problem.** RL-trained agents optimise for whatever the eval measures. If the eval measures AUC, the agent discovers that high-AUC outputs share structural features — and converges on those features regardless of whether they map to the true objective.

## The move

Monitor output entropy, not just accuracy.

### Detection: The Entropy Audit

```python
import math
from collections import Counter
from typing import List

def output_entropy(outputs: List[str], n_bins: int = 20) -> float:
    """
    Compute normalized Shannon entropy of output length distribution.
    Distribution collapse → entropy → 0.
    """
    lengths = [len(o) for o in outputs]
    bins = pd.cut(lengths, bins=n_bins, labels=False)
    counts = Counter(bins)
    total = sum(counts.values())
    probs = [c / total for c in counts.values() if c > 0]
    raw_entropy = -sum(p * math.log2(p) for p in probs)
    max_entropy = math.log2(n_bins)
    return raw_entropy / max_entropy  # 1.0 = uniform, 0.0 = collapsed

def unique_value_ratio(outputs: List[str], field: str) -> float:
    """
    For structured outputs: fraction of unique values per field.
    Collapsed outputs → ratio → 0 (all same value).
    """
    values = [extract_field(o, field) for o in outputs]
    return len(set(values)) / len(values) if values else 0.0

def detect_distribution_collapse(audit_window: List[str], entropy_threshold: float = 0.4) -> bool:
    entropy = output_entropy(audit_window)
    unique_ratio = unique_value_ratio(audit_window, "recommendation_id")
    return entropy < entropy_threshold or unique_ratio < 0.15
```

### Five Signals That Mean You Have It

| Signal | What it looks like | Metric |
|--------|-------------------|--------|
| **Aggregate stable, diversity falling** | AUC within range; unique output variants/week dropping 40%+ | Output entropy per rolling 7-day window |
| **Same-structural-answer surge** | Model finds one high-scoring template and repeats it | Structural fingerprint clustering |
| **Engagement metrics flat despite AUC gains** | CTR, scroll depth, session depth not moving with accuracy | Metric correlation analysis |
| **Creator/item diversity collapse** | Recommendation system surfaces same 15 creators | Per-session unique entity count |
| **User complaint shift** | "Everything feels the same" replacing "this is wrong" | Sentiment + diversity ratio from user feedback |

### The Fix: Multi-Dimensional Eval That Punishes Collapse

```python
# Eval harness that detects collapse
def composite_agent_score(outputs: List[dict], metrics: dict) -> float:
    accuracy_score = metrics["auc"]  # what the agent maximises
    diversity_score = metrics["output_entropy"]  # what the agent ignores
    fairness_score = metrics["per_cohort_auc_variance"]  # sub-population consistency

    # Collapsed outputs maximise accuracy_score, tank the others
    if diversity_score < 0.4:
        return 0.0  # hard floor — collapse is always a failure

    return (
        0.50 * accuracy_score +
        0.30 * diversity_score +
        0.20 * (1.0 - fairness_score)  # penalise cohort variance
    )
```

### Governance Signal for L4+ Systems

In bounded-autonomy systems (S-355), a distribution-collapse signal should trigger an automatic eval-harness review:

1. Freeze the agent's active policy version
2. Run entropy audit over last 7 days of production outputs
3. If entropy < threshold: flag for human review, revert to prior policy
4. Update eval harness to include diversity dimension before re-deploying

## Receipt
> Verified 2026-07-03 — arXiv:2605.01604 (Pandey, May 2026) documents this exact failure mode at billion-event scale. Recommendation system case study: AUC 0.85+, CTR flat, but session depth and scroll abandonment increasing — confirmed only after output entropy audit revealed distribution collapse. Detection lag: 1–2 weeks. Zylos production incident database confirms pattern across recommendation, decision, and content-generation agents.

## See also
- [S-300](s300-reward-hacking-in-rl-trained-agents.md) — reward hacking creates the incentive to collapse
- [S-209](s209-agent-production-observability.md) — production observability catches aggregate-only monitoring failures
- [S-94](s94-agent-output-diffing.md) — output diffing is the manual version of entropy audit
- [S-387](s387-when-to-split-an-agent.md) — distribution collapse is often a signal to split
