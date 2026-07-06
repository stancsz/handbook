# S-351 · The Eval Gap: Tracing Without Truth

You can see every tool call your agent makes. You cannot tell if any of them were correct. Teams instrument distributed traces with OpenTelemetry, pipe everything into LangSmith, build elaborate span hierarchies — and still ship agents that confidently hallucinate 40% of the time in production. The eval gap is the difference between knowing what happened and knowing whether it was right. Most agent teams have closed the first distance. They have not closed the second.

## Forces

- **Traces are cheap; evals are expensive.** Tracing is a technical problem with established tooling (OpenTelemetry). Evaluation is a domain problem that requires ground truth, which most teams haven't built and don't know how to maintain.
- **89% of teams have observability; 52% have evals.** (RaftLabs, 2025) — the 37-point gap explains why multi-agent debugging is described by practitioners as "mostly guesswork."
- **LLM-as-Judge is not a silver bullet.** Used without structured rubrics, multi-model cross-validation, and human calibration, it inherits the biases of the judge model and provides false confidence.
- **The five failure modes cover 90% of agent failures.** (QubitTool, 2026) — teams that build eval taxonomies around these five categories catch regressions before users do. Teams that don't keep discovering them reactively.

## The move

**Design eval-first, instrument traces to serve it.** The trace layer answers "what happened?" The eval layer answers "was it right?" The debugging layer answers "why was it wrong?" You need all three.

### Eval taxonomy — the five production failure modes

Build evals around five recurring failure categories that account for ~90% of agent failures in production (QubitTool, 2026):

1. **Hallucination** — agent generates confident but incorrect outputs, especially in multi-step chains where intermediate errors propagate
2. **Tool misuse** — agent calls the right tool for the wrong reason, or the wrong tool entirely (addressed in s349 guardrails, but eval catches what guardrails miss)
3. **Context loss** — critical information from earlier in a session is dropped due to context window management issues
4. **Goal drift** — agent pursues a sub-task past the point of usefulness, or substitutes the user's actual goal with a related but different one
5. **Cascade failure** — a small error in step N compounds through steps N+1 through N+k (a 10-step agent at 85% per-step accuracy achieves ~20% end-to-end reliability without cascade prevention)

### Structural requirements for production evals

- **Ground truth before LLM-as-Judge.** Human-calibrated golden datasets come first. Use LLM-as-Judge only to scale eval runs, not to create the evaluation standard. The judge's output quality is bounded by the rubric it's given.
- **Structured rubrics, not vibes.** A rubric should specify: what correct looks like, what partially-correct looks like, what failure looks like, and what edge cases are acceptable. Vague rubrics produce noisy, unreliable signals.
- **Multi-model cross-validation.** Run the same eval suite against Claude, GPT, and a smaller model. Divergence between judges is a signal — investigate it.
- **Sample-first, automate later.** Run 50-100 manual evals on real production inputs before building automated pipelines. This investment pays back in a rubric that actually matches your domain.
- **Regression test, not benchmark.** Treat evals as regression tests against known failure modes, not leaderboard scores. A passing eval means "this pattern no longer regresses," not "the agent is good."

### Trace architecture that serves evals

OpenTelemetry is the trace-layer standard. Extend Semantic Conventions with custom span attributes capturing: model, temperature, token counts, tool call schema version, and retrieved context IDs. These attributes feed directly into eval stratification — you need to segment "what went wrong" by model, context size, and tool chain to route fixes correctly.

Instrument: every LLM call, every tool call, every retrieval query, every handoff between agents. Do not selectively instrument.

### The eval cadence

- **Pre-commit:** run golden dataset evals on every code change touching the agent logic
- **Pre-deploy:** run full eval suite against staging environment
- **Continuous:** shadow eval (judge runs on production outputs in parallel, no blocking)
- **On-call:** eval regression alerts page the on-call engineer, not a dashboard

## Evidence

- **Blog post:** Agent Observability Engineering: 89% observability / 52% eval split; 5 failure modes covering 90% of agent failures; LLM-as-Judge requires structured rubrics and multi-model cross-validation — [QubitTool Tech Blog](https://qubittool.com/blog/agent-observability-engineering), 2026-05-21
- **Blog post:** Multi-Agent Architecture Patterns: 89% of teams have distributed tracing but only 52% have evaluation — this gap is why debugging multi-agent systems is "mostly guesswork" — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide), 2025-11-20
- **Blog post:** Why AI Agents Fail in Production: A 10-step agent at 85% per-step success achieves ~20% end-to-end reliability; the math compounds and most teams don't model it until the first incident — [Apptitude](https://apptitude.io/blog/why-ai-agents-fail-production-failure-modes), 2026-05-08

## Gotchas

- **Tracing without evals is theater.** You have data but no signal. A span tree showing every tool call is not an eval — it's raw material for one.
- **LLM-as-Judge without a rubric produces noise.** "Rate this answer 1-10" produces inconsistent scores. "Does the answer cite a source from the retrieved documents? Score 1 for yes, 0 for no, with this exception: [list]" produces actionable signal.
- **The five failure modes are a starting taxonomy, not a ceiling.** Domain-specific failure modes will emerge (e.g., in code agents: incorrect import resolution; in customer support: policy-conflicting refunds). Build them into the rubric as you discover them.
- **Eval coverage ≠ correctness.** A passing eval suite means "this set of known patterns works." It says nothing about unknown failure modes. Supplement with adversarial probing and chaos testing of agent tool chains.
