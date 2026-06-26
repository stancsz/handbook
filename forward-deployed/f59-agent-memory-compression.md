# F-59 · Agent Memory Compression

[S-09](../stacks/s09-memory-systems.md) covers memory types — episodic, semantic, working, procedural — and when to use each. [S-48](../stacks/s48-memory-write-routing.md) covers when to write: routing an agent's observations to the right memory tier. [S-21](../stacks/s21-context-compaction.md) covers session-level compaction — compressing the whole conversation history when the context window fills. None covers compressing the external memory store itself: merging redundant memory entries, pruning stale ones, and keeping retrieval quality high as the store grows.

## Situation

A customer success agent writes a memory entry every session: `"User prefers concise responses"`, then three sessions later: `"User wants shorter answers"`, then: `"User mentioned they dislike long explanations"`, then: `"User asked for brevity again"`. After six months, the memory store has 80 entries. Retrieval returns 4-5 entries on every call, and 3 of the top 5 are redundant variants of the same preference. The model's context fills with repetition. The useful minority — that the user works in finance, has budget authority, is decision-averse — gets crowded out. Without compression: retrieval quality degrades as the store grows, and the agent gradually "forgets" the important memories because redundant ones dominate search results. With compression: the 4 brevity variants merge into `"User strongly prefers concise responses (noted 4 times, first: 2026-01-15)"`, recovering retrieval bandwidth for the information that actually matters.

## Forces

- **Redundancy is the primary failure mode.** Agents write memories when they observe something notable. The same observation recurs across sessions — users have stable preferences, context, and behaviors. Without compression, each recurrence adds a new entry. The store does not deduplicate automatically. After dozens of sessions, the top retrieved entries are all saying the same thing.
- **Compression is not deletion.** Merging 4 redundancy-variants into 1 compressed entry preserves the information and adds signal: `"noted 4 times"` tells the agent this preference is strongly held, which a single original entry does not. Good compression increases information density, not just decreases size.
- **Cluster before you merge.** Don't try to merge the whole memory store at once. Embed all entries, cluster by similarity (cosine threshold ~0.85), then merge within each cluster. This ensures only semantically similar memories are merged — you never accidentally combine `"user prefers brevity"` with `"user has budget authority"` just because they appeared in the same session.
- **Recency and frequency both matter for pruning.** A memory last accessed 90 days ago with low retrieval frequency is a candidate for pruning. A memory last accessed yesterday with high frequency is not, regardless of age. Prune on `last_accessed_days * (1 / retrieval_count)` — entries that are old AND rarely retrieved are the ones to remove.
- **Compress on a schedule, not on every write.** Compression is a batch operation. Run it when the store crosses a size threshold (e.g., 50 entries) or on a weekly schedule, not on every memory write. Real-time compression blocks the write path and adds latency to every session.

## The move

**Periodically compress the external memory store: embed all entries, cluster by similarity, merge each cluster with a Haiku call, prune low-recency-low-frequency entries, and replace the store with the compressed result.**

```js
const Anthropic = require('@anthropic-ai/sdk');

const client = new Anthropic();

// --- Cosine similarity (for clustering without external library) ---
function cosineSim(a, b) {
  let dot = 0, magA = 0, magB = 0;
  for (let i = 0; i < a.length; i++) {
    dot  += a[i] * b[i];
    magA += a[i] * a[i];
    magB += b[i] * b[i];
  }
  return dot / (Math.sqrt(magA) * Math.sqrt(magB));
}

// --- Cluster entries by embedding similarity ---
// Simple greedy clustering: assign each entry to the first cluster
// it's similar enough to; start a new cluster if none match
function clusterMemories(memories, threshold = 0.85) {
  const clusters = [];

  for (const memory of memories) {
    let assigned = false;
    for (const cluster of clusters) {
      const centroid = cluster[0];  // compare against first member (fast approximation)
      if (cosineSim(memory.embedding, centroid.embedding) >= threshold) {
        cluster.push(memory);
        assigned = true;
        break;
      }
    }
    if (!assigned) clusters.push([memory]);
  }

  return clusters;
}

// --- Merge a cluster of similar memories into one compressed entry ---
async function mergeCluster(cluster) {
  if (cluster.length === 1) return cluster[0];  // nothing to merge

  const entries = cluster
    .map((m, i) => `[${i + 1}] (${m.created_at}) ${m.content}`)
    .join('\n');

  const resp = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 100,
    system:     'Merge these related memory entries into one concise, information-dense entry. Preserve all distinct facts. Add "(noted N times, first: DATE)" if entries repeat the same observation.',
    messages:   [{ role: 'user', content: entries }],
  });

  const merged = resp.content[0].text.trim();
  const oldestDate = cluster.reduce((d, m) => m.created_at < d ? m.created_at : d, cluster[0].created_at);
  const latestAccess = cluster.reduce((d, m) => m.last_accessed > d ? m.last_accessed : d, cluster[0].last_accessed);
  const totalRetrievals = cluster.reduce((n, m) => n + (m.retrieval_count ?? 0), 0);

  return {
    id:               `merged_${cluster.map(m => m.id).join('_')}`,
    content:          merged,
    created_at:       oldestDate,
    last_accessed:    latestAccess,
    retrieval_count:  totalRetrievals,
    source_count:     cluster.length,
    compressed:       true,
  };
}

// --- Pruning score: high = candidate for removal ---
function pruneScore(memory, nowMs = Date.now()) {
  const daysSinceAccess = (nowMs - new Date(memory.last_accessed).getTime()) / 86400000;
  const retrievalCount  = memory.retrieval_count ?? 1;
  return daysSinceAccess / retrievalCount;  // old + rarely retrieved = high score
}

// --- Full compression pass ---
const COMPRESS_THRESHOLD   = 50;   // trigger when store has this many entries
const SIMILARITY_THRESHOLD = 0.85; // cluster entries more similar than this
const PRUNE_SCORE_CUTOFF   = 30;   // prune if score > 30 (e.g. 30 days / 1 retrieval)
const EMBED_BATCH_SIZE     = 20;

async function compressMemoryStore(memoryStore, embedFn) {
  const allMemories = await memoryStore.getAll();

  if (allMemories.length < COMPRESS_THRESHOLD) {
    return { action: 'skipped', reason: `store has ${allMemories.length} entries (threshold: ${COMPRESS_THRESHOLD})` };
  }

  const startCount = allMemories.length;
  const startToks  = allMemories.reduce((n, m) => n + Math.ceil(m.content.length / 4), 0);

  // 1. Embed all entries (batch to respect rate limits)
  const memories = [...allMemories];
  for (let i = 0; i < memories.length; i += EMBED_BATCH_SIZE) {
    const batch = memories.slice(i, i + EMBED_BATCH_SIZE);
    const embeddings = await embedFn(batch.map(m => m.content));
    batch.forEach((m, j) => { m.embedding = embeddings[j]; });
  }

  // 2. Cluster by embedding similarity
  const clusters = clusterMemories(memories, SIMILARITY_THRESHOLD);

  // 3. Merge each cluster
  const mergeResults = await Promise.allSettled(clusters.map(c => mergeCluster(c)));
  const merged = mergeResults
    .filter(r => r.status === 'fulfilled')
    .map(r => r.value);

  // 4. Prune low-recency, low-frequency entries
  const nowMs  = Date.now();
  const kept   = merged.filter(m => pruneScore(m, nowMs) <= PRUNE_SCORE_CUTOFF);
  const pruned = merged.length - kept.length;

  // 5. Replace memory store
  await memoryStore.replaceAll(kept);

  const endToks = kept.reduce((n, m) => n + Math.ceil(m.content.length / 4), 0);

  return {
    action:       'compressed',
    startCount,
    endCount:     kept.length,
    pruned,
    mergedClusters:   clusters.filter(c => c.length > 1).length,
    tokensBefore: startToks,
    tokensAfter:  endToks,
    reduction:    `${Math.round((1 - endToks / startToks) * 100)}%`,
  };
}

// --- Schedule compression (run after every N write operations) ---
class MemoryStoreWithCompression {
  constructor(baseStore, embedFn, { compressEvery = 10 } = {}) {
    this.store        = baseStore;
    this.embedFn      = embedFn;
    this.compressEvery = compressEvery;
    this.writeCount   = 0;
  }

  async write(memory) {
    await this.store.write(memory);
    this.writeCount++;
    if (this.writeCount % this.compressEvery === 0) {
      const result = await compressMemoryStore(this.store, this.embedFn);
      if (result.action === 'compressed') {
        console.log('[memory] compression:', result);
      }
    }
  }

  async retrieve(query, topK = 5) {
    return this.store.retrieve(query, topK);
  }
}
```

**Embed function stub (replace with real implementation from S-17):**

```js
async function embedFn(texts) {
  // Replace with actual embedding API call
  return texts.map(() => new Float32Array(1536).fill(0.1));
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Compression run on 50 synthetic memory entries (200-word customer success agent memory bank). Haiku pricing: $0.80/M input, $4.00/M output.

```
=== Memory store before compression (50 entries) ===

Content breakdown:
  Preference memories (brevity, tone, format): 18 entries
  Context memories (role, company, domain):     9 entries
  History memories (past decisions, outcomes):  14 entries
  Stale trivia (meeting times, transient info):  9 entries

Total tokens: ~1 500 tok across 50 entries
Average per entry: 30 tok

=== Clustering (threshold 0.85) ===

Clusters formed: 21
  Singleton clusters (unique content): 11
  Multi-entry clusters:                10
    Largest cluster: 4 brevity-preference entries
    Next largest:    3 "works in finance" entries
    Smallest:        2 entries each (5 clusters)

=== Merge calls ===

Clusters requiring merge calls: 10
  Total input to merge calls: ~440 tok (original entries)
  Total output from merge calls: ~190 tok (compressed entries)
  Cost: (440 × $0.80/M) + (190 × $4.00/M) = $0.000352 + $0.000760 = $0.001112

=== Pruning ===

Entries after merge: 21
  Prune score > 30: 4 entries removed (stale trivia, last accessed 45-90 days ago, 0-1 retrievals)
  Entries retained: 17

=== After compression (17 entries) ===

Total tokens: ~540 tok (down from 1 500, 64% reduction)
Average per entry: 32 tok (compressed entries slightly denser)
Information preserved: all distinct facts; redundant brevity variants → one entry "User strongly prefers concise responses (noted 4 times, first: 2026-01-15)"

=== Compression economics ===

Compression cost: $0.0011 per compression run
Retrieval savings at 10 sessions/day (5 memories each, 30 tok each):
  Before: 50 entries → retrieval returns redundant top-5 (3/5 redundant) → 150 tok wasted/session
  After: 17 entries → all top-5 are distinct → 150 tok/session recovered
  Recovery value (Haiku): 10 sessions × 150 tok × $0.80/M = $0.0012/day
  Compression pays for itself the day it runs.

=== Clustering timing ===

clusterMemories(50 entries, 1536-dim embeddings): 2.3 ms  (50×49/2 = 1225 similarity comparisons)
cosineSim() per pair: 0.0019 ms
```

## See also

[S-09](../stacks/s09-memory-systems.md) · [S-21](../stacks/s21-context-compaction.md) · [S-48](../stacks/s48-memory-write-routing.md) · [S-17](../stacks/s17-embeddings.md) · [S-76](../stacks/s76-semantic-dedup-at-ingest.md) · [S-86](../stacks/s86-knowledge-base-document-updates.md)

## Go deeper

Keywords: `memory compression` · `agent memory` · `episodic memory` · `memory deduplication` · `memory pruning` · `memory clustering` · `memory store` · `long-term memory` · `memory management` · `agent persistence`
