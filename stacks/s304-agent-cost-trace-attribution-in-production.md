# S-304 · The Agent Cost Trace: Making Invisible Spend Visible

AI agent bills arrive at the end of the month with a number, not an explanation. You know you spent $14,200 on inference last week. You don't know whether it's because your retriever is stuffing 40K-token context windows into every query, your 4-agent orchestration is making redundant model calls, or a single runaway loop is spinning at $0.08 per turn. The fix is a cost trace — structured, per-span instrumentation that attributes every cent to a component, a user action, and a decision.

## Forces

- **Agent spend is non-linear and surprising.** A chat interface costs $X. The same logic wrapped in an agent costs 5–25X due to loops, retries, context reloads, and redundant tool calls. Teams don't see this until the first bill shock.
- **Standard observability traces token counts but not cost.** You can see that a trace had 12 model calls and 8 tool invocations. You can't easily answer "which user action triggered the $0.34 request?" or "which agent in my pool is burning budget fastest?"
- **Multi-agent orchestration multiplies opacity.** A supervisor dispatching 3 workers, each making 2 sub-calls, produces a 7-span tree where cost attribution to the originating request requires shared context that most tracing systems don't carry.
- **Cost anomalies are invisible without a baseline.** The difference between a healthy $0.02/turn and a degraded $0.18/turn from a context-bloating regression won't surface unless you track cost-per-span over time.

## The move

Build a cost trace layer on top of your existing instrumentation. Two pieces:

**1. Span-level cost enrichment.** Every LLM span carries a `cost_usd` attribute computed at call time from model rate × token count. No batching, no estimation — real numbers.

```python
import time
from dataclasses import dataclass, field
from typing import Optional
from functools import wraps

# Model pricing table (USD per 1M tokens, 2025 list rates)
MODEL_RATES = {
    "gpt-4o":        {"input": 2.50, "output": 10.00},
    "gpt-4o-mini":   {"input": 0.15, "output": 0.60},
    "claude-sonnet": {"input": 3.00, "output": 15.00},
    "claude-haiku":  {"input": 0.25, "output": 1.25},
    "gpt-4-turbo":   {"input": 10.0, "output": 30.00},
}

@dataclass
class CostSpan:
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float = 0.0
    parent_id: Optional[str] = None
    trace_id: str = ""
    span_id: str = ""

    def __post_init__(self):
        rates = MODEL_RATES.get(self.model, {"input": 5.0, "output": 15.0})
        self.cost_usd = (
            self.input_tokens / 1_000_000 * rates["input"]
            + self.output_tokens / 1_000_000 * rates["output"]
        )


def traced_llm_call(model: str):
    """Decorator that instruments any LLM call with cost + latency."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(prompt: str, **kwargs):
            from uuid import uuid4
            span_id = uuid4().hex[:8]
            t0 = time.perf_counter()
            result = fn(prompt=prompt, model=model, **kwargs)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            # Assume the caller extracts token counts from the response metadata
            span = CostSpan(
                model=model,
                input_tokens=result.get("input_tokens", 0),
                output_tokens=result.get("output_tokens", 0),
                latency_ms=elapsed_ms,
                span_id=span_id,
            )
            # Push to your trace store (OTLP, in-memory, whatever)
            trace_store.push(span)
            return result
        return wrapper
    return decorator


# Usage with a real client
from openai import OpenAI
client = OpenAI()

@traced_llm_call("gpt-4o")
def call_llm(prompt: str, model: str, **kwargs):
    resp = client.chat.completions.create(model=model, messages=[{"role":"user","content":prompt}], **kwargs)
    return {
        "content": resp.choices[0].message.content,
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
    }
```

**2. Trace aggregation by request root.** In multi-agent systems, propagate a `trace_id` from the root request through every downstream span. This lets you sum all child costs back to the originating user action.

```python
from collections import defaultdict

class CostAggregator:
    def __init__(self):
        self.traces: dict[str, list[CostSpan]] = defaultdict(list)

    def push(self, span: CostSpan):
        self.traces[span.trace_id].append(span)

    def total_cost(self, trace_id: str) -> float:
        return sum(s.cost_usd for s in self.traces[trace_id])

    def breakdown(self, trace_id: str) -> dict:
        spans = self.traces[trace_id]
        by_model = defaultdict(lambda: {"calls": 0, "cost": 0.0, "tokens_in": 0, "tokens_out": 0})
        for s in spans:
            m = by_model[s.model]
            m["calls"] += 1
            m["cost"] += s.cost_usd
            m["tokens_in"] += s.input_tokens
            m["tokens_out"] += s.output_tokens
        return {
            "total_cost_usd": self.total_cost(trace_id),
            "total_calls": len(spans),
            "by_model": dict(by_model),
        }


# Example: multi-agent trace breakdown
# In your orchestrator, propagate trace_id to each worker:
#   worker.run(task, trace_id=root_trace_id)
# At session end:
agg = CostAggregator()
# (push spans from the trace_store in real usage)
breakdown = agg.breakdown("req_abc123")
# {
#   "total_cost_usd": 0.0347,
#   "total_calls": 7,
#   "by_model": {
#     "claude-sonnet": {"calls": 4, "cost": 0.028, "tokens_in": 6200, "tokens_out": 890},
#     "gpt-4o-mini":   {"calls": 3, "cost": 0.0067, "tokens_in": 1100, "tokens_out": 320},
#   }
# }
```

**3. Latency-cost scatter for anomaly detection.** Plot cost vs. latency per span. Outliers (high cost, low latency = bloated context; high latency, low cost = model routing failure) flag problems faster than dashboards.

## Receipt

> Receipt pending — July 1, 2026. Pattern verified conceptually against OpenAI usage API + Arize Phoenix trace ingestion. Cost enrichment via span decorators is the standard approach used by LangSmith, Phoenix, and Weights & Biases W&B Tracer. Real deployment requires wiring to your specific trace backend.

## See also

- [S-196 · LLM Telemetry via OTel GenAI Conventions](s196-otel-genai-telemetry.md) — the observability foundation this builds on
- [S-08 · Prompt Caching](s08-prompt-caching.md) — the first-order cost lever; cost tracing reveals when caching actually helps
- [S-302 · You Have Logs, But No Answers: The Agent Eval Gap](s302-you-have-logs-but-no-answers-the-agent-eval-gap.md) — cost traces answer one class of question eval gaps leave open
