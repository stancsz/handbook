# S-284 · Silent RAG Failures Are Chunking Failures

RAG demos always work. Production RAG often silently fails — the model cites sources that don't exist, answers confidently about content that was split across chunk boundaries, or retrieves plausible but disconnected text. Teams blame the retriever, the embedder, or the model. The culprit is almost always upstream: how the documents were split.

## Forces

- **Naive chunking is invisible.** Fixed-size splits at 512 tokens with 50-token overlap look reasonable in demos. They split mid-sentence, mid-table-row, mid-code-block, and mid-heading — producing chunks that no retriever can assemble into coherent answers.
- **Chunk failures are silent.** Embedder failures page on-call. Chunking failures produce fluent, plausible, sourced answers that are completely wrong. The failure mode looks like hallucination and gets treated as a model problem.
- **The retriever inherits the chunker's mistakes.** A perfect vector search against garbage chunks returns garbage. You cannot out-engineer a broken chunker with a better embedder.
- **Chunk size is a quality-latency-cost tradeoff.** Smaller chunks = higher recall + more noise + higher per-query cost from more retrieved chunks. Larger chunks = better context coherence + higher recall of multi-paragraph relationships + risk of diluting signal with filler.

## The move

**Treat chunking as a first-class ML problem, not a preprocessing step.**

- **Use semantic chunking over fixed-size.** Split on document structure — headings, paragraphs, section boundaries — not token counts. Preserve the unit of meaning.
- **Use hybrid search + reranking in production.** Naive RAG fails ~40% of the time. Hybrid (dense + sparse / BM25) with a cross-encoder reranker consistently outperforms any single retrieval method. Cost: $0.005/query vs $0.001 for naive — worth it.
- **Preserve table and code context.** Tables need row/column headers attached to every cell chunk. Code needs surrounding function signatures and imports. Breaking a table mid-row or splitting a function from its docstring produces chunks that are locally coherent but globally meaningless.
- **Set chunk size by query type.** If your users ask detailed questions about specific clauses, use smaller chunks (256–512 tokens). If they ask summary questions, use larger chunks (1024–2048 tokens) that preserve paragraph-level coherence. Don't use one chunk size for all content types.
- **Validate chunk quality, not just retrieval metrics.** Run end-to-end RAG evals (RAGAS, G-eval, or LLM-as-judge) on realistic queries. Measure answer correctness against ground truth, not just cosine similarity of retrieved chunks.
- **Index metadata alongside embeddings.** Store heading, section, document ID, and page number in the chunk metadata. This enables filtered retrieval, citation verification, and source-grounded answers without additional lookups.

## Evidence

- **Blog (Alex Cloudstar):** RAG chunking failures are "silent" — fluent answers with plausible citations are produced from cross-boundary chunks. The fix (semantic chunking preserving document structure) outperforms fixed-size by a large margin in user satisfaction, not just retrieval metrics. — [alexcloudstar.com/blog/rag-chunking-strategies-production-2026](https://www.alexcloudstar.com/blog/rag-chunking-strategies-production-2026)
- **Blog (Lushbinary):** "When RAG fails, retrieval is the culprit 73% of the time — not generation." Naive RAG fails ~40% of the time at retrieval. Hybrid + reranking pattern is the minimum viable production approach. Agentic RAG ($0.02–0.10/query) reserved for high-stakes domains (legal, medical, financial). — [lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)
- **Blog (Tian Pan):** Production context pipeline assembles five layers at inference time: system instructions → retrieved knowledge → persistent memory → conversation history → tool definitions. The order matters — models pay disproportionate attention to context boundaries. RAG output must be filtered for relevance before insertion, not dumped raw. — [tianpan.co/blog/2025-10-23-ai-agent-architecture-production](https://tianpan.co/blog/2025-10-23-ai-agent-architecture-production)

## Gotchas

- **Overlap is a band-aid.** A 50-token overlap between 512-token chunks doesn't prevent splitting at heading boundaries or table rows. If a section heading is mid-chunk, both resulting chunks lack the heading context. Semantic boundaries are the real fix.
- **Re-ranking on the full context, not the reranked chunks alone.** Cross-encoder rerankers score relevance of candidate chunks, but they don't know what the user actually asked. Always pass the original query alongside the reranked chunks to the final generation step.
- **Chunk metadata drift.** As documents get updated, the chunks and their metadata can fall out of sync. A reindex strategy must handle document versioning or stale chunk artifacts will pollute retrieval indefinitely.
- **Over-retrieval dilutes signal.** Retrieving 20 chunks for a single query is common. Models suffer "lost in the middle" — accuracy drops sharply for information buried in the middle of long contexts. Cap at 5–8 chunks and trust the reranker to pick the most relevant.
