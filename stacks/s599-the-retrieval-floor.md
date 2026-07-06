# S-599 · The Retrieval Floor

Agents fail at the retrieval layer before they fail anywhere else. Teams obsess over model choice and orchestration topology, then ship a naive similarity search that retrieves irrelevant chunks, and wonder why their "intelligent" agent confidently hallucinates. In production, retrieval quality is the floor you cannot fall below — no amount of model sophistication compensates for a bad context.

## Forces

- **Naive embedding + top-k similarity gets you to ~70% on a demo.** The remaining 30% lives entirely in the retrieval pipeline, not the model. Teams discover this when production traffic hits and the success rate collapses.
- **The demo/production gap in retrieval is larger than in any other layer.** Test data is clean, queries are anticipated, and context fits in the chunk. Real users ask things you never trained for, in formats you never indexed, over documents that weren't designed for retrieval.
- **Retrieval quality beats model quality as an optimization target.** A $2/million-token model with excellent retrieval outperforms a $15 model with mediocre retrieval — at a fraction of the cost.

## The Move

Build the retrieval pipeline as a first-class system, not an afterthought. Three levers close the gap from demo to production:

- **Chunk on structure, not character count.** Fixed-size chunking (512 tokens, 256 overlap) destroys semantic boundaries. Split on markdown headers, code blocks, sentence boundaries, or semantic paragraphs instead — preserving the unit of meaning the user is actually querying.
- **Hybrid search is table stakes, not a nice-to-have.** Pure vector search misses exact keyword matches; pure BM25 misses semantic similarity. Production pipelines combine both (typically weighted 0.6–0.8 vector / 0.2–0.4 keyword) and re-rank the merged candidate set with a cross-encoder. Naive RAG fails 40% of the time at retrieval; hybrid closes most of that gap.
- **Over-fetch and re-rank.** Fetch 20–50 candidates, not 3–5. A re-ranker (cross-encoder or ColBERT-style) scores relevance against the full query, not just embedding similarity. This is where naive pipelines plateau.
- **Store metadata and filter aggressively.** Topic tags, recency, document type, access level — filter before vector search rather than scoring irrelevant documents down. Reduces noise in the final context window.
- **Eval retrieval independently.** Use RAGAS, Trulens, or custom retrieval recall metrics. Treat recall and MRR as first-class metrics, not model quality. A model can only answer correctly if the right facts were in the context.
- **Agentic RAG: retrieve-think-retrieve.** For complex queries, a planning agent decides whether to retrieve more, which query reformulation to use, and when the context is sufficient — rather than a single one-shot retrieval.

## Evidence

- **RAG Production Guide:** "Naive RAG gets you a 70%-quality demo and a plateau. The gap to production is three retrieval levers most teams never pull: chunking on structure (not character counts), hybrid search (vector + keyword), and re-ranking an over-fetched candidate set." — [Lushbinary RAG Production Guide 2026](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)
- **Ruchit Suthar's Production Deep Dive:** "Retrieval quality beats model quality." Documents the three-lever framework (structured chunking, hybrid search, re-ranking) with benchmarks showing 30%+ retrieval quality improvements over naive pipelines. — [RAG in Production: Chunking, Re-ranking & Hybrid Search](https://ruchitsuthar.com/blog/software-architecture/rag-in-production-chunking-reranking-hybrid-search)
- **Agent Engineering Blog:** "The gap between a retrieval system that 'works in a demo' and one that survives production is almost entirely in the retrieval pipeline." Recommends agentic RAG (retrieve-think-retrieve loops) for complex multi-hop queries. — [RAG for Agents — Agent Engineering](https://www.agentengineering.io/topics/articles/rag-for-agents)
- **Calder's Lab Cost Analysis:** Test environment: 92% success rate (clean, predictable retrieval). Production: 55% success rate — attributed primarily to 47 different data format issues the retrieval pipeline never anticipated. — [AI Agent 2025 Breakthrough: $847/Month in Production](https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/)

## Gotchas

- **Adding a more powerful model does not fix retrieval failures.** Teams routinely upgrade from GPT-4 to Claude 3.5 to o3 hoping to close the accuracy gap. The failure is upstream.
- **Over-indexing creates recall at the cost of precision.** More chunks = more noise = lower answer quality despite higher recall. Quality-aware chunking beats volume.
- **Re-rankers add latency.** Cross-encoder re-ranking adds 100–500ms per query in typical setups. Budget for it in real-time use cases or cache re-ranker scores for high-frequency queries.
- **Retrieval eval is not optional.** Without measuring recall@20 and MRR on a held-out query set, you have no signal on whether your pipeline is improving. Add evals before you need them, not after you notice degradation.
