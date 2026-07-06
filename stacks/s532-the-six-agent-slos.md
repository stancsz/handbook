# S-532 · The Six Agent SLOs — Why Your Agent Dashboard Is Lying to You

Your dashboard says the agent is healthy. 0.3% error rate, sub-second latency, no crashes. But 40% of agent tasks are silently failing — wrong tools called, wrong arguments passed, subtle hallucinations that pass the human review. Your monitoring stack was built for APIs. Agents need six signals, not one.

## Forces

- **One composite score hides which layer broke.** An `agent_score` of 0.85 can mean tool-call success at 0.97 carrying argument failures at 0.62, or grounded responses at 0.98 covering a tail-latency disaster. Bisection requires six numbers, not one.
- **Standard APM doesn't see agent failures.** HTTP status codes tell you whether a request arrived — not whether the agent's answer is correct. Agents fail silently in ways that look like success until the customer complains or the bill arrives.
- **Per-step reliability compounds downstream.** A 95%-per-step agent over 10 steps finishes ~60% of the time ([F-11](../forward-deployed/f11-agent-reliability.md)). Aggregate success metrics mask which step is the bottleneck.
- **Error rate is a lagging indicator.** A step that fails 5% of the time still succeeds 95% — it just succeeds slightly wrong. The output passes a superficial check; downstream consequences compound.

## The move

Define six operational SLOs for every agentic system. Treat them like infrastructure SLAs: set targets, measure continuously, alert on breach.

### The Six Metrics

| Metric | Measures | Working Baseline | SLO Type |
|--------|----------|-----------------|----------|
| **Task completion rate** | Trajectory delivered user goal end-to-end | ≥ 90% | Availability |
| **Tool-call success** | Right tool, schema-valid args, payload used | ≥ 95% | Availability (component) |
| **Recovery rate** | Recovered from transient tool failure | ≥ 70% | Reliability |
| **p99 latency** | Time from user input to task completion | ≤ 60s (adjust per use case) | Performance |
| **Guardrail trip rate** | Fraction of turns hitting safety/compliance gates | ≤ 2% (adjust per risk tier) | Safety |
| **Trace-grounded score** | 4-dimensional quality: grounded, complete, coherent, safe | ≥ 0.85 | Quality |

### Why six and not one

Each metric isolates a distinct failure mode:

- **Task completion** catches goal abandonment and early termination
- **Tool-call success** catches tool selection errors and schema mismatches — the most common production failure ([S-257](../stacks/s257-the-five-failure-modes-that-kill-production-agents.md))
- **Recovery rate** catches whether the agent's self-healing loops work ([S-199](../stacks/s199-agent-self-healing-loops.md))
- **p99 latency** catches tail failures that kill user experience at scale
- **Guardrail trip rate** catches over-eager safety triggering (false positives that block valid requests) or under-eager triggering (missed violations)
- **Trace-grounded score** catches quality degradation invisible to availability metrics — the model getting slightly worse without crashing

### Pinned evaluation sets

Point-in-time benchmarks answer "how good is the agent today?" The question that actually costs you money is "is the agent as good as it was last Tuesday?" A Stanford/UC Berkeley study documented GPT-4's accuracy on a specific task dropping from 84% to 51% between March and June 2023 without any version change being communicated.

Maintain a **pinned evaluation set** — a fixed collection of gold-standard input/output pairs stored in version control. Run against it on every deployment and on a nightly schedule. Track the delta. Treat regressions on the pinned set as severity-1 incidents.

```python
# Pinned eval set runner — minimal implementation
import json
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Callable

@dataclass
class EvalResult:
    name: str
    passed: bool
    score: float
    latency_ms: float
    timestamp: datetime
    regression_from_baseline: float  # negative = regression

@dataclass
class PinnedCase:
    id: str
    input: str
    expected_output: str | None
    eval_fn: Callable[[str, str], float]  # (output, expected) -> score

def run_pinned_eval(
    agent_fn: Callable[[str], str],
    cases: list[PinnedCase],
    baseline_scores: dict[str, float],
    regression_threshold: float = 0.05,
) -> list[EvalResult]:
    """
    Run a pinned eval set. A regression from baseline triggers an alert.
    See: Zylos Research, "AI Agent Longitudinal Evaluation", 2026-04-14
    """
    results = []
    for case in cases:
        start = datetime.utcnow()
        output = agent_fn(case.input)
        latency_ms = (datetime.utcnow() - start).total_seconds() * 1000

        score = case.eval_fn(output, case.expected_output or "")
        baseline = baseline_scores.get(case.id, score)  # first run = baseline
        regression = score - baseline

        results.append(EvalResult(
            name=case.id,
            passed=score >= 0.85,
            score=score,
            latency_ms=latency_ms,
            timestamp=datetime.utcnow(),
            regression_from_baseline=regression,
        ))

        # Update running baseline on sustained performance
        if regression < -regression_threshold:
            print(f"REGRESSION ALERT: {case.id} dropped {regression:.3f} from baseline")

    return results

# Nightly regression run
# def nightly_pinned_eval():
#     cases = load_cases_from_vcs("evals/pinned/")
#     baselines = load_baselines_from_vcs("evals/baselines.json")
#     results = run_pinned_eval(agent_fn=production_agent, cases=cases, baselines=baselines)
#     publish_to_datadog(results)
#     update_baseline_on_stable(results)  # only if all pass for 7 consecutive days
```

### Trace-grounded score (4 dimensions)

Composite quality scores collapse signal. Instead, measure four independent dimensions:

1. **Grounded** — claims traceable to retrieved evidence or tool results
2. **Complete** — all parts of the user's intent are addressed
3. **Coherent** — internally consistent, no contradictions across turns
4. **Safe** — no harmful content, no data leakage, guardrails intact

Each dimension scored 0–1. Surface them as four separate lines, not one average.

## Receipt

> Verified 2026-07-04 — Framework synthesized from FutureAGI's "AI Agent Reliability Metrics: Six SLOs (2026)" (updated May 20, 2026) and Zylos Research's "AI Agent Longitudinal Evaluation" (2026-04-14). Working baselines (≥90% task completion, ≥95% tool-call success, ≥70% recovery) are industry-observed production norms per FutureAGI; adjust per your actual use case. The pinned eval pattern is the canonical anti-regression pattern; the GPT-4 regression (84%→51%) is documented in the Zylos paper and is cited as the motivation for longitudinal evaluation frameworks.

## See also

- [F-11 · Agent Reliability](../forward-deployed/f11-agent-reliability.md) — pass^k compounding and per-step reliability math
- [S-257 · The Five Failure Modes That Kill Production Agents](../stacks/s257-the-five-failure-modes-that-kill-production-agents.md) — which failures map to which SLO
- [S-525 · Trace vs Eval: The Production Observability Gap](../stacks/s525-trace-vs-eval-the-production-observability-gap.md) — trace (what happened) vs eval (was it correct)
- [S-370 · Agent Chaos Engineering](../stacks/s370-agent-chaos-engineering-fault-injection-testing.md) — fault injection as a forcing function for SLO discovery
