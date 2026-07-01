# S-308 · Production RAG: The Three Levers You're Not Pulling

Naive RAG — embed docs, similarity search, top-3 into prompt — gets you a 70% demo and a plateau you cannot climb past. The gap between that and a production-grade retrieval system is three specific engineering decisions most teams never make: chunking on structure instead of character count, hybrid search instead of vector-only, and re-ranking an over-fetched candidate set before handing it to the LLM.

## Forces

- **Model quality is not the bottleneck in RAG.** A mediocre model with excellent retrieved context reliably beats a frontier model with poor context. Teams spend weeks evaluating LLMs and ship the retrieval pipeline in an afternoon — the leverage is in the pipeline, not the model.
- **Naive pipelines fail silently.** The LLM confidently restructures garbage context into fluent wrong answers. Retrieval failure looks like generation failure. You need end-to-end eval to know which layer to fix.
- **Context bloat compounds silently.** A system running for weeks accumulates 80–120K token context windows from accumulated history entries and retrieved chunks. Costs compound invisibly. Without measurement, you don't know what's burning your budget.
- **ACL and multi-tenancy filtering must be a pre-filter, not a post-filter.** Applying permissions after retrieval leaks data in the candidate set and adds latency. Do it at the vector DB query layer.

## The move

The three levers in order of impact:

1. **Chunk on structure, not character count.** Split on headers, paragraph boundaries, or semantic units — not fixed 512-token windows. Overlapping chunks (20–30% overlap) preserve cross-chunk meaning. For codebases, chunk on function or class boundaries. For legal docs, chunk on clause or section level. The right chunk size depends on your retrieval unit, not your model's context window.

2. **Use hybrid search, not vector-only.** Dense embeddings miss exact terms, proper nouns, product codes, and acronyms. BM25 (sparse) handles exact matches. Reciprocal Rank Fusion (RRF) combines both rankings. Retrieve N=50–100 candidates from the hybrid pipeline, then re-rank.

3. **Re-rank the candidate set with a cross-encoder before LLM consumption.** Bi-encoders (used for embedding) optimize for speed; cross-encoders optimize for relevance. Pass the over-fetched candidate set (top 20–50) through a cross-encoder re-ranker (e.g., BAAI/bge-reranker-v2-m3 or Cohere Rerank), then pass the top K (typically 3–10) to the LLM. This is where precision improves most.

Bonus lever — **ACL pre-filtering**: apply permission filters at the vector DB query layer, not as a post-processing step. Pre-filtering scales for multi-tenant RAG and avoids the data-leak failure mode.

**The retrieval pipeline order:** query transformation → hybrid retrieval (N=50–100) → cross-encoder re-rank → top-K → LLM. The LLM then answers from context that actually matches the query.

## Evidence

- **HN/Ask post — Cosmico's production switch from RAG to agentic search:** A team at Cosmico building with Claude Code switched from RAG to agentic search for better accuracy and lower hallucination rate, at higher cost per query. They report a clear shift from "2023: you need RAG" to "2026: agentic search outperforms RAG." — [Hacker News, Ask HN, 2025](https://news.ycombinator.com/item?id=47134263)

- **RAGie.ai engineering post — where classic RAG breaks:** "Classic RAG (embed and fetch) breaks when the source data isn't sufficient to answer a query. We spent a lot of time getting agents to refuse instead of hallucinate when the retrieved context doesn't support an answer." The fix: agentic retrieval with multi-step query planning, not one-pass retrieval. — [RAGie.ai Blog / HN Show HN, 2025](https://news.ycombinator.com/item?id=45658141)

- **Ruchit Suthar — RAG in Production deep dive:** Documents the three-lever thesis with production numbers. Key finding: "When I turn around a 'vague answers' RAG system, the fix is chunking more often than anything else. It's unglamorous but it's the lever." Also: "Garbage context, garbage answer — confidently phrased." Naive RAG achieves 70% quality and plateaus. — [Ruchit Suthar Blog, 2025](https://ruchitsuthar.com/blog/software-architecture/rag-in-production-chunking-reranking-hybrid-search)

- **Lushbinary — RAG Production Guide 2026:** Naive pipelines fail 40% of the time at retrieval. The guide documents hybrid search + agentic RAG + re-ranking as the production-ready stack. — [Lushbinary Blog, April 2026](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide/)

- **Simon Willison (HN comment, Feb 2025):** "The best vector retrieval implementations are already switching to a hybrid between vector and FTS, because it turns out BM25 is still a better algorithm for a lot of use-cases." — [Hacker News, 2025](https://news.ycombinator.com/item?id=43169099)

- **AppScale Blog — Hybrid + Re-ranking Production RAG 2026:** Covers RRF vs weighted convex combination vs calibrated fusion for combining sparse/dense rankings; cross-encoder vs bi-encoder architectural differences; latency budget breakdown of production hybrid + cross-encoder pipelines; and why ACL filtering should be a pre-filter not a post-filter. — [AppScale Blog, May 2026](https://appscale.blog/en/blog/hybrid-search-and-reranking-production-rag-bm25-dense-cross-encoder-2026)

## Gotchas

- **"Vague answers" is usually a chunking problem, not a model problem.** Before changing your LLM or tuning your prompt, audit your chunk boundaries. Overlapping chunks (20–30%) prevent signal from being split across boundaries.
- **Over-fetching then re-ranking is the right order.** Retrieving top-3 directly from vector DB is the most common mistake. You lose too many relevant candidates at the first-pass threshold. Retrieve 50–100, re-rank to 3–10.
- **Measure retrieval quality separately from generation quality.** Use RAGAS or Trulens to get retrieval-level precision/recall/F1. If retrieval Recall@K < 0.6, no amount of prompt engineering fixes it.
- **Cross-encoder latency is real.** Re-ranking 50 candidates with a cross-encoder adds 200–500ms. Budget for it. It's worth it, but you need to know where your latency budget goes.
