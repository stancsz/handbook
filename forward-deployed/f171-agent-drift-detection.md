# F-171 · Agent Drift Detection

Your dashboards are green. Error rate: 0.3%. Latency: nominal. But your agent has quietly gotten worse over six weeks — it selects the wrong tool 12% more often, its reasoning traces are shallower, and customer escalations have ticked up 18%. Nothing crashed. Nothing logged an error. The agent is "working" — producing plausible, confident, progressively wrong output. This is agent drift, and your monitoring stack isn't built to see it.

## Forces

- **Error rate is a lagging indicator for drift.** A step that fails 5% of the time still succeeds 95% — it just succeeds slightly wrong. The output passes a superficial check; the downstream consequences compound.
- **Model, prompts, and data all look unchanged — but behavior degrades anyway.** Distribution shift in the user's query patterns, subtle changes in upstream tool responses, or LLM provider rolling updates can all silently erode agent quality without touching a line of your code.
- **You don't have a baseline.** Most teams run eval at release time, then go dark until a customer complains. Without a continuous behavioral baseline, drift is invisible until it's an incident.
- **Traditional observability catches crashes, not degradation.** Token counts, latency percentiles, and error rates are all green while the agent's decision quality silently erodes.

## The move

**Measure behavioral distribution, not just system health.** Three layers:

### 1. Baseline fingerprinting at deployment

Capture behavioral distributions on a golden dataset at launch. Track:

```python
import json
from collections import Counter
from scipy.stats import entropy

def agent_fingerprint(eval_traces: list[dict]) -> dict:
    """Capture behavioral distribution from a set of eval traces."""
    tool_dist = Counter(t["tool_name"] for t in traces_to_tool_calls(eval_traces))
    tool_probs = normalize(tool_dist)  # P(tool) across runs
    tool_entropy = entropy(list(tool_probs.values())
    success_rate = mean(t["outcome"] == "success" for t in eval_traces)
    avg_reasoning_depth = mean(t.get("reasoning_steps", 0) for t in eval_traces)

    return {
        "tool_entropy": round(tool_entropy, 3),
        "tool_distribution": tool_probs,
        "success_rate": round(success_rate, 3),
        "avg_reasoning_depth": round(avg_reasoning_depth, 1),
        "timestamp": now_iso(),
    }
```

**What to capture:** tool selection distribution, reasoning depth, output schema compliance rate, RAG citation覆盖率, tool call sequencing patterns. Store per version, per prompt version.

### 2. Continuous distribution monitoring

On a sample of production traces (1–5% traffic), compute the same metrics and compare to baseline using statistical distance:

```python
from scipy.spatial.distance import jensenshellannon

def detect_drift(current: dict, baseline: dict, thresholds: dict) -> dict:
    """
    Compare current behavioral distribution to baseline.
    Uses Jensen-Shannon divergence for tool distributions
    and z-score for scalar metrics.
    """
    flags = []

    # Tool distribution drift — most sensitive signal
    current_tools = current["tool_distribution"]
    baseline_tools = baseline["tool_distribution"]
    all_tools = set(current_tools) | set(baseline_tools)
    vec_current = [current_tools.get(t, 0) for t in all_tools]
    vec_baseline = [baseline_tools.get(t, 0) for t in all_tools]
    js_div = jensenshellannon(vec_current, vec_baseline)

    if js_div > thresholds["js_divergence"]:
        flags.append(f"tool_drift: js={js_div:.3f}")

    # Scalar metric z-scores
    for metric in ["success_rate", "avg_reasoning_depth"]:
        if metric in current and metric in baseline:
            z = z_score(current[metric], baseline_series[metric])
            if abs(z) > thresholds["z_score"]:
                flags.append(f"{metric}_zscore: {z:.2f}")

    return {
        "is_drift": len(flags) > 0,
        "flags": flags,
        "js_divergence": round(js_div, 4),
    }
```

**Alert threshold:** JS divergence > 0.05 for tool distributions is a strong signal. Z-score > 2.0 on success rate or reasoning depth warrants immediate review.

### 3. Rolling regression gating

Treat drift as a release regression. When drift is detected:

1. **Halt** — freeze the agent version if drift affects a high-stakes output
2. **Isolate** — check if it's one tool, one prompt version, or a provider change
3. **Compare** — run the same golden dataset against current vs. last-known-good version
4. **Patch or rollback** — correct the prompt, revert provider, or roll back to baseline

```python
# Integration: run in your eval pipeline
DRIFT_THRESHOLDS = {
    "js_divergence": 0.05,
    "z_score": 2.0,
    "success_rate_delta": -0.05,
}

def eval_with_drift_check(agent_version: str, sample_traces: list) -> dict:
    baseline = load_baseline(agent_version="last-known-good")
    current = agent_fingerprint(sample_traces)
    drift = detect_drift(current, baseline, DRIFT_THRESHOLDS)

    if drift["is_drift"]:
        trigger_alert(drift, agent_version, current, baseline)
        # Block release: gate your CI/CD pipeline here
        return {"pass": False, "drift": drift}

    return {"pass": True, "fingerprint": current}
```

## Receipt

> Receipt pending — June 29, 2026
> Framework pattern documented from: Syrin.ai Agent Stability Index (ASI, April 2026), Veilfire agent drift tracking (January 2026), Tacnode context drift analysis (2026). Code example follows established OTEL/sampling patterns in [S-196](stacks/s196-otel-genai-telemetry.md). Thresholds are starting points — calibrate against your own distribution.

## See also

- [S-200 · Agent Reliability Compounding](stacks/s200-agent-reliability-compounding.md) — Lusser's Law applied to agent chains; drift directly compounds unreliability
- [F-167 · RAG Faithfulness Gate](forward-deployed/f167-rag-faithfulness-gate.md) — detects hallucination drift within a single retrieval cycle
- [S-196 · OTEL GenAI Telemetry](stacks/s196-otel-genai-telemetry.md) — the instrumentation layer that makes distribution sampling possible
