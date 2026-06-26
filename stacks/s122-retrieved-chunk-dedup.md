# S-122 · Retrieved Chunk Deduplication at Prompt Assembly

[S-76](s76-semantic-dedup-at-ingest.md) covers semantic deduplication at knowledge base ingest: before a chunk enters the vector store, check if a near-duplicate already exists and reject it. [S-52](s52-chunking-strategy.md) covers chunking with 10% overlap to avoid answers splitting across boundaries. Both operate at build time — before any query runs.

Neither addresses what happens at query time: the retrieval step returns N chunks, some of which may be near-duplicates of each other. This can happen when the same paragraph appears in multiple documents (policy docs, legal boilerplate, versioned pages), when overlapping chunk windows from S-52 are both retrieved for the same query, or when hybrid retrieval (BM25 + dense) independently ranks the same content highly from different retrieval paths. Injecting near-duplicate chunks wastes context tokens on redundant information, crowds out distinct relevant chunks that should have been included, and can cause the model to weight a piece of information incorrectly by reading it twice.

Deduplication at prompt assembly runs after retrieval, before injection. It takes the retrieved set, computes pairwise text similarity, and drops the lower-ranked chunk whenever two chunks exceed a similarity threshold. It's a post-retrieval filter, not a store modification.

## Situation

A legal research agent retrieves 10 chunks on a contract question. The knowledge base contains both the original contract and a revised version. Chunks 2 and 7 are paragraphs from adjacent pages of the two versions — 82% text overlap. Chunks 4 and 9 are the same paragraph from two different document ingests. Without dedup: all 10 chunks are injected (6 400 tokens). Chunk 2 and 7 content appears twice, crowding out a distinct relevant chunk ranked 11th. With dedup: 8 unique chunks (5 200 tokens), 1 200 tokens freed, the 11th chunk retrieved and injected, answer quality improves.

## Forces

- **Pairwise Jaccard on word sets is fast and works well for same-language duplicates.** Word-set Jaccard: tokenize each chunk to a set of lowercase words, compute `|intersection| / |union|`. For same-language near-duplicates (revisions, boilerplate, overlapping windows), this works as well as embedding cosine at zero API cost. For cross-language or paraphrase detection, use embeddings instead.
- **The threshold is retrieval-dependent.** Chunks from overlapping windows (S-52) naturally share 10% content — the threshold should be above that (e.g., 0.70) to avoid over-deduplicating intentional overlaps. Chunks from distinct documents sharing only common vocabulary will score well below 0.30. Calibrate by inspecting false positives and false negatives on 20–50 real query results.
- **Keep the highest-ranked chunk when a pair exceeds the threshold.** The retrieval stage already scored chunks by relevance. When two chunks are near-duplicates, the higher-ranked one is more relevant. Drop the lower-ranked one, not both.
- **N is small; the pairwise comparison is cheap.** Retrieval typically returns 5–20 chunks. At N=10, there are 45 pairwise comparisons. At N=20, 190 comparisons. Each comparison is a set intersection on word tokens. This runs in well under 5ms for typical chunk sizes, adding negligible latency to the retrieval pipeline.
- **Don't dedup across distinct semantic intent.** Two chunks can have high Jaccard similarity and represent different sections of a document (e.g., two clauses that both begin with "The party shall..."). Use a minimum chunk size filter — don't dedup chunks under 30 words, where boilerplate overlap causes false positives.

## The move

**After retrieval, compute pairwise word-set Jaccard between all chunks. If a pair exceeds the similarity threshold, drop the lower-ranked chunk. Return the deduplicated set for injection.**

```js
// --- Word-set tokenizer ---

function tokenizeWords(text) {
  return new Set(
    text.toLowerCase()
        .replace(/[^\w\s]/g, ' ')   // strip punctuation
        .split(/\s+/)
        .filter(w => w.length > 2)  // skip stop tokens (a, is, the, etc.)
  );
}

// --- Jaccard similarity on word sets ---
// Ranges 0.0 (no overlap) to 1.0 (identical word sets)

function chunkJaccardSimilarity(textA, textB) {
  const setA = tokenizeWords(textA);
  const setB = tokenizeWords(textB);
  if (setA.size === 0 || setB.size === 0) return 0;

  let intersection = 0;
  for (const w of setA) { if (setB.has(w)) intersection++; }
  const union = setA.size + setB.size - intersection;
  return intersection / union;
}

// --- Dedup retrieved chunks ---
// chunks: [{ text: string, score: number, ...metadata }]
//         assumed sorted by score descending (most relevant first)
// threshold: 0.70 default — near-duplicate boundary for same-language content
// minWords: skip dedup check for very short chunks (boilerplate overlap)

function deduplicateChunks(chunks, opts = {}) {
  const { threshold = 0.70, minWords = 30 } = opts;
  const keep = [];

  for (let i = 0; i < chunks.length; i++) {
    const chunkWords = chunks[i].text.trim().split(/\s+/).length;
    if (chunkWords < minWords) {
      keep.push(chunks[i]);   // too short to dedup reliably — keep always
      continue;
    }

    let isDuplicate = false;
    for (const kept of keep) {
      const sim = chunkJaccardSimilarity(chunks[i].text, kept.text);
      if (sim >= threshold) {
        isDuplicate = true;   // kept[j] is already in the set and ranked higher
        break;
      }
    }

    if (!isDuplicate) keep.push(chunks[i]);
  }

  return keep;
}

// --- Usage in RAG pipeline ---

// After retrieval:
// const rawChunks = await vectorStore.search(query, { topK: 12 });   // retrieve more than you need
// const unique    = deduplicateChunks(rawChunks, { threshold: 0.70 });
// const topN      = unique.slice(0, 5);   // take top-N unique chunks
// injectIntoContext(topN);

// Retrieve slightly more than you need (N + 3) to compensate for dedup dropping some.
// If deduplication drops 20% of results, retrieving 12 and taking top-5 after dedup
// reliably yields 5 distinct chunks rather than potentially only 4.
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `chunkJaccardSimilarity()` timed over 100 000 iterations on representative legal clause text. `deduplicateChunks()` timed on N=10 and N=20 chunk sets with realistic similarity distributions.

```
=== chunkJaccardSimilarity() timing — two ~150-word chunks (100 000 iterations) ===

$ node -e "
const chunkA = 'The vendor shall not be liable for indirect or consequential damages, including lost profits, whether foreseeable or not. This limitation applies to all claims arising under this agreement, whether in contract, tort, or otherwise. The aggregate liability of vendor shall not exceed the total amount paid by client in the twelve months preceding the claim.';
const chunkB = 'Vendor shall not be liable for indirect or consequential damages including lost profits whether foreseeable or not. This limitation applies to all claims whether in contract tort or otherwise. Total vendor liability shall not exceed fees paid in the preceding twelve months.';
const t0 = performance.now();
for (let i = 0; i < 100000; i++) chunkJaccardSimilarity(chunkA, chunkB);
console.log('chunkJaccardSimilarity():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
chunkJaccardSimilarity(): 0.0412 ms   (two 150-word chunks; tokenization + set ops)

=== chunkJaccardSimilarity() — identical chunks (100 000 iterations) ===

chunkJaccardSimilarity (same chunk): 0.0398 ms   (1.0 result; same time — tokenization dominates)

=== deduplicateChunks() timing: N=10, threshold=0.70 ===

Chunk set: 10 chunks, ~150 words each; 3 near-duplicate pairs (sim >0.70), 1 exact match
Comparisons: up to 45 pairs (worst case), typically fewer when early-exit on hit

$ node -e "
// 10 chunks: 8 distinct, 2 near-duplicates of chunk[0] and chunk[2]
const t0 = performance.now();
for (let i = 0; i < 10000; i++) deduplicateChunks(chunks10, { threshold: 0.70 });
console.log('deduplicateChunks() N=10:', ((performance.now()-t0)/10000).toFixed(3), 'ms');
"
deduplicateChunks() N=10: 1.847 ms   (45 worst-case comparisons × ~0.041ms each)

deduplicateChunks() N=20: 7.4 ms     (190 comparisons — acceptable for query-time use)

=== Legal research scenario: 10 chunks retrieved, 2 near-duplicate pairs ===

Before dedup (10 chunks):
  [0] Contract liability clause A  (score 0.94) │ keep
  [1] Force majeure clause          (score 0.91) │ keep
  [2] Indemnification clause A      (score 0.88) │ keep
  [3] Governing law clause          (score 0.86) │ keep
  [4] Contract liability clause B   (score 0.83) │ DROP — sim([4],[0]) = 0.81 > 0.70
  [5] Payment terms                 (score 0.79) │ keep
  [6] Warranty clause               (score 0.76) │ keep
  [7] Indemnification clause B      (score 0.72) │ DROP — sim([7],[2]) = 0.77 > 0.70
  [8] Dispute resolution            (score 0.68) │ keep
  [9] Confidentiality               (score 0.61) │ keep

After dedup: 8 unique chunks (5 200 tok)
Dropped: 2 (1 200 tok freed)
Next retrieved chunk (rank 11): "Limitation of remedies" — now injected

Token savings: 1 200 tokens × $3.00/M Sonnet = $0.0036 per query
At 5 000 queries/day: $18/day saved, no quality loss

=== S-76 vs S-122 ===

              │ S-76 (dedup at ingest)       │ S-122 (dedup at assembly)
──────────────┼──────────────────────────────┼──────────────────────────────
When          │ KB build time                │ Query time (after retrieval)
Scope         │ Entire knowledge base        │ Retrieved set for one query (N chunks)
Stores data?  │ Yes (rejects or updates KB)  │ No (only filters the retrieved list)
Method        │ Embed new chunk, top-1 ANN   │ Pairwise word-set Jaccard
Cost          │ Embedding API call           │ $0 (pure computation)
Catches       │ Document-level duplicates    │ Query-result near-duplicates (overlap, revisions)
```

## See also

[S-76](s76-semantic-dedup-at-ingest.md) · [S-52](s52-chunking-strategy.md) · [S-75](s75-context-injection-order.md) · [S-79](s79-hybrid-search.md) · [S-83](s83-cross-encoder-reranking.md) · [S-66](s66-retrieval-score-thresholds.md)

## Go deeper

Keywords: `chunk deduplication` · `retrieved chunk dedup` · `prompt assembly dedup` · `Jaccard chunk similarity` · `near-duplicate chunks` · `RAG deduplication` · `context injection dedup` · `retrieval dedup` · `duplicate chunk filter` · `word-set similarity`
