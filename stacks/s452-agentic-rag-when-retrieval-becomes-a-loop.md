# S-452 · Agentic RAG: When Retrieval Becomes a Loop

Classic RAG retrieves once, generates once, and calls it done. That works for single-hop lookups — "what's our refund policy?" But when questions are ambiguous, multi-part, or require synthesis across sources, a single retrieval pass is a coin flip. Agentic RAG wraps retrieval in a self-correcting loop: the agent retrieves, evaluates relevance, decides whether to retrieve more, rewrites the query if needed, and gates the final answer against a faithfulness judge. The hard part is knowing when this loop is worth the latency and token cost — and how to prevent it from spinning forever.

## Forces

- **Naive RAG under-retrieves on hard questions.** One top-k retrieval on a multi-hop question ("how did Q3 margins compare to Q1, adjusting for the acquisition?") often misses the documents that would answer the second half.
- **Agentic loops over-retrieve on simple questions.** Adding 3-8 LLM calls and 2-6 retrievals to a question that a single retrieval would answer burns latency (2-5x) and tokens with no quality gain.
- **Faithfulness failures are invisible without a judge.** An agent can retrieve 8 chunks, use 6, and invent a fact from the remaining 2 without any span scoring low. No self-check loop means no catch.
- **Query rewriting is the highest-leverage step most teams skip.** The user's query is rarely the best retrieval query — but rewriting adds latency and complexity, so teams skip it until users complain.

## The move

The pattern: retrieval → evaluation → conditional loop (rewrite or re-retrieve) → faithfulness gate → generate.

- **Route by question type, not default.** Start every RAG system as classic (1 retrieve, 1 generate). Graduate specific query patterns to agentic retrieval — multi-hop, ambiguous, comparative, or requiring synthesis. Log which pattern fired and why.
- **Always rewrite the query before retrieving.** Extract the actual information need, expand with synonyms or sub-questions, strip user noise. This single step often improves retrieval precision more than any embedding model change.
- **Use a relevance judge after retrieval.** Score each chunk: is this actually answering the (rewritten) question? Drop low-scoring chunks before generation. This is cheap (small model, binary score) and eliminates a major hallucination path.
- **Set a hard step budget — then halve it.** If you budget 6 retrieval steps, run the system with 3. Over-retrieval loops are more common than under-retrieval in agentic RAG, and they compound token costs fast.
- **Gate the final answer with a faithfulness judge.** After generation, score: does the answer stay within what the retrieved chunks actually support? If the judge flags a span, either re-retrieve or surface uncertainty — don't ship the fabrication.
- **Cache at the retrieval level, not the answer level.** Cache the retrieved chunks (by query hash) so that repeated question patterns hit the cache without re-running the LLM-in-the-loop. Vector DBs like Qdrant and Pinecone support this cheaply.

## Evidence

- **Engineering blog:** Agentic RAG (2026) shows classic RAG achieves ~60% task completion on multi-hop queries while agentic RAG reaches ~85% — but at 3-8x the LLM calls and 2-5x latency. Key lever: query decomposition before the first retrieval, not after. — [futureagi.com/blog/agentic-rag-systems-2025](https://futureagi.com/blog/agentic-rag-systems-2025)
- **Engineering blog:** RAG production architecture (Dec 2025) documents three primary failure layers: wrong chunks (vector search misses exact matches), wrong generation (model ignores relevant chunks), and wrong access control (RBAC/ABAC gaps in multi-tenant). The chunking strategy — recursive 512-token with 20% overlap — outperforms fixed 256/512 splits on nearly all document types tested. — [axiscoretech.com/blog/llm-agents/rag-architectures](https://axiscoretech.com/blog/llm-agents/rag-architectures)
- **Engineering blog:** Production RAG guide (Apr 2026) reports naive pipelines fail ~40% of the time at retrieval in production, with the gap being a system design problem — chunking strategy, hybrid search (BM25 + dense vectors), and re-ranking with a cross-encoder (Cohere rerank or BGE-reranker) — not a model problem. — [lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)

## Gotchas

- **Don't route all queries agentic by default.** The latency and cost premium only pays off on hard questions. Build a classifier (even a simple keyword or embedding-similarity heuristic) to route.
- **A faithfulness judge is not the same as an answer quality judge.** Faithfulness = does the answer stay within retrieved evidence. Quality = is the answer useful and well-written. Most teams conflate these and get a judge that doesn't catch hallucinations.
- **Re-ranking before generation is almost always worth it.** A cross-encoder rerank on top-20 dense+BM25 results, reduced to top-5, consistently outperforms dense retrieval alone in production. The latency cost (~200ms) is acceptable for most use cases.
- **Hybrid search (dense + sparse) is table stakes for production RAG, not optional.** Dense-only retrieval misses exact-matches on proper nouns, IDs, and technical terms. BM25 handles these. Both together beats either alone.
