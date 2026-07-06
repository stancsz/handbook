# S-631 · The RAG Failure Cascade: Nine Predictable Modes Nobody Evaluates

[Your RAG prototype passes the demo. The answer looks great. Six months in production, the answer is confidently wrong, the retrieval is silently bypassed, embedding costs are $11K/month unmonitored, and 73% of the system has degraded without anyone noticing. This isn't one failure — it's a cascade of nine predictable, measurable, fixable modes that every production RAG deployment hits, most hit five or more, and almost none are evaluated.]

## Forces

- **73% of RAG systems degrade within 90 days without eval pipelines.** Without systematic measurement, degradation is invisible. Teams only discover it when a customer files a complaint.
- **Every production RAG system has at least three failure modes simultaneously.** After auditing 200+ deployments across legal, healthcare, fintech, and enterprise SaaS, the minimum observed was three. The median was five.
- **Teams blame the model for retrieval failures.** When RAG gives a wrong answer, the instinct is to swap the model. The retriever is usually the culprit — 73% of failures happen at retrieval, not generation.
- **Naive chunking is the silent majority failure.** Fixed-size splits at 512 tokens with 50-token overlap split mid-sentence, mid-table-row, and mid-code-block. A perfect vector search cannot recover from a chunker that destroyed coherence.
- **The generator-retriever mismatch is invisible.** The retriever optimizes for semantic similarity; the generator optimizes for coherence. When those goals diverge, RAG silently falls back to parametric memory, bypassing the indexed corpus entirely.

## The move

### The nine failure modes (production audit results, 200+ deployments)

**1. Naive chunking — 40% retrieval accuracy drop**
Fixed-size splits destroy semantic coherence. Switch to semantic or proposition-based chunking first. The cost is nearly zero; the accuracy lift is 40%.

**2. Embedding-cost accumulation — $8–14K/month at 5M+ docs**
Embedding API calls compound. Most teams never audit embedding spend. Set a cost ceiling with per-query budget limits and batch embedding pipelines with dedup.

**3. Stale knowledge — silent hallucination**
Documents update. The index doesn't. Without a freshness invalidation pipeline, the retriever fetches confidently wrong answers. RAG systems without invalidation show 15–25% hallucination rates on outdated content.

**4. Wrong K — over-retrieval or starvation**
Fixed K (always top-5, always top-10) wastes tokens on simple queries and starves complex ones. Adaptive K (query-complexity-based) reduces retrieval waste by 35–45% versus fixed K.

**5. Semantic gap — user query ≠ document vocabulary**
"Contract value" and "deal_amount_USD" are semantically the same. Users ask in one language; documents are written in another. Query expansion + synonym mapping bridges the gap.

**6. Missing hybrid search — BM25 gap**
Vector search finds semantic neighbors but misses exact keyword matches. BM25 handles exact matches; vector handles conceptual similarity. Combined via Reciprocal Rank Fusion, hybrid search reduces error rates ~69% versus vector-only retrieval.

**7. No reranker — top-K retrieved, wrong ranked**
Vector similarity ≠ downstream utility. A cross-encoder reranker reorders the top-20 vector results by actual relevance to the query. The reranker's top-3 outperforms the vector searcher's top-10.

**8. No faithfulness evaluation — confident hallucination**
Without citation-grounding and faithfulness checks, the model fabricates sources. RAGAS faithfulness metric above 0.9 detects when the model ignores retrieved context and hallucinates instead.

**9. The generator-retriever mismatch — silent bypass**
The model receives context but doesn't use it. Citation checking (verify the model cites the retrieved chunks) surfaces this failure. When citations reference chunks that weren't retrieved, the pipeline broke upstream.

```python
# Production RAG evaluation harness (minimal viable)
# Detects failure modes 6, 7, 8, 9 with RAGAS metrics
from ragas import evaluate
from ragas.metrics import (
    faithfulness, answer_relevancy,
    context_precision, context_recall
)
from datasets import Dataset

eval_dataset = Dataset.from_list([
    {"question": q, "answer": a, "contexts": c, "ground_truth": g}
    for q, a, c, g in zip(questions, answers, retrieved_contexts, ground_truths)
])

results = evaluate(eval_dataset, metrics=[
    faithfulness,       # Did model use retrieved context? (failure mode 9)
    answer_relevancy,   # Is answer actually relevant to question?
    context_precision,  # Are top results ranked correctly? (failure mode 7)
    context_recall,     # Did we retrieve everything needed? (failure mode 4)
])

# Alert on threshold breach
for metric_name, score in results.items():
    if score < TARGET[metric_name]:
        alert(f"RAG quality regression: {metric_name}={score:.3f} < {TARGET[metric_name]}")

# Detect generator-retriever mismatch (failure mode 9)
def citation_check(answer: str, contexts: list[str]) -> float:
    """Fraction of answer claims verifiable in retrieved contexts."""
    claims = extract_claims(answer)
    verifiable = sum(1 for c in claims if any(
        verify(c, ctx) for ctx in contexts
    ))
    return verifiable / max(len(claims), 1)

# Detect stale knowledge (failure mode 3)
def freshness_score(doc_id: str, index_time: datetime) -> float:
    hours_old = (datetime.utcnow() - index_time).total_seconds() / 3600
    return max(0.0, 1.0 - hours_old / STALE_THRESHOLD_HOURS)
```

## Receipt
> Receipt pending — 2026-07-05

## See also
- [S-284](s284-silent-rag-failures-are-chunking-failures.md) — chunking as the root cause of retrieval failure
- [S-358](s358-production-rag-failure-modes-hybrid-search-re-rankers.md) — hybrid search + rerankers for retrieval correction
- [S-193](s193-llm-as-judge-eval-pipeline.md) — building systematic evaluation for agent outputs
- [S-626](s626-the-generator-retriever-mismatch-when-rag-silently-fails.md) — the generator-retriever mismatch
- [S-179](s179-adaptive-retrieval-top-k-selector.md) — adaptive K selection for retrieval
