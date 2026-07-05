# S-633 · The Real Cost Anatomy of Production Agents

When agents hit production, the cost model surprises every team. It's not the LLM price you expected — it's the compound effect of step count, routing decisions, and infrastructure overhead you didn't model upfront.

## Forces

- **LLM API cost is 60–80% of total spend, but teams budget for infrastructure.** The obvious place to cut (compute) is not where the money actually goes.
- **Step count is a multiplier, not a constant.** Each additional tool call or LLM turn compounds cost linearly — and multi-agent systems multiply it again across agents.
- **Naive vs agentic RAG costs 10x more per query.** Teams reach for agentic RAG before verifying their retrieval problem actually needs it.
- **Only 11% of enterprise agentic AI pilots reach production.** The ones that do share a common trait: they modeled cost before architecture.

## The move

**Cost = (steps per run) × (model cost per step) + infrastructure overhead**

This formula — not model benchmark rankings — is what production teams use to make routing decisions.

### Tiered model routing

Use cheap models for orchestration, expensive ones only for generation:

- **Routing/orchestration:** o3-mini, Qwen3-8B, or Gemma-4-31b (fast, cheap, sufficient for "what should happen next")
- **Complex reasoning:** Claude 3.7 Sonnet or GPT-4o for multi-step logic
- **Code generation:** Specialized models or fine-tuned variants for code-heavy steps

The WhatLLM.org June 2026 Artificial Analysis snapshot shows the top open-weight task cost at **$0.476 per task** — with the frontier proxy models running 3.8x higher. For agents executing hundreds of steps, this gap is decisive.

### Step count is your primary lever

From 6 months of real production data (Inventiple, April 2026), across 4 agentic systems:

| System | Type | Framework | Avg Steps/Run | Monthly Runs |
|--------|------|-----------|---------------|--------------|
| A | Support Triage | LangGraph | **2.4** | 12,000 |
| B | Document Processor | LangGraph | **4.8** | 8,500 |
| C | Sales Research Crew | CrewAI | **8.2** | 3,200 |
| D | Code Review Agent | Custom | **6.1** | 5,800 |

System C (multi-agent CrewAI) costs ~3.4x more per run than System A (single-agent LangGraph) due to step count alone. Architecture choice cascades directly into cost.

### Match RAG complexity to query complexity

~60% of production queries need only single-hop retrieval. Force agentic RAG (with knowledge graphs, re-ranking, query decomposition) on simple queries and you're paying a **10x cost multiplier** for no precision gain.

| Paradigm | Precision | Cost/Query | Latency |
|----------|-----------|-----------|---------|
| Naive RAG | ~70–80% | $0.001 | <1s |
| Advanced RAG | ~85–90% | $0.005 | 2–3s |
| Agentic RAG | ~90%+ | $0.010 | 4–6s |

Benchmark from JobsbyCulture agentic RAG guide (May 2026) confirms: **only 40% of production queries justify the agentic RAG path**.

### Budget infrastructure at 20–40% of LLM cost

Vector DB hosting, observability tooling, compute for tool execution, and retry logic add roughly **$0.0002–$0.0008 per step** on top of LLM costs. Teams who budget only for API calls consistently get surprised.

### Cut costs 40–70% without touching model quality

Real optimizations from production teams: semantic caching (avoid re-running semantically identical queries), early-exit routing (detect satisfiable answers before full execution), and model downgrade on low-stakes steps. These collectively cut LLM spend by 40–70% in the Inventiple dataset.

## Evidence

- **Benchmarking post:** Inventiple — "The Real Cost of Running Agentic AI in Production: 6 Months of Data from 4 Deployments" (April 2026) — tracked API spend per model, infrastructure costs, and cost-per-execution metrics across System A–D. Confirms LLM API calls = 60–80% of total operating cost. — https://www.inventiple.com/blog/agentic-ai-production-cost-analysis
- **Research analysis:** WhatLLM.org — "Cost per Task Is the New Agentic AI Model Benchmark" (June 2026) — introduces cost-per-task as the primary benchmark for agentic workloads, with live data on 69 models. Top open-weight task cost at $0.476; frontier vs value gap of 3.8x. — https://whatllm.org/blog/agentic-ai-cost-per-task
- **Framework comparison:** JobsbyCulture — "Agentic RAG in 2026: Architecture Patterns, Frameworks & When to Use It" (May 23, 2026) — benchmarks Naive vs Advanced vs Agentic vs Adaptive RAG across precision, cost/query, and latency. ~60% of production queries need only single-hop retrieval. — https://jobsbyculture.com/blog/agentic-rag-guide-2026
- **Market data:** Detroit Computing — "Agentic AI in 2026: What It Actually Costs" (2026) — notes 65% of enterprises run agentic pilots but only 11% reach production, with enterprise build costs ranging $50K–$400K+ depending on complexity. — https://detroitcomputing.com/blog/agentic-ai-enterprise-costs-and-reality
- **HN primary source:** Evan Drake — Opensoul Show HN (July 2026) — real 6-agent marketing crew with Director, Strategist, Creative, Producer, Growth Marketer, and Analyst agents running on scheduled heartbeats with per-agent budget enforcement. — https://news.ycombinator.com/item?id=47336615

## Gotchas

- **Modeling cost before building is not optional.** The teams who reach production modeled step count × model cost before writing orchestration code. The teams who don't hit surprise bills at 3 a.m.
- **Multi-agent doesn't always mean better — it always means costlier.** Each agent is an additional LLM call chain. CrewAI's role-based model enables clean architecture but System C's 8.2 average steps/run vs System A's 2.4 shows the compounding cost. Split only when specialization pays for itself.
- **Cheap models handle orchestration surprisingly well.** Qwen3 and Gemma-4-31b at 40–50 tokens/sec on local hardware (Reddit r/LocalLLaMA, June 2026) are fast enough for routing decisions. Reserve Claude/GPT-4o for generation steps only.
