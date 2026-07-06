# S-243 · Agentic Inference Cost Stratification

A prototype agent costs $20 in API credits. That same agent in production costs $9,800/month. The gap is not a bug — it is a structural consequence of how agentic loops consume tokens. The teams that survive this do not optimize harder; they stratify.

## Forces

- **Agents retry, chain, and stuff context windows.** A single agent call is not expensive. But agents chain. They retry on failure. They pack full conversation history into every call. The same workload costs 5–47× more in production than in prototype. — [Edgeless Lab, The Real Cost of Running AI Agents in Production, 2026](https://edgelesslab.com/blog/real-cost-ai-agents-production-2026)
- **Most teams do not track agent spend.** Only 63% of organizations running AI agents actively track LLM costs. Enterprise LLM spending hit $8.4 billion in H1 2025, doubling from the prior period. — [Vincent van Deth, The Real Cost of AI Agents in Production, 2025](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Not every subtask in an agentic workflow requires frontier intelligence.** Routing a classification decision through GPT-4o is a 40× overpayment versus a 500M-parameter classifier. The question is how to make routing reliable enough to bet production quality on. — [AgentMarketCap, Agent Token Cost Optimization, 2026](https://agentmarketcap.ai/blog/2026/04/08/agent-token-cost-optimization-production-inference-spend)

## The move

Implement three-tier cost stratification across the inference pipeline. Route aggressively by task type, not by model preference.

**Tier 1 — Lookups and routing (90% of calls, ~$0.10–0.50/1M tokens)**
- Use small models (<7B parameters) for: classification, intent routing, format normalization, duplicate detection, simple retrieval filtering
- A small classifier reliably determines which pool model to invoke downstream
- These calls dominate volume but consume negligible budget

**Tier 2 — Reasoning and synthesis ($3–15/1M tokens)**
- Claude 3.5 Sonnet, GPT-4o, Gemini 2.0 Flash for: multi-step tool orchestration, document synthesis, complex extraction, policy reasoning
- Gate these calls behind Tier 1 routing — never let an agent reach for a frontier model without a reason
- Apply quality gates: if a Tier 2 call fails, do not blindly retry — check if a simpler Tier 1 path resolves the task

**Tier 3 — Deep analysis and frontier tasks ($15–75/1M tokens)**
- Claude 3 Opus, o1, o3 for: novel problem decomposition, ambiguous strategy decisions, high-stakes synthesis
- These should be rare — under 5% of total calls for most production workloads
- Instrument aggressively: every Tier 3 invocation should be logged with its trigger condition so the routing logic can be refined

**Context window management — the multiplier killer**
- Enforce hard limits on conversation history passed to frontier models
- Summarize or truncate after N rounds rather than letting context grow unbounded
- Each 8K-token context window that could have been 1K is a 7× cost multiplier per turn

## Evidence

- **Real production case:** Vincent van Deth runs 11 agents in production with an initial bill of $2,847/month. Through multi-model routing, quality gates, and context window management, he reduced spend to $370/month — an **87% reduction** — while blind tests showed outputs indistinguishable from an all-Opus baseline at 94%. — [Vincent van Deth, The Real Cost of AI Agents in Production, 2025](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Research-backed routing:** UC Berkeley, Anyscale, and Canva (ICLR 2025) demonstrated that trained routing classifiers using RouteLLM achieve **85% cost reduction while maintaining 95% of GPT-4 performance** on agentic benchmarks. The routing model does not need to be smart — it needs to be calibrated. — [AgentMarketCap citing RouteLLM/ICLR 2025](https://agentmarketcap.ai/blog/2026/04/08/agent-token-cost-optimization-production-inference-spend)
- **Enterprise cost scale:** A team shipped their first AI agent as a prototype ($20 in API credits). Month-one production bill: $3,200. Month two: $9,800. The agent worked exactly as designed. The cost surprise was entirely in token volume dynamics. — [Edgeless Lab, The Real Cost of Running AI Agents in Production, 2026](https://edgelesslab.com/blog/real-cost-ai-agents-production-2026)

## Gotchas

- **Routing classifiers need calibration data, not just intuition.** A routing model trained on synthetic data will route incorrectly on real production distributions. Build routing evals from live traffic, not from prototype runs.
- **Context window costs dominate at scale, not per-call price.** The $/1M token rate matters less than the average context size per turn. A 2× reduction in context length is worth more than a 2× reduction in token pricing.
- **Retry loops are the silent cost multiplier.** Each retry doubles the cost of a failed call. Instrument retry rates per task type — if any task retries more than 20% of the time, the routing or tool definition needs fixing, not the model.
- **Quality gates can degrade UX if too aggressive.** A gate that blocks LLM calls too aggressively will surface failures to end users. Test gate thresholds against actual failure modes, not against the happy path.
