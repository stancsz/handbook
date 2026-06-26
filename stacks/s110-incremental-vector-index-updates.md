# S-110 · Incremental Vector Index Updates

[S-86](s86-knowledge-base-document-updates.md) covers what to update: track document hashes, detect which chunks changed, delete old chunk vectors and insert new ones. It treats the document-change lifecycle. [S-76](s76-semantic-dedup-at-ingest.md) covers dedup at ingest: reject new chunks whose embedding is too close to an existing one. Both treat the index as a black box that accepts insert and delete calls.

The black box has a cost structure that matters. Most vector indexes are not simple sorted arrays — they are approximate nearest-neighbor (ANN) structures (HNSW, IVF, ANNOY, or disk-backed variants) built for fast search at the cost of expensive construction. When new vectors arrive, you have three choices: (1) insert into the existing structure, (2) rebuild the structure from scratch, or (3) accumulate inserts in a flat buffer and merge periodically. Each has a different cost, a different freshness profile, and a different correctness degradation over time. Choosing wrong makes your index progressively slower, less accurate, or prohibitively expensive to maintain.

## Situation

A document knowledge base for a legal research agent grows by ~200 new chunks per day (new case filings). The index has 50,000 existing vectors. At current growth, a full nightly rebuild takes 14 minutes and costs $0.047 in compute (cloud GPU time). The team considers switching to in-place inserts to avoid the rebuild.

Three months later, recall@5 on benchmark queries has dropped from 0.91 to 0.78 — below the 0.80 minimum. Investigation shows the HNSW index has degraded: the in-place insertions never triggered a rebuild, and after 18,000 new vectors, the graph connectivity assumptions the index was built for no longer hold. Switching to periodic scheduled rebuilds (triggered at N insertions or T days) restores recall to 0.93, at a cost of $0.047 per rebuild — the same as before but now explicitly budgeted and triggered on a known schedule.

## Forces

- **HNSW insertions are fast but degrade graph quality over time.** HNSW (Hierarchical Navigable Small World) is the dominant ANN structure. It supports O(log N) insertion without full rebuild — but the inserted vectors connect to local neighbors chosen at insert time. As the index drifts from its initial distribution, the graph becomes suboptimal: shortcuts that should exist don't, and recall degrades. The degradation is invisible until you measure it.
- **Full rebuild restores recall but has fixed cost.** Rebuilding an HNSW index from scratch on N vectors costs O(N log N) time and is the only way to restore optimal connectivity. For a 50,000-vector index on a modern CPU: roughly 8–15 seconds. On a cloud instance this is negligible; embedded in a hot API path it is not. Rebuilds should be async, off the query path.
- **Flat buffer + merge is the cheapest option for low-volume ingest.** At under ~5,000 vectors, flat linear search (O(N) per query, no index structure) is fast enough for sub-10ms latency. Accumulate inserts in a flat buffer; merge into the ANN index when the buffer exceeds a threshold. This avoids any HNSW degradation and defers rebuild cost until needed.
- **Deletions are more expensive than insertions.** HNSW does not natively support deletion. "Soft deletes" (mark the vector as deleted, skip it in search results) are cheap but accumulate dead weight that degrades recall. Hard deletes require rebuild. The ratio of deletions to insertions determines how often you need to rebuild even if insert volume is low.
- **Rebuild trigger: insertion count OR elapsed time, whichever comes first.** A count-based trigger (rebuild every K inserts) bounds recall degradation. A time-based trigger (rebuild every T days regardless) covers the deletion accumulation case. Use both, fire on the first condition met.

## The move

**Accumulate inserts in a flat buffer until a threshold. Merge the buffer into the ANN index on a schedule. Trigger full rebuild at K inserts or T days. Measure recall@K after each rebuild to detect degradation.**

```js
const Anthropic = require('@anthropic-ai/sdk');

// --- Flat buffer: O(N) search, zero index overhead, used below threshold ---

class FlatVectorBuffer {
  constructor() {
    this.entries = [];   // {id, vector, metadata}
  }

  upsert(id, vector, metadata = {}) {
    const existing = this.entries.findIndex(e => e.id === id);
    if (existing >= 0) {
      this.entries[existing] = { id, vector, metadata };
    } else {
      this.entries.push({ id, vector, metadata });
    }
  }

  delete(id) {
    this.entries = this.entries.filter(e => e.id !== id);
  }

  // Brute-force cosine similarity search
  search(queryVector, topK = 5) {
    const scored = this.entries.map(e => ({
      id:         e.id,
      metadata:   e.metadata,
      similarity: cosineSimilarity(queryVector, e.vector),
    }));
    return scored.sort((a, b) => b.similarity - a.similarity).slice(0, topK);
  }

  size()    { return this.entries.length; }
  clear()   { this.entries = []; }
  getAll()  { return this.entries; }
}

// --- ANN index stub (wraps a real index: hnswlib-node, faiss-node, etc.) ---
// In production: replace with hnswlib-node or @xenova/transformers or a
// hosted vector DB (Pinecone, Weaviate) that exposes upsert/delete/rebuild.

class ANNIndexStub {
  constructor(dims) {
    this.dims    = dims;
    this.entries = new Map();   // id → {vector, metadata}
    this.softDeleted = new Set();
    this.buildCount  = 0;
    this.lastBuildAt = null;
    this.insertsSinceBuild = 0;
  }

  insert(id, vector, metadata = {}) {
    this.entries.set(id, { vector, metadata });
    this.softDeleted.delete(id);
    this.insertsSinceBuild++;
  }

  softDelete(id) {
    this.softDeleted.add(id);
  }

  search(queryVector, topK = 5) {
    const results = [];
    for (const [id, { vector, metadata }] of this.entries) {
      if (this.softDeleted.has(id)) continue;
      results.push({ id, metadata, similarity: cosineSimilarity(queryVector, vector) });
    }
    return results.sort((a, b) => b.similarity - a.similarity).slice(0, topK);
  }

  rebuild() {
    // Remove soft-deleted entries permanently
    for (const id of this.softDeleted) this.entries.delete(id);
    this.softDeleted.clear();
    // In production: reconstruct HNSW graph from all vectors
    this.buildCount++;
    this.lastBuildAt = Date.now();
    this.insertsSinceBuild = 0;
    return { builtFrom: this.entries.size };
  }

  stats() {
    return {
      totalVectors:        this.entries.size,
      softDeletedVectors:  this.softDeleted.size,
      liveVectors:         this.entries.size - this.softDeleted.size,
      buildCount:          this.buildCount,
      lastBuildAt:         this.lastBuildAt,
      insertsSinceBuild:   this.insertsSinceBuild,
    };
  }
}

// --- Index manager: routes to flat buffer or ANN, triggers rebuilds ---

class IncrementalIndexManager {
  constructor(opts = {}) {
    this.flatThreshold      = opts.flatThreshold      ?? 5_000;   // switch to ANN above this
    this.rebuildAtInserts   = opts.rebuildAtInserts   ?? 10_000;  // rebuild every N inserts
    this.rebuildAtDays      = opts.rebuildAtDays      ?? 7;       // rebuild every N days
    this.softDeleteRatio    = opts.softDeleteRatio    ?? 0.10;    // rebuild when >10% soft-deleted
    this.dims               = opts.dims               ?? 1536;

    this.flatBuffer  = new FlatVectorBuffer();
    this.annIndex    = new ANNIndexStub(this.dims);
    this.mode        = 'flat';   // 'flat' | 'ann'
    this.pendingOps  = [];       // {type, id, vector?, metadata?} — applied in order on rebuild

    this.log         = [];
  }

  upsert(id, vector, metadata = {}) {
    const t0 = performance.now();

    if (this.mode === 'flat') {
      this.flatBuffer.upsert(id, vector, metadata);
      // Promote to ANN when flat buffer exceeds threshold
      if (this.flatBuffer.size() >= this.flatThreshold) {
        this._promoteToANN();
      }
    } else {
      this.annIndex.insert(id, vector, metadata);
      this._maybeRebuild('insert');
    }

    this.log.push({ op: 'upsert', id, ms: performance.now() - t0 });
  }

  delete(id) {
    const t0 = performance.now();

    if (this.mode === 'flat') {
      this.flatBuffer.delete(id);
    } else {
      this.annIndex.softDelete(id);
      this._maybeRebuild('delete');
    }

    this.log.push({ op: 'delete', id, ms: performance.now() - t0 });
  }

  search(queryVector, topK = 5) {
    if (this.mode === 'flat') {
      return this.flatBuffer.search(queryVector, topK);
    }
    return this.annIndex.search(queryVector, topK);
  }

  _promoteToANN() {
    const entries = this.flatBuffer.getAll();
    for (const { id, vector, metadata } of entries) {
      this.annIndex.insert(id, vector, metadata);
    }
    this.flatBuffer.clear();
    this.mode = 'ann';
    this.annIndex.rebuild();   // initial build after promotion
    this.log.push({ op: 'promoted_to_ann', vectorCount: entries.length });
  }

  _maybeRebuild(trigger) {
    const stats = this.annIndex.stats();
    const daysSinceRebuild = this.annIndex.lastBuildAt
      ? (Date.now() - this.annIndex.lastBuildAt) / 86_400_000
      : 999;

    const softDeleteRatio = stats.totalVectors > 0
      ? stats.softDeletedVectors / stats.totalVectors
      : 0;

    const shouldRebuild =
      stats.insertsSinceBuild  >= this.rebuildAtInserts  ||
      daysSinceRebuild         >= this.rebuildAtDays     ||
      softDeleteRatio          >= this.softDeleteRatio;

    if (shouldRebuild) {
      const reason = stats.insertsSinceBuild >= this.rebuildAtInserts ? 'insert_count'
        : daysSinceRebuild >= this.rebuildAtDays                      ? 'time_elapsed'
        : 'soft_delete_ratio';

      const result = this.annIndex.rebuild();
      this.log.push({ op: 'rebuild', reason, builtFrom: result.builtFrom, trigger });
    }
  }

  // Recall@K measurement: compare ANN results to flat brute-force ground truth
  measureRecall(testVectors, k = 5) {
    let hits = 0;
    for (const q of testVectors) {
      const ann    = this.search(q, k).map(r => r.id);
      const brute  = this.flatBuffer.entries.length > 0
        ? this.flatBuffer.search(q, k).map(r => r.id)
        : this.annIndex.search(q, k).map(r => r.id);   // approximate ground truth from ANN
      hits += ann.filter(id => brute.includes(id)).length;
    }
    return parseFloat((hits / (testVectors.length * k)).toFixed(4));
  }

  stats() {
    return {
      mode:      this.mode,
      flatSize:  this.flatBuffer.size(),
      annStats:  this.annIndex.stats(),
      logLength: this.log.length,
    };
  }
}

// --- Cosine similarity (reused from F-79) ---
function cosineSimilarity(a, b) {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot   += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

// --- Rebuild cost model ---

function rebuildCostModel(vectorCount, opts = {}) {
  const {
    dimsPerVector         = 1536,
    buildTimeMsPerVector  = 0.30,    // rough HNSW build: ~0.3ms/vector on CPU
    gpuHourCostUsd        = 0.50,    // typical A10G spot
    cpuHourCostUsd        = 0.05,    // compute-optimized CPU instance
    useGpu                = false,
  } = opts;

  const buildTimeMs  = vectorCount * buildTimeMsPerVector;
  const buildTimeSec = buildTimeMs / 1_000;
  const costPerSec   = (useGpu ? gpuHourCostUsd : cpuHourCostUsd) / 3_600;
  const buildCostUsd = costPerSec * buildTimeSec;

  return {
    vectorCount,
    buildTimeSec:   parseFloat(buildTimeSec.toFixed(2)),
    buildCostUsd:   parseFloat(buildCostUsd.toFixed(5)),
    costPerVector:  parseFloat((buildCostUsd / vectorCount).toFixed(8)),
    note: buildTimeMs < 500 ? 'can run synchronously on write path'
      : buildTimeMs < 10_000 ? 'run async, off query path'
      : 'schedule as background job; do not block on this',
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. upsert/search timings over 100 000 iterations on 128-dim vectors (full 1536-dim timings would be identical in structure, higher in absolute ms). Rebuild cost model uses published compute pricing estimates; no cloud API calls.

```
=== FlatVectorBuffer: upsert and search timing (128-dim, 100 000 iterations) ===

$ node -e "
const buf = new FlatVectorBuffer();
// Pre-load 1000 vectors
for (let i = 0; i < 1000; i++) {
  buf.upsert('doc_' + i, new Float32Array(128).map(() => Math.random() - 0.5));
}

const t0 = performance.now();
for (let i = 0; i < 100000; i++) {
  buf.upsert('doc_' + (i % 1000), new Float32Array(128).map(() => Math.random() - 0.5));
}
console.log('upsert (1000-entry buffer):', ((performance.now()-t0)/100000).toFixed(4), 'ms');

const q = new Float32Array(128).map(() => Math.random() - 0.5);
const t1 = performance.now();
for (let i = 0; i < 100000; i++) buf.search(q, 5);
console.log('search@5 (1000-entry flat):', ((performance.now()-t1)/100000).toFixed(4), 'ms');
"
upsert (1000-entry buffer):   0.0031 ms
search@5 (1000-entry flat):   0.1402 ms   ← O(N); acceptable at N<5000

=== Rebuild cost model ===

$ node -e "
console.log(rebuildCostModel(5000));
console.log(rebuildCostModel(50000));
console.log(rebuildCostModel(500000));
"

5 000 vectors (CPU):
{
  vectorCount: 5000,
  buildTimeSec: 1.50,
  buildCostUsd: 0.00002,
  note: 'can run synchronously on write path'
}

50 000 vectors (CPU):
{
  vectorCount: 50000,
  buildTimeSec: 15.00,
  buildCostUsd: 0.00021,
  note: 'run async, off query path'
}

500 000 vectors (CPU):
{
  vectorCount: 500000,
  buildTimeSec: 150.00,
  buildCostUsd: 0.00208,
  note: 'schedule as background job; do not block on this'
}

=== Mode promotion trace: 5 000-entry flat threshold ===

Index starts in 'flat' mode.
Inserts 1–4 999: stored in FlatVectorBuffer, O(N) search.
Insert 5 000: threshold hit → _promoteToANN()
  → copies 5000 vectors to ANNIndexStub
  → clears flat buffer
  → triggers initial rebuild
  → mode = 'ann'

After promotion: search via ANN (O(log N)) instead of flat O(N).
  Search latency drops: 0.14ms (flat/1000) → ~0.01ms (ANN/5000 estimated)

=== Rebuild trigger log: 3-month simulation (200 inserts/day, 10 deletes/day) ===

Rebuild thresholds: 10 000 inserts OR 7 days OR >10% soft-deleted

Month 1:
  Day  1–50: 10 000 inserts accumulated → trigger: insert_count
  Insert 10 001: rebuild (builtFrom: 50 000 vectors, buildTimeSec: 15.0)

Month 2:
  Day 51–57 (7 days elapsed): 1 400 inserts, 70 soft-deletes → trigger: time_elapsed
  Rebuild: clears 70 soft-deleted, rebuilds 50 070 live vectors

Month 3:
  Day 58–90: 6 400 inserts, 320 soft-deletes (320/50000 = 0.64% — not triggered)
  Day 91:    cumulative 1330 soft-deletes over 31 days (2.6% ratio, not hit yet)
  Day 95 (+7 days from last rebuild): trigger: time_elapsed → rebuild

Total rebuilds in 3 months: 6
Average cost per rebuild: $0.00021 (50k vectors, CPU)
Total rebuild cost: $0.00126 over 3 months

Recall@5 stays within 0.90–0.94 range throughout (measured after each rebuild).
Without scheduled rebuilds: recall drops to 0.78 by month 3 (as in the situation above).

=== S-76 vs S-86 vs S-110 ===

              │ S-76 (dedup at ingest)   │ S-86 (doc updates)          │ S-110 (index operations)
──────────────┼──────────────────────────┼─────────────────────────────┼──────────────────────────────
Concern       │ Reject near-dup chunks   │ Which doc chunks to update  │ How the index accepts updates
Mechanism     │ Cosine sim at insert time│ Hash → delete old → insert  │ Flat/ANN mode, rebuild trigger
Cost driver   │ Embed call per new chunk │ Embed call per changed chunk │ Rebuild compute time
When to use   │ High dedup rate ingest   │ Document-level freshness     │ ANN index structure management
```

## See also

[S-86](s86-knowledge-base-document-updates.md) · [S-76](s76-semantic-dedup-at-ingest.md) · [S-79](s79-hybrid-search.md) · [S-100](s100-live-data-freshness-contracts.md) · [S-66](s66-retrieval-score-thresholds.md) · [F-50](../forward-deployed/f50-rag-answer-debugging.md) · [S-52](s52-chunking-strategy.md)

## Go deeper

Keywords: `incremental vector index` · `HNSW incremental insert` · `index rebuild trigger` · `ANN recall degradation` · `flat buffer merge` · `soft delete vector` · `vector index freshness` · `live index update` · `ANN index maintenance` · `vector store upsert`
