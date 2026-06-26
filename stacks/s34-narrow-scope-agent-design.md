# S-34 · Narrow-Scope Agent Design

Give one agent one job. Not one agent that *can* do one job — one agent *designed* to do only that job, with exactly the tools, context, and permissions that job requires and nothing else. The enterprise shift toward task-specific agents (up from ~5% to a projected ~40% of enterprise apps in 2026) is not a trend toward more automation — it is a correction away from the general assistant that tried to do everything and shipped reliably for nothing.

## Situation

Your agent works in testing but wanders in production. It has access to eight tools, a long system prompt that covers every case, and a model good enough to reason through all of them — but it still calls the wrong tool occasionally, costs 3× what you modeled, and fails in ways that are hard to audit. The problem is not the model. It is the surface.

## Forces

- Every tool in scope is a tool the model can call instead of the right one. Tool-selection error scales with surface area: more irrelevant tools visible = more off-by-one calls, regardless of model quality.
- Context tokens carry a multiplier at every topology level ([F-18](../forward-deployed/f18-architecture-sets-the-cost-floor.md)). An agent definition that is 4× wider pays 4× the context cost on every call — that cost is permanent, not a tuning variable.
- A narrow agent is easy to evaluate: one task class, one oracle, one failure mode. A wide agent produces diverse outputs that require diverse evals — the evaluation surface sprawls with the tool surface ([F-07](../forward-deployed/f07-evaluation-driven-development.md)).
- Permissions follow scope. A narrow agent that needs only read access cannot be coerced into a write — the blast radius of a compromise or a prompt-injection is bounded by what the agent can actually do ([F-13](../forward-deployed/f13-prompt-injection.md)).
- Narrow scope conflicts with the desire to ship one agent that handles everything. That desire is real — but the general assistant is hard to verify ([S-32](s32-verifiability-divider.md)), expensive to run, and brittle to failure modes you didn't test. It demos better than it ships.

## The move

**Scope the agent at the task boundary, not the capability boundary.** The question is not "what is this model capable of?" — it is "what does this specific job require?" Build the tool list, context, and system prompt from that answer and remove everything else. If another job needs different tools, it gets its own agent.

**Treat tool count as a cost and a risk.** Every additional tool widens the selection surface and inflates context. The default is one tool; the second tool needs a use-case that proves it. Five tools is a design smell unless five distinct actions genuinely occur within one task.

**Write the system prompt as a scope declaration, not a capability list.** "You are a price-lookup agent. Use `lookup_price` to answer every request. Do nothing else." is a better system prompt than "You are a helpful e-commerce assistant. Use the right tool for each request." — because it leaves no ambiguity about what is in scope and what is not.

**Compose narrow agents at the orchestration layer, not inside each agent.** When a task genuinely needs three capabilities, build three narrow agents and a thin orchestrator — not one wide agent that does all three. The orchestrator's job is routing; each specialist's job is execution ([S-05](s05-multi-agent-patterns.md)).

**Derive permissions from scope.** Least-privilege is scope applied to access control. An agent that only reads prices should have a read-only API key. An agent that only sends emails should have no access to inventory. Scope-first design makes least-privilege the natural outcome, not a retrofit ([F-10](../forward-deployed/f10-agent-identity-and-access.md)).

## Receipt

> Verified 2026-06-26 — Node, `gpt-tokenizer` (cl100k; approximate for Claude within ~10–20%). Tool-selection error model: empirical literature range of ~2% per irrelevant tool exposed (7–15% at N=5); 2% per tool is a conservative floor — used as the multiplier. The "same task" framing isolates scope as the only variable.

```
Same task: look up current price of SKU-A44

Configuration          ctx_tokens  extra_tools  est_selection_error
Narrow (1 tool)                66            0  0%
Wide   (6 tools)              270            5  10%

Context blowup:  4.09x  (204 extra tokens every call)
Error-rate gap: +10pp from unnecessary tool surface
```

**What the receipt shows:**

- The wide agent's context is **4.09×** the narrow agent's — not because the task changed, but because scope changed. At production call volumes, that multiplier is a permanent tax on the cost floor.
- Exposing 5 irrelevant tools adds an estimated **10 percentage-point** selection-error rate for the same query. Neither extra context nor a better model eliminates this: the selection ambiguity is structural, not model-quality-limited.
- The narrow agent's selection error is zero by construction — there is only one tool to call. Verifiability ([S-32](s32-verifiability-divider.md)) is a consequence of scope: one tool, one oracle, zero ambiguity about what a correct call looks like.

The lesson: a general agent with many tools is not more powerful than a narrow agent at the narrow task — it is more expensive and less reliable at it. Generality earns its cost only at tasks that genuinely span all the tools.

## See also

[S-23](s23-workflows-vs-agents.md) · [S-05](s05-multi-agent-patterns.md) · [S-32](s32-verifiability-divider.md) · [F-18](../forward-deployed/f18-architecture-sets-the-cost-floor.md) · [F-10](../forward-deployed/f10-agent-identity-and-access.md)

## Go deeper

Keywords: `task-specific agent` · `narrow scope` · `tool surface` · `selection error` · `least privilege` · `specialist agent` · `agent composition` · `single-responsibility` · `enterprise agent` · `scope declaration`
