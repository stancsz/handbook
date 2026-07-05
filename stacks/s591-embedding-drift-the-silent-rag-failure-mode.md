# S-591 · Embedding Drift: The Silent RAG Failure Mode

Retrieval works perfectly — no errors, no alerts, high similarity scores — but the wrong chunks rank first. Answer quality degrades over weeks before anyone notices.

## Forces
- **RAG retrieval is geometry-dependent and brittle to change.** The cosine similarity that powers vector search only works when query and document embeddings live in the same geometric space. When that space shifts, similarity scores become meaningless — without throwing a single error.
- **Teams pin the embedding model but not the pipeline.** Pinning model version is necessary but insufficient. Chunking strategy, preprocessing, and embedding dimensionality also shape the vector space, and any change to them silently corrupts retrieval.
- **Embedding staleness is invisible by design.** Vector search returns something on every query. High cosine similarity gives false confidence. The system degrades gradually — recall dropping from 0.92 to 0.74 — until a customer flags a wrong answer weeks later.
- **Re-indexing is expensive, so teams avoid it.** Full corpus re-embedding is the natural fix, but it's cost-prohibitive at scale, so teams patch around it instead of solving it.

## The move

**Pin the full embedding pipeline, not just the model version.**

1. **Version everything in the embedding stack.** Lock the embedding model, chunking strategy, preprocessing pipeline, and dimensionality reduction config. Tag each version. Store version metadata alongside every vector in the database.

2. **Version your vectors.** Don't overwrite the production index when upgrading. Keep old vectors tagged with the old pipeline version. Query against the version matching the current pipeline.

3. **Detect drift with a fixed test set.** Maintain a golden corpus of 50–100 documents with known relevant queries and expected top chunks. Run retrieval quality on this set weekly. Alert when recall drops below your baseline threshold — this is your canary for embedding drift.

4. **Use hybrid search as drift resistance.** Combine dense vectors (embeddings) with sparse retrieval (BM25 / keyword). When embedding geometry drifts, keyword overlap still retrieves relevant documents, reducing the blast radius.

5. **Track document freshness per-chunk.** Store the embedding timestamp on each vector. Alert when average staleness exceeds a threshold (e.g., 30 days). Prioritize re-embedding for frequently-queried chunks.

6. **Plan re-indexing as a routine operation, not an emergency.** Schedule quarterly full re-embeddings. Treat it like database migrations — versioned, tested, rollback-capable.

## Evidence
- **Blog (Ortem Technologies, May 2026):** Embedding staleness causes recall to drop silently from 0.92 to 0.74 in production systems with no errors or alerts. The fix requires pinning the full pipeline (model + chunking + preprocessing) and versioning vectors. — [https://ortemtech.com/blog/embedding-staleness-corrupting-rag-system-2026](https://ortemtech.com/blog/embedding-staleness-corrupting-rag-system-2026)
- **Conference talk (AI in Production 2025):** Digits engineer observed "silent embedding drift" as a core production RAG challenge — re-indexing is prohibitively expensive at scale, so systems slowly degrade. Proactive freshness tracking per document was the recommended approach. — [https://digits.com/blog/ai-in-production-2025](https://digits.com/blog/ai-in-production-2025)
- **Engineering blog (DigitalOcean, 2026):** RAG systems fail in production when evaluation only checks final answer quality, not retrieval quality separately. Recommended fix: separate retrieval metrics (context precision, recall) from generation metrics (groundedness, faithfulness), and run fixed test sets before and after any pipeline change. — [https://www.digitalocean.com/community/conceptual-articles/why-rag-systems-fail-in-production](https://www.digitalocean.com/community/conceptual-articles/why-rag-systems-fail-in-production)

## Gotchas
- **Pinning the model alone is not enough.** Changing chunk size, overlap percentage, or preprocessing (e.g., removing special characters, changing case normalization) all reshape the vector space and break existing embeddings.
- **Similarity scores are relative, not absolute.** A score of 0.87 means nothing without knowing what the top-k looked like last month. Track ranking position on a fixed query set, not raw scores.
- **Hybrid search hides the drift signal.** BM25 rescuing retrieval quality means you won't notice embedding drift via answer quality — but your vector store is still silently corrupted for new queries that don't have keyword overlap.
- **Re-embedding a live index mid-pipeline corrupts it in real time.** Never mix old and new embeddings in the same index. Use a shadow index, validate, then swap atomically.
