# S-287 · RAG Retrieval Quality Beats Model Quality

Naive RAG — embed docs, vector search, top-k, stuff into prompt — gets you a 70% quality demo and then stalls. The gap to production is almost entirely in the retrieval pipeline, not the model. Most teams upgrade models when they should be fixing chunking.

## Forces

- **Retrieval is the bottleneck, not generation.** A frontier model with poor context produces confident, polished garbage. A mediocre model with excellent context answers correctly.
- **Naive vector search has three known failure modes.** Vocabulary mismatch (exact terms like `ISSUE-1234` get missed by dense embeddings), "lost in the middle" (LLMs deprioritize context in the middle of long prompts), and chunking artifacts (arbitrary splits break semantic units).
- **Chunking is the highest-leverage, most-neglected optimization.** Teams spend weeks tuning the model and days on the retriever. The split point should follow document structure, not character counts.
- **Hybrid search is the default answer for retrieval gaps.** Dense (vector) + sparse (keyword) with Reciprocal Rank Fusion outperforms either alone — but only if you over-fetch candidates before reranking, not after.
- **Re-rankers can hurt if applied wrong.** Applying a cross-encoder reranker directly to top-k from a vector DB degrades quality — you need to over-fetch (top-50 or top-100), then rerank, then truncate to final top-k.

## The move

Three levers that reliably close the demo-to-production gap:

- **Chunk on structure, not counts.** Use document hierarchy (headings, sections, tables, code blocks) as chunk boundaries. Match chunk strategy to document type — a changelog benefits from entry-level chunks; a policy doc from section-level. Semantic chunking (embedding gradient breaks) beats fixed-size overlap.
- **Deploy hybrid search + RRF.** Combine dense retrieval (semantic similarity) with sparse retrieval (BM25 keyword matching). Fuse with Reciprocal Rank Fusion: `score = Σ 1/(k + rank_i)` where k=60. This handles both semantic intent and exact terminology.
- **Over-fetch, then rerank.** Retrieve 50–100 candidates, apply a cross-encoder reranker (e.g., `bge-reranker-v2-m3` or `cohere-rerank`), then truncate to top-5. Skipping the over-fetch step means the reranker has no room to exercise its pairwise preference.

## Evidence

- **Blog post:** "RAG in Production: Chunking, Re-ranking, and Hybrid Search" — documents the three-lever model with production benchmarks; explicitly states "retrieval quality beats model quality" as the core thesis — [Ruchit Suthar](https://ruchitsuthar.com/blog/software-architecture/rag-in-production-chunking-reranking-hybrid-search)
- **Engineering post:** "Building a Production RAG System: From Hybrid Search to Agentic Retrieval" — details hybrid search with RRF, Q&A-augmented chunking, and the vocabulary mismatch problem from real internal document systems via MCP — [onseok](https://onseok.github.io/posts/building-production-rag-system)
- **Guide:** "RAG in 2026: The Complete Production Guide" — finds naive pipelines fail 40% of the time at retrieval; covers agentic RAG, RAGAS evaluation, and production patterns — [Lushbinary](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide/)

## Gotchas

- **Over-fetching without a reranker just adds noise.** Top-100 from a vector DB without reranking is worse than top-5 — you've diluted signal with irrelevant candidates.
- **Cross-encoder rerankers are expensive per call.** Budget for ~5–10ms per document in the candidate set. This is fine for 50–100 candidates per query but doesn't scale to naive top-k retrieval at query time without batching.
- **Context window management is a retrieval problem, not a model problem.** Teams reach for 128k context models when the real fix is better top-k precision — the model answers better from 5 relevant chunks than from 50 loosely relevant ones.
