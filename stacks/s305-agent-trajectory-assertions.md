# S-305 · Agent Trajectory Assertions

You can assert that an agent answered correctly. You cannot assert that it reached the answer the right way — by reading the right documents, calling the right tools, following the right chain of reasoning — until you write assertions over its full trajectory, not just its final output.

## Forces

- Final-output assertions (JSON schema, required fields, type checks) catch format failures but miss behavioral failures: wrong tool selection, wrong document read, wrong reasoning chain.
- The agent's "answer" is often fine in isolation — the failure is in the path taken to produce it. A medical agent that outputs correct advice but reached it by ignoring the patient history is dangerous.
- Trajectory-level assertions require a grader that can inspect the intermediate steps — the tool calls, the reasoning trace, the retrieved context — not just the terminal response.
- Most eval frameworks are slow and batch-oriented. Assertions that don't run in CI catch regressions after deployment, not before.

## The move

Define **trajectory assertions** — programmatic checks over the full agent run (input → reasoning trace → tool calls → output), not just the final response.

### Anatomy of a trajectory assertion

A trajectory assertion has three components:

**1. Trace probe** — captures the full run. Model providers that support extended trace exports (Anthropic, OpenAI) give you a structured JSON of every turn, tool call, and tool result. For others, instrument the agent loop directly:

```python
import json, time, uuid
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class TrajectoryTrace:
    run_id: str
    input: str
    turns: list[dict]
    output: str
    latency_ms: float
    total_tokens: int
    tool_calls: list[dict]
    errors: list[str]

class TrajectoryTracer:
    def __init__(self, callback=None):
        self.traces: list[TrajectoryTrace] = []
        self._callback = callback  # hook for async ingestion

    def wrap(self, agent_fn):
        """Decorator that traces any agent function."""
        def wrapped(input_text: str, **kwargs) -> TrajectoryTrace:
            run_id = str(uuid.uuid4())[:8]
            turns, tool_calls, errors = [], [], []
            start = time.monotonic()

            # Intercept tool calls by monkey-patching the tool registry
            original_call = None
            def trace_tool_call(tool_name, tool_args):
                tool_calls.append({
                    "run_id": run_id, "turn": len(turns),
                    "tool": tool_name, "args": tool_args,
                    "ts": time.time()
                })
                return original_call(tool_name, tool_args) if original_call else None

            # Run the agent — implementation varies by framework
            output, metadata = agent_fn(input_text, tool_interceptor=trace_tool_call, **kwargs)
            turns = metadata.get("turns", [])

            trace = TrajectoryTrace(
                run_id=run_id, input=input_text, turns=turns,
                output=output, latency_ms=(time.monotonic() - start) * 1000,
                total_tokens=metadata.get("total_tokens", 0),
                tool_calls=tool_calls, errors=errors
            )
            self.traces.append(trace)
            if self._callback:
                self._callback(trace)
            return output
        return wrapped
```

**2. Assertion library** — checks against the captured trace:

```python
from dataclasses import dataclass
from typing import Callable, Any
import re

@dataclass
class AssertionResult:
    name: str
    passed: bool
    detail: Optional[str] = None

class TrajectoryAssertions:
    def __init__(self, trace: TrajectoryTrace):
        self.trace = trace

    def tool_was_called(self, tool_name: str) -> AssertionResult:
        called = [t for t in self.trace.tool_calls if t["tool"] == tool_name]
        return AssertionResult(
            name=f"tool_was_called({tool_name})",
            passed=len(called) > 0,
            detail=f"Called {len(called)} time(s)" if called else "Never called"
        )

    def tool_not_called(self, tool_name: str) -> AssertionResult:
        called = [t for t in self.trace.tool_calls if t["tool"] == tool_name]
        return AssertionResult(
            name=f"tool_not_called({tool_name})",
            passed=len(called) == 0,
            detail=f"Called {len(called)} time(s): {[t['tool'] for t in called]}"
        )

    def retrieved_document_mentions(self, keyword: str) -> AssertionResult:
        docs = [t for t in self.trace.tool_calls if t["tool"] in ("search", "retrieve", "rag_query")]
        hits = [d for d in docs if keyword.lower() in str(d.get("args", {})).lower()]
        return AssertionResult(
            name=f"retrieved_document_mentions({keyword!r})",
            passed=len(hits) > 0,
            detail=f"Found in {len(hits)}/{len(docs)} retrieval calls"
        )

    def output_contains(self, pattern: str, flags=re.IGNORECASE) -> AssertionResult:
        match = re.search(pattern, self.trace.output, flags)
        return AssertionResult(
            name=f"output_contains({pattern!r})",
            passed=bool(match),
            detail=match.group(0) if match else None
        )

    def output_excludes(self, pattern: str) -> AssertionResult:
        match = re.search(pattern, self.trace.output, re.IGNORECASE)
        return AssertionResult(
            name=f"output_excludes({pattern!r})",
            passed=not bool(match),
            detail=f"Found forbidden pattern: {match.group(0)}" if match else None
        )

    def no_error(self) -> AssertionResult:
        return AssertionResult(
            name="no_error",
            passed=len(self.trace.errors) == 0,
            detail=f"{len(self.trace.errors)} error(s): {self.trace.errors}"
        )

    def latency_under(self, ms: int) -> AssertionResult:
        return AssertionResult(
            name=f"latency_under({ms}ms)",
            passed=self.trace.latency_ms < ms,
            detail=f"{self.trace.latency_ms:.0f}ms"
        )

    def tool_call_count_in_range(self, min_calls: int, max_calls: int) -> AssertionResult:
        n = len(self.trace.tool_calls)
        passed = min_calls <= n <= max_calls
        return AssertionResult(
            name=f"tool_call_count({min_calls}-{max_calls})",
            passed=passed,
            detail=f"{n} calls"
        )

    def run_all(self, assertions: list[Callable[[], AssertionResult]]) -> dict:
        results = {}
        for fn in assertions:
            result = fn()
            results[result.name] = result
        return results
```

**3. Eval suite with pass@k** — run k trials and report pass rate:

```python
from collections import defaultdict
import numpy as np

@dataclass
class EvalTask:
    name: str
    input: str
    assertions: list  # list of callables or assertion dicts
    k: int = 5  # number of trials

@dataclass
class TaskResult:
    task_name: str
    pass_at_k: float  # fraction of trials with all assertions passing
    trial_results: list[dict]
    avg_latency_ms: float

def run_eval_suite(tasks: list[EvalTask], tracer: TrajectoryTracer) -> list[TaskResult]:
    results = []
    for task in tasks:
        task_results = []
        for trial in range(task.k):
            output = tracer.agent_fn(task.input)  # your agent
            trace = tracer.traces[-1]
            assertions = TrajectoryAssertions(trace)
            # Resolve assertion callables
            resolved = []
            for a in task.assertions:
                if callable(a):
                    resolved.append(a)
                elif isinstance(a, dict):
                    # Support YAML-defined assertions: {"tool_was_called": "search"}
                    method_name = list(a.keys())[0]
                    if hasattr(assertions, method_name):
                        method = getattr(assertions, method_name)
                        resolved.append(lambda m=method, v=a[method_name]: m(v))
            res = assertions.run_all(resolved)
            task_results.append(res)

        all_passed = [all(r[p].passed for p in r) for r in task_results]
        pass_at_k = sum(all_passed) / len(all_passed)
        results.append(TaskResult(
            task_name=task.name,
            pass_at_k=pass_at_k,
            trial_results=task_results,
            avg_latency_ms=np.mean([t.trace.latency_ms for t in tracer.traces[-task.k:]])
        ))
    return results

def print_report(results: list[TaskResult]):
    print(f"\n{'Task':<40} {'Pass@K':>8}  {'Trials':>6}")
    print("-" * 60)
    for r in results:
        bar = "█" * int(r.pass_at_k * 20) + "░" * (20 - int(r.pass_at_k * 20))
        marker = "✅" if r.pass_at_k >= 0.8 else "⚠️" if r.pass_at_k >= 0.5 else "❌"
        print(f"{marker} {r.task_name:<38} {r.pass_at_k:>7.1%}  {bar}")
```

**Integration pattern — run in CI before deploy:**

```yaml
# .github/workflows/agent-eval.yml
- name: Run trajectory assertions
  run: |
    python -m agent_eval_suite \
      --tasks tasks/regression_set.yaml \
      --agent agent/production.py \
      --min-pass-rate 0.80 \
      --trials 3
  env:
    AGENT_API_KEY: ${{ secrets.AGENT_API_KEY }}
```

The YAML task file defines inputs and expected trajectories:

```yaml
# tasks/regression_set.yaml
tasks:
  - name: "pricing_query_returns_official_rates"
    input: "What is the enterprise pricing for 500 seats?"
    k: 3
    assertions:
      - tool_was_called: "search_knowledge_base"
      - output_contains: "\\$|credit|plan"
      - output_excludes: "I don't know"
      - tool_call_count: [1, 5]  # min, max

  - name: "refund_request_no_hallucinated_policy"
    input: "Customer #4421 wants a refund for order #9981"
    k: 3
    assertions:
      - tool_was_called: "lookup_order"
      - retrieved_document_mentions: "order"
      - no_error: null
```

## Receipt

> Receipt pending — 2026-07-01

## See also

- [F-12 · LLM-as-a-Judge](f12-llm-as-a-judge.md) — the judge is the grader for semantic assertions that programmatic checks can't cover
- [F-02 · Evaluation at Scale](f02-evaluation-at-scale.md) — the three-layer eval stack: unit tests, LLM judge, human review
- [S-49 · Retrieval Evaluation](s49-retrieval-evaluation.md) — eval for the retrieval half of the trajectory; pair with trajectory assertions for the generation half
- [F-188 · AI Agent Red Teaming](f188-ai-agent-red-teaming.md) — adversarial inputs belong in the eval suite as regression tasks
