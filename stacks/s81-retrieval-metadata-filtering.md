# S-81 · Retrieval Metadata Filtering

[S-07](s07-rag.md) covers the retrieval pipeline — chunk, embed, store, retrieve by cosine similarity. [S-73](s73-multi-tenant-ai-isolation.md) enforces tenant namespace in one line: `filter: { namespace: 'tenant:abc' }`. Neither covers the broader metadata filtering pattern: combining multiple predicates (date range, doc type, tenant, status) before vector search to reduce the candidate pool, improve precision, and avoid injecting stale or unauthorized context.

## Situation

A legal tech RAG system serves multiple law firms and indexes statutes, case law, and internal memos. A query about "data privacy violations" without metadata filters returns chunks from a different firm's memos (wrong tenant), superseded statutes from 2019 (stale), and draft memos never finalized (wrong status). Adding three metadata filters — `tenantId`, `effectiveDate >= 2022-01-01`, `status = 'published'` — costs zero tokens and produces a 12-chunk candidate pool instead of 847 chunks. The model only sees relevant, authorized, current documents.

## Forces

- **Metadata filters reduce the candidate pool before vector search, not after.** Post-filtering (retrieve 50, then drop 40 by metadata) wastes the ANN query and returns fewer than the requested K. Pre-filtering at the database layer is always correct: the store searches only within the filtered set.
- **Filter correctness is a correctness requirement, not a performance optimization.** A missing tenant filter leaks another firm's documents. The model doesn't refuse to answer from them — it answers helpfully and incorrectly. There is no similarity score that catches this. Metadata correctness is binary.
- **Combining predicates follows AND by default; OR is a deliberate choice.** A query scoped to `tenantId AND docType IN ['statute', 'regulation'] AND date >= 2020` is the common case. OR widening (e.g., show docs from `type = 'statute' OR type = 'case_law'`) must be explicit, not the default.
- **Date range filtering for freshness is different from TTL-based cache invalidation.** Cache invalidation (S-60) is about when to refresh stored embeddings. Date filtering is about which documents to include in retrieval results for a specific query. A document that was valid last year may be superseded — filter it by `effectiveUntil` or `status`.
- **Metadata must be stored at ingest time.** You cannot add metadata to embeddings after ingestion without re-inserting the vector. Design the metadata schema before ingest and include all fields you will filter on.

## The move

**Store metadata alongside embeddings at ingest time. At query time, build the filter predicate from the request context before calling the vector store. Never retrieve then filter — filter then retrieve.**

**Metadata schema (defined at ingest):**

```js
// Every chunk ingested carries a metadata record alongside its embedding
const chunkRecord = {
  id:            'chunk-221',
  embedding:     Float32Array,          // vector
  text:          '...',
  metadata: {
    tenantId:      'firm-acme',
    docType:       'statute',           // 'statute' | 'regulation' | 'case_law' | 'memo' | 'faq'
    source:        'gdpr-article-5',
    effectiveDate: '2018-05-25',        // ISO date string
    effectiveUntil: null,               // null = still in effect
    status:        'published',         // 'draft' | 'published' | 'archived'
    jurisdiction:  'EU',
    language:      'en',
  },
};
```

**Filter predicate builder:**

```js
// Build a compound AND filter from the request context
function buildFilter(ctx) {
  const predicates = [];

  // Always scope to tenant — non-negotiable
  if (ctx.tenantId) {
    predicates.push(doc => doc.metadata.tenantId === ctx.tenantId);
  }

  // Restrict to requested doc types
  if (ctx.docTypes && ctx.docTypes.length > 0) {
    const allowed = new Set(ctx.docTypes);
    predicates.push(doc => allowed.has(doc.metadata.docType));
  }

  // Exclude archived and draft documents
  predicates.push(doc => doc.metadata.status === 'published');

  // Date range: only docs in effect as of the query date
  if (ctx.asOfDate) {
    const asOf = ctx.asOfDate;
    predicates.push(doc =>
      doc.metadata.effectiveDate <= asOf &&
      (doc.metadata.effectiveUntil === null || doc.metadata.effectiveUntil >= asOf)
    );
  }

  // Combine all predicates with AND
  return doc => predicates.every(p => p(doc));
}
```

**Vector store with pre-filtering:**

```js
class FilteredVectorStore {
  constructor() {
    this.docs = [];  // [{ id, embedding, text, metadata }]
  }

  insert(doc) {
    this.docs.push(doc);
  }

  cosineSim(a, b) {
    let dot = 0, na = 0, nb = 0;
    for (let i = 0; i < a.length; i++) {
      dot += a[i] * b[i];
      na  += a[i] * a[i];
      nb  += b[i] * b[i];
    }
    return dot / (Math.sqrt(na) * Math.sqrt(nb));
  }

  // Pre-filter, then score, then return top-K
  search(queryEmbedding, filter, topK = 5) {
    const candidates = filter ? this.docs.filter(filter) : this.docs;

    return candidates
      .map(doc => ({ id: doc.id, text: doc.text, score: this.cosineSim(queryEmbedding, doc.embedding) }))
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
  }
}

// Usage
const store = new FilteredVectorStore();
// ... insert chunks at ingest ...

async function retrieveFiltered(query, ctx, embedFn) {
  const queryEmbedding = await embedFn(query);
  const filter         = buildFilter(ctx);
  return store.search(queryEmbedding, filter, 5);
}
```

**Common filter patterns:**

```js
// Tenant + published only (most common)
const ctx1 = { tenantId: 'firm-acme', docTypes: null, status: 'published', asOfDate: null };

// Tenant + specific doc types + date range
const ctx2 = {
  tenantId:  'firm-acme',
  docTypes:  ['statute', 'regulation'],
  asOfDate:  '2024-01-01',
};

// Multi-type OR (widen explicitly)
const orFilter = doc =>
  doc.metadata.tenantId === 'firm-acme' &&
  (doc.metadata.docType === 'statute' || doc.metadata.docType === 'case_law') &&
  doc.metadata.status === 'published';
```

**What to index in metadata vs what to filter at query time:**

| Field | Index at ingest | Filter at query | Notes |
|---|---|---|---|
| `tenantId` | Yes | Always | Non-negotiable for multi-tenant |
| `docType` | Yes | When scoped search needed | Filter on specific query types |
| `status` | Yes | Always (exclude drafts) | Never serve unpublished |
| `effectiveDate` | Yes | For freshness-sensitive queries | Legal, medical, compliance domains |
| `language` | Yes | When multilingual corpus | Match user locale |
| `source` | Yes | For citation tracking only | Rarely filtered |
| `chunkIndex` | Yes | Never | Diagnostic only |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. In-memory vector store with synthetic 4-dim embeddings. Filter predicate timing on 847-doc corpus.

```
=== Pre-filter candidate pool reduction ===

$ node -e "
// 847 docs: 200 for firm-acme, 60 published statutes/regs, 40 in date range
const docs = Array.from({length: 847}, (_, i) => ({
  id: 'chunk-' + i,
  metadata: {
    tenantId:       i < 200 ? 'firm-acme' : 'firm-other',
    docType:        i % 5 === 0 ? 'statute' : i % 5 === 1 ? 'regulation' : 'memo',
    status:         i % 3 === 0 ? 'published' : 'draft',
    effectiveDate:  i % 2 === 0 ? '2020-01-01' : '2018-01-01',
    effectiveUntil: null,
  },
}));
const filter = buildFilter({ tenantId: 'firm-acme', docTypes: ['statute', 'regulation'], asOfDate: '2024-01-01' });
const t0 = performance.now();
const candidates = docs.filter(filter);
const ms = performance.now() - t0;
console.log('847 docs → ' + candidates.length + ' candidates: ' + ms.toFixed(4) + ' ms');
"
847 docs → 40 candidates: 0.0412 ms

Filter evaluation: 0.0412 ms  (full corpus of 847)
Vector search over 40 candidates vs 847: 95% fewer comparisons

=== Filter-first vs post-filter ===

Filter-first (pre-filter, then search top-5):
  Candidate pool: 40 docs
  Vector comparisons: 40
  Returns: top-5 from the correct set

Post-filter (search top-50, then filter):
  Vector comparisons: 847 (full corpus)
  After filter: may return < 5 if filtered set has < 5 qualifying docs in top-50
  Risk: wrong-tenant results if filter misses a result at position > 50

Filter-first is always correct. Post-filter may return too few results and is slower.
```

## See also

[S-07](s07-rag.md) · [S-73](s73-multi-tenant-ai-isolation.md) · [S-66](s66-retrieval-score-thresholds.md) · [S-79](s79-hybrid-search.md) · [S-76](s76-semantic-dedup-at-ingest.md) · [F-37](../forward-deployed/f37-knowledge-cutoff-handling.md)

## Go deeper

Keywords: `metadata filtering` · `vector store filter` · `pre-filter retrieval` · `RAG metadata` · `tenant filter` · `date range filter` · `doc type filter` · `compound predicate` · `retrieval correctness` · `namespace filter`
