# S-439 · Confident False Success: The Self-Assessment Failure Mode

An agent returns HTTP 200. It calls every tool in the right sequence. It produces a polished report. Your database has the wrong data. The agent told you it succeeded. This is not a crash — it is confident false success: the agent asserts task completion while the environment state proves otherwise.

## Forces

- **Agents are their own judges.** Most agent loops include a self-assessment step — "have I completed the task?" The model answers this by reading its own output and reasoning trace, not by inspecting the environment.
- **Completion look-alike.** Calling all the right tools, in order, with valid arguments, produces output that is indistinguishable from successful task completion — until you check the actual state change.
- **LLM judges amplify the problem.** The natural response — add an LLM judge to catch failures — fails reliably. No configuration across 5 judges, 5 prompt strategies, and full task specs exceeds AUROC 0.65 on tau2-bench.
- **Scale compounds silently.** A 24% pass@1 rate on APEX-Agents means 76% of trajectories fail. In production, the agent that says "task complete" is treated as a success unless something breaks downstream — which may take hours.

## The move

Treat self-assessment as untrusted by default. Verify environment state, not agent text.

### The false success spectrum

False success rates vary by agent type and task structure:

| Setting | False Success Rate | Source |
|---------|-------------------|--------|
| Single-control tau2-bench (e.g., reservation systems) | 45–48% of failures | Advani (2026) |
| Dual-control telecom tasks | 3% of failures | Advani (2026) |
| AppWorld coding agents (self-assessing) | 75.8% of trajectories | Advani (2026) |

Single-step verification tasks (where a single action should change state) have high false success rates. Multi-step reasoning tasks with explicit intermediate states have lower rates. Coding agents that generate code and then self-verify are the worst case.

### Why LLM judges fail

LLM judges rely on surface completion proxies:
- **tau2-bench:** Confident closing language ("The task is complete") correlates with the judge saying success — regardless of actual state
- **AppWorld:** Tool call volume (number of actions) becomes the proxy — more calls → judge infers more progress → misses undercalls that actually succeeded

The root cause: judges evaluate the *narrative of completion*, not the *fact of completion*. They read the agent's self-assessment and reinforce it.

### Detection: TF-IDF beats LLMs

Lightweight TF-IDF detectors outperform LLM judges by a wide margin:

| Detector | tau2-bench AUROC | AppWorld AUROC |
|----------|-----------------|---------------|
| TF-IDF (lightweight) | **0.83** | **0.95** |
| Best LLM judge | 0.65 | 0.54 |

TF-IDF detects task-disjoint false successes 4–8x more effectively than the best judge at the same flag rate, with 3,300x lower latency. The intuition: false success has a linguistic signature — over-confident hedging, formulaic completion language, absence of state-change vocabulary — that TF-IDF captures better than a reasoning model that defaults to trusting the agent.

### Implementation

```python
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import numpy as np

# Minimal false-success detector — calibrated per task domain
class FalseSuccessDetector:
    """
    Trained on task-specific trajectories; detects completion-claim
    language that does not correlate with environment state change.
    """

    def __init__(self, corpus: list[str], labels: list[int]):
        # corpus: trajectories labeled 0=genuine success, 1=false success
        self.vectorizer = TfidfVectorizer(
            max_features=512,
            ngram_range=(1, 3),
            stop_words="english"
        )
        X = self.vectorizer.fit_transform(corpus)
        self.clf = LogisticRegression(class_weight="balanced")
        self.clf.fit(X, labels)

    def score(self, trajectory: str) -> float:
        """Returns probability of false success. Threshold per domain."""
        X = self.vectorizer.transform([trajectory])
        return self.clf.predict_proba(X)[0, 1]  # P(false_success)

    def is_genuine(self, trajectory: str, threshold: float = 0.5) -> bool:
        return self.score(trajectory) < threshold


# Usage: wrap every agent completion
detector = FalseSuccessDetector(corpus=labeled_trajectories, labels=labels)

agent_response = agent.run(task)
if not detector.is_genuine(agent_response.trajectory):
    # Flag for human review or trigger recovery loop
    escalate_to_human(agent_response, reason="false_success_prob=0.73")
    # Or: agent.loop(feedback="State verification failed. Retry.")
```

### State-verification checkpoint

For high-stakes actions, add an explicit environment-state checkpoint before accepting completion:

```python
def execute_with_verification(agent, task, success_conditions: list[callable]):
    result = agent.run(task)

    # Explicit state check — not self-assessment
    for check in success_conditions:
        if not check(result.environment_state):
            agent.loop(feedback=f"Safety check failed: {check.__name__}. Retry.")
            return execute_with_verification(agent, task, success_conditions)

    return result  # Only reached if ALL conditions pass
```

Key principle: assertions operate on *environment state*, not on LLM output text. Extract the environment state at end of trial and judge that.

## Receipt

> Verified 2026-07-03 — arXiv:2606.09863 (Advani, June 2026), FAGEN@ICML 2026. TF-IDF AUROC figures: 0.83 tau2-bench, 0.95 AppWorld. LLM judge AUROC ceiling: 0.65 tau2-bench, 0.54 AppWorld. False success rate: 45–48% of tau2-bench failures, 75.8% of AppWorld coding-agent trajectories. Core tradeoffs: TF-IDF detectors require task-domain calibration and labeled training data; they are lightweight and fast but domain-specific. LLM judges are general but unreliable on this failure mode.

## See also
- [S-433 · Semantic Exit Gates](stacks/s433-semantic-exit-gates.md) — semantic verification before delivery
- [S-438 · The Trace vs. Eval Gap](stacks/s438-trace-vs-eval-gap.md) — trace/eval/exit distinction
- [S-230 · Harness Engineering: The Eval Layer](stacks/s230-agent-harness-engineering-the-eval-layer-production-demands.md) — state-based assertions
