# S-623 · Token Cost at Scale: The Hidden Scaling Law for Agentic Systems

The moment you ship an agent — not a chatbot, not a completion endpoint — cost stops being linear and starts being exponential. Single-turn token math falls apart the moment an agent loops, re-plans, or calls tools. Most teams discover this after a $3,400 incident.

## Forces

- **Token math is non-obvious** — a single chatbot response is 200–500 tokens. An agent task averages ~47,000 tokens. That's 70–230× more, not 2–3×.
- **Loops compound invisibly** — recursive retrieval, self-correction, and re-planning each add LLM turns. Without hard limits, cost grows with problem complexity, not problem size.
- **Multi-step workflows are the norm** — analyze → retrieve → generate → validate → refine. Each step is a separate LLM call. At scale, you pay for every step.
- **Enterprise spend is significant** — average AI operational cost hit $85,521/month per enterprise in 2025 (Zylos Research). Model API spend industry-wide doubled from $3.5B to $8.4B in under a year.
- **The recovery gap** — 60–85% of agent spend is recoverable through caching, routing, and budget controls. Teams that don't build these in from day one pay the full bill.

## The Move

Treat agent cost as a first-class architectural concern, not an afterthought.

- **Hard token budgets per agent, per session.** Every agent gets a max tokens limit enforced in the executor, not as a system prompt suggestion. A customer service agent that asked for "all product variations" burned $3,400 in 47 minutes because there was no budget guard at the execution layer.
- **Circuit breakers, not just guardrails.** Guardrails validate output. Circuit breakers halt execution. The runaway pattern — recursive tool calls feeding back into the retrieval → generate loop — requires execution-level intervention, not prompt-level warnings.
- **Route cheap tasks to cheap models.** Gemini 2.0 Flash Lite costs $0.08/M input tokens vs Claude Sonnet 4.6 at $3.00/M. Simple classification, routing, and formatting tasks don't need frontier models. Intelligent model routing is the single highest-leverage cost control.
- **Prompt caching for repeated agent workflows.** Agent workflows are often structurally identical across runs — same tool definitions, same system prompts, same retrieval schemas. Prompt caching eliminates re-transmission of static context, recovering significant spend on repetitive agent loops.
- **Stateful agents need stateful cost tracking.** Per-request cost attribution across a multi-step agent run requires instrumentation at the executor level. You cannot optimize what you cannot measure. Log token usage per tool call, per LLM turn, per session.
- **Partition state and scale Redis before the LLM.** At 100K requests/hour, the first bottleneck is not the model — it's checkpoint writes. A single Redis instance buckles at ~40K concurrent writes. Partition by `thread_id` from the start. The operational cost of sharded Redis is far less than the cost of a scaling crisis mid-deployment.
- **Build cost observability into the trace.** LangSmith, Phoenix, or custom dashboards should surface cost per run, tokens per step, and cost-per-user-segment. Batch cost anomalies — a session using 10× more tokens than p95 — trigger alerts, not just logs.

## Evidence

- **Dataku tracked 50 agentic tasks across Claude 3.5 Sonnet, GPT-4o, and Gemini 2.0 Flash.** Average agent task consumed ~47K tokens vs 200–500 for a simple chatbot Q&A. Research tasks hit 200K+ tokens. The multiplier comes from multi-step tool use and iterative refinement — not from longer outputs.
  — *[The Real Cost of AI Agents: Token Usage Analysis](https://dataku.ai/blog/real-cost-of-ai-agents-token-usage-50-tasks)* — dataku.ai, Feb 2025

- **Zylos Research documented production cost incidents.** Runaway agent loops cost anywhere from $15 in 10 minutes to $47,000 over 11 days. The same research found 60–85% of agent spend is recoverable through caching, routing, and budget enforcement — but most teams learn this only after the first incident.
  — *[AI Agent Cost Engineering — Production Token Economics](https://zylos.ai/en/research/2026-05-02-ai-agent-cost-engineering-token-economics/)* — Zylos Research, May 2026

- **A LangChain-based customer service agent entered a recursive loop** when a user asked about "all possible product variations." In 47 minutes, the agent consumed 2.3 million tokens — $3,400 — because there was no circuit breaker between the retrieval, generation, and refinement steps.
  — *[AI Agents Production 2025: How I Avoided $3.4K Mistakes](https://tolearn.blog/blog/ai-agents-production-guide)* — ToLearn Blog, Sep 2025

- **LangGraph production deployments hit the state layer first, not the LLM.** At 100K req/hr, a single Redis instance buckles at ~40K concurrent checkpoint writes. Partition by `thread_id` is required before LLM autoscaling. p95 end-to-end latency under 300ms is achievable with Redis-backed checkpointing and partitioned state.
  — *[LangGraph Multi-Agent Architecture: State Control at 100K Requests/Hour](https://markaicode.com/architecture/langgraph-multi-agent-architecture)* — Markaicode, Jul 2026

## Gotchas

- **Per-token pricing masks multi-turn cost.** $2.50/M for GPT-4o input sounds cheap. A 10-step agent at 5K tokens per step is $0.125/run. At 1M requests/month, that's $125,000 — invisible in per-token pricing until the bill arrives.
- **Context window limits don't cap cost.** Increasing context windows lets agents handle longer tasks, but they still consume tokens proportional to the full context on each LLM turn. A 200K-token context costs more per turn than a 32K one.
- **Rate limiting and cost caps are different things.** API providers limit requests/minute. They do not cap your dollar spend. A recursive loop inside rate limits still burns budget at full price.
- **Tool call overhead compounds.** Each tool call involves an LLM turn to decide which tool to call, plus the tool execution, plus processing the result back into context. A 5-tool agent does 5+ LLM turns per task, not 1.
