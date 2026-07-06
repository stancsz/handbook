# S-651 · Agentic SLOs: The Six Metrics That Actually Matter

[Traditional SLOs assume 200-or-500. AI agents return 200 while being confidently wrong — and standard APM misses it entirely. If you measure only availability and latency, you don't know if your agent is working.]

## Forces

- **Agents fail on a spectrum, not a binary.** A 94% task-success rate and an 81% rate look identical in your APM dashboard. Both return 200. Neither crashes. The drift is invisible until a customer reports it — three weeks later.
- **Compounding kills reliability silently.** A 4-agent pipeline where each step has 95% reliability gives you 81.5% end-to-end reliability — lower than any individual step. Traditional SRE error budgets assume independent steps; agentic steps aren't.
- **HTTP status lies about agent quality.** The agent returns 200 with a hallucinated policy number. The agent calls the right tool with wrong arguments. The agent completes the task in 47 seconds instead of 4. APM sees three healthy services. The user gets a wrong answer.
- **Teams mistake instrumentation for reliability.** Tracing every LLM call is not the same as knowing whether the agent achieved the user's goal. You need goal-level metrics, not call-level metrics.

## The Move

Treat agent reliability as **six independent SLOs**, each with its own SLI, target, and error budget. An aggregate "agent score" hides which layer broke. Six discrete metrics don't.

### The Six SLIs

| # | SLI | Measures | Target (baseline) | Type |
|---|-----|----------|-------------------|------|
| 1 | **Task completion rate** | End-to-end goal achieved, not just response returned | ≥ 90% | Availability |
| 2 | **Tool-call success** | Right tool, valid args, response used by next step | ≥ 95% | Component |
| 3 | **Recovery rate** | Transient tool failures recovered without escalation | ≥ 70% | Reliability |
| 4 | **P99 task latency** | Time from first user input to goal achieved or graceful fail | ≤ 5 min (batch), ≤ 30s (interactive) | Latency |
| 5 | **Guardrail trip rate** | Safety/egress filters that block or redact output | 1–5% (too low = they're not working) | Policy |
| 6 | **Trace-grounded score** | 4-D rubric: grounding, safety, efficiency, utility | ≥ 0.8 / 1.0 | Quality |

### Defining SLIs You Can Actually Measure

```
```python
# Task completion SLI — define per workflow type
# "Did the agent achieve the stated goal?"
def task_completion_check(trace):
    workflow_type = trace.metadata["workflow_type"]

    if workflow_type == "ticket_creation":
        # Deterministic: did the ticket exist with correct fields?
        return (
            trace.output.get("ticket_id") is not None
            and trace.output.get("ticket_id") != "FAILED"
            and trace.db_verify("ticket", trace.output["ticket_id"])
        )
    elif workflow_type == "code_review":
        # LLM-as-judge with rubric
        score = llm_judge.evaluate(
            trace,
            rubric="finds_real_bugs AND not_false_positives"
        )
        return score >= 0.8
    else:
        return None  # Undefined — don't count toward SLO

# Tool-call success SLI — instrument every tool boundary
def tool_success_metric(tool_result, tool_config):
    return (
        tool_result.error is None          # didn't throw
        and tool_result.output is not None  # returned data
        and tool_result.output_used        # next agent consumed it
    )

# Recovery rate SLI
def recovery_metric(trace):
    failures = [s for s in trace.steps if s.tool_failed]
    recoveries = [f for f in failures if f.recovered_within(max_retries=2)]
    if not failures:
        return None  # No failures = doesn't affect SLO
    return len(recoveries) / len(failures)

# Guardrail trip rate SLI — monitor the policy layer
def guardrail_trip_rate(trace):
    trips = trace.metadata.get("guardrail_trips", 0)
    return trips / trace.total_requests
```

### Error Budget Policy: Burn Rate Alerting

Traditional threshold alerts fire on absolute counts. Error budget alerts fire on *burn rate* — how fast you're consuming your allowed failure quota.

```python
def burn_rate(failures_in_window, window_hours,
              total_budget, budget_period_hours=720):
    """
    Budget period: 30 days = 720 hours.
    SLO: 90% task completion = 10% allowed failures.
    Total budget = 0.10 * total_tasks_in_30_days.
    """
    budget_per_hour = total_budget / budget_period_hours
    actual_rate = failures_in_window / window_hours
    return actual_rate / budget_per_hour

# Alert thresholds (from Google SRE error budget playbook):
# 14.4x burn rate over 1h  → CRITICAL (budget gone in ~2 days)
#  6.0x burn rate over 6h  → WARNING  (budget gone in ~5 days)
#  3.0x burn rate over 24h → WATCH    (budget gone in ~10 days)

def slo_alert(burn_rate_val, window_hours):
    if window_hours == 1 and burn_rate_val >= 14.4:
        return "CRITICAL: error budget nearly exhausted"
    elif window_hours == 6 and burn_rate_val >= 6.0:
        return "WARNING: budget burning faster than acceptable"
    elif window_hours == 24 and burn_rate_val >= 3.0:
        return "WATCH: sustained degradation"
    return None  # Within budget
```

### Alerting Anti-Patterns

**Don't alert on individual task failures.** A 90% SLO tolerates 10% failure — you will fatigue your on-call engineer alerting on every miss.

**Do alert on budget burn rate.** The burn rate tells you *whether the SLO is at risk*, not just whether a failure occurred.

**Alert on SLO regression, not score level.** A task-completion rate of 85% is fine if your SLO is 80%. It's a violation only if it's below your SLO *and* burning budget faster than acceptable.

## Receipt

> Verified 2026-07-05 — Research synthesis from FutureAGI (2026-05-20), Chanl Blog (2026-05-28), BuildMVPFast (2026), Microsoft Tech Community (2026). Core six-SLO framework, burn rate thresholds, and SLI definitions trace to these sources. Code examples constructed from standard Prometheus/OpenTelemetry patterns described in source material. Receipt pending — live implementation run with production data.

## See also

- [S-281 · Agent Evaluation Is the Missing Layer Nobody Builds Until Production Breaks](stacks/s281-agent-evaluation-the-layer-nobody-builds-until-production-breaks.md) — Eval frameworks that feed the trace-grounded score SLI
- [S-340 · Agent Hard Enforcement Plane](stacks/s340-agent-hard-enforcement-plane.md) — Hard caps, loop bounds, escalation gates that enforce the latency and recovery SLIs
- [S-646 · The Multi-Agent Error Compounding Problem](stacks/s646-the-multi-agent-error-compounding-problem.md) — Why end-to-end reliability is worse than any single step's
- [S-649 · The Inference Cost Cliff](stacks/s649-the-inference-cost-cliff.md) — Cost SLOs as a parallel reliability axis
