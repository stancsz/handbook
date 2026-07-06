# S-551 · Agent Semantic Versioning: The Versioning Gap

When you bump the agent's version from `2.1.0` to `2.2.0`, what actually changed? You don't know — and neither do your downstream consumers. The version number tags the agent; it doesn't protect the teams depending on it.

## Forces

- Semantic versioning assumes you can verify behavioral equivalence from a specification — agents produce non-deterministic outputs that make this impossible
- Output schema drift (renamed fields, arrays becoming objects, quoting changes) breaks consumers silently: no exception, no 500, just wrong data
- A routine model update can silently shift which behavioral path the agent takes — tool selection rate, refusal threshold, reasoning depth — without touching a single line of code
- The agent's version number is meaningless to downstream teams: it tells you the agent changed, not whether your integration still works
- Downstream teams (mobile apps, third-party integrations, enterprise customers on pinned versions) can't re-run CI on their end when you deploy — they need a real contract

## The move

The core fix: **version the behavioral contract, not the agent**. The agent's version number is metadata. The behavioral contract is the real interface.

### 1. Define the behavioral surface

The contract isn't "the system prompt" or "the model version." It's the observable behavior downstream consumers depend on. Define it as a set of behavioral assertions:

```python
class AgentContract:
    """Minimal behavioral surface for a customer-service agent."""
    version: str = "1.0.0"

    # Output schema assertions
    def assert_response_schema(self, response: dict) -> bool:
        assert "status" in response, "Missing 'status' field"
        assert "message" in response, "Missing 'message' field"
        assert response["status"] in {"pending", "resolved", "escalated", "rejected"}
        return True

    # Behavioral assertions
    def assert_tool_selection_rate(self, trace: list[dict]) -> bool:
        """Escalate tool selected in <5% of non-critical sessions."""
        escalate_count = sum(1 for t in trace if t.get("tool") == "escalate")
        return (escalate_count / len(trace)) < 0.05

    def assert_refusal_rate(self, trace: list[dict]) -> bool:
        """Valid requests refused <2% of the time."""
        refusals = sum(1 for t in trace if t.get("outcome") == "refused")
        return (refusals / len(trace)) < 0.02
```

### 2. Freeze behavioral snapshots at each release

Before every deployment, run the full behavioral contract against a pinned evaluation trace set. Store the results alongside the agent version:

```
contracts/
  v1.3.0/
    evaluation_traces.parquet   # 500 production traces, pinned
    contract_results.json       # {schema_valid: true, tool_rate: 0.023, refusal_rate: 0.014}
  v1.4.0/
    evaluation_traces.parquet
    contract_results.json
```

The pinned traces are your "regression baseline." They're sampled from real production sessions, labeled with expected behavior, and frozen. They never change. Every release re-evaluates against the same traces.

### 3. Enforce schema contracts at tool boundaries

The most common breaking change: the agent's output shape shifts after a model or prompt update. Enforce schema validation at the output boundary, not just at parse time:

```python
from pydantic import BaseModel, ValidationError
import jsonschema

TOOL_CONTRACT_SCHEMA = {
    "type": "object",
    "required": ["status", "message"],
    "properties": {
        "status": {"type": "string", "enum": ["pending", "resolved", "escalated", "rejected"]},
        "message": {"type": "string", "minLength": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1}  # optional
    }
}

def enforce_tool_contract(response: dict, version: str) -> dict:
    """Validate agent output against the contract for this version."""
    schema = load_contract_schema(version)  # versioned schema registry
    try:
        jsonschema.validate(instance=response, schema=schema)
        return response
    except ValidationError as e:
        # Log the schema violation. Don't silently pass.
        logger.error(f"Contract violation v{version}: {e.message}")
        return inject_contract_fallback(response, schema)
```

### 4. Apply expand-contract with explicit migration windows

When the contract must change, follow the migration pattern from [S-64](s64-agent-output-schema-versioning.md) with a behavioral overlay:

1. **Expand**: Add the new field (`current_state`) alongside the old (`status`). Both are valid.
2. **Notify**: Push the new contract spec to downstream consumers with a migration deadline (minimum 30 days).
3. **Enforce dual-read**: The agent output adapter reads both fields during the migration window — the contract validator passes if either satisfies the requirement.
4. **Contract**: After the migration window, drop the old field from the contract. Downstream teams that haven't migrated fail visibly, not silently.

### 5. Monitor behavioral drift between releases

Between formal releases, track behavioral drift continuously:

```python
BEHAVIORAL_SLO = {
    "tool_selection_rate": {"threshold": 0.05, "tolerance": 0.01},
    "refusal_rate": {"threshold": 0.02, "tolerance": 0.005},
    "schema_violation_rate": {"threshold": 0.001, "tolerance": 0},
    "avg_turns_per_session": {"threshold": 12, "tolerance": 2},
}

def check_behavioral_drift(current_traces: list[dict], baseline: dict) -> list[str]:
    violations = []
    for metric, config in BEHAVIORAL_SLO.items():
        current = compute_metric(metric, current_traces)
        if abs(current - baseline[metric]) > config["tolerance"]:
            violations.append(
                f"Behavioral drift: {metric}={current:.3f} "
                f"(baseline={baseline[metric]:.3f}, tolerance=±{config['tolerance']:.3f})"
            )
    return violations
```

When violations appear between releases, that's a silent regression — [S-220](s220-agentic-behavioral-regression-suite.md) is the companion for building the evaluation infrastructure. The behavioral regression suite is the agent's real test suite; version bumps are just timestamps.

## Receipt

> Verified 2026-07-04 — Framework derived from published patterns: Tian Pan (tianpan.co, 2026-04-17) on output schema drift failure modes, Zylos Research (2026-02-27) on schema migration strategies for agent systems. Three failure modes confirmed against production incident reports: output schema drift (40-60% break rate across model updates per cited analysis), behavioral path shifts post-model-update, and tool contract evolution breaking LLM-dependent parsing. Code examples represent working patterns from documented agent deployment stacks. Behavioral SLO thresholds are representative; calibrate against your own trace baseline.

## See also

- [S-64](s64-agent-output-schema-versioning.md) — Schema versioning design: `_v` field, additive-only rule, migration playbook
- [S-120](s120-output-schema-backward-compat-adapter.md) — Delivery-layer schema adapter for uncoordinated consumers
- [S-220](s220-agentic-behavioral-regression-suite.md) — Behavioral regression suite: the real test infrastructure
- [S-451](s451-llm-as-judge-failure-modes-the-echo-chamber-problem.md) — Judge calibration for behavioral evaluation
