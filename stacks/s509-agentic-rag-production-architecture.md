# S-509 · Agentic RAG: From Retrieval Theater to Production Recall

Standard RAG demos work. Production RAG fails silently — wrong chunks surface, dense-only search misses keyword-heavy queries, rerankers degrade latency, and the agent treats all retrieval failures the same. The shift from naive RAG to agentic RAG is the move from "fetch top-k chunks" to "decide what to retrieve, how, and when."

## Forces

- **Dense embeddings miss lexical queries:** Pure vector search excels at semantic similarity but fails on specific IDs,型号 numbers, error codes, and proper nouns. Keyword searches return nothing while conceptually similar documents rank high — and vice versa.
- **Chunk boundaries are arbitrary:** Splitting by token count or sentence boundaries creates chunks that split concepts mid-thought. The LLM gets half a table or a paragraph that starts mid-argument. Retrieval relevance suffers.
- **Static retrieval ignores query intent:** Naive RAG always retrieves the same way regardless of whether the user wants a comparison, a procedure, or a definition. One-size retrieval flattens query diversity.
- **Rerankers trade latency for quality:** Cross-encoder rerankers can double end-to-end latency. Teams either skip reranking and accept lower quality, or add it and miss SLA targets. The sweet spot is conditional reranking.
- **Agent context overflow kills recall:** Feeding retrieved chunks directly into the agent context window without filtering causes the model to reason over irrelevant content, degrading the answer quality it should improve.

## The Move

### 1. Hybrid search with Reciprocal Rank Fusion (RRF)

Combine dense (embedding) and sparse (BM25/keyword) retrieval, then fuse results with RRF. The formula: `score = Σ 1/(k + rank_i)` where k=60 suppresses rank noise. Dense captures conceptual matches; sparse captures exact matches. RRF combines them without requiring a separate training step.

```python
# RRF fusion across dense + sparse result sets
def rrf_fusion(dense_results, sparse_results, k=60):
    fused = {}
    for rank, doc_id in enumerate(dense_results):
        fused[doc_id] = fused.get(doc_id, 0) + 1 / (k + rank + 1)
    for rank, doc_id in enumerate(sparse_results):
        fused[doc_id] = fused.get(doc_id, 0) + 1 / (k + rank + 1)
    return sorted(fused, key=fused.get, reverse=True)
```

### 2. Q&A-augmented chunking

Instead of arbitrary chunking, pre-process documents into question-answer pairs. Store both the question and the answer chunk. At query time, embed the user question and retrieve against the question field — the embedding space now measures question-to-question similarity, which is semantically closer to actual information need than passage-to-question similarity.

This approach (documented in production RAG systems at onseok.github.io, March 2026) outperforms naive chunking on direct-answer queries because retrieval matches query type to content type.

### 3. Conditional reranking

Not every query benefits from a cross-encoder rerank. Gate it: if the top-1 dense+sparse fused result has a score significantly higher than top-2, skip reranking (confidence is already high). Only invoke the reranker when recall ambiguity exists — typically when top results are near-tied. This cuts the reranker call rate by 60-80% while preserving quality gains on ambiguous queries.

### 4. Agentic retrieval — the agent decides the strategy

Move retrieval logic inside the agent loop. Instead of a fixed retrieval pipeline, the agent analyzes each sub-question and selects: keyword search, semantic vector search, metadata filter (date, author, product), or skip retrieval (already in context). This is the 2026 production pattern replacing "naive RAG" and even "advanced RAG."

The agent gets a tool per retrieval mode. It chooses dynamically based on the query type. One query might trigger vector search; the next might trigger a filtered database lookup — both feeding the same answer synthesis step.

### 5. Context window hygiene at retrieval

Never feed all retrieved chunks to the agent. Rank retrieved chunks by relevance score, then truncate to a token budget (e.g., 4,000 tokens). Pass only the top-ranked, not all results above a score threshold. Score-aware truncation prevents context pollution from marginally-relevant chunks.

## Evidence

- **Production RAG engineering:** onseok.github.io documents hybrid search with RRF, the reranker latency trap, Q&A-augmented chunking, and agentic retrieval as the evolved production pattern replacing naive/advanced RAG — [Building a Production RAG System](https://onseok.github.io/posts/building-production-rag-system/), March 2026
- **Industry adoption:** IBM Developer confirms chunking quality determines RAG system quality more than embedding model selection — [Enhancing RAG Performance with Smart Chunking Strategies](https://developer.ibm.com/articles/awb-enhancing-rag-performance-chunking-strategies)
- **Token economics:** Cross-encoder reranking adds meaningful latency and cost; teams cutting reranker invocation rates via conditional gating recover 60-80% of reranker overhead — [Zylos Research: AI Agent Cost Engineering](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/)

## Gotchas

- **Q&A chunking triples preprocessing cost** — generating question-answer pairs for large corpora requires LLM calls on every document. Budget the preprocessing compute; it pays off in retrieval accuracy.
- **RRF k=60 is empirically standard but not universal** — some domains benefit from k=30-50. Benchmark with your actual query distribution, especially if you have heavy keyword queries vs. conceptual ones.
- **Hybrid search doubles your vector DB queries** — you now query dense and sparse independently. At scale, this means 2× query compute and 2× index storage. Factor this into your infrastructure cost model before going wide.
- **Agentic retrieval adds LLM calls per sub-question** — the agent decides which tool to call before calling it. This is one extra LLM turn per retrieval decision. For latency-sensitive applications, cache the retrieval strategy decision for repeated query types.
