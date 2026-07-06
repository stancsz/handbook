# S-458 · Agentic Cost Multiplication: The Loop Tax Nobody Prices

Token pricing looks cheap until your agent loops. The gap between per-token API cost and real production spend is 5–50×, driven by iterative execution, context window inflation across multi-agent handoffs, and retry compounding. Most teams discover this when the bill arrives — not during architecture planning.

## Forces

- **Agentic loops dwarf single-shot calls.** A chatbot response consumes 200–500 tokens. A single agent task with tool use averages 47,000 tokens (70–230× more) — and that's the average. Long-running tasks regularly hit 200,000+ tokens.
- **Output tokens are the hidden multiplier.** Output tokens cost 3–5× more than input tokens across every major provider. Agentic systems are output-heavy: each reasoning step, tool result, and synthesis pass burns output tokens.
- **Multi-agent handoffs compound context.** Passing full conversation history between agents — the naive approach — multiplies token cost by the number of handoffs. Three agents in sequence means the downstream agent gets billed for all upstream context on every call.
- **Tiered model routing pays for itself but requires instrumentation.** 70–80% of agent workloads can run on budget/mid-tier models, but most teams don't instrument cost-per-step visibility so they can't route intelligently.
- **The pilot-to-production cost cliff.** Teams routinely see $500/month in development scale to $50,000/month in production — not because the model changed, but because users hit real-world retry loops, longer conversations, and higher concurrency.

## The Move

**Instrument cost at the step level, not the request level.** Every agentic system needs cost tracking per tool-call, per handoff, and per session — not just per API call.

- **Budget context from day one.** Set per-task token budgets (e.g., 15,000 tokens max). When the agent approaches the limit, route to a cheaper model or surface a human decision. This alone prevents runaway costs from infinite loops.
- **Route models by task complexity, not global policy.** Use o3-mini or Gemini Flash for extraction and classification (sub-$0.01 per task). Reserve Sonnet/Claude 3.7 for synthesis and reasoning. Teams using intelligent tiered routing report 60–75% cost savings versus single-model deployments.
- **Prune context before handoffs.** Don't pass full conversation history between agents. Use summarization or selective memory retrieval to send only task-relevant context. This cuts downstream token costs per handoff dramatically.
- **Implement circuit breakers on loops.** Track how many tool-call iterations occur within a single task. Set hard limits (5–10 iterations) with explicit escalation paths. This prevents the most expensive failure mode: an agent looping indefinitely.
- **Capture cost-per-completed-task, not per-token.** The metric that matters is outcome cost: how much did it cost to fully resolve one customer query, generate one report, complete one code review? This unblocks real optimization decisions that per-token reporting obscures.

## Evidence

- **Real-world token tracking:** One developer tracked 50 agentic tasks across Claude 3.5 Sonnet, GPT-4o, and Gemini 2.0 Flash, logging every token consumed. Average task consumed 47,000 tokens. Code generation + testing hit 67,300 tokens per task. Single-shot chatbot responses are 200–500 tokens. — [dataku.ai — "The real cost of AI agents: I tracked token usage for 50 agentic tasks"](https://dataku.ai/blog/real-cost-of-ai-agents-token-usage-50-tasks)
- **Input pricing collapse, output remains:** Input token costs dropped 85% since GPT-4 launch ($30/M tokens in mid-2023 → under $3/M in Q1 2026). Output tokens remain 3–5× more expensive than inputs across all providers. Output-heavy agent patterns are the primary cost driver. — [Digital Applied — "LLM API Pricing Index: AI Agent Deployment Costs Guide"](https://www.digitalapplied.com/blog/llm-api-pricing-index-cost-tracker-ai-agent-deployments)
- **The pilot cliff:** Approximately 7 in 10 GenAI projects failed to reach production in 2025. Cost explosion was a primary cause: teams saw costs jump from $500/month in dev/test to $50,000/month in production. Root causes included undefined retry policies, unbounded session lengths, and lack of per-task budgets. — [dataa.dev — "From AI Pilots to Production Reality: Architecture Lessons from 2025"](https://www.dataa.dev/2026/01/01/from-ai-pilots-to-production-reality-architecture-lessons-from-2025-and-what-2026-demands)
- **Tiered routing savings:** Teams implementing intelligent model routing (budget models for 70–80% of tasks, frontier models only for complex synthesis) report 60–75% cost savings. Budget-tier models handle extraction, classification, and routine tool calls adequately at a fraction of frontier pricing. — [Digital Applied — "LLM API Pricing Index"](https://www.digitalapplied.com/blog/llm-api-pricing-index-cost-tracker-ai-agent-deployments)

## Gotchas

- **Per-token pricing is a lie.** The "5-cent task" becomes $1–3 once you include retries, context passes, and operator time. Price the outcome, not the API call.
- **AutoGen generates more LLM calls than CrewAI or LangGraph.** Measured at 12.3 average calls per task versus 4.2 (LangGraph) and 6.1 (CrewAI). More calls means more output tokens, more latency, and higher cost.
- **Context summarization at handoff has quality risk.** Summarizing context before passing between agents can lose critical details. Test that downstream agents produce the same quality of output with summarized versus full context — it's not always safe to prune.
- **The retry loop is the cost killer.** Every retry doubles token consumption for that step. Without circuit breakers, a flaky tool integration or slow API response can multiply a $0.10 step into a $5.00 failure.
