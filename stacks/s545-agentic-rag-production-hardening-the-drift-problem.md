# S-545 · Agentic RAG — Hardening Against the Drift Problem

Your RAG demo worked great in August. By November it silently started returning worse answers — not because the model degraded, but because embeddings drifted, chunk boundaries stopped making sense, and relevance scores no longer reflected actual utility. Nobody noticed until customers complained. This is the agentic RAG hardening problem: not building retrieval, but keeping it honest over time.

## Forces

- **Reindexing is prohibitively expensive** — teams let RAG systems slowly degrade rather than pay the recompute cost of re-embedding everything
- **Silent embedding drift** — the gradual degradation of embedding model quality (model updates, distribution shift, corpus evolution) that goes unnoticed until it significantly impacts performance
- **Naive RAG fails on multi-step questions** — a rigid chunk → retrieve top-k → generate pipeline breaks on anything requiring cross-document reasoning or query reformulation
- **The observability gap is structural** — 89% of teams have span-level monitoring, but only 52% have automated evals running in CI; the debugging gap lets drift persist until users catch it
- **RAG maturity path has three distinct phases**, and most teams plateau at phase one

## The Move

Move through the RAG maturity path deliberately, then layer in the agentic self-correction loop that is the actual production differentiator.

### Phase 1 — Naive RAG (acceptable only as a spike)
- Chunk text into fixed-size segments → embed → store in vector DB
- Retrieve top-k by cosine similarity → inject into LLM context → generate
- **Fails on**: multi-hop questions ("what changed in Q3 and why?"), ambiguous queries, stale results, duplicate/threshold-edge cases

### Phase 2 — Advanced RAG (the minimum production baseline)
- **Pre-retrieval**: query expansion, query rewriting, HyDE (generate hypothetical doc, use it to retrieve real docs)
- **Post-retrieval**: rerank results (Cross-Encoder or ColBERT), context compression, duplicate-aware dedup
- **Index-time**: semantic chunking (by sentence/paragraph/section boundaries, not token count), metadata enrichment
- **Retrieval**: hybrid search (dense vectors + sparse BM25), ensemble fusion (RRF)

### Phase 3 — Agentic RAG (the hardening layer)
- **Planning agent**: classifies query type → routes to appropriate retrieval strategy (FAQ lookup, doc search, knowledge graph walk, web search)
- **Self-correction loop**: LLM evaluates whether retrieved context answers the question; if not, reformulates query and retries (up to N iterations)
- **Multi-source orchestration**: parallel query across vector DB + knowledge graph + web, then synthesize
- **Groundedness verification**: after generation, a critic agent checks whether the answer is actually supported by retrieved context — hallucination gate before output

### Phase 4 — Production hardening (the operational layer)
- **Target metrics** (from RAGAS/DeepEval research-backed benchmarks):
  - Retrieval precision ≥ 70%
  - Generation groundedness ≥ 90%
  - End-to-end task success ≥ 85%
- **Automated evals in CI**: run DeepEval or RAGAS metrics on every PR using LLM-as-judge
- **Embedding drift detection**: schedule periodic re-eval of a golden query set against current index; alert on recall drop > 5%
- **Cost guardrail**: set per-query token budget and hard stop on retrieval depth; agentic RAG with 4-agent workflows costs $5–8 per complex task — budget for it explicitly

## Evidence

- **Conference report:** "AI in Production 2025" (Digits-sponsored post) — documented silent embedding drift as the primary RAG degradation mechanism in production; reindexing costs cited as the primary blocker for remediation — [https://digits.com/blog/ai-in-production-2025](https://digits.com/blog/ai-in-production-2025)

- **Enterprise guide:** Agentic RAG in Production (aliac.eu) — defines the three-phase RAG maturity path (Naive → Advanced → Agentic); recommends RAGAS reference-free metrics (faithfulness, answer relevancy, context precision, context recall); suggests DeepEval with 50+ metrics and native Pytest integration for CI pipelines — [https://aliac.eu/blog/agentic-rag-in-production](https://aliac.eu/blog/agentic-rag-in-production)

- **Engineering blog:** Medium — "Production-Grade Agentic Multimodal RAG System" — documents a full open-source stack (JinaAI embeddings, Nomic Atlas, Whisper, pgvector) with local model deployment for data sovereignty, audit logging, and observability via Langfuse; observes that agentic RAG "doesn't just retrieve documents — it understands them" — [https://medium.com/@salil.kadam/building-a-production-grade-agentic-multimodal-rag-system-from-concept-to-deployment-37da28cb0547](https://medium.com/@salil.kadam/building-a-production-grade-agentic-multimodal-rag-system-from-concept-to-deployment-37da28cb0547)

- **LangChain survey (1,300+ professionals):** 57% of organizations have agents in production, but the observability-to-evals gap (89% monitoring vs. 52% running automated evals) is the structural reason drift goes undetected — cited in RaftLabs multi-agent systems analysis — [https://www.raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- **Don't skip to agentic RAG without hardening Advanced RAG first.** The self-correction loop amplifies existing retrieval quality problems, not fixes them — if your baseline recall is low, the agent just confidently re-retrieves the wrong things
- **Embedding model upgrades are invisible breaking changes.** When your embedding provider ships a new version, cosine similarity scores shift. Set a pinned embedding model version and test before upgrading — never auto-migrate
- **Groundedness verification adds latency and cost.** The critic agent gate adds 1–2 extra LLM calls per query. Budget this; don't discover it in a load test
- **Hybrid search is worth the complexity.** Pure vector retrieval misses exact-keyword matches that BM25 handles well. Teams that skip hybrid search consistently underperform on technical queries (method names, product IDs, proper nouns)
