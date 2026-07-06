# S-329 · Agentic RAG: The Three Levers That Close the Naivety Gap

Naive RAG — embed docs, similarity search, stuff top-3 into prompt — gets you a 70%-quality demo and a plateau you can't climb past. You've been told "just add a vector DB" and now you have one. The retrieval still fails on exact matches, ambiguous queries, and documents that don't chunk cleanly. The problem is never the embedding model. The problem is the retrieval pipeline.

## Forces

- **Retrieval quality beats model quality.** A mediocre model with excellent retrieved context reliably beats a frontier model with poor context. The model can only reason over what you put in front of it — but teams keep swapping models instead of fixing the pipe. (Ruchit Suthar, June 2026 — https://ruchitsuthar.com/blog/software-architecture/rag-in-production-chunking-reranking-hybrid-search)
- **Chunking is the largest single determinant of RAG quality.** A chunk is the unit of both indexing and retrieval. Once embedded, you can only retrieve at that granularity. You can have the best embedding model, most powerful re-ranker, and perfect tool interface — and still get poor retrieval because the underlying chunks are wrong. (AgentEngineering, April 2026 — https://www.agentengineering.io/topics/articles/rag-for-agents)
- **The "Lost in the Middle" problem bites regardless of context window size.** Information buried in the middle of long contexts causes 73% performance degradation on reasoning tasks, even with million-token windows. Safety guardrails get buried. Persona bleeding causes hallucinations. The fix is architectural, not prompt-level. (Comet, 2026 — https://www.comet.com/site/blog/multi-agent-systems)
- **Naive RAG silently caps at 70%.** Production retrieval fails 40% of the time at the retrieval stage alone. Teams mistake the ceiling for a model problem and iterate the wrong variable. (Lushbinary, April 2026 — https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)

## The Move

The gap from 70% to production-grade is three retrieval levers. Pull all three, in order.

**Lever 1: Chunk on structure, not character counts.**
- Chunk boundaries should respect semantic units — paragraphs, code blocks, table rows, section headers — not fixed 512-token windows.
- Overlapping chunks (20-30% overlap) preserve continuity across boundaries without duplicating enough to confuse.
- For code: split on function/method boundaries, not lines. For tables: treat each row as a chunk with header context. For mixed documents: use a hierarchical chunk (parent chunk + child chunks) so parent context travels with the child on retrieval.
- Parent-child chunking is the highest-leverage upgrade for complex documents. Index child chunks; retrieve them; then fetch the parent for full context.

**Lever 2: Hybrid search (dense + sparse) beats pure vector.**
- Pure vector search misses exact matches — codes, SKUs, acronyms, proper nouns. These are often the most relevant items.
- Hybrid combines dense vector similarity with sparse keyword (BM25) retrieval. Most vector DBs support this natively now.
- Apply ACL/security filters as a pre-filter (before vector search), not post-filter. Post-filtering on a small retrieved set causes invisible security gaps in multi-tenant systems.
- Query rewrite is often skipped but critical for vague user queries. Expand ambiguous queries with synonyms or reframe them before retrieval.

**Lever 3: Re-rank an over-fetched candidate set.**
- Vector search retrieves by approximate nearest neighbor — fast but approximate. Re-ranking takes a larger candidate set (top-15 to top-30) and applies a cross-encoder for precise relevance scoring.
- Cohere Rerank v3 and bge-reranker-v2-m3 are the dominant choices in production. This is the cheapest production upgrade available — it adds ~50-200ms latency and fixes the majority of retrieval failures without touching the model.
- After re-ranking, apply lost-in-the-middle mitigation: put the top 3-5 chunks at the boundaries of the context window, not the middle. System instructions and task-relevant context go at the boundaries; model attention decays in the middle.
- For agentic RAG: route to specialized retrievers based on query type. A policy question hits a policy index; a code question hits a code index. Single-index retrieval is a proxy for "we haven't thought about query routing."

**Bonus lever — Agentic RAG (the loop):**
- Naive RAG is one-shot: query → retrieve → answer. Agentic RAG adds a check step: if retrieved context doesn't answer the question, reformulate the query and retrieve again.
- This is the difference between RAG generation 2 (naive) and generation 3 (agentic). It trades latency for recall — worth it for high-stakes retrieval tasks.
- A retrieval grader (lightweight LLM call or embedding similarity threshold) determines whether to loop or proceed to generation.

## Evidence

- **Blog post:** "RAG in Production: Chunking, Re-ranking & Hybrid Search" — Ruchit Suthar documents the three-lever framework and reports naive RAG plateaus at 70% quality. Independent validation from multiple teams in comments and cited case studies. — https://ruchitsuthar.com/blog/software-architecture/rag-in-production-chunking-reranking-hybrid-search
- **Technical article:** "RAG in Production: Chunking, Hybrid Search, and Agentic Retrieval" — AgentEngineering (April 2026) provides detailed chunking strategies including parent-child chunking, with benchmarked impact on retrieval quality. — https://www.agentengineering.io/topics/articles/rag-for-agents
- **Research synthesis:** Comet blog on multi-agent systems cites the "Lost in the Middle" study (Liu et al., 2024) showing 73% performance degradation on middle-position context. Validates the architectural argument against naive context stuffing. — https://www.comet.com/site/blog/multi-agent-systems
- **Industry report:** Lushbinary's 2026 RAG Production Guide reports 40% failure rate at the retrieval stage for naive pipelines and catalogs the specific failure modes (query ambiguity, chunk boundary mismatch, hybrid retrieval absence). — https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide

## Gotchas

- **Re-ranking before filtering.** Never re-rank before applying ACL filters — you'll score documents the user can't see, wasting latency and potentially exposing irrelevant-but-restricted content in the candidate pool.
- **Chunk overlap that's too large.** 50% overlap doubles your index size and introduces near-duplicate context that degrades generation quality. 20-30% is the sweet spot for most document types.
- **Single retrieval round is a hidden assumption.** Naive RAG's single-shot assumption fails on multi-hop questions (e.g., "what was the revenue trend and what changed in the strategy?"). Agentic RAG's loop is not optional for complex queries — it's the mechanism that closes the recall gap.
- **RAGAS-style metrics are necessary but insufficient.** RAGAS measures answer relevance and faithfulness, but doesn't measure retrieval recall. A system can score well on RAGAS while missing the right documents entirely. Track hit-rate@K and MRR@K alongside RAGAS.
- **The re-ranker latency budget is easy to blow.** A naive hybrid + cross-encoder pipeline can hit 400-600ms end-to-end. Budget: BM25/vector pre-filter ~20ms, candidate retrieval ~50ms, re-ranking ~100-200ms, context assembly ~50ms. Profile each stage; the re-ranker is usually the bottleneck.
