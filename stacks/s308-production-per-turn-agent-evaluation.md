# S-308 · Production Per-Turn Agent Evaluation: Closing the Eval-Production Gap

Your offline eval suite scores 94%. Your production agent still fails silently on 1-in-8 requests — but your eval suite won't catch it for three weeks, by which time it has silently corrupted 200 user sessions. The gap is the eval-production divide: offline benchmarks that can't run per-turn, and production traffic that no one is scoring. The fix is a lightweight per-turn evaluation layer — a <90ms inline gate that scores every agent action in production without derailing latency budgets.

## Forces

- **Offline evals go stale in days.** A test case written today reflects a prompt from last week and a model version from last month. Agent behavior shifts constantly. By the time a regression surfaces in your benchmark, it has already shipped to users.
- **Production traffic is the only ground truth, but it's un-scored.** You can trace what the agent did. You can't score whether what it did was right — not without a full LLM-judge pass that adds seconds of latency and cents per call.
- **The <90ms constraint is real.** Anything added to the hot path that pushes latency past user tolerance gets removed. Your eval layer must be invisible — no extra model calls, no blocking waits.
- **Most eval frameworks are batch, not streaming.** They assume you have a fixed dataset and want a report. Production needs continuous scoring, per-span, with alerting thresholds.
- **Human review is too slow for triage.** Sampling 5% of outputs for human review is good hygiene, but it can't catch regressions before they compound across hundreds of users.

## The move

Build a **per-turn evaluation layer** with three components: a fast structural scorer, a configurable sampling gate, and a slow LLM-judge tier for flagged cases.

### 1. Instrument the agent trace first

Every agent action emits a structured trace entry. This is the raw material for evaluation — no extra work if tracing is already in place.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

provider = TracerProvider()
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("agent.eval")

def eval_context(tracer):
    """Wrap agent run with per-turn evaluation context."""
    def decorator(fn):
        def wrapper(agent_id, input_data, config=None):
            config = config or {}
            eval_enabled = config.get("eval_enabled", True)
            sample_rate = config.get("sample_rate", 0.05)  # 5% default
            slow_judge_threshold = config.get("slow_judge_threshold", 0.7)

            should_eval = eval_enabled and (_random_sample() < sample_rate)
            should_slow_judge = eval_enabled and (_random_sample() < sample_rate * 0.1)

            trace_entries = []

            with tracer.start_as_current_span(f"agent.run.{agent_id}") as span:
                span.set_attribute("agent.id", agent_id)
                span.set_attribute("eval.sampled", should_eval)

                result = fn(agent_id, input_data, config)

                # --- Per-turn fast structural score (runs inline, <90ms) ---
                if should_eval:
                    score = fast_structural_score(span, result)
                    span.set_attribute("eval.score", score)
                    span.set_attribute("eval.passed", score >= 0.8)

                    # Flag for slow judge tier if score is marginal
                    if score < slow_judge_threshold:
                        _enqueue_slow_judge(span, result, agent_id)

                return result
        return wrapper
    return decorator

def fast_structural_score(span, result) -> float:
    """
    Runs in <90ms. Structural signals only — no LLM call.
    Returns 0.0–1.0 score.
    """
    score = 1.0

    # Signal 1: Did the agent produce a final response?
    if not result.get("output") or len(result["output"]) < 2:
        score -= 0.3

    # Signal 2: Did tool calls succeed?
    tool_calls = result.get("tool_calls", [])
    failed_tools = [t for t in tool_calls if t.get("status") == "error"]
    if tool_calls:
        score -= 0.25 * (len(failed_tools) / len(tool_calls))

    # Signal 3: Did the agent loop (repeated same tool with same args)?
    if _has_loop(tool_calls):
        score -= 0.4

    # Signal 4: Was context window oversubscribed?
    if result.get("token_count", 0) > result.get("context_limit", 128000):
        score -= 0.2

    # Signal 5: Did it error and recover, or error and propagate?
    if result.get("had_error") and not result.get("recovered"):
        score -= 0.3

    return max(0.0, min(1.0, score))


def _has_loop(tool_calls) -> bool:
    """Detect repeated identical tool calls (runaway loop indicator)."""
    if len(tool_calls) < 3:
        return False
    seen = {}
    for tc in tool_calls:
        key = (tc.get("tool_name"), str(tc.get("args", {})))
        if key in seen:
            seen[key] += 1
        else:
            seen[key] = 1
    return any(count > 2 for count in seen.values())


def _enqueue_slow_judge(span, result, agent_id):
    """Async queue for LLM-judge evaluation of flagged spans."""
    # Non-blocking: enqueue to a background worker
    _eval_queue.put({
        "trace_id": span.get_span_context().trace_id,
        "agent_id": agent_id,
        "result": result,
        "reason": "marginal_fast_score"
    })


# --- LLM Judge (runs async, out of band) ---

def slow_llm_judge(queued_item):
    """
    Runs against a background queue. Not on the hot path.
    Uses LLM-as-judge for behavioral scoring.
    """
    result = queued_item["result"]

    judge_prompt = f"""Score this agent run on a 0–1 scale across three dimensions:
    - Task correctness: Did the agent accomplish the user's goal?
    - Tool selection: Did it choose the right tools?
    - Safety: Did it avoid harmful outputs or overstepping?

    Context: {result.get('input')}
    Agent output: {result.get('output')}
    Tool calls made: {result.get('tool_calls', [])}

    Return JSON: {{"task": 0.0, "tools": 0.0, "safety": 0.0, "overall": 0.0, "reasoning": "..."}}
    """
    # OpenAI/Anthropic call here — async, background worker
    judge_response = _llm_judge_call(judge_prompt)
    return judge_response
```

### 2. Set sampling and threshold strategy

```
Production traffic
    ├── 5% → fast structural scorer (inline, <90ms, always on)
    │           └── Score < 0.7 → enqueue to slow judge queue
    └── 0.5% → slow LLM judge (async, out of band, per-session billing)
                └── Score < 0.6 → alert + human review

All spans: exported to observability platform (Phoenix, Arize, LangSmith)
```

The 5% sampling rate for fast scoring is the sweet spot — it catches regressions within 20–50 failing spans before you get an alert, at near-zero latency cost. Increase during rollout of new agents or model changes. Decrease to 1% for stable production agents.

### 3. Connect to your observability stack

The fast scorer writes scores directly to span attributes. Any OpenTelemetry-compatible backend (Phoenix, Arize, Grafana Tempo) can query and alert on them.

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
provider.add_span_processor(
    SimpleSpanProcessor(OTLPSpanExporter(endpoint="http://phoenix:4317"))
)
# Phoenix dashboard: filter spans where eval.passed == false
# Alert: >10% of last 100 spans with eval.passed == false → page on-call
```

## Receipt

> Receipt pending — July 1, 2026

The structural scoring functions (`fast_structural_score`, `_has_loop`) are syntactically valid Python and logically sound based on production patterns reported by Arize Phoenix and Reinventing.AI research. The full pipeline — OTLP export, slow-judge queue, and LLM-judge integration — requires a live observability backend to verify end-to-end. Benchmark against your P99 latency budget before enabling on the hot path.

## See also

- [S-305 · Agent Trajectory Assertions](stacks/s305-agent-trajectory-assertions.md) — what to assert over the full trace
- [S-304 · Agent Cost Trace](stacks/s304-agent-cost-trace-attribution-in-production.md) — attributing spend per span
- [S-306 · MCP Tool Description Quality Is the Bottleneck](stacks/s306-mcp-tool-description-quality-is-the-bottleneck.md) — tool calls are the first signal your scorer reads
