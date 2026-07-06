# S-320 · Agentic RAG: When Retrieval — Not Generation — Becomes the Bottleneck

Every AI roadmap in 2024 said "build a RAG pipeline." By 2025, teams discovered the bottleneck was never the LLM. It was the retrieval step sitting in front of it.

## Forces

- **Naive RAG fails ~40% of the time at retrieval in production.** The standard pipeline — embed, store, top-k, generate — works for demos. It breaks on exact-match queries (product codes, ticket IDs), low-frequency terms, and queries that don't match document vocabulary. "How do I cancel?" doesn't retrieve "Account Termination Policy."
- **The LLM layer has outpaced the retrieval layer.** Model context windows grew from 8K to 200K tokens. Embedding models improved. But teams kept using the same naive retrieval pipeline and wondering why answers were wrong.
- **Agentic RAG introduces new failure modes.** Agents that iterate on retrieval, route between tools, and self-correct introduce failure points naive pipelines don't have — and require eval infrastructure to catch.
- **The "lost in the middle" problem compounds with agents.** Retrieving 10 chunks works for a chatbot. An agent that retrieves, generates, retrieves again, and re-generates can pollute its context window with the same irrelevant chunks repeatedly, degrading output quality with each pass.

## The Move

Move the retrieval system from a static pipeline to an active, evaluated, agentic layer. The core shifts:

- **Hybrid search is now table stakes, not optimization.** Dense embeddings alone miss exact-match queries. Pair dense (semantic) with sparse (BM25 keyword) retrieval using Reciprocal Rank Fusion (RRF) to combine scores. Teams deploying this report significant recall improvements over dense-only pipelines.
- **Rerankers can help or hurt — test your cutoff.** A cross-encoder reranker reorders retrieved chunks by relevance to the query. In some architectures, the reranker improves top-1 accuracy but degrades the tail of the result list. Measure end-to-end answer quality, not just retrieval metrics.
- **Q&A-augmented chunking beats arbitrary splits.** Instead of splitting documents at fixed token boundaries, split on semantic boundaries (paragraphs, sections) and prepend a synthetic Q&A pair that captures what question each chunk answers. This closes the vocabulary gap between how documents are written and how users query them.
- **Self-check loops gate generation, not just retrieval.** The most common agentic RAG failure: an agent retrieves 8 chunks, uses 6, and fabricates a fact from none of them. No span scores low on faithfulness. A lightweight self-check step — "does this claim appear in the retrieved context?" — catches this. Without it, the agent has every framework feature except the one that prevents hallucination.
- **Step and token budgets with circuit breakers are non-negotiable.** Multi-pass retrieval loops can thrash indefinitely. Enforce hard limits on max retrieval steps and per-turn token counts. Budget the loop to maintain predictability.
- **Evaluate the pipeline end-to-end with RAGAS or TruLens.** Single-metric retrieval evaluation (recall@k) doesn't capture generation quality. RAGAS providesFaithfulness, Answer Relevancy, and Context Precision scores. TruLens adds a programmatic eval graph. Without automated eval, you discover failures from customers, not tests.

## Evidence

- **Engineering blog:** Onseok documented building a production RAG system across thousands of internal documents (engineering issues, SDK code, design specs) served to agents via MCP. The system evolved from "Advanced RAG" toward "Modular RAG" with pluggable retrieval components, noting that rerankers can degrade tail quality and hybrid search with RRF is essential for exact-match queries like `ISSUE-1234`. — [onseok.github.io/posts/building-production-rag-system](https://onseok.github.io/posts/building-production-rag-system)
- **Research report:** Lushbinary's 2026 RAG production guide found naive RAG pipelines fail approximately 40% of the time at retrieval in production. Key failure modes: semantic gap (vocabulary mismatch between queries and documents), context window pollution from over-retrieval, and chunking artifacts from arbitrary document splits. Recommends hybrid search + RRF + RAGAS evaluation as baseline. — [lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)
- **Engineering post:** FutureAGI's agentic RAG analysis documented a real production incident: a research agent retrieved 8 chunks, used 6, and fabricated a fact from none of them. No span scored faithfulness. No judge gated the answer. Root cause: self-check loops were absent. The post catalogs failure modes unique to agentic RAG — over-retrieval, under-retrieval, tool misrouting, judge drift, state contamination — that don't exist in classic RAG. — [futureagi.com/blog/agentic-rag-systems-2025](https://futureagi.com/blog/agentic-rag-systems-2025)
- **Framework comparison:** Tacavar's 2026 comparison of LangGraph, AutoGen, and CrewAI noted LangGraph's graph-based topology is well-suited for modular RAG pipelines where each retrieval step is a node, while CrewAI's role-based model maps naturally to specialist retrieval agents (one for documents, one for code, one for tickets). — [tacavar.com/blog/ai-agent-frameworks-compared-2026](https://tacavar.com/blog/ai-agent-frameworks-compared-2026)

## Gotchas

- **Don't rerank without measuring end-to-end.** Cross-encoder rerankers improve first-pass retrieval quality but can hurt generation quality if the reranker isn't calibrated to your query distribution. Always measure answer correctness, not just retrieval precision.
- **Chunking strategy is higher-leverage than embedding model choice.** Teams obsess over switching from `text-embedding-3-small` to `text-embedding-3-large` when the real win is changing how documents are split. Semantic chunking with Q&A pre-generation consistently outperforms token-window splits.
- **Agentic RAG without eval is a hallucination amplifier.** Each agentic pass compounds retrieval errors into generation errors. You needFaithfulness-gated generation steps, not just better retrieval.
- **"Agentic" is not automatically better than classic RAG.** For single-hop queries (answer a question from a document), classic RAG with hybrid search outperforms agentic RAG. Splitting into agents only pays off for multi-hop queries where different retrieval strategies are needed for different steps.
