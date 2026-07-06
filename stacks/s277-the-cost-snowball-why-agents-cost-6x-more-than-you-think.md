# S-277 · The Cost Snowball — Why Agent Costs Are 6× What Raw API Pricing Predicts

Raw LLM pricing pages are practically useless for predicting production agent costs. A $2.50/M input-token model doesn't cost $2.50 per task — it might cost $1.10, or $8.00, depending entirely on your orchestration choices. The gap between advertised and actual cost comes from context accumulation, multi-turn reasoning, and tool-call overhead that standard API pricing models never show you.

## Forces

- **Token context grows at every step.** Each ReAct loop iteration re-passes the full conversation history, tool results, and intermediate outputs. By step 4 of a 4-step task, a 100-token user prompt has become 2,050 tokens of effective input — a 20× multiplier that's invisible on the pricing page.
- **Non-LLM costs can exceed LLM costs.** MCP tool calls, knowledge-base lookups, and external API fees added $0.30 to one team's $0.80 LLM spend — a 37% overrun nobody was tracking.
- **Multi-agent costs compound, not add.** A 4-agent orchestrator-worker workflow runs multiple LLM calls per step, each with its own context growth. Teams report $5–8 per complex task before they model the economics.
- **Retry loops and fallbacks are invisible budget killers.** A 20% retry rate doubles your LLM cost overnight with no alerting unless you've instrumented it.

## The move

Model cost from the bottom up, not from the pricing page:

1. **Track effective input tokens, not prompt tokens.** Sum the actual tokens sent to the model at each step — user prompt + conversation history + all tool outputs accumulated so far. This is your real input. The pricing page number is meaningless in isolation.
2. **Add a 5–8× multiplier for multi-step tasks.** A 4-step ReAct loop typically sends 5,500–22,000 effective input tokens per task, even when the user typed 100. Budget accordingly.
3. **Instrument non-LLM costs from day one.** MCP tool calls, database queries, email API fees, and embedding lookups can add 20–40% to LLM spend and often exceed it in data-heavy workflows. Use AgentMeter or custom traces to expose this.
4. **Use the five-tier cost model as a sanity check.** Tier 1 (simple chatbots) run $30–150/month. Tier 2 (tool-using agents) run $200–800/month. Tier 3 (RAG agents) run $500–2,500/month. Tier 4 (multi-agent) run $2,000–15,000/month. Tier 5 (complex orchestration) has no ceiling. If your spend doesn't match your tier, something is misconfigured.
5. **Multi-agent is cheaper per task for complex work, not more expensive.** Ivern benchmarks show 40–60% cost savings running multi-agent workflows for research and analysis tasks versus single-agent loops — because specialized agents make fewer reasoning steps and waste less context on irrelevant context.
6. **BYOK vs subscription economics are real.** Median BYOK user spend is $8/month versus $25/month for subscription tools. For teams running hundreds of agent tasks daily, bringing your own API keys cuts cost by 3–10×.

## Evidence

- **Blog — TokenFence (2026-03-21):** Multi-step agent context grows 6× between step 1 and step 4 in typical ReAct loops — "By step 4, the input has grown to 2,050 tokens for that single step alone. The total input for one 4-step task: 6,550 tokens." — [tokenfence.dev/blog/ai-agent-cost-benchmarks-2026-real-numbers](https://tokenfence.dev/blog/ai-agent-cost-benchmarks-2026-real-numbers)
- **Blog — AgentMeter (2026-03-23):** Real support ticket resolution cost $1.10 total — $0.80 in LLM calls and $0.30 in MCP tool calls and external API fees. "Non-LLM costs can represent 27%+ of total task cost." — [grislabs.com/blog/agentmeter/how-much-do-ai-agents-cost](https://www.grislabs.com/blog/agentmeter/how-much-do-ai-agents-cost)
- **Report — Ivern AI (2026-04-25):** 200-task benchmark across 6 providers. Multi-agent workflows cost $0.08–$1.20 per task depending on model and architecture. BYOK users averaged $8/month vs $25/month subscriptions (3× savings). Multi-agent saved 40–60% on complex research and blog tasks. — [ivern.ai/blog/ai-agent-cost-benchmark-report-2026](https://ivern.ai/blog/ai-agent-cost-benchmark-report-2026)

## Gotchas

- **Don't budget from the pricing page.** Multiply by 5–8× for multi-step tasks before committing to a cost model.
- **Don't ignore tool-call costs.** They can exceed LLM costs in data-heavy workflows and won't appear in your OpenAI/Anthropic billing.
- **Don't assume multi-agent = more expensive.** For complex tasks, specialized agents with tight scopes waste less context and cost less overall.
- **Don't skip retry budgets.** A 20% retry rate will double your invoice with no warning if you haven't instrumented it.
