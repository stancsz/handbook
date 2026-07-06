# S-587 · Agent Loop Prevention and Cost Circuit Breakers

Agents that loop are the single most expensive production failure mode — a single stuck agent can accumulate hundreds or thousands of dollars before anyone notices. Teams are discovering that guardrails alone aren't enough; they need layered financial and operational controls built into the execution loop itself.

## Forces

- **Agent loops compound silently between the retry layer and the billing cycle.** A recovery system that retries failures, combined with an agent that fails the same way, creates a doom spiral invisible at the timeout level but catastrophic on the invoice.
- **LLM token costs are non-linear with retries.** Each retry re-passes context. A 5-step task that fails on step 4 costs ~4x on the retry. After 3 retries, you're paying 12x for a single logical operation that a circuit breaker would have cut at $2.
- **The gap between "completed within timeout" and "completed without overspend" is invisible to most tooling.** Timeout-based monitoring misses the most common failure: an agent that works but fires far more LLM calls than expected.
- **OWASP LLM Top 10 v2.0 names Excessive Agency as a top production risk.** An agent that loops while holding write access doesn't just waste money — it extends the window for cascading data corruption.

## The Move

Implement cost and loop controls in three stacked layers, not one:

- **Layer 1 — Hard iteration cap.** Set `max_iterations` on every agent loop. This is the floor, not the ceiling. Typical values: 5-15 for planning agents, 3-5 for tool-calling agents. Document the choice — the number matters and changes with model quality.

- **Layer 2 — Recovery anti-loop.** If a retry mechanism exists (and it should for production systems), enforce three constraints: maximum N recovery attempts per item per day (e.g., 3), a minimum time gap between attempts on the same item (e.g., 2 hours), and automatic skip on non-retryable errors (auth failures, content policy violations). This breaks the doom spiral where a stuck item triggers retry → fails → retry → fails indefinitely, each cycle burning $2-5 on Opus-tier models.

- **Layer 3 — Cost circuit breaker.** A monitoring process (typically running every 30 minutes) reads session logs, calculates per-session spend, and halts agents that exceed a per-session or per-day budget. Budgets should be scoped to task type: research agents might allow $5/session; write agents $0.50/session. When triggered, alert and move on — do not auto-retry.

- **Layer 4 — Structured output with validation gates.** Pydantic-based output validation catches hallucinated or malformed tool responses before they propagate as input to the next agent step. A bad response at step N that goes unchecked becomes the input to step N+1, where it either triggers a loop (agent keeps trying to parse it) or silently propagates a wrong answer. Validate before passing the output downstream.

- **Scope least-privilege to execution phase.** An agent mid-loop holding database write access is exponentially more dangerous than one holding read access. Separate the permission model from the agent identity: planning phase gets broad context; execution phase gets only what the specific action requires, and that access is revoked on loop detection.

## Evidence

- **arXiv catalog of 63 LLM-agent budget overrun incidents:** An empirical study documenting that a single retry loop can accumulate thousands of dollars before detection, with retry loops identified as the dominant failure class. The paper proposes affine-typed Rust mitigations and catalogs failure modes by architecture. — [arXiv:2606.04056](https://arxiv.org/html/2606.04056v1)

- **Production incident report (Q1 2025):** A SaaS company deployed an autonomous data cleanup agent with write access to the primary customer database. Over a weekend, the agent processed 14,000 records, applied an unanticipated transformation, and corrupted 9,000 records. Recovery took 31 engineering hours. Root cause: missing guardrails — the agent's prompt did not anticipate the specific edge case. Reported in OWASP LLM Top 10 v2.0 context. — [Logiciel Guardrails Guide](https://logiciel.io/blog/guardrails-agentic-ai)

- **Cost circuit breaker implementation (Fountain City Tech):** A team describing their three-layer system: timeout-based monitoring (misses overspend within a job), recovery anti-loop (max 3 retries, 2-hour gap, skip non-retryable errors), and cost circuit breaker (runs every 30 minutes against session logs). The anti-loop layer specifically prevents the doom spiral where a recovery mechanism combined with a failing agent compounds costs indefinitely. — [Fountain City Tech](https://fountaincity.tech/resources/blog/ai-agent-cost-circuit-breaker)

- **Reddit r/LocalLLaMA thread on agent loops and cost overruns (5 months ago):** Practitioners reporting use of `max_iterations` as the baseline approach, with interest in more sophisticated monitoring. Multiple respondents cite surprise at how quickly token costs accumulate when an agent retries a 10-step task multiple times. — [Reddit r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1r41h6v/how_do_you_handle_agent_loops_and_cost_overruns/)

## Gotchas

- **Setting `max_iterations` too low causes false positives.** An agent doing genuine 12-step reasoning that hits a limit of 10 produces a worse outcome than one that loops 12 times — it stops mid-reasoning and returns an incomplete answer. Calibrate limits by task complexity, not default.
- **The cost circuit breaker runs out-of-band — it has latency.** A 30-minute polling interval means a burst of expensive calls between checks is invisible until the next run. For high-stakes write operations, consider inline per-call budget tracking, not just aggregate session tracking.
- **Output validation is only as good as the schema.** If the Pydantic model accepts a wide range of outputs to "be flexible," it validates nothing. Keep validation schemas tight and specific to the expected output structure.
- **Recovery anti-loop constraints interact badly with idempotency.** A 2-hour gap on retry means a legitimately failed task (transient error, not a loop) waits 2 hours before the next attempt. For time-sensitive operations, the gap needs to be shorter or the retry path needs a back-off strategy rather than a hard skip.
