# S-49 · Retrieval Evaluation

A RAG pipeline has two failure modes: the model hallucinates, and the retriever doesn't find the right chunks. Eval suites ([F-07](../forward-deployed/f07-evaluation-driven-development.md)) catch the first. Retrieval metrics catch the second. Without retrieval metrics, you can't tell whether a bad answer was the model's fault or the retriever's.

## Situation

A support bot gives inconsistent answers about enterprise pricing. The system prompt says to answer from retrieved docs. The eval suite passes — the model's answers look reasonable. The actual cause: chunk_077 (the enterprise pricing page) was never retrieved for pricing queries — its embedding was too close to the "billing FAQ" cluster and always lost in reranking. The model was doing its best with wrong context. A retrieval eval with Recall@5 would have caught it immediately.

## Forces

- Retrieval and generation are separate failure surfaces. The model can be good and the retriever bad; they need separate metrics. "The answer was wrong" doesn't tell you whether retrieval failed, the model failed, or the source doc was wrong.
- Recall@K is the primary retrieval metric for RAG. It asks: of the known-relevant chunks, what fraction appear in the top K results? For RAG, K is typically 3–5 (the number of chunks injected into context). A miss at K=5 means the model never had access to the right information.
- Precision@K matters when context length is limited. If you inject K=3 chunks and only one is relevant, the model must reason around noise. Precision@3 = 0.33 is costly — you're paying for 3 chunks of context and two are distractors.
- MRR (mean reciprocal rank) tells you where relevant chunks land. MRR = 0.50 means the first relevant chunk is at position 2 on average. For single-relevant-doc queries, MRR is the right primary metric.
- The labeling bottleneck is real but bounded. You need labeled (query, relevant_chunk_ids) pairs. Labeling 50–100 pairs by hand or with an LLM judge ([F-12](../forward-deployed/f12-llm-as-a-judge.md)) costs $5–20 and is a one-time investment. Without labels, you're tuning by intuition.
- Retrieval metrics must be re-run after every corpus change. Adding 500 new documents changes the embedding neighborhood and can displace previously well-ranked chunks. Treat the retrieval eval suite as a regression test, not a one-time measurement.

## The move

**Build a labeled test set and compute Recall@K, Precision@K, and MRR before shipping and after every corpus update.**

**Step 1 — Build the test set.**
For each representative query type, identify which chunk(s) in your corpus are the ground-truth relevant ones:
```js
const testCases = [
  {
    query:    'What is the refund policy?',
    relevant: ['chunk_012', 'chunk_089'],  // IDs of ground-truth chunks
  },
  // ... 50-100 total cases
];
```

Label manually for high-stakes queries; use an LLM judge for the bulk:
```
Judge prompt: "Is this document chunk relevant to answering the query? Answer yes or no."
```

**Step 2 — Run retrieval and compute metrics.**
```js
function recallAtK(retrieved, relevant, k) {
  const topK = new Set(retrieved.slice(0, k));
  return relevant.filter(r => topK.has(r)).length / relevant.length;
}

function precisionAtK(retrieved, relevant, k) {
  const topK = retrieved.slice(0, k);
  return topK.filter(r => relevant.includes(r)).length / k;
}

function mrr(retrieved, relevant) {
  const idx = retrieved.findIndex(r => relevant.includes(r));
  return idx === -1 ? 0 : 1 / (idx + 1);
}

// Run for each test case, average across the suite
const results = testCases.map(tc => {
  const retrieved = retriever.search(tc.query, k=5).map(r => r.id);
  return {
    recall3:    recallAtK(retrieved, tc.relevant, 3),
    recall5:    recallAtK(retrieved, tc.relevant, 5),
    precision3: precisionAtK(retrieved, tc.relevant, 3),
    mrr:        mrr(retrieved, tc.relevant),
  };
});
```

**Step 3 — Set thresholds and act on misses.**

| Metric | Target | Below target → action |
|---|---|---|
| Recall@5 | ≥ 0.85 | Find missed queries; inspect missed chunks |
| Precision@3 | ≥ 0.50 | Reduce noise chunks; improve chunking strategy |
| MRR | ≥ 0.70 | Improve ranking; add reranker ([S-27](s27-reranking.md)) |

**When Recall@5 misses a query: diagnose before tuning.** Common causes:
1. **Chunk too coarse** — the relevant info is buried in a large chunk with other content. Rechunk more granularly.
2. **Missing metadata** — the chunk exists but has no signal connecting it to the query vocabulary. Add title/section as a prefix to the chunk text.
3. **Embedding blind spot** — the query term and the chunk term are semantically distant even though they mean the same thing (e.g. "cancel" vs "terminate subscription"). Add a synonym expansion layer or use a domain-tuned embedding model ([S-17](s17-embeddings.md)).
4. **Reranker error** — the chunk was retrieved at position 8 but reranked out of the top 5. Inspect the reranker score for the missed chunk.

## Receipt

> Verified 2026-06-26 — Node.js. Retrieval evaluation metrics computed exactly (no model calls needed — pure set operations on chunk IDs). Labeling cost estimate based on $0.05/LLM-judge call at 100 cases. Embedding search cost negligible ($0.0000002/query).

```
=== Retrieval evaluation: 5-query pilot test ===

Query                            Recall@3  Recall@5  Precision@3  MRR
What is the refund policy?         1.00     1.00       0.67       1.00
How do I cancel my subscription?   1.00     1.00       0.33       0.50
Is there a free trial?             0.50     1.00       0.33       0.50
Enterprise pricing options         0.00     0.00 ←     0.00       0.00  ← miss
GDPR data deletion request         1.00     1.00       0.67       1.00

Avg (macro):                       0.70     0.80       0.40       0.60

→ Query 4 failure: chunk_077 not in top-5 at all.
  Diagnosis: inspect chunk_077 embedding; check corpus neighborhood.

=== Cost ===
Labeling 100 test cases (LLM judge):  ~$5.00  (one-time)
Running 100-query eval suite:          $0.00002  (embedding queries only)
Re-running after corpus update:        $0.00002  (same cost, always cheap)
```

The key number: Recall@5 = 0.80 means 1 in 5 queries is sending the model into a context where the right information is absent. The model will do something with the wrong context — it may hallucinate, give a vague answer, or correctly say "I don't know." All three are worse than finding the right chunk.

## See also

[S-07](s07-rag.md) · [S-17](s17-embeddings.md) · [S-27](s27-reranking.md) · [F-07](../forward-deployed/f07-evaluation-driven-development.md) · [F-12](../forward-deployed/f12-llm-as-a-judge.md)

## Go deeper

Keywords: `retrieval evaluation` · `Recall@K` · `Precision@K` · `MRR` · `nDCG` · `RAGAS` · `RAG evaluation` · `retrieval metrics` · `chunk quality` · `embedding blind spot`
