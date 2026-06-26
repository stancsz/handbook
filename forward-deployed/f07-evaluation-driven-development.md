# F-07 · Evaluation-Driven Development

Wire evals into your dev loop so quality is a gate, not a guess. Where [F-02](f02-evaluation-at-scale.md) measures quality in production, this is the discipline of catching regressions *before* they ship.

## Forces
- A prompt or model change can silently degrade outputs that still look fine — no exception, no crash
- Manual QA on every change doesn't scale; teams either ship blind or stall
- LLM-as-judge is powerful but expensive — judging every call can dwarf the agent's own cost
- Final-output scoring misses *how* an agent failed when the trajectory was wrong but the answer looked right

## The move

- **Treat evals like tests.** Define what "good" means, encode it as reusable metrics, run them on every PR in CI, and gate merges on regression. Quality stops being a vibe.
- **Prefer code checks over judges where you can.** Deterministic checks (forbidden words, citation-required, schema-valid) are cheaper and exact — use them for anything with a binary answer. Reserve LLM-as-judge for fuzzy quality (accuracy, tone, helpfulness).
- **Make regressions traceable.** Tools like `deepeval` (plugs into pytest via `assert_test`) and Braintrust's `eval-action` (posts per-scorer improvements/regressions as PR comments) carry git metadata, so a quality drop traces to a commit.
- **Budget the eval cost.** One agent session is hundreds of LLM calls; judging each can 10× the workload. Sample a percentage of traces/spans — stratified, e.g. favor longer-running spans — instead of judging everything.
- **Judge the trajectory, not just the answer.** Agent-as-a-Judge evaluates the full reasoning path (tool calls, intermediate steps), catching failures output-only scoring misses.

## Receipt
> Tooling behavior (`deepeval` pytest integration, Braintrust `eval-action` PR comments, git-linked experiments) sourced from each project's documentation. The "eval cost can be ~10× the agent workload" figure is a reported practitioner account, not a measured constant — budget and measure your own. Agent-as-a-Judge reaching ~90% human alignment vs 60–70% for output-only LLM-as-judge is from ["When AIs Judge AIs"](https://arxiv.org/abs/2508.02994) (arXiv 2508.02994), validated on the DevAI benchmark (55 dev tasks). Sources verified 2026-06-25; not independently reproduced here.

## See also
[F-02](f02-evaluation-at-scale.md) · [F-03](f03-failure-modes.md) · [F-05](f05-agent-failure-taxonomy.md) · [W-05](../workspace/w05-llmops-observability.md) · [F-01](f01-shipping-ai.md)

## Go deeper
Keywords: `evaluation-driven development` · `LLM-as-judge` · `Agent-as-a-Judge` · `deepeval` · `Braintrust` · `eval in CI` · `regression gating` · `GEval` · `trajectory evaluation`
