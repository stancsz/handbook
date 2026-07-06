# S-666 · Agent Token Economics: Why Your $50/mo Chatbot Bills $2,800/mo as an Agent

[You have a RAG chatbot running cleanly at $50/month. Then you wrap it in an agent loop — plan, tool, observe, reflect — and the bill jumps 50x. Nobody warns you about this. The compounding is structural, not accidental, and it hits before you've written a single line of business logic.]

## Forces
- [Token growth is super-linear, not linear — each agent step resends the entire prior context, so costs compound faster than usage increases]
- [The reflex to route everything to the most capable model (Opus, o1) destroys economics when called 50+ times per task]
- [Fine-tuning locks you into one provider; routing is model-agnostic but requires a quality gate layer you have to build]
- [Embedding drift silently degrades retrieval quality over time, causing more agent loops to compensate — a cost spiral with no obvious spike]
- [Most teams don't track AI spend granularly: only 63% of enterprises monitor LLM cost at all, even as enterprise spend hit $8.4B in H1 2025]

## The move
Build token economics as a first-class engineering discipline from day one, not an afterthought when the bill arrives.

- **Multi-model routing as the default gate.** Route by task complexity: Haiku-class tasks (classification, extraction, simple rewrite) stay on fast/cheap models. Route up to Sonnet/Claude Haiku for reasoning tasks, Opus only for final synthesis. The break-even for building a routing layer is ~$200/month in LLM spend — below that, engineering time isn't worth it.
- **Context pruning between agent steps.** Don't resend full conversation history at every loop. Summarize or truncate prior context after each tool call. This is the single highest-leverage cost lever.
- **Quality gates before expensive calls.** Run a cheap model first to score output quality; escalate to expensive model only on low-confidence results. This alone can cut Opus calls by 60-70%.
- **Track per-agent, per-task token counts as KPIs.** Set token budgets per task type. When a task type consistently hits 80% of its budget, revisit the agent loop depth or routing.
- **Monitor embedding drift.** Track retrieval similarity scores over time. Silent degradation causes agents to loop more to compensate. Re-index on a schedule or when drift exceeds a threshold, not on a fixed calendar.
- **Latency and cost improve together with routing.** Smaller models respond in 200-400ms vs 2-4 seconds for Opus. Routing can improve average response time by 60% while cutting cost — the incentives align.

## Evidence
[Cross-referenced across production cost reports, framework comparisons, and enterprise evaluations]

- **Production case study (Vincent van Deth, Jan 2026):** 11 agents running at $2,847/month. Applied multi-model routing, quality gates, and context management — cost dropped to $370/month (87% reduction), 94% quality maintained. Routing alone cut average latency by 60% because most requests hit faster models. Break-even for routing infrastructure was ~$200/month in spend. — [https://vincentvandeth.nl/blog/real-cost-ai-agents-production](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Enterprise telemetry (AnhTu.dev, May 2026):** An agent run executes a plan → tool → observe → reflect loop, each step resending full prior context. For a task that would take one LLM call as a chatbot, the agentic version makes 12-50+ calls. Token consumption grows super-linearly, not linearly, with loop depth. — [https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257](https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257)
- **Enterprise adoption data (Islands HQ, Jan 2026):** AI infrastructure costs dropped 70% since 2020, but agentic loops compound so aggressively that absolute bills still grow. Only 63% of enterprises track AI spend at all. ~40% of enterprises now spend over $250K/year on LLM — yet most lack per-agent cost attribution. — [https://www.islandshq.xyz/blog/the-real-cost-of-production-ai-agents-infrastructure-apis-and-hidden-operational-expenses](https://www.islandshq.xyz/blog/the-real-cost-of-production-ai-agents-infrastructure-apis-and-hidden-operational-expenses)
- **Embedding drift (Digits AI in Production, 2025):** Teams that don't reindex RAG systems see gradual embedding quality degradation. "Silent embedding drift" goes unnoticed until it drives more agent retry loops, which shows up as a cost spike with no obvious cause. — [https://digits.com/blog/ai-in-production-2025](https://digits.com/blog/ai-in-production-2025)

## Gotchas
- [Routing logic is model-agnostic but the quality gate LLM costs are real — budget 5-10% of total spend for the gate itself]
- [Fine-tuning an agent's routing model sounds appealing but locks you into one provider and requires ongoing maintenance as use cases evolve; routing adapts instantly to new models or pricing]
- [Context truncation is lossy — aggressive pruning can remove the thread that the agent actually needed; test truncation strategies on real production traces, not synthetic scenarios]
- [The 87% cost reduction case required running 11 agents for months before the routing layer was built — the lesson is to design for it from the start, not retrofit it]
