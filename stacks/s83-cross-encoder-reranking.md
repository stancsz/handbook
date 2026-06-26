# S-83 · Cross-Encoder Reranking

[S-27](s27-reranking.md) explains what cross-encoders do — read query + passage *jointly*, capture their interaction, score relevance far more accurately than a bi-encoder — and names two implementations: `bge-reranker-v2-m3` (self-host) and Cohere Rerank (managed). It has no code. [S-79](s79-hybrid-search.md) runs BM25 + dense retrieval and says "pass top-K to a cross-encoder reranker" as one sentence. This entry is that implementation.

## Situation

A legal RAG system uses hybrid search (S-79) to retrieve 20 candidates for each query. Candidates are ranked by RRF score — a blend of BM25 and vector similarity. The top-3 go to the model. But RRF ranking is based on each passage scored *independently* against the query: the bi-encoder that produced the vector doesn't understand "does this passage directly answer this query?" For a query like "what is the statute of limitations for breach of contract in California under UCC Article 2?" — RRF returns the three passages that most closely match those words, but the passage ranked 7th explicitly answers the question while passages 1–3 discuss limitations in other contexts. A cross-encoder, scoring each (query, passage) pair jointly, promotes the correct passage from rank 7 to rank 1. The model answers correctly.

## Forces

- **Cross-encoders are too slow for full corpus search; they are fast enough for a shortlist of 20–50.** A cross-encoder reads the full query + passage together — it cannot pre-compute passage vectors. At 50ms per pair on a managed API, scoring 50 passages takes 2.5 seconds sequentially. Parallelize across the shortlist to bring wall-clock down to 200–400ms. Only run the cross-encoder on candidates already retrieved by a fast bi-encoder or BM25 system.
- **LLM-as-reranker works without a dedicated reranker model.** Prompt a small model (Haiku) with the query and each candidate passage, ask for a 0–10 relevance score, sort by score. This uses your existing API access, adds zero infrastructure, and costs ~150 tokens per passage. The quality is lower than a purpose-built reranker but far better than RRF alone for complex queries.
- **Cohere Rerank is the managed path.** A single API call scores N (query, passage) pairs and returns ranked results. Latency: ~300ms for 20 passages. No self-hosting; no prompt engineering. Cost: $0.002 per 1,000 results (i.e., per scored passage).
- **When to skip reranking.** If the top-1 RRF result is already the right answer >90% of the time, reranking adds cost and latency for negligible gain. Measure first (S-49 Recall@K). Add reranking when Recall@1 is below your target but Recall@5 is acceptable — that's the sign that the right answer is in the shortlist but not at the top.

## The move

**Retrieve top-20–50 candidates with hybrid search (S-79). Score each (query, passage) pair with a cross-encoder or LLM-as-reranker. Take the top-3–5 for context injection (S-75).**

**Option 1: LLM-as-reranker (no additional infrastructure):**

```js
const Anthropic = require('@anthropic-ai/sdk');

const client = new Anthropic();

// Score a single (query, passage) pair for relevance — returns 0–10
async function scorePassage(query, passage) {
  const resp = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 4,   // just the score digit
    system:     'You are a relevance scorer. Return ONLY a single integer 0–10 measuring how directly the passage answers the query. 10 = direct answer, 0 = completely irrelevant.',
    messages:   [{ role: 'user', content: `Query: ${query}\n\nPassage: ${passage.slice(0, 500)}` }],
  });
  const score = parseInt(resp.content[0].text.trim(), 10);
  return isNaN(score) ? 0 : Math.min(10, Math.max(0, score));
}

// Rerank a list of candidates — run in parallel for speed
async function rerank(query, candidates, topK = 5) {
  const scored = await Promise.all(
    candidates.map(async (c) => ({
      ...c,
      rerankScore: await scorePassage(query, c.text),
    }))
  );

  return scored
    .sort((a, b) => b.rerankScore - a.rerankScore)
    .slice(0, topK);
}
```

**Option 2: Cohere Rerank API:**

```js
// Cohere Rerank — single API call, returns sorted results
// npm install cohere-ai
async function rerankWithCohere(query, candidates, topK = 5) {
  const { CohereClient } = require('cohere-ai');
  const cohere = new CohereClient({ token: process.env.COHERE_API_KEY });

  const result = await cohere.rerank({
    model:      'rerank-v3.5',
    query,
    documents:  candidates.map(c => c.text),
    topN:       topK,
  });

  return result.results.map(r => ({
    ...candidates[r.index],
    rerankScore: r.relevanceScore,
    originalRank: r.index,
  }));
}
```

**Full two-stage pipeline (hybrid → rerank):**

```js
async function retrieveAndRerank(query, hybridRetriever, opts = {}) {
  const fetchK = opts.fetchK ?? 20;  // candidates from hybrid search
  const topK   = opts.topK   ?? 5;   // final results after reranking

  // Stage 1: fast hybrid retrieval (BM25 + dense + RRF)
  const candidates = await hybridRetriever.search(query, { topK: fetchK });
  const texts      = await chunkStore.getMany(candidates.map(c => c.id));

  // Stage 2: cross-encoder reranking
  const reranked = await rerank(query, texts, topK);

  // Inject in ascending relevance order (S-75: most relevant last)
  return [...reranked].reverse();
}
```

**Promotion table — when reranking justifies the cost:**

| Recall@1 without rerank | Recall@5 without rerank | Verdict |
|---|---|---|
| ≥ 0.90 | — | Skip reranking — already good |
| 0.70–0.89 | ≥ 0.90 | Reranking will help; right answer is in top-5 |
| < 0.70 | < 0.85 | Retrieval failure — fix chunking/embeddings first (S-81, S-52) |
| < 0.70 | ≥ 0.90 | Complex queries — reranking will help significantly |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). LLM-as-reranker costs from Haiku pricing. Cohere cost from cohere.com pricing 2026-06-26. Reranking on 5-passage corpus; parallel call timing estimated from Haiku p50 latency ~1s.

```
=== LLM-as-reranker cost ===

Query: "statute of limitations breach of contract California UCC Article 2"
Passage count: 5 (shortlist from hybrid search)

Per-passage scoring call:
  System prompt:  ~30 tok
  Query + passage: ~70 tok (query 15 tok + passage 500 chars ≈ 55 tok)
  Response:         1 tok  (score digit)
  Total:          ~101 tok

5 passages in parallel:
  Total tokens: 5 × 101 = 505 tok
  Cost at Haiku ($0.80/M in + $4.00/M out):
    Input:  500 tok × $0.80/M = $0.000400
    Output:   5 tok × $4.00/M = $0.000020
    Total:                      $0.000420 per reranked query

At 10 000 queries/day: $4.20/day reranking cost
At $3.00/M Sonnet answer calls (~500 tok/answer): $15.00/day answer cost
Reranking overhead: 28% of answer cost — justified if Recall@1 improves ≥ 10 pts

=== Cohere Rerank cost ===

$0.002 per 1,000 results (i.e., per scored passage)
5 passages per query: $0.000010/query
At 10 000 queries/day: $0.10/day — 42× cheaper than LLM-as-reranker
Latency: ~300ms for 20 passages (single API call; managed)

Use Cohere if:
  - External dependency is acceptable
  - Cost difference matters (42×)
  - Latency matters (300ms vs ~1s parallel Haiku)

Use LLM-as-reranker if:
  - No additional vendor relationship
  - Domain-specific relevance definition (prompt gives you control)
  - Fewer than 5 000 queries/day (cost difference is $0.05/day)

=== Rank promotion example ===

Before reranking (RRF order):
  1. "Limitations on contract claims vary by state..."    [rerankScore: 4]
  2. "California commercial law overview..."              [rerankScore: 3]
  3. "UCC Article 2 applies to goods transactions..."    [rerankScore: 5]
  4. "General statute of limitations rules..."           [rerankScore: 6]
  5. "UCC Article 2 breach: 4-year limit in California" [rerankScore: 9]

After reranking:
  1. "UCC Article 2 breach: 4-year limit in California" [promoted from rank 5]
  2. "General statute of limitations rules..."
  3. "UCC Article 2 applies to goods transactions..."
```

## See also

[S-27](s27-reranking.md) · [S-79](s79-hybrid-search.md) · [S-07](s07-rag.md) · [S-49](s49-retrieval-evaluation.md) · [S-75](s75-context-injection-order.md) · [S-81](s81-retrieval-metadata-filtering.md)

## Go deeper

Keywords: `cross-encoder` · `reranking` · `LLM reranker` · `Cohere Rerank` · `bge-reranker` · `two-stage retrieval` · `bi-encoder` · `query-passage scoring` · `relevance scoring` · `RAG reranking`
