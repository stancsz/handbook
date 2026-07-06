# S-339 · Agent Cost Engineering: The Production Reckoning

Every team that takes an agent from prototype to production hits the same wall: the costs are 5–15× higher than the POC suggested. Token spend, infrastructure, observability, and runaway loops compound fast. Production teams are converging on a disciplined cost-engineering stack — and the teams that skip it are paying for it in incidents.

## Forces

- **Prototype costs are fiction.** POC environments lack retry logic, observability, budget circuit breakers, and the multi-turn loops that production traffic demands.
- **60–85% of AI spend is recoverable** through prompt caching, model routing, and hard budget enforcement — but most teams discover this only after their first runaway agent incident.
- **Runaway loops are the #1 cost killer.** Loops have cost teams from $15 in 10 minutes to $47,000 over 11 days — and they're entirely preventable with the right guards.
- **Stack stratification is changing where money flows.** Specialized layers (sandboxing, routing, caching) now warrant dedicated budget lines, not afterthought engineering.

## The Move

A three-layer cost engineering stack that gates runaway spend before it becomes an incident:

- **Layer 1 — Budget circuit breakers.** Hard per-session and per-day cost caps at the orchestration layer. Set them before launch, not after. Token budgets on the LLM API are a blunt instrument; implement application-level limits that kill the loop at a defined spend threshold.
- **Layer 2 — Intelligent model routing.** Route simple tasks (intent classification, routing decisions, low-stakes lookups) to Haiku-class models at ~$1–3/M tokens. Reserve Opus/Sonnet for complex reasoning. Model tiering alone typically recovers 30–40% of spend. The routing agent itself should be a fast, cheap model.
- **Layer 3 — Prompt caching + semantic caching.** Persistent conversation context (system prompts, tool schemas, domain knowledge) should be cached at the protocol level. Re-running the same embedding queries across similar intents is wasted spend. Cache at the semantic level, not just the token level.

## Evidence

- **Survey:** Enterprise average AI operational costs reached $85,521/month in 2025, with 60–85% of spend identified as recoverable through caching, routing, and budget enforcement. — Zylos Research, "AI Agent Cost Engineering — Production Token Economics," 2026-05-02 — https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics
- **Incident data:** Runaway agent loops have caused documented costs ranging from $15 in 10 minutes to $47,000 over 11 days. Teams without circuit breakers treat these as acceptable risk. — Zylos Research, "AI Agent Cost Engineering," 2026
- **Survey:** Token and API costs represent 30–50% of total agent production cost; compute infrastructure adds 20–35%; observability adds 10–20%; hidden costs account for 15–25%. Prototype costs are consistently 5–15× lower than production reality. — Xcapit, "The Real Cost of Running AI Agents in Production," Antonella Perrone (COO), 2025-11-04 — https://www.xcapit.com/en/blog/real-cost-ai-agents-production
- **Blog:** Shopify Sidekick's architecture evolution illustrates how tool proliferation compounds costs — each additional tool in the agent's repertoire adds per-turn token overhead, retry probability, and observability complexity. Tool design discipline (limiting scope, clear action boundaries) is cost engineering. — Shopify Engineering, "Building Production-Ready Agentic Systems," 2025-08-26 — https://shopify.engineering/building-production-ready-agentic-systems

## Gotchas

- **Setting budget limits after a runaway incident is too late.** Define circuit breakers at the architecture stage, not the post-mortem stage.
- **Model routing without a cheap routing model creates a circular cost problem.** The router itself must be fast and cheap — don't route through an Opus call to decide whether you need an Opus call.
- **Caching that isn't invalidated is a correctness trap.** Stale embedded context silently degrades quality. Cache TTLs and invalidation signals must be explicit.
- **Hidden costs compound silently.** Embedding generation, vector DB queries, observability API calls, and log storage are easy to overlook but can represent 15–25% of total spend in mature systems.
