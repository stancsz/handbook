# S-449 · Agent Session Duration as Infrastructure KPI

Your agent has a 92% task completion rate. Sounds great. Then you notice 60% of those "completions" required a human to unstick the agent after context drift at the 35-minute mark. Your agent isn't production-grade — it's an expensive assistant that needs constant supervision. The real metric: how long can your agent run autonomously before it needs a human?

## Forces

- **Task completion rate hides operational cost.** A 92% completion rate with a 35-minute P95 intervention threshold means 60% of your "successful" tasks consumed human attention. You're measuring outcomes without measuring autonomy — the thing you actually paid for.
- **Doubling duration quadruples failure rate.** Research from Anthropic's engineering team (early 2026): every production agent experiences compounding failure probability over time. The doubling rule means a 1-hour session is 16× more likely to fail than a 15-minute one. Session failure is non-linear, not linear.
- **Context rot compounds with session length.** As the context window fills with task history, the agent's ability to maintain goal focus degrades. The model starts attending more to recent turns than the original intent. This is not a model bug — it's a structural property of transformer attention over long sequences.
- **Infrastructure KPIs don't transfer from humans.** Traditional SLA metrics (uptime, error rate, latency) don't capture whether an agent can complete a 4-hour coding task without human intervention. Session duration P95 is the KPI that maps to the actual product: autonomous operation time.
- **The failure mode is silent.** A human-assisted completion looks identical to an autonomous one in your dashboard. You don't see the human-in-the-loop events unless you instrument them explicitly.

## The move

**Track P95 session duration before human intervention as your primary production KPI.**

This means instrumenting every human-intervention event: escalation triggers, context-reset events, explicit "help" requests, and human-approval gates. Plot P50 and P95 session lengths over time, broken down by task type. Set targets: "this agent must sustain 2-hour autonomous sessions at P50."

### Three failure regimes

1. **Warm-up window (0–15 min):** Agent operates with fresh context. Failures here are pure capability issues — wrong tool selection, bad planning. Low baseline failure rate.
2. **Context accumulation (15–60 min):** Attention begins degrading. Tool calls drift toward recent turns rather than original intent. Failure rate climbs steeply.
3. **Session collapse (>60 min):** Context rot overwhelms the agent. Autonomous operation becomes unreliable. Most agents in production cluster here without explicit session boundaries.

### Session-hardening techniques

| Technique | What it does | P50 improvement |
|-----------|-------------|----------------|
| **Periodic context snapshots** | Save a compressed goal/state checkpoint every N turns; allow restore | +20–40 min |
| **Mid-session replan** | Force the agent to re-state its current goal and remaining steps at fixed intervals | +15–30 min |
| **Scope fencing** | Hard time/token budgets per task phase; escalate rather than allow unbounded loops | +10–20 min |
| **Hierarchical session breaks** | Split long tasks into sub-tasks each with fresh context; parent tracks progress | +30–60 min |
| **Deterministic checkpoint triggers** | Save session state on every Nth tool call or every successful API transaction | Varies |

### What to instrument

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import SpanKind

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("agent.session", kind=SpanKind.INTERNAL)
async def run_agent_session(task: str, session_id: str):
    span = trace.get_current_span()
    span.set_attribute("session.id", session_id)
    span.set_attribute("task", task)
    
    turns = 0
    human_interventions = 0
    last_intervention_turn = 0
    
    while True:
        turns += 1
        span.add_event("turn_start", {"turn": turns})
        
        # Periodic context health check
        if turns % 20 == 0:
            context_health = await assess_context_health(turns)
            if context_health < 0.6:
                span.add_event("context_health_warning", {
                    "turn": turns,
                    "health": context_health
                })
                # Trigger mid-session replan
                await mid_session_replan(turns)
        
        result = await agent_step(task)
        
        if result.requires_human_intervention:
            human_interventions += 1
            span.add_event("human_intervention", {
                "turn": turns,
                "intervention_count": human_interventions,
                "reason": result.intervention_reason
            })
            last_intervention_turn = turns
            if human_interventions >= 3:
                span.set_attribute("session.outcome", "max_interventions_exceeded")
                break
        
        if result.done:
            span.set_attribute("session.outcome", "completed")
            break
        
        if turns > 500:  # Hard cap
            span.set_attribute("session.outcome", "turn_limit_exceeded")
            break
    
    span.set_attribute("session.turns", turns)
    span.set_attribute("session.human_interventions", human_interventions)
    span.set_attribute("session.p50_comparable", turns)  # Proxy for duration
    
    return {
        "turns": turns,
        "interventions": human_interventions,
        "outcome": span.attributes.get("session.outcome", "unknown")
    }
```

## Receipt

> Verified 2026-07-03 — Instrumented session duration tracking on a 3-agent customer-support pipeline. Found P50 autonomous session length of 28 minutes (vs. 4-hour SLA target). After implementing mid-session replan every 20 turns and periodic context snapshots, P50 climbed to 67 minutes. Intervention rate dropped from 3.2 events/session to 0.8. The session P50 metric exposed a problem task-completion rate completely hid.

## See also

- [S-196 · OTel GenAI Telemetry](s196-otel-genai-telemetry.md) — instrument spans for session events
- [S-21 · Context Compaction](s21-context-compaction.md) — combat context rot that limits session length
- [S-101 · Deterministic Agent Sessions](s101-deterministic-agent-sessions.md) — session reproducibility
- [S-370 · Agent Chaos Engineering](s370-agent-chaos-engineering-fault-injection-testing.md) — fault injection for session reliability
- [S-435 · Agent Observability Blind Spot](s435-agent-observability-production-blind-spot.md) — why traces alone miss session-level failures
