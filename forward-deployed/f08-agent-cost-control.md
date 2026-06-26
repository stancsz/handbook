# F-08 · Agent Cost Control

Keeping a production agent's spend from spiraling. Where [F-07](f07-evaluation-driven-development.md) makes quality a gate, this makes cost one — the operational discipline of seeing, capping, and attributing what an agent costs.

## Forces
- An agent has no natural ceiling — priced per token, it can loop into millions of tokens in minutes with no cap to stop it
- The unit shifted: cost-per-token is falling, but agents burn 5–30× more tokens per task, so bills rise anyway
- The monthly invoice is a postmortem; by the time it arrives, the runaway already happened
- The token bill is only part of the cost — retrieval, orchestration, and idle infra are unmetered by it

## The move

- **Measure cost-per-completed-task, not cost-per-token.** Agents make 3–10× more LLM calls than a chatbot; an unconstrained coding task can burn $5–8 in API fees alone. Per-token is the wrong altitude — track what a finished task costs.
- **Instrument at runtime, not from the invoice.** Tag every call (customer, feature, environment), track per-task spend, and alert on anomalies live. You can't govern what you can't see — see [W-05](../workspace/w05-llmops-observability.md).
- **Cap hard at every layer.** Per-request, per-session, and per-day token/dollar limits with automatic termination, plus bounded retries, recursion depth, and tool calls per task ([S-19](../stacks/s19-agent-loop.md)). Without a cap there is no ceiling.
- **Pull the big levers in order.** Model routing first — route easy work to small models (~60% savings reported; defaulting every call to a frontier model is the largest controllable overspend). Then prompt caching ([S-08](../stacks/s08-prompt-caching.md)). Then trim context, which bloats silently as history grows ([S-13](../stacks/s13-context-engineering.md)).
- **Forecast the whole stack, and bring finance in early.** Tokens are one bucket; retrieval, orchestration, and idle GPU/infra are others the LLM bill never shows. Project cost before a deployment ships, not after the bill lands.

## Receipt
> The token-count multiplier (agentic workloads use ~5–30× more tokens per task) is Gartner (March 2026). Cost-overrun prevalence (92% of agentic-AI adopters see overruns; 71% lack cost visibility/control) is IDC. Blended token price fell ~67% YoY (≈$18.40→$6.07 per million tokens, Q1'25→Q1'26) while bills rose — reported from aggregated enterprise API data. Savings figures (model routing ~60%, prompt caching 45–80%, output priced ~4:1 over input) are consistent across 2026 FinOps/agent-cost writeups — directional, benchmark your own. Specific company "burned the annual budget" anecdotes circulating in 2026 are reported, not independently verified. Verified 2026-06-25.

## See also
[F-07](f07-evaluation-driven-development.md) · [S-06](../stacks/s06-model-routing.md) · [S-08](../stacks/s08-prompt-caching.md) · [S-19](../stacks/s19-agent-loop.md) · [W-05](../workspace/w05-llmops-observability.md)

## Go deeper
Keywords: `FinOps for AI` · `cost per task` · `token budget` · `spend caps` · `model routing` · `prompt caching` · `cost attribution` · `runaway agent` · `unit economics`
