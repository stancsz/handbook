# S-369 · Production Cost Engineering for Agentic AI

Agentic AI costs scale super-linearly with complexity — a single-step support triage costs $0.003/run, a multi-agent research crew costs $0.52/run. The gap isn't obvious until you've already built the expensive version. This entry is for teams that need to make cost-aware architecture decisions before they ship.

## Forces

- **API spend is 60–80% of total operating cost** — infra costs are rounding errors by comparison. Optimizing the model layer gives the highest leverage.
- **Cost per run spans 10–170x across deployment patterns** — the difference between a naive single-agent and a well-routed multi-agent crew is an order of magnitude, not a percentage point.
- **Per-step cost compounds.** Every additional tool call, reasoning loop, and agent handoff multiplies token consumption. Teams underestimate this until the first billing cycle.
- **"Add an agent" is the most expensive default** — multi-agent coordination delivers capability but at a cost premium that rarely gets re-examined post-launch.
- **Semantic caching and model routing deliver 30–70% savings without touching quality** — the low-hanging fruit goes unpicked because costs aren't instrumented in the first place.

## The move

**Instrument cost-per-execution as a first-class metric, then make architectural decisions against it.**

### 1. Know your cost baseline by system archetype

Real production data from 4 deployments over 6 months (Inventiple, Oct 2025–Apr 2026):

| System | Type | Framework | Avg Steps/Run | Monthly Volume | Cost/Run | Monthly API Cost |
|--------|------|-----------|---------------|----------------|----------|-----------------|
| Support Triage | Single agent, 3 tools | LangGraph | 2.4 | 12,000 | $0.003 | $36 |
| Document Processor | Sequential chain, 5 tools | LangGraph | 4.8 | 8,500 | $0.14 | $1,190 |
| Sales Research Crew | Multi-agent (3 agents) | CrewAI | 8.2 | 3,200 | $0.52 | $1,664 |
| Code Review Agent | Single agent, 7 tools | Custom | 6.1 | 5,800 | $0.31 | $1,798 |

**Cost/run scales ~15x from simple triage to multi-agent crew.** Step count and model tier are the dominant factors.

### 2. Route models by query complexity — not by default

Route 60–70% of requests to a cheap model (Claude Haiku / GPT-4o-mini). Use a fast classifier or LLM judge to determine complexity before routing. Teams doing this cut API spend by 40–60% with measurable quality maintained.

Per-ticket cost comparison (support ticket resolution, ~3,550 tokens total):
- All Sonnet 4: **$0.016/run**
- With 60% routed to Haiku: **~$0.008/run** (50% savings)
- With semantic caching on top: **~$0.005/run** (68% total savings)

### 3. Cache semantically, not by exact match

Standard key/value caching misses 40–60% of cacheable queries because users phrase the same intent differently. Semantic caching with an embedding store ( Voyage-3-lite at $0.02/M tokens for embeddings ) catches re-phrased duplicates. Typical hit rate: 25–35% of production traffic. Embedding cost is negligible ($0.0001/query); savings are 15–35% on API calls.

### 4. Instrument at the step level, not the request level

LangSmith, Arize Phoenix, or Langfuse can tag every tool call and LLM turn with cost. A 12-step agent has 12+ places where cost can leak. Teams that don't instrument per-step can't identify where 80% of spend is going — and the answer is rarely where they think.

Minimum cost tracking per run: input tokens × model input rate + output tokens × model output rate + embedding cost for any RAG retrieval + infra allocation. Surface this on a dashboard alongside latency and success rate.

### 5. Set cost circuit breakers before you need them

Without hard limits, a looping agent can consume the monthly budget in hours. Set per-session token limits and cost caps that halt execution and alert on-call. One team's agent got stuck in a retrieval loop and ran $3,400 in a weekend (ToLearn Blog).

### 6. Know when NOT to use agentic patterns

Agentic RAG costs $0.06–0.31/query vs $0.01–0.05 for standard RAG — 6x premium. Use agentic retrieval only for multi-hop reasoning, document comparison, or ambiguous queries requiring iterative self-correction. For straightforward factual lookups ("what's our refund policy?"), a fixed retrieve-then-generate pipeline wins on cost and latency (<1s vs 2–8s).

## Evidence

- **Engineering blog:** Real cost data across 4 production systems over 6 months — cost/run ranges from $0.003 to $0.52 by system complexity — [Inventiple: The Real Cost of Running Agentic AI in Production](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)
- **Community reference:** Detailed per-action cost model for a support ticket resolution pipeline with token counts and per-model pricing — [agentic-ai-system-design-primer: Real-World Numbers](https://github.com/HimClix/agentic-ai-system-design-primer/blob/main/resources/cost-engineering/real-world-numbers.md)
- **Engineering post:** One team's agentic RAG loop consumed $3,400 over a weekend without circuit breakers — [ToLearn Blog: AI Agents Production 2025](https://tolearn.blog/blog/ai-agents-production-guide)
- **Agentic RAG comparison:** Traditional vs agentic RAG cost/accuracy table — agentic RAG hits 78% accuracy on complex queries vs 34% for traditional, at 6x cost — [Jahanzaib.ai: Agentic RAG Production Guide](https://www.jahanzaib.ai/blog/agentic-rag-production-guide)

## Gotchas

- **Don't benchmark cost in dev — instrument it in prod.** Token counts vary with real input distributions in ways dev queries don't capture.
- **Cheaper models + orchestration beats expensive models + no orchestration.** GPT-3.5 + tools via LangGraph outperformed GPT-4 zero-shot on coding tasks (48% → 95.1%). Model cost and capability aren't a substitute for architecture.
- **Context management costs more than you think.** The model layer is 60–80% of cost, but context construction (RAG retrieval, conversation history, tool overhead) can double effective token count per run. Profile context construction separately.
- **Multi-agent overhead compounds.** Each agent in a crew needs its own system prompt, context injection, and output parsing. A 3-agent CrewAI system at 8.2 avg steps/run costs 170x more per execution than a 2-step single-agent triage.
- **Model routing savings are real but require a quality gate.** Route by complexity classification, but audit the routing decisions weekly — LLM judges occasionally misclassify, and edge cases cluster at the complexity boundary.
