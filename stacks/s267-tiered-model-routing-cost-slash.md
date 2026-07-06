# S-267 · Tiered Model Routing — The Cost Architecture That Pays the Bill

You don't need GPT-4o for every step. Most agent tasks are mundane: classify an email, extract a date, format a string, route a request. But teams slap a frontier model on every node and wonder why a single autonomous task burns $100/day. The fix is routing — and it's now a first-class architectural concern, not a cost-cutting afterthought.

## Forces

- **Output tokens cost 3–6× more than input tokens.** A reasoning chain that generates 500 output tokens costs as much as 2,000 input tokens. This asymmetry means cheap models win for tool-calling loops, even if they lose on reasoning.
- **80% of agent calls don't need a frontier model.** Production teams consistently find that bulk tasks (classification, extraction, formatting, routing) hit 95%+ accuracy on Haiku or GPT-4o-mini — at 10–20× lower cost.
- **Context caching changes the math.** Claude's cache reads are 4× cheaper than standard reads ($0.30 vs $1.25/M tokens for Sonnet). GPT-4o cache reads are 10× cheaper ($0.25 vs $2.50/M). If you're re-sending the same system prompt or document across calls, caching can halve your bill without touching the model choice.
- **Task complexity is predictable.** The "hard" parts of an agent workflow — planning, error recovery, synthesis — cluster in specific nodes. Everything else is pattern-matching at its core.

## The move

Route by task complexity, not by global budget. A three-tier hierarchy typically covers production workloads:

- **Tier 1 — Haiku / GPT-4o-mini / Gemini Flash:** Classification, extraction, routing, formatting, tool selection, simple tool execution. These handle 70–80% of calls.
- **Tier 2 — Sonnet / GPT-4o / Gemini Pro:** Reasoning chains, error recovery, multi-step synthesis, document analysis, persona-bearing responses.
- **Tier 3 — Opus / GPT-4.5 / o3:** Complex planning, adversarial safety checks, novel problem-solving, quality gate decisions that require high-fidelity reasoning.

Implement routing with a classifier node that runs on the cheapest model — it reads the current state and emits a tier label, which gates which model gets called next. Keep the classifier simple: rule-based if possible, a single Haiku call if not.

**Cache aggressively.** For agents with large system prompts, long documents, or repeated context, cache reads reduce input costs by 4–10×. Budget the cache invalidation logic: stale context is the failure mode.

**Route on outcome quality, not capability.** If Haiku hits 97% accuracy on your classification task in production, it stays at Tier 1. If it drops to 80% on a specific intent type, that intent type escalates. Measure, don't assume.

## Evidence

- **Paxrel reduced agent costs from ~$90/month to ~$3/month** by routing 80% of calls to smaller models, reserving frontier models only for complex reasoning chains. The key insight: "80% of those calls don't need a frontier model." — [Paxrel Blog, AI Agent Cost Optimization 2026](https://paxrel.com/blog-ai-agent-cost-optimization)
- **TokenFence's 2026 cost analysis** shows Claude Haiku 3.5 at $0.80/M input vs Claude Sonnet 4 at $3.00/M — a 3.75× input cost difference. For a classification task that uses 500 input tokens, this is $0.0004 vs $0.0015 per call. Scale to 10,000 calls/day and that's $4/day vs $15/day on input tokens alone.
- **Claude cache reads are 4× cheaper** than standard reads ($0.30 vs $1.25/M for Sonnet). GPT-4o cache reads are 10× cheaper ($0.25 vs $2.50/M). For agents re-sending the same system prompt or document across calls, this is a "free" optimization. — [TokenFence, Claude vs GPT-4o Cost Comparison 2026](https://tokenfence.dev/blog/claude-vs-gpt4o-cost-comparison-ai-agents-2026)
- **LangGraph, CrewAI, and AutoGen all support model swapping at the call level**, making tiered routing a drop-in pattern. CrewAI's role-based architecture makes it particularly natural — assign the "router" agent a cheap model and the "reasoner" a frontier one. — [ExamCert, LangGraph vs CrewAI vs AutoGen 2026](https://www.examcert.app/blog/langgraph-vs-crewai-vs-autogen-agent-frameworks-2026)

## Gotchas

- **Don't route without measuring.** The tier boundaries are task-specific. What works for text extraction may fail for intent classification. Build a small eval set per task type and gate on accuracy, not on guesswork.
- **Tool-calling consistency varies by model.** Haiku and GPT-4o-mini have strong tool-calling APIs, but some open-source models degrade significantly on structured tool use. Test the full call loop, not just the text output.
- **Cache invalidation is an unsolved ops problem.** Stale context in memory systems can propagate incorrect information across sessions. When you cache aggressively, build explicit TTL logic or version-gated invalidation.
- **Human-in-the-loop steps break the cost model.** If a human reviews every Tier 3 output, the cost of the human dwarfs the LLM cost. Tier 3 is only worth it for fully autonomous workflows.
- **Output token costs are still frontier-model-dominated.** GPT-4o outputs at $10/M vs $0.60/M for GPT-4o-mini. If your agent generates long reasoning traces or tool-result summaries, output tokens can dominate even with input-side routing wins. Profile your actual token split.
