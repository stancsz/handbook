# S-344 · Cost-Aware Multi-Dimensional Agent Evaluation

Your agent scores 89% on accuracy. Production tells a different story: it costs $3.40 per task, violates your data residency policy, and produces inconsistent results on the same input. You optimized for the one number benchmarks report, and shipped a system that fails on the five numbers that matter in production.

Accuracy-only evaluation is the performance metric equivalent of measuring a car by 0-60 time alone. Real agents live in cost budgets, latency SLAs, compliance frameworks, and reliability requirements. The CLEAR framework (Cost, Latency, Efficacy, Assurance, Reliability) operationalizes this — five dimensions, not one.

## Forces

- **50× cost variance for equivalent accuracy.** Systematic analysis of 12 agent benchmarks found agents ranging from $0.10 to $5.00 per task at similar accuracy. Teams that only measure accuracy ship agents that are technically correct and financially ruinous. The benchmark leaders never reported cost.
- **Performance drops 35–60% from lab to production.** Reliability at inference time (single run) is 60%; consistency across 8 runs drops to 25%. An agent that scores 89% once may score 45% on rerun — but accuracy-only benchmarks only measure single runs.
- **Security and compliance are invisible in benchmarks.** Zero of 12 major benchmarks systematically evaluate prompt injection resistance, policy compliance, or data handling. An agent that passes every accuracy test but leaks PII is a catastrophic failure, not a minor shortcoming.
- **The efficiency frontier is non-obvious.** The best agent isn't the most accurate — it's the most accurate per dollar, per millisecond, within your compliance envelope. These four constraints trade off in ways single-dimension benchmarks can't reveal.

## The move

The CLEAR framework measures five dimensions simultaneously. Each is measurable with production traces and structured logging.

### The five dimensions

**C — Cost per task.** Total tokens × cost/token across all model calls, including retries, tool results, and context. Break it down by component (planner, worker, judge) so you can route cost. Target: lowest cost that meets your reliability threshold — not lowest cost, period.

**L — Latency.** p50, p95, p99 task completion time. For multi-turn agents, measure per-turn latency and total task duration separately. A 2-second per-turn agent that completes in 3 turns is better than a 500ms per-turn agent that loops 12 times.

**E — Efficacy (accuracy).** Task completion rate on verifiable tasks. For open-ended tasks, use LLM-as-judge with a reference answer or rubric. Segment by task type — a routing agent that scores 95% on intent classification but 40% on edge cases is not a 95% agent.

**A — Assurance (safety + compliance).** Prompt injection resistance (measured by red-teaming), policy adherence (does it follow your escalation rules, data handling requirements), and output schema conformance. This is binary pass/fail on hard constraints, not a score.

**R — Reliability (consistency).** Pass-rate across N identical runs. Run each test case 3–8 times with temperature=0. Report both mean score and standard deviation. A 70% consistent agent (σ=2) is more deployable than a 85% agent (σ=22).

### Practical implementation

```python
from dataclasses import dataclass
from typing import Optional
import time

@dataclass
class CLEARResult:
    cost_usd: float          # total cost for this task
    latency_ms: float        # wall-clock time
    efficacy_score: float    # 0.0–1.0 task completion
    assurance_pass: bool    # True = passes all hard constraints
    reliability_score: float # consistency: std of efficacy across runs
    runs: int               # how many times this was run

def evaluate_agent_clear(
    agent_fn,
    test_cases: list[dict],
    runs_per_case: int = 8,
    cost_per_1k_tokens: float = 0.003,
    judge_model: str = "gpt-4o-mini",
) -> dict:
    """
    CLEAR evaluation across N test cases, M runs each.
    Returns per-case results and aggregate CLEAR scores.
    """
    results = []
    for case in test_cases:
        case_runs = []
        for _ in range(runs_per_case):
            start = time.monotonic()
            trace = agent_fn(case["input"])
            elapsed_ms = (time.monotonic() - start) * 1000

            cost = sum(
                (tok_count / 1000) * cost_per_1k_tokens
                for tok_count in trace.token_counts
            )

            # Efficacy: checkable task or LLM-as-judge
            if "expected_output" in case:
                efficacy = float(trace.output == case["expected_output"])
            else:
                efficacy = llm_judge_score(
                    case["input"], trace.output,
                    case.get("rubric"), model=judge_model
                )

            # Assurance: hard constraints
            assurance = all([
                not contains_pii_leak(trace.output),
                follows_policy(trace, case.get("policy")),
                conforms_schema(trace, case.get("required_schema")),
            ])

            case_runs.append(CLEARResult(
                cost_usd=cost,
                latency_ms=elapsed_ms,
                efficacy_score=efficacy,
                assurance_pass=assurance,
                reliability_score=0.0,  # filled below
                runs=1,
            ))

        # Aggregate reliability across runs
        efficacy_scores = [r.efficacy_score for r in case_runs]
        import statistics
        mean_eff = statistics.mean(efficacy_scores)
        std_eff = statistics.stdev(efficacy_scores) if len(efficacy_scores) > 1 else 0.0

        # R = consistency = how stable is the efficacy score
        # Lower std = higher reliability; invert to 0-1 scale
        reliability = max(0.0, 1.0 - (std_eff / 0.5))  # assumes max std of 0.5

        for r in case_runs:
            r.reliability_score = reliability

        results.extend(case_runs)

    # Aggregate across all cases
    return {
        "C": statistics.mean(r.cost_usd for r in results),
        "L_p50": sorted(r.latency_ms for r in results)[len(results)//2],
        "L_p95": sorted(r.latency_ms for r in results)[int(len(results)*0.95)],
        "E": statistics.mean(r.efficacy_score for r in results),
        "A": statistics.mean(float(r.assurance_pass) for r in results),
        "R": statistics.mean(r.reliability_score for r in results),
        "n_cases": len(test_cases),
        "n_runs": runs_per_case,
    }
```

### The efficiency frontier

Once you have CLEAR scores, plot E (efficacy) vs C (cost) per task type. The Pareto frontier tells you where to target. An agent at (E=0.82, C=$0.18) dominates one at (E=0.85, C=$2.10) for most production use cases — 3× the cost for 3% more accuracy is rarely worth it.

Apply conformant prediction: set a minimum reliability threshold (e.g., R≥0.70) and only compare agents above it. A 95% accurate agent with R=0.30 is more dangerous than an 82% agent with R=0.85 — it fails silently and unpredictably.

### Failure mode: the A trap

Assurance (A) is the most ignored CLEAR dimension and the most dangerous to ignore. Unlike the other four, A is a gate, not a score. An agent that passes 99% of A checks but fails 1% is not a 99% agent — it is a compliance violation waiting to happen. Treat A as a deployment gate: P(assurance_pass) must be ≥0.99 before the agent ships. Measure A separately per compliance category (data residency, escalation policy, PII handling) and gate each independently.

## Receipt

> Receipt pending — 2026-07-02. A minimal CLEAR harness was designed in this entry but not yet executed. Next step: instrument a production agent trace with token_counts and run the 8-run reliability pass on a 20-case eval set. Expected output: C/E/R scores stratified by task type, with cost breakdown per agent component.

## See also

- [S-302 · You Have Logs, But No Answers: The Agent Eval Gap](s302-you-have-logs-but-no-answers-the-agent-eval-gap.md) — the observability foundation this builds on
- [S-325 · The Token Economy: Why Agents Cost 50–500× More in Production](s325-agent-token-economy-production-cost-reality.md) — cost mechanics this extends
- [S-292 · LLM-as-Judge Failure Modes](s292-llm-as-judge-failure-modes.md) — the judge scoring layer used for Efficacy on open-ended tasks
- [S-308 · Production Per-Turn Agent Evaluation](s308-production-per-turn-agent-evaluation.md) — per-turn scoring that feeds into CLEAR dimensions
