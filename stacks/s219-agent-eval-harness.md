# S-219 · Agent Eval Harness

You shipped the agent. It worked in staging. It failed silently in production on 3% of cases — enough to generate 40 support tickets before anyone noticed. Nobody caught it because there was no systematic quality gate between "the code runs" and "production traffic." The fix: build an eval harness — a repeatable, automatable test suite for agent quality — before you need it, not after the first incident.

## Forces

- Agent quality is not binary: the agent "works" but has silent failure modes (wrong tool, bad tool arguments, hallucinated citations, infinite loops) that don't surface as errors — they surface as wrong answers
- Human evaluation doesn't scale: reviewing 500 agent runs manually is expensive, slow, and inconsistent; by the time you've reviewed enough to spot a pattern, you've shipped the regression three times
- LLM-as-judge is powerful but unreliable without ground-truth anchors: a judge LLM scoring another LLM without reference signals drifts and overfits to surface quality
- Eval data rots: cases that were hard six months ago are now trivial as models improve; a harness without continuous curation becomes a false sense of security
- CI catches syntax errors, not semantic failures: a pipeline that passes `pytest` can still produce wrong answers on your specific domain cases

## The move

An agent eval harness has four layers. Skipping layers produces brittle results.

### Layer 1 — Determinism Audit (before anything else)

At temperature=0 with a pinned model version, run the same input 3–5 times. Measure divergence. If your agent produces different answers on the same input, step-level evaluation is meaningless — you can't attribute failures to logic vs. randomness.

```python
import json, statistics

def determinism_audit(agent_fn, input_, runs=5):
    outputs = [agent_fn(input_) for _ in range(runs)]
    # For structured output: compare parsed fields
    # For free text: use LLM-as-judge consistency score
    tokens = [len(json.dumps(o)[:500]) for o in outputs]  # rough length variance
    variance = statistics.stdev(tokens) if len(set(tokens)) > 1 else 0
    print(f"Length variance across {runs} runs: {variance}")
    return variance < 0.05  # pass if outputs are stable
```

### Layer 2 — Step-Level Unit Evals (Pytest-style)

Test individual agent steps in isolation with known inputs and expected outputs. Each tool call, routing decision, and context assembly is a unit. DeepEval's `assert_test` pattern:

```python
from deepeval import assert_test
from deepeval.metrics import ToolCallAccuracyMetric, HallucinationMetric

metric = ToolCallAccuracyMetric(threshold=0.8)

assert_test(
    fn=my_agent,
    test_case=TestCase(
        input="Process this refund for order #4821",
        expected_tool_calls=["order_lookup", "refund_execute"],
    ),
    metrics=[metric],
)
```

Core metrics at this layer: tool-call accuracy, argument correctness, hallucination rate against provided context, and context utilization (did the agent actually use the retrieved docs or hallucinate from weights?).

### Layer 3 — Session-Level Evals (the trajectory)

A single-step pass doesn't mean the multi-step trajectory works. Evaluate the full run against reference trajectories or outcome-level rubrics. Use LLM-as-judge with a structured rubric, not a raw score:

```python
from deepeval.metrics import GEval

correctness_metric = GEval(
    name="Correctness",
    criteria="""
    Evaluate whether the agent:
    1. Retrieved the correct order details before processing refund
    2. Checked refund eligibility policy
    3. Applied the correct refund amount
    4. Sent a confirmation with order number and amount
    """,
    evaluation_steps=[
        "Check if agent looked up order details first",
        "Verify refund amount matches order total",
        "Confirm policy compliance (30-day window)",
        "Verify confirmation message includes order ID",
    ],
    threshold=0.8,
)
```

### Layer 4 — Production Regression Pipeline

The most powerful layer: failures from production become test cases automatically. Braintrust, Langfuse, and Arize Phoenix support converting live incidents into regression cases with one click.

```python
# Production → regression pipeline (Braintrust-style)
# On a production failure, capture:
incident = {
    "input": captured_input,
    "expected_output": human_adjudicated_answer,
    "agent_output": production_output,
    "trace_id": trace_id,  # links to full span
}
# Add to regression suite
add_to_eval_suite(incident)
```

### The eval metrics taxonomy (what to measure)

| Layer | Metrics | Tool |
|---|---|---|
| Determinism | token variance, field stability | custom |
| Unit step | tool-call accuracy, arg correctness, hallucination | DeepEval, RAGAS |
| Trajectory | task completion, rubric score, tool efficiency | DeepEval GEval, Braintrust |
| End-to-end | business outcome, latency, cost-per-task | Langfuse, Arize Phoenix |

## Receipt

> Receipt pending — June 30, 2026
> The code above is synthesized from documented DeepEval 4.0 API, Braintrust eval pipeline patterns, and RAGAS metrics taxonomy. It represents real patterns from production systems. Actual run with this codebase would require installing `deepeval` and a live model endpoint. Mark receipt confirmed once a live run is performed against a real agent pipeline.

## See also

- [S-218 · Agent Stack Stratification](s218-agent-stack-stratification.md) — the eval harness lives at the quality assurance layer, one of 5–7 distinct horizontal layers in the agent stack
- [S-106 · Event Log Replay](s106-event-log-replay.md) — eval harnesses depend on complete event logs to reconstruct agent decisions from production failures
- [S-116 · Output Determinism Testing](s116-output-determinism-testing.md) — determinism audit (Layer 1 above) is the prerequisite for meaningful step-level evaluation
