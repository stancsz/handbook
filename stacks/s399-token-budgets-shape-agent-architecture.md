# S-399 · Token Budgets Shape Agent Architecture

Agentic systems don't fail on capability — they fail on cost. Context compounds token-for-token through every turn, and the gap between a naive agent and a cost-governed one is 5x to 10x on the same task. Budget enforcement isn't an optimization pass; it's a first-class architectural constraint that shapes orchestration design, model selection, and the decision of whether to split into multiple agents.

## Forces

- **Context compounds at a triangular rate, not linear.** Each turn includes all prior turns. A 10-turn workflow doesn't cost 10× a single query — it costs ~55× (n(n+1)/2). Teams that model agent cost as "turns × average per-turn cost underprice by 3–5× consistently
- **Average agent task burns 47K tokens; naive chatbots burn 200–500.** That's 70–230× more. Some production tasks hit 200K+. The unit economics are nothing like chat, and most teams discover this from the bill, not from modeling
- **Context eviction is silent hallucination.** When the context window fills, the model doesn't error — it starts forgetting earlier tool outputs, reading files it claims to have read, and fabricating results. No crash, just confident wrong answers
- **Token spend is the most underestimated infrastructure line item.** Gartner tracked inference cost as the top production blocker for 49% of organizations running agents in 2025. The scramble to govern spend is real and recent — TechCrunch covered it in June 2026
- **Budget enforcement shapes architecture itself.** Teams that add hard token caps discover they need to split monolithic agents into smaller, stateless units — not for parallelism, but so each unit fits in budget. Cost governance forces decomposition

## The move

Treat the token budget as the primary resource constraint, not a post-launch concern.

**Enforce at three layers:**

- **Prompt hygiene** — system prompts are loaded on every turn. Every unnecessary instruction, example, or reference table costs its full token weight per call. Audit with a tokenizer before shipping, not after
- **Context compression** — summarize and evict mid-workflow rather than accumulating. Summarize previous turns into a "compressed memory" block; let the agent re-hydrate from it when needed. This is structurally different from truncation
- **Runtime budget caps** — hard per-task token limits enforced at the orchestration layer (not the model). Hard caps with clear fallback behavior when exceeded (escalate, defer, or fail). This prevents runaway loops from generating 10× budget in a single task

**Route by task cost profile:**

- Fast/low-stakes tasks (routing, classification, formatting) → fast cheap models (Gemini Flash, Haiku-class)
- Reasoning-heavy tasks (analysis, code generation, multi-step planning) → frontier models
- Route on task type, not globally. Model routing alone can cut spend 40–60% on mixed workloads

**Design for stateless agents where possible:**

- A 10-turn monolithic agent accumulates context for the full run. Five 2-turn stateless agents, each invoked fresh, pay only n(n+1)/2 per sub-task — dramatically less total context. The tradeoff is coordination overhead and loss of cross-turn memory, which you replace with structured output passing

## Evidence

- **Blog (dataku.ai):** Average agent task across 50 real tasks × 3 models consumed ~47K tokens — 70–230× more than a simple chatbot response (200–500 tokens). Code generation + testing tasks hit 67K tokens (Claude 3.5 Sonnet). Research tasks averaged 38–42K tokens. — [URL](https://dataku.ai/blog/real-cost-of-ai-agents-token-usage-50-tasks)
- **Blog (Waxell, May 2026):** Context window cost compounds at a triangular series, not linear. A 10-turn workflow costs ~55× a single-turn task, not 10×. Teams modeling linear cost underprice by 3–5×. Hard budget enforcement at the orchestration layer is the architectural response. — [URL](https://waxell.ai/blog/ai-agent-context-window-cost)
- **Engineering blog (Supergood, March 2026):** Token spend is the most underestimated production line item. Five governance layers: prompt hygiene, context compression, prompt caching, model routing, runtime budget enforcement. Model routing alone cuts mixed-workload costs 40–60%. — [URL](https://supergood.solutions/blog/token-budget-management-production-ai-agents-2026/)

## Gotchas

- **Prompt caching is not a substitute for budget discipline.** Caching reduces repeated load costs but doesn't prevent context growth within a session. A caching hit on a 100K-token context still pays for the full forward pass
- **Soft limits fail.** Setting "prefer smaller models when under 50% budget" creates incentive mismatches and silent cost overruns. Hard caps with explicit fallback behavior — escalate, defer, or fail — are the only reliable pattern
- **The model doesn't know when to stop.** Without explicit max_turns or max_tokens enforcement, an agent in a loop will happily burn the rest of the context window generating slightly revised versions of wrong output. The guard is in the orchestration layer, not the model prompt
