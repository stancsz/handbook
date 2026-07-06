# S-411 · Production Agent Cost Architecture

The 5-line demo and the production agent are not the same product — and the gap between them has a price tag. When agents chain, retry, and compound context across long-horizon tasks, costs explode in ways that aren't obvious from any single API call.

## Forces

- **Agent costs compound non-linearly.** A single call isn't expensive. But agents retry, chain into downstream calls, stuff context windows with conversation history, and call tools that generate their own token streams. One production team reported 180K tokens per blog post — not from output length, but from reasoning chains, tool call loops, and quality validation.
- **Tracking is an afterthought.** The FinOps Foundation found that AI spending doubled in enterprise environments in 2025, yet only 63% of organizations actively track their AI spend. The rest are flying blind.
- **Architectural decisions are cost decisions.** Context window size, orchestration model, retry policies, memory tiering — every design choice maps directly to a line item on the API bill.
- **87% of cost is invisible until you measure it.** Token overhead from orchestration layers, redundant tool calls, and context stuffing are the biggest culprits — not the model prices themselves.

## The Move

Production cost discipline for agents requires three layered interventions:

- **Token budget model routing.** Route simple queries to smaller/faster models. Assign task complexity classifiers upstream. A single-layer routing decision — "is this a lookup or a reasoning task?" — can move 50%+ of traffic to cheaper models without quality degradation.
- **Context summarization and eviction.** Summarize older conversation turns instead of passing full history. Implement hard context limits with aggressive compression. The V8 dispatcher pattern reduces per-dispatch overhead from ~1,500 tokens (template compilation) to ~200 tokens (native skill activation).
- **Multi-level cost gates.** Stack semantic caching (deflects ~30% of queries entirely), model routing (handles another ~50% on cheaper models), prefix caching (reduces remaining per-request cost), and batch scheduling (captures async workloads at ~50% discount). Each layer composes to 80%+ reduction from baseline.
- **Agent-side budget awareness.** Agents that observe and reason about their own resource consumption — early task completion when budget is constrained, cheaper tool preference — reduce cost structurally rather than reactively.
- **Hard circuit breakers on token spend.** Set per-task token budgets with explicit fail-closed behavior. A single runaway agent loop has burned thousands of dollars in hours.

## Evidence

- **Personal production report:** One AI architect running 11 agents in production saw a December 2025 bill of $2,847/month. After three months of layered optimization — routing, caching, summarization, prefix caching — the same workload ran for $370/month. An 87% reduction, same outputs. — [Vincent van Deth, AI Architect](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Enterprise telemetry:** FinOps Foundation reported AI spending doubled in enterprise environments in 2025. Enterprise LLM spending hit $8.4 billion in H1 2025 alone. Near 40% of enterprises now spend over $250,000 annually on language models. — [FinOps Foundation via Vincent van Deth](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Compound cost mechanism:** A content generation agent was burning 180K tokens per blog post. The bloat came from reasoning chains, tool call loops, and quality validation — not the output. Token overhead from the orchestration layer (V7 template compilation) was ~1,500 tokens per dispatch vs ~200 tokens with the V8 native dispatcher. — [Vincent van Deth](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Orchestration framework costs:** HN discussion on multi-agent orchestration surfaced that "naive approaches are stateless" and pass entire conversation threads as context — a pattern that scales poorly and costs exponentially. Recommended pattern: treat only the most recent task-relevant context as the active window. — [Hacker News: Ask HN on multi-agent orchestration](https://news.ycombinator.com/item?id=47660705)

## Gotchas

- **Don't optimize before measuring.** The biggest cost sources are usually invisible (orchestration overhead, redundant context stuffing) — instrument first with per-call token tracking before redesigning anything.
- **Hard token limits are cheaper than LLM-powered fallback logic.** Adding "smart" fallback behavior to handle context overflows often costs more than the overflow itself. Prefer hard cuts.
- **Model routing quality thresholds drift.** What routes cleanly today may degrade as models are updated. Build automated quality regression checks into the routing layer, not just cost controls.
- **Caching works for retrieval, not for generation.** Semantic caching deflects repeated queries but doesn't help unique reasoning chains — the highest-cost agent behaviors are also the least cacheable.
