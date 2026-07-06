# S-221 · Agentic RAG — Retrieval as an Adaptive Loop

Naive RAG (chunk → retrieve top-k → generate) breaks on multi-hop questions, ambiguous queries, and stale indexes. Agentic RAG upgrades retrieval from a one-shot lookup into a reasoning loop: the agent plans, retrieves, evaluates quality, and self-corrects — looping until the answer is grounded or the search space is exhausted.

## Forces

- Naive RAG has three structural failures: query-document mismatch (vague queries miss document facets), no quality gate (pipeline proceeds regardless of retrieval quality), and uniform processing (all query types get identical retrieval strategy)
- The RAG failure rate in enterprise is ~72% in year one — most failures stem from treating retrieval as plumbing rather than a reasoned process
- Agentic RAG adds latency and token cost on every loop iteration — unconstrained loops can run 10+ retrieval steps, making the cost profile 5–15x higher than prototype estimates
- The gap between naive and agentic RAG is the line between a search engine and a research assistant — but the assistant can also waste tokens chasing ghosts

## The move

**The core loop:**
```
Query → [Plan retrieval strategy] → [Execute retrieval(s)]
     → [Evaluate result quality] → [Self-correct or synthesize]
     → [Generate answer or loop]
```

**Key techniques that make it work:**

- **Query decomposition:** Break multi-hop questions into sub-queries, each routed to the appropriate index or data source. A question like "What changed in our Q3 compliance policy and how does it affect our EU operations?" requires at minimum two retrievals over different corpora.
- **Routing layer:** Before retrieval, classify query type — factual lookup, comparison, summarization, reasoning chain — and route to the optimal retrieval strategy or index. Don't route everything through the same vector search.
- **Self-RAG / CRAG (Corrective RAG):** After retrieval, have a lightweight judge (small classifier or LLM check) evaluate whether the retrieved chunks actually answer the query. If not, reformulate and retry. If the judge is uncertain, escalate to a different retrieval method.
- **Hard retry limits with fallback:** The most common agentic RAG failure is the infinite loop. Set a max iteration cap (typically 3–5) and define explicit fallback behavior (degrade to broader retrieval, return partial answer, escalate to human). Measure reformulation rate — if >20% of queries need reformulation, fix the retrieval layer, not the agent.
- **Hybrid retrieval at the base layer:** Combine dense vector search with BM25 keyword search before the agentic loop. The agentic layer corrects strategy, but it operates on top of a retrieval foundation that must be solid. Parent-document retrieval (fetch the full document from which a chunk was drawn) reduces hallucination risk from partial-chunk context.
- **Re-rank before generate:** After agentic retrieval produces a candidate set, use a cross-encoder re-ranker before injecting into the generation prompt. This matters more as agentic loops pull from multiple sources — relevance scoring compounds across retrieval steps.

## Evidence

- **Industry report (Technspire, Dec 2025):** Customer service and compliance automation were the two highest-volume production RAG deployments in 2025, both requiring multi-hop reasoning over structured and unstructured sources. Foundational insight: "Agents work where software engineering discipline works. Bounded scope, tested behavior, scoped identity, observable runtime." — [State of Agentic AI 2025](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)
- **Engineering guide (aliac.eu, Feb 2026):** Outlines the RAG maturity path: Naive RAG → Advanced RAG (pre/post retrieval optimization) → Modular RAG (component swapping) → Agentic RAG (full planning + self-correction loop). Real production numbers: Harvey AI achieved 0.2% hallucination rate serving 700+ legal clients; Deutsche Telekom hit 89% acceptable answer rate across 2M+ conversations. Key warning: 72% of enterprise RAG implementations fail or significantly underdeliver in year one. — [Agentic RAG in Production](https://aliac.eu/blog/agentic-rag-in-production)
- **Engineering blog (1337skills, May 2026):** Documents three critical anti-patterns: (1) infinite retry loops with no hard cap and no fallback, (2) over-routing with complex conditional graphs where a single hybrid retriever would perform better, (3) context stuffing with 20 chunks when quality matters more than quantity. Recommends starting with the simplest architecture that meets requirements and adding complexity only when metrics show it is insufficient. — [Agentic RAG Architecture Patterns](https://1337skills.com/blog/2026-05-21-agentic-rag-architecture-patterns)

## Gotchas

- **Context stuffing is the silent killer:** More retrieved chunks do not mean better answers. A single well-scoped chunk beats ten noisy ones. Use the evaluation step to filter aggressively, not just expand.
- **Measuring reformulation rate is the first signal:** If >20% of queries require query reformulation, the root cause is almost always in the retrieval layer (bad chunking, wrong embedding model, stale index) — not in the agent logic. Fix the foundation before adding agentic complexity.
- **Prototype cost ≠ production cost:** The prototype-to-production cost multiplier for agentic systems is 5–15x due to retry loops, multi-step retrieval, observability overhead, and reliability engineering. Teams that don't budget for this see 3-figure to 5-figure surprises in their first runaway loop incident.
- **Hybrid architectures are the norm, not the exception:** Most teams running agentic RAG in production use LangGraph for orchestration and LlamaIndex for retrieval tooling — not one framework for everything. LangGraph handles the state machine; LlamaIndex handles chunking, embedding, hybrid search, and re-ranking. This separation of concerns maps to the agent stack stratification pattern (S-218).
