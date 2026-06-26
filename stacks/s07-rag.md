# S-07 · RAG

Retrieval-Augmented Generation: fetch the relevant slice of a large corpus and inject it as context, instead of trying to fit everything in the window or fine-tune.

## Forces
- You have more information than fits in a context window
- The model's training data is stale or doesn't include your private data
- Fine-tuning is expensive, slow, and overkill for knowledge lookup
- Retrieval adds latency and a new failure mode: bad retrieval → bad answer

## The move

**The loop:**
```
Query → [Embed query] → [Vector search in corpus] → [Retrieve top-K chunks]
     → [Inject chunks into context] → [LLM generates answer]
```

**Steps to implement:**

1. **Chunk your documents.** 512–1024 tokens per chunk with ~10% overlap. Too small = missing context; too large = diluted signal.

2. **Embed each chunk.** Use an embedding model (`text-embedding-3-small` from OpenAI, or a local `nomic-embed-text` via Ollama). Store vectors in a vector DB.

3. **At query time:** embed the query, retrieve top-K chunks by cosine similarity (K = 3–5 for most tasks).

4. **Inject and prompt:**
```
Answer the question using ONLY the context below.
If the answer isn't in the context, say "I don't know."

Context:
{retrieved_chunks}

Question: {query}
```

5. **Rerank:** retrieve wide, then re-score the shortlist with a cross-encoder for precision — one of the highest-ROI upgrades. See [S-27](s27-reranking.md).

**When RAG beats fine-tuning:**
- Knowledge changes frequently
- You need source citations
- Data is private and can't go into training
- Budget is limited

**When fine-tuning wins:**
- You need the model to behave differently (tone, format, task type)
- The knowledge is stable and the volume is large enough to train on
- Latency from retrieval is unacceptable

## Receipt
> Receipt pending — 2026-06-25. Pattern is well-established; specific chunk sizes and retrieval configurations should be tuned per corpus. Vector DB benchmarks change frequently — verify at ann-benchmarks.com before committing to a database.

## See also
[S-27](s27-reranking.md) · [S-17](s17-embeddings.md) · [S-31](s31-prompt-compression.md) · [S-09](s09-memory-systems.md) · [R-03](../frontier/r03-fine-tuning-vs-prompting.md) · [S-33](s33-live-data-vs-stale-snapshots.md)

## Go deeper
Keywords: `RAG` · `vector database` · `Chroma` · `pgvector` · `Pinecone` · `Weaviate` · `FAISS` · `cross-encoder reranking` · `HyDE` · `RAGAS`
