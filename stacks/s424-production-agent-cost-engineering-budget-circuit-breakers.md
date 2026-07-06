# S-424 · Production Agent Cost Engineering — Budget Circuit Breakers and the Runaway Loop Problem

Your agent's first production incident won't be a bad output. It'll be a number on your invoice. Two LangChain agents at an unnamed company entered an infinite conversation loop for eleven days — nobody caught it, nobody had limits. The bill: $47,000. The pipeline was budgeted at under $200/month. The problem isn't your model. It's that you shipped autonomous agents with a cost model built for a chatbot.

## Forces

- **LLMs are stateless loops** — unlike deterministic code, a language model doesn't inherently know when to stop; given a tool, it will keep calling it until told otherwise
- **Cost compounds with autonomy** — the shift from "LLM as chat tool" to "LLM as autonomous agent" fundamentally changes token economics; what cost $0.01/chat in a demo can cost $500/day in production
- **Budget enforcement is an afterthought** — most teams build agents first and add cost controls weeks later, after they've already burned money
- **Prompt context grows unbounded** — multi-step tool chains, memory retrieval, and conversation history all pile into context windows, multiplying token costs quadratically
- **Rate limits intersect badly with cost spikes** — a retry loop on a rate-limited API can trigger exponential backoff that, across multiple agents, creates a token multiplier effect

## The Move

Treat cost as a first-class infrastructure concern from day one, not a post-incident patch.

**Hard budget enforcement via API gateway:**
- Route all agent LLM calls through a proxy (e.g., a pre-funded API key with a hard spend limit) rather than direct API calls
- Every agent gets its own spend key scoped to its workflow — a runaway loop can only burn what you've pre-loaded
- This is a physical constraint, not a prompt instruction: the agent literally cannot exceed the budget

**Prompt caching as the default optimization:**
- Anthropic's cached prompts (by reference) can reduce repeated-context costs by 60–85% on workflows with fixed system prompts and stable tool schemas
- Cache the system prompt, tool definitions, and any static retrieved context between agent steps
- Cache invalidation on tool schema updates only

**Tiered model routing:**
- Route deterministic, tool-calling steps (format validation, routing decisions, simple retrieval) to Haiku-class models ($1/M input tokens)
- Reserve Opus/Sonnet/GPT-4o for reasoning, synthesis, and complex decisions
- The orchestrator-worker pattern — one smart orchestrator decomposing tasks and delegating to cheap workers — yields 40–60% cost savings (beam.ai, 2026)
- Implement routing via a model selection layer that evaluates request complexity before routing, not via post-hoc fallback

**Per-step token budgets and circuit breakers:**
- Set a hard max tokens per step (e.g., 2,048 output tokens for a tool call result), with a circuit breaker that halts and escalates on overflow
- Implement max-turn limits on agent loops: hard stop after N consecutive tool calls without a final answer
- Exponential backoff on rate limits with jitter — but cap the total retries to prevent runaway retry multiplication

**Observability layer for spend:**
- Log every agent turn with: input tokens, output tokens, model, cost at that step, cumulative session cost
- Alert thresholds: warn at 50% of budget, halt at 90%
- Dashboards showing cost over time per agent, per workflow, per user

## Evidence

- **InfoWorld / engineering analysis:** One company's two LangChain agents ran an unmonitored conversation loop for 11 days, generating $47,000 in inference costs from a pipeline budgeted at under $200/month. Root cause: no hard budget enforcement, no turn-count circuit breaker. — [The Real Cost of Agentic AI — InfoWorld](https://www.infoworld.com/article/4181397/the-real-cost-of-agentic-ai.html)
- **Zylos Research / cost engineering analysis:** Production AI spend doubled from $3.5B to $8.4B (late 2024 → mid-2025); enterprises now average $85,521/month in AI operational costs (2025); 60–85% of that spend is recoverable through prompt caching, model routing, and hard budget enforcement; runaway loops documented at $15 in 10 minutes to $47,000 over 11 days. — [AI Agent Cost Engineering — Production Token Economics — Zylos Research](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/)
- **Beam.ai / orchestration patterns analysis:** The orchestrator-worker pattern — a smart orchestrator decomposing and delegating to cheaper, task-specific workers — yields 40–60% cost savings compared to routing everything through a single powerful model; 40% of multi-agent pilots fail within six months, often due to ungoverned cost escalation. — [6 Multi-Agent Orchestration Patterns for Production (2026) — Beam.ai](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)

## Gotchas

- **Pre-funded spend keys with hard limits are not the same as usage alerts.** An alert tells you the bill is high after the fact; a hard limit physically prevents the agent from calling the API past the cap. Use the former for monitoring, the latter for protection.
- **Cache invalidation is non-obvious in agentic workflows.** If your tool schema or system prompt changes mid-session, stale cached context can cause subtle wrong outputs that are worse than the cache miss. Version your cached artifacts and bust on schema change.
- **Context accumulation between steps is the hidden cost multiplier.** Each tool call result gets added to the next context window. A 10-step chain with 512-token tool results grows context by 5K tokens on every iteration. Use selective context pruning or truncation, not unbounded growth.
- **Max-turn limits must account for legitimate multi-step workflows.** A hard stop at 10 turns will kill a 12-step legal document analysis. Set turn limits per task type and have a tiered escalation: warn → escalate to human → halt.
- **Model routing based on output fallback is too late.** If you route to a cheap model and it fails, you've already burned tokens on the cheap call plus the fallback call. Route on input complexity analysis before the first call, not on output quality after.
