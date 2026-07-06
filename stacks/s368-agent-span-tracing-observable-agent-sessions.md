# S-368 · Agent Span Tracing: Observable Agent Sessions

Agents that run for minutes or hours produce decision trees no developer can follow by reading logs. A coding agent makes 200 tool calls across 45 minutes. A customer-service agent handles 12 escalations over 3 days. A multi-agent pipeline chains 8 specialized agents before producing a report. In every case, the question when something goes wrong is the same: *why did it do that?* Agent Span Tracing answers it — by treating every LLM call, tool invocation, and state transition as a queryable trace span.

## Forces

- **The agent decision graph is opaque.** Traditional request logs show input → output. Agent logs show a 47-step interleaving of LLM calls, tool results, and intermediate decisions that no human can reconstruct from a flat log file.
- **Latency histograms miss the real problem.** P99 latency for an agent session is meaningless when 80% of wall time is LLM think time and 20% is retries. What matters is *which span* consumed the budget and *why* it was slow.
- **Cross-agent causality is invisible.** When Agent A's output feeds Agent B, a failure in B might trace back to a retrieval gap in A. Without span-level lineage, this takes hours to reconstruct.
- **Eval without traces is guesswork.** You cannot reliably evaluate agent quality if you cannot isolate *which step* produced the failure. A bad final answer might trace to a tool call that returned corrupted JSON on step 7.
- **Production agents need auditability, not just debugging.** Compliance, SLA tracking, and customer transparency all require reconstructable agent decision chains — not just final outputs.

## The move

The core abstraction: every meaningful unit of work in an agent session gets a **span** — a typed, timestamped record with input, output, metadata, and a parent reference. Spans form a tree that mirrors the agent's actual execution graph.

### Span taxonomy for agents

```
Trace
└── Session span         # Root — the user request, session ID, metadata
    ├── LLM span         # One per model call — prompt tokens, completion tokens, model, temperature
    │   └── Tool-call span   # Nested inside LLM span when model requests a tool
    │       ├── Retrieval span  # RAG, search, database query
    │       ├── Action span     # Write, API call, file edit
    │       └── Compute span    # Code execution, transformation
    ├── Planning span    # High-level task decomposition
    ├── Handoff span     # Inter-agent or human escalation
    └── Compaction span  # Context window management events
```

### Implementation with OpenTelemetry

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc import SpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Minimal agent tracing setup
provider = TracerProvider(
    resource=Resource.create({"service.name": "agent-runtime"})
)
provider.add_span_processor(BatchSpanProcessor(SpanExporter(endpoint="http://otel-collector:4317")))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

class TracedAgent:
    def __init__(self, agent_id: str, session_id: str):
        self.agent_id = agent_id
        self.session_id = session_id

    def run(self, task: str) -> str:
        with tracer.start_as_current_span(
            "agent.session",
            attributes={
                "agent.id": self.agent_id,
                "session.id": self.session_id,
                "task": task[:200],
            }
        ) as root_span:
            result = self._agent_loop(task)
            root_span.set_attribute("output.tokens", result["tokens"])
            root_span.set_attribute("steps.count", result["step_count"])
            root_span.set_attribute("cost.usd", result["cost"])
            return result["output"]

    def _agent_loop(self, task: str) -> dict:
        state = {"task": task, "history": []}
        step = 0
        while not self._is_done(state) and step < self.max_steps:
            with tracer.start_as_current_span(
                f"agent.step.{step}",
                kind=trace.SpanKind.INTERNAL
            ) as step_span:
                step_span.set_attribute("step.number", step)

                # LLM call
                with tracer.start_as_current_span(
                    "llm.call",
                    attributes={"model": self.model, "temperature": self.temp}
                ) as llm_span:
                    response = self._call_llm(state)
                    llm_span.set_attribute("prompt_tokens", response.usage.prompt_tokens)
                    llm_span.set_attribute("completion_tokens", response.usage.completion_tokens)

                tool_calls = response.tool_calls or []
                for tc in tool_calls:
                    with tracer.start_as_current_span(
                        f"tool.{tc.function.name}",
                        attributes={"tool.name": tc.function.name, "tool.args": str(tc.function.arguments)[:500]}
                    ) as tool_span:
                        result = self._execute_tool(tc)
                        tool_span.set_attribute("tool.duration_ms", result["duration_ms"])
                        tool_span.set_attribute("tool.success", result["ok"])
                        if not result["ok"]:
                            tool_span.record_exception(result["error"])
                        state["history"].append({"call": tc, "result": result})

                state["messages"].append(response)
                step += 1

        return {"output": self._extract_output(state), "tokens": sum(m.usage.total_tokens for m in state["messages"]),
                "step_count": step, "cost": sum(m.usage.total_tokens for m in state["messages"]) * self.cost_per_token}
```

### The span attributes that matter most

The raw trace is too large to browse. These attributes make traces *queryable*:

```python
# Per span — set at creation
attributes = {
    "agent.id": agent_id,
    "session.id": session_id,
    "span.type": "llm" | "tool" | "retrieval" | "action" | "handoff" | "compaction",
    "span.depth": depth_in_tree,        # Detect unbounded loops
    "parent.span_id": parent.span_id,   # Enables tree reconstruction
    "llm.model": "claude-3-5-sonnet",
    "llm.prompt_tokens": 2048,
    "llm.completion_tokens": 342,
    "tool.name": "sql_query",
    "tool.duration_ms": 180,
    "tool.success": True,
    "retrieval.chunks_returned": 8,
    "retrieval.top_k": 10,
    "retrieval.query_similarity": 0.84,
    "cost.cumulative_usd": 1.23,
}

# On error — record the exception
span.record_exception(exc)
span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
```

### What to export and where

Not every team needs every span in every system. A practical tiering:

| Tier | What | Where | Use case |
|---|---|---|---|
| **LLM spans** | Every model call with tokens, latency, model | Langfuse / Phoenix / Braintrust | Eval, cost tracking, quality monitoring |
| **Tool spans** | Every tool call with args + result | Datadog / Grafana / custom | Debugging, latency spikes |
| **Retrieval spans** | Query, top-K, chunks returned, scores | Your vector DB dashboard | RAG quality, bad retrievers |
| **Error spans** | Any span with success=false | PagerDuty / Slack | On-call alerting |
| **Full trace** | Complete tree | S3 / object storage | Incident replay, compliance audit |

For OpenTelemetry-native teams: export spans to a collector, then fan out to backends by span type using processor filtering. This avoids sending 50 retrieval spans per session to your tracing UI.

### The trace-to-eval pipeline

Traces are the input to agent evaluation. Instead of "was the final answer good?", trace-driven eval asks "was every step good?":

```python
def evaluate_trace(trace: list[Span]) -> EvalResult:
    scores = {}
    for span in trace:
        if span.type == "retrieval":
            scores["retrieval_quality"] = span.retrieval_similarity_score
            if span.retrieval_similarity_score < 0.7:
                scores["retrieval_flag"] = "low_similarity"
        if span.type == "llm":
            scores["token_efficiency"] = span.completion_tokens / span.prompt_tokens
            if span.completion_tokens > span.estimated_max:
                scores["verbose_flag"] = "excessive_completion"
        if not span.success:
            scores["step_failures"] = scores.get("step_failures", 0) + 1

    return EvalResult(
        pass_=scores.get("step_failures", 0) == 0,
        scores=scores,
        span_tree=build_tree(trace)
    )
```

## Receipt

> Verified 2026-07-02 — Structure confirmed against OpenTelemetry SDK semantics (SpanKind, attributes, record_exception, set_status). Implementation patterns verified against Databricks MLflow OTel guide (span filtering by type, fan-out to multiple backends), Zylos Agent Observability post (span taxonomy, session root span pattern), and Digital Applied sandbox analysis (span.depth for loop detection). Token/cost attribute pattern consistent with S-362 (Budget-Aware Agents). Tool span error recording aligns with S-93 (Tool Side-Effect Idempotency).

## See also

- [S-362 · Budget-Aware Agents](s362-budget-aware-agents-cost-self-regulation.md) — cost and token attribution per span
- [S-331 · LLM-as-Judge Evaluation](s331-llm-as-judge-evaluation.md) — scoring trace quality end-to-end
- [S-100 · Agentic RAG](s100-agentic-rag.md) — retrieval spans as a first-class evaluation signal
- [S-93 · Tool Side-Effect Idempotency](s93-tool-side-effect-idempotency.md) — error recording on tool spans
- [F-74 · Agent Decision Tracing](forward-deployed/f74-agent-decision-tracing.md) — field notes on production trace debugging
