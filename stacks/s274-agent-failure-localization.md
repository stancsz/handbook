# S-274 · Agent Failure Localization — From Production Incident to Regression Test

A production agent fails at step 9 of a 12-step trace. You have the full execution log — every tool call, every LLM response, every intermediate output. Finding the root cause still takes hours because you don't know whether step 9 broke because of a bad observation (the tool returned garbage), a bad decision (the model chose the wrong tool), or a bad execution (the tool was called correctly but the result was mishandled). The pattern: instrument traces, localize failures to a specific step, then auto-generate a regression test that locks the fix permanently.

## Forces

- **88% of agent failures trace to infrastructure gaps — not model quality** (Zylos Research, 2026, 591 incidents). The model is usually not the culprit; the tooling around it is.
- **Traces are long and non-linear.** A 50-step agent trace has combinatorial interaction between steps — the error at step 40 was seeded by a subtle misreading at step 3.
- **Reproducing failures is the hard part.** The same prompt with a different timestamp or slightly different tool output produces a different trajectory. You need to freeze the non-determinism to make the bug reproducible.
- **Manual regression tests decay.** Engineers write tests from memory after incidents. The tests cover what they think broke, not what actually broke. A failure-localization pipeline covers the actual failure surface.
- **[S-202](../stacks/s202-llm-as-judge-harness.md) LLM-as-Judge harnesses** measure whether outputs are good. This pattern tells you *which step* produced the bad input that corrupted everything downstream.

## The move

**Three-stage pipeline: Trace → Isolate → Regression.**

### Stage 1 — Structured trace capture

Every agent run produces a trace with typed spans. Minimum viable schema:

```
trace_id, span_id, parent_span_id, step_number,
event_type: "llm_call" | "tool_call" | "tool_result" | "observation",
model, prompt_tokens, completion_tokens, latency_ms,
tool_name (if tool_call/result),
input_hash, output_hash, step_status: "success" | "warning" | "error"
```

Use OpenTelemetry GenAI conventions ([S-196](../stacks/s196-otel-genai-telemetry.md)) — `genai.*` attribute names are vendor-neutral and interoperable with Langfuse, Phoenix, and Datadog.

Record `input_hash` and `output_hash` (SHA-256 of the span content) so identical steps across runs can be deduplicated and clustered.

### Stage 2 — Failure localization

Isolate the **critical failure step**: the earliest step that, if corrected, would have produced a correct final output.

Two complementary strategies:

**A. Guarded constraint synthesis (Microsoft AgentRx approach)**

From tool schemas + domain policies, synthesize executable constraints for each step. A constraint is a predicate that must hold:

```
tool_call("send_email", args):
  constraint: args.recipients ⊆ user_authorized_contacts
  constraint: args.body.length <= 5000
```

During replay, evaluate every constraint at every step. The first constraint violation is the critical failure step. This is deterministic — no LLM required.

**B. Delta-based blame assignment**

1. Run the failed trace once, recording all outputs.
2. Replay from each step checkpoint with a reference (known-good) tool stub instead of the live tool.
3. If substituting step K's output with the reference produces a correct final result, step K is the critical failure step.

```
for k in range(num_steps):
    stubbed_trace = replay(trace, stub_from=k, stubs=golden_stubs)
    if evaluate(stubbed_trace) == PASS:
        critical_step = k
        break
```

### Stage 3 — Auto-generate regression test

Once the critical step is identified, generate a test case from the captured trace:

```python
import json, hashlib

def trace_to_regression_test(trace: list[dict], critical_step: int,
                             test_name: str) -> str:
    """
    Convert a failed trace into a pytest test.
    The test stubs everything up to critical_step, runs it live,
    then asserts the critical step's output matches the captured (correct) output.
    """
    case = {
        "name": test_name,
        "critical_step": critical_step,
        "input_snapshot": trace[critical_step - 1]["tool_result"],
        "expected_output": trace[critical_step]["expected_tool_result"],
        "golden_stubs": {
            i: trace[i] for i in range(critical_step)
        }
    }

    test_code = f'''
import pytest
from your_agent import Agent

@pytest.fixture
def golden_stubs():
    stubs = {{}}
    # {len(case["golden_stubs"])} stubs from trace
    return stubs

def test_{test_name.replace(" ", "_").replace("-", "_")}(golden_stubs):
    agent = Agent(stubs=golden_stubs)
    # Step {critical_step}: verify correct tool + args
    step = agent.step({case["input_snapshot"]!r})
    assert step.tool_name == "{trace[critical_step]["tool_name"]}"
    assert step.arguments == {case["expected_output"]!r}
'''
    return test_code

# Generate + write
with open(f"tests/regressions/test_{case['name']}.py", "w") as f:
    f.write(trace_to_regression_test(trace, critical_step, "send_email_budget_guard"))

# Append to conftest.py marker so it runs in CI
```

The generated test stubs everything upstream, runs the critical step live, and asserts the exact expected behavior. Any future code change that breaks this step now fails the test immediately — not in production.

## Receipt

> Receipt pending — July 1, 2026
> The trace schema, constraint synthesis, and delta-based blame approaches are documented in Microsoft Research's AgentRx paper (March 2026) and Zylos Research's trace-driven debugging analysis (April 2026). The `trace_to_regression_test` generator above is a reference implementation pattern — not yet run against a live agent. Validate against your own trace schema before CI integration.

## See also

- [S-196 · OTel GenAI Telemetry](../stacks/s196-otel-genai-telemetry.md) — trace capture substrate
- [S-202 · LLM-as-Judge Harness](../stacks/s202-llm-as-judge-harness.md) — measuring whether outputs are good; this pattern feeds it
- [S-106 · Event Log Replay](../stacks/s106-event-log-replay.md) — replay infrastructure that Stage 2 builds on
- [F-74 · Agent Decision Tracing](../forward-deployed/f74-agent-decision-tracing.md) — causal chain logging; prerequisite for Step 2
- [S-116 · Output Determinism Testing](../stacks/s116-output-determinism-testing.md) — verifying that stub substitution is valid
