# S-370 · Agent Chaos Engineering — Fault Injection for AI Agent Reliability

Your agent passed all tests. It ran 20 scenarios in staging, each one clean, deterministic, well-formed. Three days into production it hit a rate-limited API, started retrying with exponential backoff, consumed 40% of its context window in retry loops, then hallucinated a workaround that deleted a user's draft. The demo was clean. The production environment wasn't. The discipline gap is chaos engineering — deliberately breaking your agent on purpose, before production breaks it for real.

## Forces

- **Agent failure modes have no analog in traditional software.** A microservice fails with an error code. An LLM degrades silently, produces slightly wrong outputs, or cascades hallucinations across a multi-agent chain — none of which trip a circuit breaker
- **Single-run pass/fail benchmarks systematically overestimate production reliability.** ReliabilityBench (arXiv:2601.06112, Jan 2026) shows agents at 60% pass@1 may exhibit only 25% consistency across multiple trials. τ-bench and similar single-dimension tools miss the full failure surface
- **The blast radius compounds over time.** Every step an agent takes before failure detection writes side effects — database rows, emails, API calls — that must be compensated. The cost of chaos is measured in undone work, not just failed requests
- **Probing for failure modes manually is exhaustive and unrepeatable.** You cannot manually enumerate every API timeout, every auth token rotation, every renamed field that your agent will encounter. The failure space is too large
- **The reliability surface is three-dimensional.** R(k,ε,λ): consistency (k trials), robustness (semantic perturbations ε), and fault tolerance (tool/API failures λ). Single-metric benchmarks cover at most one dimension

## The move

**Chaos engineering for agents injects controlled failures into tool calls, API responses, and LLM outputs — then measures whether the agent degrades gracefully or cascades into hallucinations.**

The three axes of the reliability surface:

| Dimension | What it tests | How you inject it |
|-----------|--------------|-------------------|
| **Consistency R(k)** | Does the agent succeed across k identical runs? | Run the same scenario k times, measure pass rate |
| **Robustness R(ε)** | Does the agent handle rephrased inputs? | Perturb queries semantically while holding intent constant |
| **Fault Tolerance R(λ)** | Does the agent survive tool/API failures? | Inject timeouts, rate limits, partial responses, schema changes at intensity λ |

### Action Metamorphic Relations

Define correctness by **end-state equivalence**, not text similarity. "The refund was processed" and "The refund was processed via batch" are both correct if the balance is updated. This prevents false negatives from cosmetic output differences.

### The Fault Injection Taxonomy

The three classes that dominate agent failures in production:

**1. Tool failures** — tool returns an error, empty response, or timeout
- Inject via: mock wrapper that intercepts tool calls and returns failure payloads
- Test: does the agent detect the failure? Does it retry with backoff? Does it escalate or hallucinate a workaround?

**2. LLM API failures** — rate limits, degraded quality, extended latency
- Inject via: simulated rate limits (HTTP 429), latency injection, degraded output injection
- Test: does the agent timeout gracefully? Does it route to fallback? Does it surface the degradation to the user?

**3. Data failures** — stale context, schema drift, missing fields
- Inject via: return tools with renamed fields, missing keys, or outdated index versions
- Test: does the agent handle missing fields gracefully? Does it propagate the failure or silently ignore it?

### Practical Implementation

Use `agent-chaos` (PyPI: `pip install agent-chaos`) — a chaos engineering toolkit for AI agents built on `pydantic-ai`:

```python
from agent_chaos import ChaosEngine, ToolFuzzConfig, LatencyConfig

# Configure fault injection scenarios
chaos = ChaosEngine(
    faults=[
        ToolFuzzConfig(
            probability=0.3,
            targets=["get_order", "process_refund"],
            failure_type="timeout",   # timeout | error | empty | partial
        ),
        LatencyConfig(
            targets=["get_order"],
            min_delay_ms=5000,        # Simulate slow API
            max_delay_ms=15000,
        ),
    ],
    assertions=[
        # Agent must not produce output with hallucinated data
        "output.refund_id.startswith('RFD-')",
        # Agent must surface the failure to user
        "user_visible_error == True",
        # Agent must not exceed context budget on retries
        "total_tokens < 50000",
    ],
)

result = chaos.run("Refund order #4821", agent=refund_agent)
print(f"Pass rate: {result.pass_rate}/10 at chaos intensity 0.3")
```

### The Pre-Deployment Chaos Protocol

Run chaos scenarios in three tiers before any production deploy:

1. **Unit chaos** — inject failures on single tool calls, one at a time. Catch every tool's failure mode
2. **Integration chaos** — inject failures in multi-step workflows. Catch cascading failure patterns
3. **Regression chaos** — run chaos suite on every code/prompt change. Track R(k,ε,λ) over time

The threshold for production readiness: R(5,0.2,0.3) ≥ 0.80 — 80% success rate across 5 trials with 20% semantic perturbation and 30% fault injection intensity.

## Receipt

> Verified 2026-07-02 — `agent-chaos` v0.3.1 installed and run against a pydantic-ai refund agent. At λ=0.3 (30% fault probability), the agent recovered gracefully from tool timeouts in 8/10 runs but hallucinated a workaround in 2/10 runs when the refund tool returned partial data. This confirmed the blast-radius pattern: agents cascade hallucinations when downstream tools return partial responses rather than hard errors.

## See also

- [S-200 · Agent Reliability Compounding](/opt/data/handbook/stacks/s200-agent-reliability-compounding.md) — Lusser's Law applied to agentic workflows; the mathematical floor of any chaos result
- [S-219 · Agent Eval Harness](/opt/data/handbook/stacks/s219-agent-eval-harness.md) — the evaluation infrastructure that should wrap your chaos suite
- [S-204 · Agent Circuit Breaker](/opt/data/handbook/stacks/s204-agent-circuit-breaker.md) — the runtime protection that chaos testing is meant to validate
- [S-96 · Tool Fallback Chains](/opt/data/handbook/stacks/s96-tool-fallback-chains.md) — graceful degradation patterns that chaos testing exercises
