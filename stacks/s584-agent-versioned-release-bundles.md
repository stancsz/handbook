# S-584 · Agent Versioned Release Bundles: The Release Engineering Discipline AI Never Had

[S-101](s101-deterministic-agent-sessions.md) covers deterministic agent sessions — append-only action logs and replay. [S-209](s209-agent-production-observability.md) covers observability — OTel tracing, span conventions, and monitoring dashboards. [S-222](s222-agent-trajectory-replay.md) covers trajectory replay — reconstructing the exact decision context for debugging.

None of these cover the release engineering question: **what combination of parts shipped, and was it safe to ship?**

When a traditional service fails, you know what version ran. When an AI agent fails, you often don't — because the agent's behavior is the emergent product of five loosely-coupled inputs that change independently: the prompt, the model, the tool manifest, the retrieval/memory config, and the validator. Teams that treat agent deployment as "update the prompt string" ship silent regressions daily. Teams that treat it as a versioned bundle with a rollback target ship with confidence.

## Forces

- An agent's behavior is a composite of 5+ independently-versioned components — changing any one is a de-facto new release, but most teams have no mechanism to detect or track this
- Agent quality is non-binary and probabilistic — a regression does not surface as a crash, it surfaces as degraded accuracy or a changed decision pattern that users may not report
- Traditional blue/green and canary deployments use binary health checks that don't apply — an agent can return "200 OK" while being confidently wrong
- Rollback in traditional software is git revert; in an agent system, reverting the prompt while the model version has moved forward creates a compound state that neither old nor new

## The move

### 1. Define the release bundle

Treat every production agent deployment as an atomic bundle with a named, recoverable version. Minimum viable bundle:

```yaml
agent_bundle_v2_3_1:
  prompt_version: "prompts/customer-support/v2.3.1.yaml"
  model_version: "claude-sonnet-4-20250514"
  tool_manifest_version: "tools/csat-bot/v8.2.sha256"
  retrieval_config_version: "retrieval/csat-v3.yaml"
  validator_version: "validators/csat-checker/v1.4.yaml"
  memory_config_version: "memory/sessions-v2.yaml"
  released_at: "2026-07-04T09:00:00Z"
  released_by: "team-lead"
  rollout_strategy: "canary_10pct"
```

Every component that influences agent output gets a version tag. Store the bundle manifest alongside your deployment — in Git, a DB table, or a versioned config file. The critical property: given a bundle ID, you can reconstruct exactly what ran.

### 2. Instrument bundle identity at runtime

Inject the bundle version into every LLM call and tool invocation as metadata:

```python
# Every LLM call carries the bundle context
response = anthropic.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    system=system_prompt,
    messages=conversation_history,
    extra_headers={
        "X-Agent-Bundle": current_bundle.id,
        "X-Agent-Bundle-Hash": current_bundle.content_hash,
    }
)

# Every tool call logs the bundle version
async def call_tool(tool_name, args, bundle_id):
    span.set_attributes({
        "agent.bundle_id": bundle_id,
        "agent.bundle_hash": bundle.content_hash,
        "agent.prompt_version": bundle.prompt_version,
        "agent.model_version": bundle.model_version,
    })
    result = await execute_tool(tool_name, args)
    log_tool_result(result, bundle_id=bundle_id)
    return result
```

This means every trace, every replay session, every user complaint can be traced back to the exact bundle that produced it. Without this, you are doing archaeology.

### 3. Canary with behavioral gates, not health checks

Traditional canary uses error rate and latency thresholds. Agent canary must also use behavioral metrics:

```python
def canary_gate(candidate_bundle, production_bundle, traffic_pct=10):
    """
    Route N% of traffic to candidate bundle.
    Compare behavioral metrics against production baseline.
    Only promote if all gates pass.
    """
    canary_results = run_shadow_traffic(candidate_bundle, sample_size=200)
    baseline_results = load_production_baseline(candidate_bundle.task_type)

    gates = {
        "task_completion_rate": (
            canary_results.completion_rate >= baseline_results.completion_rate * 0.95
        ),
        "tool_call_accuracy": (
            canary_results.tool_accuracy >= baseline_results.tool_accuracy * 0.97
        ),
        "hallucination_rate": (
            canary_results.hallucination_rate <= baseline_results.hallucination_rate * 1.05
        ),
        "avg_cost_per_task": (
            canary_results.cost_per_task <= baseline_results.cost_per_task * 1.10
        ),
    }

    if all(gates.values()):
        promote_bundle(candidate_bundle)
    else:
        rollback_candidate(candidate_bundle)
        alert_oncall(f"Canary gates failed: {[k for k,v in gates.items() if not v]}")
```

Behavioral gates compare the new bundle against a frozen baseline on the same task distribution. The 5% tolerance on completion rate accounts for natural variance — tight enough to catch regressions, loose enough to avoid false positives.

### 4. Implement progressive rollout with abort points

```python
STAGES = [
    {"pct": 1, "duration_minutes": 30, "gate": "smoke_tests_only"},
    {"pct": 10, "duration_minutes": 120, "gate": "behavioral_comparison"},
    {"pct": 50, "duration_minutes": 240, "gate": "full_metrics"},
    {"pct": 100, "duration_minutes": 0, "gate": "full_production"},
]

async def progressive_rollout(bundle: AgentBundle, stages=STAGES):
    for stage in stages:
        route_traffic(bundle.id, stage["pct"])
        await asyncio.sleep(stage["duration_minutes"] * 60)
        metrics = fetch_bundle_metrics(bundle.id, window_minutes=stage["duration_minutes"])

        if not evaluate_gate(stage["gate"], metrics, bundle):
            log.critical(f"Rollout aborted at {stage['pct']}% — {bundle.id}")
            rollback_to_previous(bundle)
            notify_oncall(bundle, stage, metrics)
            return False

        log.info(f"Stage {stage['pct']}% passed — {bundle.id}")

    finalize_rollout(bundle)
    return True
```

Each abort point is a hard stop. Unlike traditional deployments where you can "proceed with caution," an agent bundle promotion that fails a behavioral gate should rollback, not proceed.

### 5. Rollback to the last known good bundle

Rollback is not "revert the prompt string." It is redeploy the complete bundle:

```python
async def rollback_to_previous(failed_bundle: AgentBundle):
    """Restore the complete bundle, not just the prompt."""
    last_good = db.query("""
        SELECT * FROM agent_bundles
        WHERE agent_id = :agent_id
          AND status = 'production'
          AND released_at < :current_at
        ORDER BY released_at DESC
        LIMIT 1
    """, agent_id=failed_bundle.agent_id, current_at=failed_bundle.released_at)

    if not last_good:
        log.critical("No last-known-good bundle found — escalate to human review")
        escalate_to_human(failed_bundle)
        return

    # Restore every component of the bundle
    restore_prompt(last_good.prompt_version)
    restore_retrieval_config(last_good.retrieval_config_version)
    restore_memory_config(last_good.memory_config_version)
    restore_validator(last_good.validator_version)

    # Note: model_version rollback requires provider support
    # Log a warning if model_version differs between bundles
    if last_good.model_version != failed_bundle.model_version:
        log.warning(f"Model version differs: {last_good.model_version} vs {failed_bundle.model_version}")
        alert_oncall("Model rollback not guaranteed — provider-level change")

    activate_bundle(last_good)
    log_agent_event("ROLLBACK", bundle_id=last_good.id, reason=f"Failed {failed_bundle.id}")
```

The model version field deserves special handling. Most providers don't offer model version rollback. If your bundle changes the model, your rollback only restores the other 4 components — and you must acknowledge this limitation explicitly.

## Receipt

> Receipt pending — 2026-07-04. Behavioral canary gates and bundle manifest versioning implemented from scratch; no existing entry covers this release engineering discipline. Core pattern validated against LangChain 2026 survey (57.3% in production, only 37.3% run online evaluations — confirms gap). Related: s101 (deterministic sessions), s209 (observability), s222 (trajectory replay), s352 (compensation keys).

## See also

- [S-101 · Deterministic Agent Sessions](s101-deterministic-agent-sessions.md) — append-only action logs that make bundles auditable
- [S-209 · Agent Production Observability](s209-agent-production-observability.md) — OTel tracing and span conventions for agent spans
- [S-352 · Agentic Compensation Keys](s352-agentic-compensation-keys-the-autonomous-retry-era.md) — compensation for post-success unintended states
- [S-222 · Agent Trajectory Replay](s222-agent-trajectory-replay.md) — replaying specific bundle executions for debugging
