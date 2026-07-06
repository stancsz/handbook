# S-293 · RAG Plateau: Naive Retrieval Never Pulls These Three Levers

Naive RAG — embed the docs, similarity search, top-3 chunks, dump into prompt — gets you a 70% quality demo and a plateau you cannot climb past. The gap to production lives in three retrieval levers that most teams never pull, and the fix is retrieval quality, not model quality.

## Forces

- **Chunk boundaries are permanent once indexed.** A chunk is the unit of both retrieval and context. Once a document is split on character counts, you cannot retrieve at sentence-level granularity even if the query matches exactly one sentence. The granularity problem is baked into the index.
- **Semantic gap is a vocabulary problem, not a relevance problem.** Users ask in their language; documents are written in organizational language. Pure vector similarity collapses when "cancel my account" and "account termination policy" live in different embedding space.
- **Over-fetching is invisible cost.** Fetching 10 chunks instead of 3 doesn't just slow things down — it pollutes the context window with semi-relevant noise, and the LLM averages across all of it, producing mediocre answers that look confident.
- **RAG failures live at retrieval, not generation.** 73% of RAG failures occur at the retrieval step. Throwing a better model at a bad retrieval pipeline makes failures more confident, not more correct.

## The Move

Three levers, applied in order of leverage:

- **Chunk on structure, not character count.** Split on natural boundaries — headings, sections, paragraphs, table rows, function definitions. Add parent-chunk IDs so a semantically chunk can be expanded with its parent section during retrieval. For code: split on function/class boundaries. For contracts: split on clause boundaries with clause numbers preserved.
- **Hybrid search (vector + keyword) is the default, not the exception.** BM25 handles exact-match queries that embeddings miss. Use reciprocal rank fusion (RRF) to combine scores. The semantic gap problem is solved at retrieval time, not by better embeddings.
- **Re-rank an over-fetched candidate set.** Fetch 20 candidates (vector + BM25), then re-rank with a cross-encoder (Cohere Rerank, bge-reranker) down to top 5. This separates the recall problem (broad search) from the precision problem (scoring what actually answers the question).

## Evidence

- **Production guide:** Lushbinary's 2026 RAG analysis finds naive pipelines fail at retrieval ~40% of the time, with 73% of failures at the retrieval step rather than generation — "Retrieval quality beats model quality."
- **Engineering analysis:** AgentEngineering (April 2026) documents that fixed-size chunking bisects sentences, separates headings from content, and splits code across function boundaries — all retrievable but practically useless.
- **Practitioner deep-dive:** Ruchit Suthar's production RAG analysis (June 2026) finds hybrid search with RRF combines vector recall with BM25 precision, and re-ranking top-20 → top-5 reduces context window noise while preserving coverage.

## Gotchas

- **Overlapping chunks add noise, not recall.** Overlap helps at boundaries but compounds context pollution. 10-15% overlap is sufficient; more than that degrades answer quality.
- **Embedding model matters more than vector DB choice.** The same document chunked identically, embedded with a domain-specific model (e.g., bge-m3 for code, sentence-transformers for prose) consistently outperforms generic OpenAI embeddings in production evals.
- **Naive RAG "works" in demos because demos use the same vocabulary.** Production queries from real users introduce vocabulary drift, multi-part questions, and conversational context that embeddings handle poorly without hybrid search.
- **Re-ranking adds latency.** A cross-encoder rerank of 20 → 5 adds ~200-400ms. Teams that skip it because it "slows things down" are trading 400ms for consistent answer quality degradation on complex queries.
