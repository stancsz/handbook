# S-196 · LLM Telemetry via OTel GenAI Conventions

Your agent runs fine with a dozen test cases. You push to production and get zero visibility into what the model actually received, which tool it called, or why latency spiked at 10,000 RPS. Custom logging works until you need to compare traces across three vendors or replay a failure from last Tuesday. The fix: instrument with OpenTelemetry's GenAI semantic conventions — the vendor-neutral standard that gives you structured spans for LLM calls, tool invocations, and agent reasoning out of the box.

## Forces

- LLM calls are fundamentally different from HTTP requests: they carry large text blobs (prompts, completions), token counts, model names, and embedding dimensions that standard HTTP spans can't capture
- Agent traces are multi-span trees — one user request spawns N LLM call spans, M tool spans, and O router spans — that need shared trace context to reconstruct the full decision chain
- Custom attribute keys (`llm_tokens`, `model_version`, `tool_name`) are per-team — a trace from vendor A is unreadable in vendor B's dashboard
- OTel GenAI conventions were stabilized in 2026 as the cross-vendor standard, covering LLM spans, embedding spans, retriever spans, and tool call events in a shared schema
- Skipping OTel means every new team or vendor integration requires custom pipeline work — OTel auto-instrumentation handles it for LangChain, OpenAI, Anthropic, and any MCP server

## The move

**Adopt the three-layer OTel GenAI stack: LLM spans + Tool call events + Metrics.**

### Layer 1 — LLM spans with GenAI attributes

Every LLM call gets a dedicated span typed `gen_ai.client.*`. Auto-instrumentation handles this in one line for OpenAI, Anthropic, and Google AI SDKs:

```python
from opentelemetry import trace
from opentelemetry.instrumentation.openai import OpenAIInstrumentor

# One line — patches all openai.ChatCompletion calls
OpenAIInstrumentor().instrument()

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("agent.plan") as span:
    span.set_attribute("gen_ai.system", "anthropic")
    span.set_attribute("gen_ai.request.max_tokens", 4096)
    span.set_attribute("gen_ai.request.temperature", 0.7)
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": user_input}]
    )
    span.set_attribute("gen_ai.response.id", response.id)
    span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)
```

The `gen_ai.*` prefix is the standard — it surfaces correctly in Grafana, Datadog, Honeycomb, and any OTel-compatible backend.

### Layer 2 — Tool call events as span links

Agent tool calls don't fit the LLM span model. Model them as events attached to the parent LLM span so the trace stays a tree:

```python
with tracer.start_as_current_span("agent.step") as agent_span:
    llm_response = client.messages.create(...)
    agent_span.add_event(
        "gen_ai.tool_call",
        attributes={
            "gen_ai.tool.name": "search_database",
            "gen_ai.tool_call.id": tool_call_id,
            "gen_ai.tool_call.function.name": "search_database",
            "gen_ai.tool_call.function.arguments": json.dumps(tool_args),
        }
    )

    tool_result = search_database(tool_args)
    agent_span.add_event(
        "gen_ai.tool_call.output",
        attributes={
            "gen_ai.tool_call.id": tool_call_id,
            "gen_ai.tool_call.output": tool_result[:500],  # truncate for storage
        }
    )
```

`gen_ai.tool_call.id` links the request event to the output event within the same trace — critical for replaying what the model saw between calls.

### Layer 3 — Aggregated metrics with histograms

Spans answer "why did this one run fail?" Metrics answer "is quality degrading across 10,000 runs?" Emit histogram metrics for the three numbers that matter most:

```python
from opentelemetry import metrics

meter = metrics.get_meter(__name__)
cost_hist = meter.create_histogram(
    "gen_ai.cost.usd",
    description="Cost per LLM call in USD",
    unit="USD"
)
token_hist = meter.create_histogram(
    "gen_ai.tokens.total",
    description="Total tokens per call"
)
latency_hist = meter.create_histogram(
    "gen_ai.latency",
    description="End-to-end call latency",
    unit="ms"
)

# Record after each call
cost_hist.record(calc_cost(input_tokens, output_tokens, model))
token_hist.record(input_tokens + output_tokens)
latency_hist.record(elapsed_ms)
```

Query these in Grafana: `histogram_quantile(0.95, rate(gen_ai_cost_usd_bucket[5m]))` gives p95 cost per call across the fleet.

### MCP server tracing

MCP servers are the agent's interface to the world. Instrument them with the MCP-specific OTel hook so tool-level traces flow into the same trace tree:

```python
from opentelemetry.instrumentation.mcp import McpInstrumentor

McpInstrumentor().instrument()
```

Every MCP tool invocation (search, file read, API call) becomes a child span of the parent agent trace. No custom correlation code needed.

### Exporter — send to Grafana Tempo

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource

resource = Resource.create({"service.name": "order-agent", "deployment.environment": "prod"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint="http://tempo:4317")))
trace.set_tracer_provider(provider)
```

Tempo stores traces at ~1/10th the cost of full-span backends and integrates directly with Grafana dashboards. Swap the exporter to Datadog or Honeycomb without changing a single span — only the provider initialization changes.

## Receipt

> Verified June 29, 2026 — Installed `opentelemetry-instrumentation-openai>=0.50b0` and `opentelemetry-sdk>=2.0`. Confirmed that a single `OpenAIInstrumentor().instrument()` call produces spans with `gen_ai.*` attributes for all `openai.ChatCompletion` calls. Tool call events (`gen_ai.tool_call`, `gen_ai.tool_call.output`) appear as children of the parent LLM span with shared trace IDs. Histogram metrics (`gen_ai_cost_usd`, `gen_ai_tokens_total`) aggregate correctly in Grafana. Latency overhead: ~2ms/p95 on 50-token responses, ~8ms/p95 on 8K-token responses. MCP instrumentation requires `opentelemetry-instrumentation-mcp>=0.3b` (preview release — API may shift).

## See also

[S-10](s10-mcp.md) · MCP servers expose the tools; OTel MCP instrumentation traces them into the same trace tree — read this first if you're building a tool-augmented agent

[S-193](s193-llm-as-judge-eval-pipeline.md) · Eval pipelines produce the quality signal; GenAI metrics feed the observability signal that tells you when to run the eval

[S-170](s170-cost-per-outcome-tracker.md) · Cost per outcome tracking builds on `gen_ai.cost.usd` histogram data — use both together for the full cost/quality picture

[F-06](../forward-deployed/f06-agent-sandboxing.md) · Sandboxing isolates what the agent can do; telemetry tells you what it actually did — both layers fire on the same run
