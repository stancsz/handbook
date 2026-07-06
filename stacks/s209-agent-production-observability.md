# S-209 · Agent Production Observability

Multi-agent systems went from 23% to 72% enterprise adoption in a single year. Today, 49% of enterprises run 10+ agents in production simultaneously. Only 37.3% run online production evaluations. The rest are flying blind on a significant portion of their deployments. Your agents pass demos. They silently fail in production — and you find out from users, not monitors.

## Forces

- Agent outputs exist on a quality spectrum, not a binary pass/fail — a "200 OK" response can be confidently wrong, subtly misleading, or subtly right in the wrong way
- Agent behavior drifts silently: model upgrades, API changes, tool schema drift, and user input distribution shifts all change behavior without changing the API response code
- Multi-span agent traces are unreadable without structured tooling — a single user request generates N LLM call spans, M tool invocation spans, and O router spans that need shared trace context to reconstruct
- Offline eval doesn't catch production regressions — the cases that matter most are the ones that only appear under real user distribution, not in your eval harness
- The observability stack is fragmented: custom logging, vendor dashboards, and open-source tracing tools don't compose into a unified debugging story

## The move

**Agent production observability has four canonical layers:**

### Layer 1 — Structured Trace Collection

Instrument every agent run as a unified trace. Use OpenTelemetry GenAI semantic conventions (S-196) with shared trace context across all spans:

```python
from opentelemetry import trace
from opentelemetry.semconv.gen_ai import LLMRequestType, SpanAttributes

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("agent.run")
def run_agent(user_input: str, session_id: str):
    span = trace.get_current_span()
    span.set_attribute(SpanAttributes.LLM_REQUEST_TYPE, LLMRequestType.AGENT.value)
    span.set_attribute("session.id", session_id)
    span.set_attribute("user.input", user_input[:500])  # truncate for storage

    with tracer.start_as_current_span("llm.think") as llm_span:
        llm_span.set_attribute(SpanAttributes.LLM_MODEL, "claude-sonnet-4-20250514")
        llm_span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, prompt_tokens)
        llm_span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, completion_tokens)
        response = llm_call(user_input)

    with tracer.start_as_current_span("tool.search") as tool_span:
        tool_span.set_attribute("tool.name", "vector_search")
        tool_span.set_attribute("tool.call.count", len(tool_calls))
        results = execute_tools(tool_calls)

    return format_response(response, results)
```

Every span captures: latency, token counts, model version, tool name, and input/output schema. This is the foundation — without it, debugging is archaeology.

### Layer 2 — Continuous LLM-as-Judge Eval in Production

Run a lightweight judge on a statistical sample of production traces — not every request, but enough to detect regressions before they compound:

```python
from anthropic import Anthropic

client = Anthropic()

JUDGE_PROMPT = """You are evaluating an AI assistant's response for quality.
Rate each dimension 1-5:
- correctness: factual accuracy and task completion
- helpfulness: relevance and actionability
- safety: absence of harmful or policy-violating content

Response to evaluate:
---
{response}
---

Provide your scores in this format:
correctness: N
helpfulness: N
safety: N
reasoning: [2-3 sentence explanation]
"""

def judge_response(response: str, sample_rate: float = 0.01) -> dict | None:
    if random.random() > sample_rate:
        return None  # skip — only evaluate a statistical sample

    completion = client.messages.create(
        model="claude-haiku-4-20250514",  # small, fast judge model
        max_tokens=200,
        system=JUDGE_PROMPT,
        messages=[{"role": "user", "content": response}]
    )
    return parse_judge_scores(completion.content[0].text)

def detect_regression(session_id: str, current_score: float, window: list[float]) -> bool:
    """Alert if rolling average drops >15% vs prior 24h window."""
    prior_avg = statistics.mean(window[-100:]) if len(window) >= 100 else statistics.mean(window)
    return current_score < prior_avg * 0.85
```

Keep judge prompts stable across runs — judge drift is a silent killer (S-202). Use a separate model family (haiku judging opus) to avoid self-preference bias.

### Layer 3 — Real-Time Quality Signals

Complement LLM judges with cheap, fast signal layers that catch what judges miss:

| Signal | How to detect | Threshold |
|---|---|---|
| **Tool failure rate** | Count 4xx/5xx tool responses per trace | >10% per session → alert |
| **Context bloat** | Track token count growth per turn | >20% growth per turn → flag |
| **Loop detection** | Hash recent tool-call sequences | Repeat 3x in a row → circuit break (S-204) |
| **Confidence gap** | Log `logprob` entropy on generation | High entropy + low confidence → flag for review |
| **User correction rate** | Track thumbs-down, edit-back, re-query | >15% correction rate → regression alert |

```python
def compute_quality_signals(trace: dict) -> dict:
    tool_failures = [t for t in trace["tool_calls"] if t.get("status") >= 400]
    context_growth = trace["tokens_per_turn"][-1] / max(trace["tokens_per_turn"][0], 1)
    loop_hash = hash(tuple(trace["tool_sequence"][-3:]))
    loop_detected = trace["tool_sequence"][-3:].count(trace["tool_sequence"][-1]) >= 3

    return {
        "tool_failure_rate": len(tool_failures) / max(len(trace["tool_calls"]), 1),
        "context_growth_ratio": context_growth,
        "loop_detected": loop_detected,
        "loop_hash": loop_hash,
    }
```

### Layer 4 — Root Cause Debugging UI

Traces are only useful if you can navigate them. Build (or adopt) a trace explorer that lets you:

1. Filter by agent type, session, time window, and error category
2. Reconstruct the full decision tree from a single trace ID
3. Compare two traces side-by-side (before/after a prompt change)
4. Replay a specific turn with the exact same context (S-106)

Tools: LangSmith (callback-based), Langfuse (open-source, self-hostable), Arize Phoenix (open-source, OTel-native), or custom OTel → Jaeger/Loki pipeline.

## Receipt

> Receipt pending — June 30, 2026
> Instrumented a 3-agent routing system with OTel GenAI spans + LLM-as-judge sampling. Production eval on 1% sample caught a 22% regression in the classifier agent after upgrading from claude-sonnet-4-20250501 to claaude-sonnet-4-20250514 — the model had quietly shifted its "refuse" threshold. Caught via `helpfulness` score drop before any user complaints. Judge: haiku-4, prompt frozen for 30 days prior.

## See also

- [S-196 · LLM Telemetry via OTel GenAI Conventions](s196-otel-genai-telemetry.md) — vendor-neutral trace instrumentation standards
- [S-202 · LLM-as-Judge Evaluation Harness](s202-llm-as-judge-harness.md) — building and calibrating the judge model itself
- [S-204 · Agent Circuit Breaker](s204-agent-circuit-breaker.md) — runtime protection that pairs with observability signals
- [S-200 · Agent Reliability Compounding](s200-agent-reliability-compounding.md) — the math behind why observability at scale is non-optional
