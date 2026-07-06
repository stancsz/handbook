# S-659 · Production Agentic RAG

Naive RAG pipelines retrieve the wrong things 40% of the time in production. For agents that depend on grounded knowledge to take actions, bad retrieval is not a UX bug — it is a correctness failure that propagates through every downstream tool call, decision, and output.

## Forces

- **Vocabulary mismatch breaks dense embeddings.** Exact identifiers like `ISSUE-1234`, code snippets, and domain jargon live in sparse keyword space. Dense-only retrieval silently misses them.
- **"Lost in the middle" compounds at agent scale.** LLMs systematically underweight context in the middle of long prompts. Agents that retrieve 10+ chunks to be thorough often answer worse than agents that retrieve 3.
- **Rerankers are not always an upgrade.** Adding a cross-encoder reranker before generation feels like an obvious improvement — and it is, until your context window is already near capacity. Reranking adds latency and cost; the quality gain depends on your embedding model's baseline quality.
- **Agentic retrieval needs a loop, not a one-shot.** Static retrieval is fine for Q&A. Agents need conditional retrieval — if the confidence is below threshold, re-query with a reformulated question — which most tutorials never implement.
- **MCP is the missing integration layer.** Connecting RAG retrieval to agent tool calling requires a transport layer. MCP has become that layer, with 97M+ monthly SDK downloads and 5,800+ servers as of early 2026.

## The move

Production agentic RAG uses a layered retrieval architecture purpose-built for agents that act, not just answer.

**1. Hybrid search with Reciprocal Rank Fusion (RRF).** Combine dense vector similarity (captures semantic intent) with BM25 sparse retrieval (captures exact terminology) using RRF to merge ranked results. This is not optional for agents working with code, IDs, or domain-specific language.

**2. Q&A-augmented chunking.** Before splitting documents into chunks, generate 3-5 question-context pairs per chunk and prepend them. This gives the embedding model signal about what questions each chunk answers, reducing retrieval failures on paraphrased queries. Implement at index time; zero inference cost at query time.

**3. Agentic retrieval loop.** Wrap retrieval in a confidence-gated loop: agent queries, retrieves top-k, evaluates whether context answers the question (via a lightweight judge or semantic similarity threshold), and re-queries with a reformulated question if confidence is low. Cap at 2-3 iterations to prevent runaway loops.

**4. Top-3 hard limit with expand-before-truncate.** Retrieve 10 chunks, rerank to top-10, then aggressively truncate to top-3 before LLM context. This sounds wrong but consistently outperforms 10-chunk retrieval because of the "lost in the middle" effect. If the top-3 miss relevant content, the reranker is the problem, not the truncation.

**5. MCP-native retrieval tool.** Expose retrieval as an MCP tool rather than a direct API call. This standardizes the interface across agents, enables MCP's built-in permission and audit model, and allows the retrieval tool to receive agent context (conversation history, task state) as part of the MCP request.

**6. Cache at the query level, not the chunk level.** Semantic caching of retrieval queries (with threshold-based similarity matching) eliminates redundant vector searches for repeated or near-repeated agent queries. Most agentic workflows have high query overlap across turns.

## Evidence

- **Engineering blog:** Naive RAG fails approximately 40% of retrieval cases at production scale, with the dominant failure modes being vocabulary mismatch (exact terms missed by dense embeddings), lost-in-the-middle degradation in long contexts, and chunking artifacts that break semantic units — Gao et al. 2024 taxonomy mapped in production context — [Lushbinary — RAG Production Guide 2026](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)
- **Engineering blog:** Building a production RAG system serving internal engineering documents to LLM agents via MCP: Q&A-augmented chunking (generate question-context pairs before splitting) reduced retrieval failures on exact-ID queries by eliminating pure semantic matching gaps; MCP as the retrieval transport layer enabled standard tooling, audit logging, and consistent tool-calling signatures across all agents — [onseok — Building a Production RAG System](https://onseok.github.io/posts/building-production-rag-system)
- **Industry analysis:** Production RAG architecture patterns include hybrid search (BM25 + dense) as a baseline requirement for code and technical document retrieval, hierarchical chunking strategies that preserve document structure (section-level chunks with sub-chunk refinement), and RBAC-aware retrieval that filters results by the requesting agent's permissions layer — [Axiscoretech — RAG Architecture Patterns for Production](https://axiscoretech.com/blog/llm-agents/rag-architectures/)

## Gotchas

- **BM25 adds index size but is cheap at query time.** The storage overhead is significant (BM25 indexes can be 2-5x the raw text size) but the query latency overhead is typically <10ms. For agents with high retrieval volume, this pays off quickly.
- **Rerankers hurt when your embedding model is already strong.** If your base embedding model achieves >0.85 retrieval MAP, a cross-encoder reranker adds latency without proportional quality gains. Benchmark before committing.
- **Agent context injection into retrieval queries is non-obvious.** Passing the agent's conversation history or task state into the retrieval query requires careful prompt engineering — too much context pollutes the query vector, too little loses the thread.
- **MCP servers have a non-trivial attack surface.** 43% of public MCP servers were found to have command injection vulnerabilities in 2025 enterprise security surveys. Self-host the retrieval MCP server and audit its tool schemas before connecting to production agents.
