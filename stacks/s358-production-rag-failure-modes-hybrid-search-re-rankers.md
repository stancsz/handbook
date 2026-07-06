# S-358 · Production RAG Failure Modes: Hybrid Search + Re-Rankers

Naive RAG — embed, store, retrieve top-k, generate — works in demos. It fails in production. Not at generation, and not because the model is wrong. It fails at retrieval: the wrong documents surface, the right ones get buried, and the LLM confidently synthesizes a bad answer from bad context. Fixing this requires hybrid retrieval and a re-ranker, but teams approach it wrong and still end up with polished demos instead of reliable systems.

## Forces

- **Naive RAG fails at retrieval ~40% of the time.** Not at generation, not at prompting — at the retrieval step. Teams spend weeks tuning the model and prompts while the bottleneck stays untouched.
- **73% of RAG failures happen in retrieval, not generation.** When the pipeline produces a wrong answer, the instinct is to blame the LLM. Usually it's the retrieval.
- **Semantic gap is the silent killer.** User queries and document passages use different vocabulary. "How do I cancel?" does not semantically match "Account Termination Policy" in dense vector space — even with a good embedding model.
- **Retrieval degrades under real load.** Engineering docs, support content, and legal text contain exact phrases that matter. Dense embeddings alone cannot capture exact-match signal. Sparse retrieval (BM25) captures that, but misses semantic nuance. You need both.
- **Re-rankers are not optional in production.** Passing top-k retrieved results directly to the LLM is lazy. A cross-encoder re-ranker re-scores the candidate set against the query and surfaces the actually-relevant documents — even if they ranked 11th in vector space.

## The move

### 1. Run hybrid search by default, not as optimization

Combine dense vector search (semantic similarity) with sparse BM25 (exact keyword matching). Dense captures conceptual overlap; sparse captures exact terminology that semantic models miss. Most vector DBs support this natively — Pinecone, Qdrant, Weaviate, pgvector all expose hybrid or hybrid-equivalent modes. Set it as the default retrieval path; don't add it when recall looks bad.

### 2. Right-size your chunk size — 512 tokens is the practical ceiling

Lushbinary's production data shows that chunks larger than ~512 tokens dilute the signal: the LLM averages across the whole context rather than focusing on the most relevant passage. Smaller chunks with overlap preserve topical focus. The exception is structured documents (tables, code) where larger chunks preserve relational context — but those need special handling, not a blanket "bigger chunks = better context" assumption.

### 3. Place a re-ranker between retrieval and generation

After hybrid search returns top-k (say, k=30), run a cross-encoder re-ranker that scores each candidate against the original query. Pass the top 5-10 to the LLM. This is where the 15-30% RAGAS metric improvement comes from. Without it, you're handing the LLM a noisy candidate list and expecting it to do your retrieval job.

### 4. Monitor recall at rank-k, not just overall quality

The standard evaluation is end-to-end answer quality. This hides retrieval failures. Track where the correct document ranks in your retrieval results — if it's consistently at position 11+, your hybrid search needs tuning, not your model.

### 5. Semantic caching reduces cost 30-50% before you optimize prompts

LLM call reduction through semantic caching — deduplicating semantically similar queries — delivers 30-50% cost reduction. This compounds with multi-agent pipelines where the same queries hit the same retrieval layer repeatedly. Layer it in before rewriting prompts or swapping models.

## Evidence

- **Blog post:** Naive RAG fails 40% at retrieval; 73% of failures are at retrieval, not generation; re-ranking improves RAGAS metrics 15-30% — [Lushbinary, RAG Production Guide 2026](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)
- **Case study:** A production RAG system retrieved a document about a custom override phrase ("dead-letter queue threshold") at rank 11 — outside top-10, never passed to the LLM — despite accurate dense retrieval. The exact keyword signal BM25 would have caught was absent from the semantic embedding space. Fixed by adding hybrid search. — [Towards Data Science, Hybrid Search and Re-Ranking in Production RAG](https://towardsdatascience.com/hybrid-search-and-re-ranking-in-production-rag)
- **Framework blog:** 2026 RAG pipelines are described as six layers (embedding, vector DB, retrieval, re-ranking, generation, evaluation) with hybrid + re-ranker as the production baseline, not an optimization. — [Future AGI, RAG Architecture in 2026](https://futureagi.com/blog/rag-architecture-llm-2025)

## Gotchas

- **BM25 alone is not hybrid.** Teams add BM25 and call it hybrid, but BM25 + dense is only useful when both signals are actually combined — typically via Reciprocal Rank Fusion (RRF). Naive score combination often hurts more than helps.
- **Re-rankers add latency.** A cross-encoder re-ranker (Cohere Rerank, BGE-Reranker) adds 100-300ms per query. Budget for it. If latency is critical, cache re-ranker outputs for repeated query patterns.
- **Top-k is not one-size-fits-all.** k=5 for short factual queries; k=30 for complex research tasks. Retrieval depth should match query complexity, not a fixed constant.
- **Chunking strategies must match your content types.** Fixed-size chunking with overlap works for prose. It destroys tables, code blocks, and structured documents. Use semantic chunking (by heading, by sentence boundary) for structured content.
- **Eval before and after every change.** RAGAS metrics (groundedness, context adherence, faithfulness, answer relevance) are the minimum. Without baseline metrics, you cannot know if your hybrid + re-ranker changes improved or degraded recall.
