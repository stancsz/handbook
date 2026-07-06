# S-401 · Agent Drift — The Longitudinal Regression Problem

You ship a great agent on Monday. It scores 91% on your eval suite. By Friday it's at 74%. By next Monday, your on-call engineer has manually intervened eight times. The code didn't change. The prompt didn't change. Nothing broke — the agent just quietly became worse. This is agent drift: behavioral degradation in production with no code change to blame. And it's the most underreported failure mode in AI infrastructure today.

## Forces

- **Canonical benchmarks are point-in-time lies.** A 94% on MMLU tells you how the agent performed on a curated test set in April. It tells you nothing about whether it still behaves that way in July, after the model provider quietly updated their weights, the input distribution shifted, or the agent's internal memory accumulated enough context artifacts to bias its decisions.
- **No code change means no CI trigger.** Your regression suite only runs when code changes. Agent drift has no trigger — it accumulates silently across the background radiation of model updates, data shifts, and context rot. Every status indicator reads green.
- **The gap between "passes eval" and "works in production" is a moving target.** A single eval run answers "how good is the agent today?" The question that matters is "is the agent as good as it was last Tuesday?" Traditional ML monitoring (accuracy, latency, error rate) doesn't catch behavioral drift — the agent still returns 200s, still produces valid JSON, still calls the right tools. The outputs are just worse.
- **Drift compounds before it surfaces.** Stanford's 2026 AI Index and multiple practitioner reports confirm: behavioral degradation in production agents typically takes 10–14 days to reach visible failure levels, but accuracy can drop 15–25 percentage points in that window. By the time users complain, the damage is done.

## The Move

Agent drift has three distinct manifestations, each requiring a different detection approach:

### The Three Drift Axes

**Semantic drift** — the agent's outputs progressively deviate from the original intent, even on the same inputs. The agent still answers questions, but the answers shift in framing, depth, or emphasis in ways that compound over time. Detected via: golden dataset scoring over time (rerun the same test cases monthly and track score variance).

**Behavioral drift** — the agent's action patterns change: tool selection frequency shifts, reasoning chains get shorter or longer, refusal behavior changes. Detected via: behavioral telemetry — track tool selection distribution, average reasoning steps, and escalation rate per week. A 2σ shift in any axis is a leading indicator.

**Coordination drift** (multi-agent only) — inter-agent agreement rates decline, handoff quality degrades, consensus rounds increase. Detected via: multi-agent telemetry — track consensus convergence rate and inter-agent agreement scores over time.

### The Anti-Drift Architecture

The fix is not a monitoring dashboard. It's a continuous evaluation loop that runs against a tracked golden dataset on a schedule, regardless of whether anything changed:

```python
from datetime import datetime, timedelta
from typing import Callable
import anthropic

class DriftDetector:
    """
    Reruns a golden dataset against the live agent on a schedule.
    Tracks score trajectories to detect degradation before users notice.
    """

    def __init__(
        self,
        golden_dataset: list[dict],
        scoring_fn: Callable[[dict, dict], float],
        baseline_threshold: float = 0.90,
        drift_threshold_pct: float = 0.05,  # 5% drop triggers alert
        window_days: int = 14,
    ):
        self.golden = golden_dataset
        self.score_fn = scoring_fn
        self.baseline_threshold = baseline_threshold
        self.drift_threshold_pct = drift_threshold_pct
        self.window_days = window_days
        self.client = anthropic.Anthropic()
        self.history: list[dict] = []  # {"date": ..., "scores": [float, ...]}

    def run_eval(self) -> dict:
        """Run full golden dataset against the live agent."""
        scores = []
        for case in self.golden:
            response = self.client.messages.create(
                model="claude-sonnet-4-6-20250514",
                max_tokens=1024,
                system=case["system_prompt"],
                messages=[{"role": "user", "content": case["input"]}],
            )
            score = self.score_fn(case, response)
            scores.append(score)

        return {
            "date": datetime.utcnow().isoformat(),
            "mean": sum(scores) / len(scores),
            "min": min(scores),
            "max": max(scores),
            "scores": scores,
        }

    def detect_drift(self) -> dict:
        """
        Compare current window average to previous window.
        Triggers alert if drop exceeds drift_threshold_pct.
        """
        current = self.run_eval()
        self.history.append(current)

        # Keep only window
        cutoff = datetime.utcnow() - timedelta(days=self.window_days)
        self.history = [
            h for h in self.history
            if datetime.fromisoformat(h["date"]) >= cutoff
        ]

        if len(self.history) < 2:
            return {"status": "insufficient_data", "current_mean": current["mean"]}

        # Compare to oldest point in window
        baseline_record = self.history[0]
        baseline_mean = baseline_record["mean"]
        current_mean = current["mean"]

        pct_change = (current_mean - baseline_mean) / baseline_mean

        return {
            "status": "drift_detected" if pct_change < -self.drift_threshold_pct else "ok",
            "current_mean": current_mean,
            "baseline_mean": baseline_mean,
            "pct_change": pct_change,
            "window_days": self.window_days,
            "num_cases": len(self.golden),
        }
```

### Operational Schedule

Don't just detect drift — operationalize the response:

| Interval | Action |
|----------|--------|
| **Daily** | Run behavioral telemetry (tool selection distribution, step counts, error rates). No scoring — just anomaly detection. |
| **Weekly** | Rerun golden dataset scoring. Compare to 7-day and 14-day baselines. Alert on >3σ drop. |
| **Monthly** | Full regression suite against all golden cases. Update baseline if scores stabilize higher. Retire cases the agent consistently nails; add cases it struggles with. |
| **On model update** | Mandatory full eval run before traffic cutover. Compare to pre-update baseline. Block if drop >2%. |

### The Golden Dataset Maintenance Loop

Golden datasets rot too. If you never update them, they stop reflecting real production inputs. Treat them as living infrastructure:

- **Add production inputs** that triggered escalations or edge cases. Every user complaint is a missed test case.
- **Prune cases** the agent scores 100% on consistently — they add no signal, only noise.
- **Tag cases by topic and difficulty** so you can measure drift per-segment. A 3% overall drop might be 15% on code-generation cases and flat on summarization.
- **Version golden datasets** in git alongside agent code. The eval for v2.3 should run against golden-v2.3, not the dataset that was current when v2.0 shipped.

## See also

- [S-246 · The Production Eval Pipeline — Four Stages, Zero Surprises](s246-production-eval-pipeline-the-four-stage-loop.md) — covers the architectural layers of eval; S-401 adds the temporal dimension
- [S-220 · Agentic Behavioral Regression Suite](s220-agentic-behavioral-regression-suite.md) — covers regression on change events; S-401 covers regression from background factors
- [S-383 · Goal Drift: The Silent Competence Erosion Pattern](s383-goal-drift-the-silent-competence-erosion-pattern.md) — covers goal-level drift in long-horizon tasks; S-401 covers behavioral drift across all task types
