# S-229 · Iteration Budgets — The Loop Control Pattern `max_iterations` Gets Wrong

Setting a hard `max_iterations` cap is the obvious first move. It is also the wrong one. Teams that rely on it discover that agents hit the cap mid-work, fail silently, and return incomplete results with no signal that they ran out of runway. The real pattern is a layered budget system: hard dollar caps, soft iteration counts, and forced reasoning checkpoints that prevent wasted iterations before they happen.

## Forces

- **Agents consume tokens on the way out, not just on the way in** — a failing loop bloats context with repeated error messages, tool results, and apologies until you've spent $3 on a single task
- **`max_iterations` is a blunt instrument** — it stops the loop but provides no early warning, no graceful degradation, and no signal to the caller that the task is incomplete
- **The cost of a wasted iteration compounds** — each iteration re-sends full context; the marginal cost isn't flat, it's escalating as the context window fills
- **Silent failures are worse than expensive ones** — a capped-out agent returning partial work is harder to debug than one that loudly times out or budgets out
- **Iteration count ≠ progress** — a model can loop 10 times without improving; counting iterations doesn't measure whether the agent is converging

## The move

Layer three controls, not one:

- **Hard dollar cap per session** — set an absolute spend limit tied to a session ID (`x-litellm-trace-id`). This is the circuit breaker. When the cap hits, the session terminates and the caller gets an explicit error. LiteLLM implements this as `max_budget_per_session`. A $0.50 cap on a code-fix task means you never wake up to a $200 bill.
- **Soft iteration warning** — trigger a budget-pressure signal to the model at 60-70% of the iteration limit, not at 100%. The model can then self-correct: simplify its approach, escalate to a fallback, or return what it has. Hermes Agent's "Iteration Budget Pressure" feature (GitHub issue #414) surfaces this as an explicit LLM-level warning before the hard stop.
- **Pre-mortem reasoning checkpoint** — before each iteration, require the agent to articulate in a scratchpad: what it observed, what it believes the root cause is, and why the next action addresses the root cause rather than the symptom. If the reasoning doesn't align with available evidence (stack trace, tool output), block the solution generation. This cuts loop iterations per fix from ~8 to ~2 in benchmarks, and cost per fix from $2+ to $0.18.
- **Context truncation over hard caps** — when context approaches 80% utilization, compress conversation history rather than letting it grow to the limit. Active context is worth more than history.
- **Typed escalation paths** — define explicit fallback behaviors for different budget-exceeded scenarios: retry with a simpler model, return a partial result with confidence score, or hand off to a human.

## Evidence

- **Reddit r/LocalLLaMA:** Practitioners report `max_iterations` as the common naive approach; production teams move to session-scoped dollar caps and monitoring dashboards. The top answer pattern: combine hard caps with per-turn cost estimates projected before the turn executes. — [reddit.com/r/LocalLLaMA/comments/1r41h6v](https://www.reddit.com/r/LocalLLaMA/comments/1r41h6v/)
- **Reddit r/ClaudeAI:** A developer benchmarked a "Pre-Mortem" workflow — forcing the model to prove root cause in a scratchpad before code generation — and achieved an 11x cost reduction per fix ($2+ → $0.18) with Sonnet 3.5, while also reducing average iterations from ~8 to ~2. — [reddit.com/r/ClaudeAI/comments/1qax78h](https://www.reddit.com/r/ClaudeAI/comments/1qax78h/agentic_loops_were_costing_me_2_per_fix_just/)
- **LiteLLM docs:** LiteLLM's iteration budget system implements two independent controls: `max_iterations` (hard call count cap) and `max_budget_per_session` (dollar cap per session, tracked via `x-litellm-trace-id`). Both require a session ID to track calls within a session. Dollar caps are recommended over iteration counts because token cost varies by model and context size. — [docs.litellm.ai/docs/a2a_iteration_budgets](https://docs.litellm.ai/docs/a2a_iteration_budgets)

## Gotchas

- **Dollar caps require per-session IDs** — without `session_id` / `x-litellm-trace-id`, LiteLLM cannot track spend per logical conversation, making dollar caps ineffective across concurrent sessions
- **Hard iteration caps cause silent partial failures** — the agent stops, returns whatever state it had, and the caller has no way to distinguish "task complete" from "task aborted at iteration 10"
- **Iteration counts don't account for context size** — 5 iterations with a 180K-token context costs far more than 20 iterations with a 4K context; raw iteration counts are a poor proxy for cost
- **Self-healing loops are real** — some agent patterns genuinely need 15-20 attempts to converge on a correct solution (e.g., complex code修复); a hard cap of 10 destroys correctness on legitimate multi-step tasks; the soft warning at 60-70% gives the model a chance to either succeed or self-escalate before the hard stop
- **Budget pressure signals need LLM support** — the Hermes Agent approach of warning the LLM itself before the cap is hit only works if the model's system prompt can process and respond to that signal; not all models handle mid-loop instruction injection gracefully
