# W-04 · Observability

Log what the model does, what it costs, and when it fails. You can't improve what you can't measure.

## Forces
- LLM calls are black boxes by default — you see input and output, not what happened in between
- Token costs accumulate invisibly until the invoice arrives
- Failures are silent in agentic systems unless you add tracing
- Too much logging is noise; too little and you're debugging blind

## The move

**Minimum viable logging for every LLM call:**
```python
import time, logging

logger = logging.getLogger("llm")

def traced_call(client, **kwargs):
    start = time.monotonic()
    response = client.messages.create(**kwargs)
    elapsed = time.monotonic() - start

    logger.info({
        "model": kwargs.get("model"),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_ms": round(elapsed * 1000),
        "stop_reason": response.stop_reason,
    })
    return response
```

**What to log, always:**
- Model name
- Input + output token count
- Latency (wall clock)
- Stop reason (natural vs. max_tokens vs. tool_use)
- Any tool calls made

**What to log for agentic systems:**
- Agent ID and step number (to trace multi-step flows)
- Tool name + input + output (truncated)
- Retry count
- Total cost estimate (input_tokens × input_price + output_tokens × output_price)

**Production standard: OpenTelemetry GenAI conventions**

Don't invent attribute names. The OpenTelemetry **GenAI Semantic Conventions** (from the OTel GenAI SIG) are the vendor-neutral standard — use the `gen_ai.*` names so any backend (Grafana, Datadog, Langfuse, Arize) understands your traces:

- `gen_ai.request.model` · `gen_ai.usage.input_tokens` · `gen_ai.usage.output_tokens` · `gen_ai.response.finish_reasons` · `gen_ai.provider.name`
- For agents, the span tree mirrors the run: a top-level `invoke_agent` span with child `chat` spans (each LLM call) and `execute_tool` spans (each tool call) — see [W-05](w05-llmops-observability.md).

```python
from opentelemetry import trace
tracer = trace.get_tracer("llm-agent")

with tracer.start_as_current_span("chat") as span:
    span.set_attribute("gen_ai.request.model", model)
    response = client.messages.create(...)
    span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)
```

Two cautions: most of these conventions are still **experimental** as of 2026 (pin with `OTEL_SEMCONV_STABILITY_OPT_IN` to avoid churn), and put prompt/response *text* in span **events**, not attributes — attributes are indexed and will leak PII into your backend.

**Managed options:** Langfuse (open-source, self-hostable), LangSmith (hosted), Arize Phoenix (open-source).

## Receipt

> Verified 2026-06-25 — the `traced_call` wrapper (ported to the Anthropic Node SDK) run against llama3.2 via Ollama (localhost:11435), logging one line per call:

```
{"model":"llama3.2","input_tokens":2511,"output_tokens":7,"latency_ms":1199,"stop_reason":"end_turn"}
```

The prompt was five words ("Name three primary colors.") with no tools — yet **2,511 input tokens** were billed. That gap is the whole point of the entry: the local bridge injects a large default system prompt you never wrote, and you only see it because you logged `input_tokens`. Unmeasured, it's invisible until the bill. The `gen_ai.*` OTel attributes above are the documented standard names; not exercised in this minimal run.

## See also
[W-05](w05-llmops-observability.md) · [F-02](../forward-deployed/f02-evaluation-at-scale.md) · [F-03](../forward-deployed/f03-failure-modes.md) · [S-05](../stacks/s05-multi-agent-patterns.md)

## Go deeper
Keywords: `OpenTelemetry` · `GenAI semantic conventions` · `gen_ai attributes` · `Langfuse` · `LangSmith` · `Arize Phoenix` · `token cost tracking` · `LLM tracing` · `distributed tracing`
