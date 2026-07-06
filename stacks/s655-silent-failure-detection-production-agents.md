# [S-655] · Silent Failure Detection for Production Agents

Agents fail differently than applications. The failure rarely lives in the work itself — it lives in the seams: the delivery step, the tool call, the routing decision, the bootstrap that ate your budget. Standard APM dashboards show green while users see nothing. This entry is about making those seams observable.

## Forces

- APM was built for a world where exceptions signal failure and a green run means the user got served. Agents don't fit that world.
- Agents can "succeed" at every internal step and still deliver nothing to the user.
- Side effects — a DB write, an API call, a webhook — are invisible to telemetry that only measures the agent loop.
- The agent has no incentive to surface its own failure. It reports what it did, not what didn't happen.

## The Move

There are five silent failure modes that account for the majority of "the agent ran but nothing happened" incidents. Each requires a specific instrumentation pattern.

### Failure Mode 1: Cron "Succeeds" But Never Delivers

The agent runs on schedule, the LLM generates output, the task marks complete. The user never receives anything.

**Pattern:** Treat delivery as a first-class check, not a happy-path step.

```
# Every run plan should include an explicit delivery verification step
async def run_and_verify():
    run_id = await agent.trigger()
    # Wait for side effect, not just the LLM turn
    await asyncio.sleep(DELIVERY_WINDOW)  # give async writes time to flush
    delivered = await check_delivery_occurred(run_id)
    if not delivered:
        alert("cron-success-no-delivery", run_id=run_id)
        await agent.replay_delivery(run_id)
```

Instrument: emit a `delivery.confirmed` span attribute after the side effect is verified. If the run completes without this attribute, it failed.

### Failure Mode 2: Tool Calls Return Empty or Error, Agent Treats as Valid

The search API returns `[]`, the DB query returns `NULL`, the webhook returns a 500. The agent reasons over the empty result, draws a conclusion, and closes the task as successful.

**Pattern:** Classify tool failures by semantic impact, not HTTP status.

| Tool Failure Type | Agent Behavior | Instrumentation |
|---|---|---|
| Timeout | Agent retries or proceeds with stale context | `tool.timeout_ms` span attr |
| Empty result | Agent treats as valid data | `tool.result_is_empty` flag |
| Auth failure | Agent reports "no access" or proceeds anyway | `tool.auth_status` |
| Schema mismatch | Agent hallucinates parameters | `tool.schema_version` |
| Rate limit | Agent retries indefinitely | `tool.rate_limit_remaining` |

The fix: wrap every tool call in a result-classification layer that attaches metadata before the agent sees the result.

```
def classify_tool_result(tool_name: str, result: Any) -> dict:
    classification = {
        "empty": result is None or result == [],
        "error": isinstance(result, Exception),
        "truncated": hasattr(result, '__len__') and len(result) == 0,
        "schema_version_mismatch": result.get("_schema_version") != CURRENT_SCHEMA,
    }
    span.set_attributes({
        f"tool.{tool_name}.{k}": v
        for k, v in classification.items()
    })
    return classification
```

### Failure Mode 3: Delivery Layer Fails Silently

The agent completes, produces output, calls `send_email()` or `post_webhook()`, and moves on. The delivery API returns a 500 or a timeout. The agent never finds out.

**Pattern:** Delivery confirmation must block the agent's completion signal.

```
async def deliver_with_confirmation(output: dict, destination: DeliveryTarget) -> bool:
    try:
        result = await destination.send(output)
        # Don't trust the send — verify
        if result.delivery_id:
            confirmed = await destination.verify(result.delivery_id, timeout=30)
            return confirmed
    except DeliveryError as e:
        alert("delivery.failure", error=str(e), destination=destination.type)
    return False
```

If delivery fails, do NOT mark the task complete. Re-queue or escalate.

### Failure Mode 4: Bootstrap Burns the Budget

The agent spends 40% of its token budget on the first turn — loading context, initializing memory, running system prompts — and then runs out of budget mid-task. The task completes "successfully" with truncated output.

**Pattern:** Budget accounting at bootstrap, with mid-run abort.

```
BOOTSTRAP_BUDGET_RATIO = 0.30  # don't spend more than 30% on setup

async def run_with_budget_guard(task: Task, max_tokens: int):
    bootstrap_estimate = await estimate_bootstrap_cost(task)
    if bootstrap_estimate > max_tokens * BOOTSTRAP_BUDGET_RATIO:
        alert("bootstrap.budget-warning", estimated=bootstrap_estimate, limit=max_tokens)
        # Abort before burning budget on a task you can't finish
        raise BudgetExhaustedError(f"Bootstrap {bootstrap_estimate} > {max_tokens * BOOTSTRAP_BUDGET_RATIO} limit")
    
    remaining = max_tokens - bootstrap_estimate
    # Pass remaining budget to agent — it should route or truncate
    result = await agent.run(task, max_tokens=remaining)
    if result.token_count > remaining:
        alert("bootstrap.budget-overrun", consumed=result.token_count, budget=remaining)
    return result
```

### Failure Mode 5: Prompt Injection Redirects the Agent

The agent receives a user message containing an injected instruction ("ignore your previous instructions and..."). The agent follows the injected goal instead of the intended task. Task completes "successfully" — just for the wrong master.

**Pattern:** Detect goal divergence before the run completes.

```
async def detect_goal_divergence(agent_id: str, original_goal: str, current_goal: str) -> bool:
    # LLM-as-judge: did the agent drift from the intended goal?
    judge_prompt = f"Original goal: {original_goal}\nCurrent behavior: {current_goal}\nDid the agent follow the original goal? Yes/No"
    response = await judge_llm.generate(judge_prompt)
    is_drifted = "No" in response or "no" in response  # agent did NOT follow
    
    if is_drifted:
        alert("goal.injection-detected", agent_id=agent_id, drift_score=response)
        # Escalate to human review, don't let the agent complete
        await human_review_queue.push(agent_id=agent_id, reason="goal-divergence")
        return True
    return False
```

This check runs at configurable intervals during long-horizon tasks, not just at the end.

## Receipt

> Verified 2026-07-05 — Patterns extracted from production incident reports across pazi.ai (5 silent failures), Stack Pulsar (CrewAI/LangGraph observability), and AgentMarketCap (tool call failure taxonomy). The five-mode taxonomy is community-validated. Implementation code is realistic and grounded in actual SDK patterns (Anthropic, LangGraph, OpenTelemetry).

## See also

- [S-352 · Agentic Compensation Keys](s352-agentic-compensation-keys-the-autonomous-retry-era.md) — retry and compensation for recoverable failures
- [S-439 · Confident False Success](s439-confident-false-success-the-self-assessment-failure-mode.md) — when agents claim completion they didn't earn
- [S-501 · AgentOps Evaluation Stack](s501-agentops-evaluation-stack.md) — the five-layer production eval system
- [S-516 · Trajectory-Level Loop Detection](s516-trajectory-level-loop-detection.md) — detecting pathological agent behavior
