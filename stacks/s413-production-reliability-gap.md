# S-413 · The Test-Production Reliability Gap

Agent demos lie. The gap between a controlled evaluation and live production is not a tuning problem — it is an architectural problem that most teams discover only after shipping.

## Forces

- **Demo environments are unnaturally clean.** Test queries are curated, inputs are valid, tools return well-formed data, and context windows never overflow. Production is none of these things.
- **Success rate in testing does not transfer.** Calder's Lab tracked a real production system: 92% test success, 55% production success — a 37-point collapse. The system was not broken; the environment was different.
- **Token costs compound under failure.** When an agent fails mid-task, it retries, re-chains, and stuffs context with accumulated history. The $200/month budget became $847/month at the same task volume.
- **Measurement is the exception, not the norm.** Cleanlab's survey of 1,837 engineering teams found only 5% had agents live in production — and fewer than 1 in 3 of those teams were satisfied with their observability. Most are flying blind.

## The move

Build the production failure mode before the success mode.

- **Instrument before you optimize.** LangSmith, Phoenix, or even structured JSON logs — measure what actually breaks in a two-week production window before tuning for high success rates. You will find different failure modes than your tests predicted.
- **Design for graceful degradation, not peak reliability.** An agent that degrades predictably (returns a partial answer, calls a human, fails loudly with structured error) is worth more than one that silently succeeds 92% then collapses on 8% unseen inputs.
- **Budget for failure compounding.** Every retry doubles token cost. Every context overflow doubles it again. Model the worst-case token-per-task ratio, not the median.
- **Stratify your stack so failures are contained.** Sandboxed tool execution (E2B, Modal, Firecracker microVMs) means a bad tool call doesn't corrupt agent state. The orchestration layer, tool layer, and memory layer should each fail independently.
- **Rehearse the edge cases that demo queries never surface.** Empty database rows, malformed API responses, rate limit errors, session timeouts. If your agent cannot handle them, neither can your success rate.
- **Track production success rate as a primary metric, not a derived one.** Set an explicit reliability target before you ship. 85%? 95%? That target shapes your entire architecture — from how many agents you run to how you handle tool failures.

## Evidence

- **Engineering blog:** MeetSpot's production agent cost jumped from $200/month (budgeted) to $847/month (actual) while success rate dropped from 92% to 55% — driven by retries, context stuffing, and 47 distinct data format issues in production that never appeared in testing. — [Calder's Lab](https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/)
- **Enterprise survey:** Of 1,837 engineering and AI leaders surveyed, only 95 had AI agents live in production. Of those, fewer than 1 in 3 were satisfied with observability and guardrail coverage. 70% of regulated enterprises rebuild their agent stack every 3 months or faster. — [Cleanlab / MIT State of AI](https://cleanlab.ai/ai-agents-in-production-2025/)
- **Sandbox isolation:** The V8 dispatcher reduced per-dispatch overhead from ~1,500 tokens (template compilation) to ~200 tokens (native skill activation) — nearly eliminating orchestration layer cost — by separating execution sandbox from orchestration logic. — [Vincent van Deth](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)

## Gotchas

- **Tuning your prompts based on test results makes production worse.** Each prompt change that boosts test performance is optimizing for a distribution you won't see in production. You are fitting to the wrong set.
- **"It worked in the demo" is a project-killing sentence.** If you cannot articulate the production failure modes your agent is designed to survive, it is not ready to ship.
- **Cost observability lags reliability observability.** Most teams track success rate but not token-per-task cost. The two are correlated — high-failure agents cost 4-5x more per successful task due to retry compounding.
