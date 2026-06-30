# S-235 · Production Failure → Regression Test

An agent fails in production. A human triages it. The same failure reappears two weeks later in a different context. This loop — failure, fix, recurrence — is the most expensive pattern in agentic systems. The fix: wire every confirmed production failure directly into an automated test case that runs on every commit.

## Forces

- **Production failures are the ground truth your eval set lacks.** Benchmarks are synthetic; production incidents are real. Converting incidents to test cases is the highest-signal data you can add to your eval suite.
- **Manual test authoring doesn't scale.** A team with 200 agent incidents per month cannot write test cases fast enough to keep up — and manual authoring introduces human bias about what "the failure was."
- **The same failure recurs in different shapes.** A wrong-tool-selection bug triggered by a specific product name will appear as a hallucinated field name two weeks later. Without a structured failure schema, you can't cluster related incidents.
- **Regression suites that aren't maintained rot.** Test cases written once and never updated diverge from the agent's actual behavior. The suite grows silent, passes everything, and tells you nothing.
- **The feedback loop is the product.** Teams that close the production→test→deploy→production loop fastest ship the most reliable agents.

## The move

Three stages: **capture**, **structure**, **circulate**.

### Stage 1 — Capture

Instrument the agent loop to emit structured failure events on every non-nominal outcome. Don't wait for a user complaint. Classify failures at the point of detection, not post-hoc.

```python
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import json

class FailureMode(Enum):
    WRONG_TOOL_SELECTION = "wrong_tool_selection"
    TOOL_ARGUMENT_ERROR = "tool_argument_error"
    HALLUCINATED_CITATION = "hallucinated_citation"
    SCHEMA_VIOLATION = "schema_violation"
    LOOP_ESCALATION = "loop_escalation"
    TIMEOUT = "timeout"
    INDIRECT_INJECTION = "indirect_injection"
    UNKNOWN = "unknown"

@dataclass
class FailureEvent:
    incident_id: str
    failure_mode: FailureMode
    severity: str  # P0/P1/P2/P3
    agent_version: str
    model: str
    input_message: str
    conversation_history: list[dict]
    tool_call_sequence: list[dict]  # [{"tool": "...", "args": {...}, "result": "..."}]
    expected_behavior: str
    must_not_happen: list[str]
    metadata: dict = field(default_factory=dict)

    def to_test_case(self) -> dict:
        """Convert a production failure to a structured test case."""
        return {
            "id": f"TC-{self.incident_id}",
            "source": "production_incident",
            "incident_id": self.incident_id,
            "failure_mode": self.failure_mode.value,
            "severity": self.severity,
            "agent_version": self.agent_version,
            "model": self.model,
            "input": {
                "user_message": self.input_message,
                "conversation_history": self.conversation_history,
            },
            "expected_behavior": {
                "tool_sequence": self.expected_behavior,
                "must_not": self.must_not_happen,
            },
            "tags": self.metadata.get("tags", []),
        }
```

### Stage 2 — Structure

Every failure event gets a **strict schema** — the test case must include the input, the expected tool sequence, and hard constraints (things the agent must not do). A severity classification anchors priority.

The key discriminator is `must_not_happen`: explicit statements of what the agent must not produce or execute. This is where most test suites are weak — they check what the agent *should* do, not what it *must not* do. Injections, data exfiltration, unauthorized tool calls — these are constraint violations, not action mismatches.

```python
def log_failure(event: FailureEvent, test_registry_path: str):
    """Append a production failure to the regression test registry."""
    tc = event.to_test_case()

    # Only promote P0/P1 to regression; P2/P3 go to a review queue
    if event.severity in ("P0", "P1"):
        with open(f"{test_registry_path}/{tc['id']}.json", "w") as f:
            json.dump(tc, f, indent=2)
        print(f"Promoted {tc['id']} ({event.failure_mode.value}) → regression suite")
    else:
        with open(f"{test_registry_path}/review_queue/{tc['id']}.json", "w") as f:
            json.dump(tc, f, indent=2)
        print(f"Queued {tc['id']} for human review")
```

### Stage 3 — Circulate

Run the regression suite on every deploy. Score the pass rate per failure mode class. A regression in "wrong_tool_selection" failures after a model swap is a signal that the new model has a different tool-calling distribution — not a bug, but a deployment gating decision.

```python
def run_regression_suite(test_dir: str, agent_fn, threshold: float = 0.95) -> dict:
    """Run all production-incident regression tests against the agent."""
    results = {"passed": 0, "failed": 0, "errors": []}
    for tc_file in Path(test_dir).glob("*.json"):
        tc = json.loads(tc_file.read_text())
        result = agent_fn(
            message=tc["input"]["user_message"],
            history=tc["input"]["conversation_history"],
            expected=tc["expected_behavior"],
        )
        if evaluate_test_case(tc, result):
            results["passed"] += 1
        else:
            results["failed"] += 1
            results["errors"].append(tc["id"])

    rate = results["passed"] / (results["passed"] + results["failed"])
    if rate < threshold:
        raise RegressionGate(f"Regression suite at {rate:.1%} < {threshold:.0%} threshold")
    return results
```

## Receipt

> Receipt pending — June 30, 2026

The pattern is implemented at Arthur AI, Maxim AI, and multiple internal enterprise systems (per public case studies and arxiv:2512.04123). The code above is a minimal working skeleton; a real implementation wires into your observability platform (OpenTelemetry spans → failure event emission → test registry) and your CI pipeline.

## See also

- [S-230 · Agent Harness Engineering](s230-agent-harness-engineering-the-eval-layer-production-demands.md) — building the eval layer production demands
- [S-233 · Agent Failure Classification](s233-agent-failure-classification-and-recovery-pipeline.md) — taxonomy powering the failure mode field above
- [S-193 · LLM-as-Judge Eval Pipeline](s193-llm-as-judge-eval-pipeline.md) — scoring outputs in the evaluate_test_case function
- [F-05 · Agent Failure Taxonomy](forward-deployed/f05-agent-failure-taxonomy.md) — naming the failure classes
