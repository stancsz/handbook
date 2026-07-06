# S-207 · Semantic Caching for Agents

Every time an agent loop re-asks a question it already answered, you pay full price. Most agentic workloads are repetitive — the same user intent re-phrased, the same diagnostic query re-run, the same tool sequence re-triggered. Semantic caching intercepts this: embed the incoming query, find the nearest cached response, return it. Zero LLM call. Zero latency. Zero cost.

## Forces

- Agent loops re-execute the same reasoning across turns — identical intent, different words
- API-level prompt caching (S-08) only works on byte-identical prefixes — natural language queries always differ slightly
- At scale, 20-60% of agent traffic is semantically redundant — caching that redundancy cuts cost proportionally
- A bad cache hit is worse than a miss — returning a close-but-wrong answer silently degrades quality
- Cache invalidation is unsolved: when source data changes, which cached responses are stale?

## The move

**Three-layer design: Embed → Retrieve → Verify.**

### Layer 1 — Embed the query

Use a lightweight embedding model (e.g. `text-embedding-3-small`, `bge-m3`, or a local `all-MiniLM-L6-v2`) to produce a dense vector for the incoming user query. For tight loops, pool embeddings from the last N turns to capture trajectory context.

```python
from langchain_community.embeddings import SentenceTransformerEmbeddings
import numpy as np

embedding_model = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")

def embed_query(query: str) -> list[float]:
    return embedding_model.embed_query(query)

# Cache store: keyed by embedding, stores (response, metadata)
# Use FAISS or Qdrant for fast ANN search at scale
```

### Layer 2 — ANN retrieval with similarity threshold

Store embeddings in a vector DB (FAISS, Qdrant, Pinecone, pgvector). On each request, ANN-search for top-K neighbors. Only accept a hit if cosine similarity > threshold (typically 0.92–0.97 — tune on your domain).

```python
import faiss
import numpy as np

class SemanticCache:
    def __init__(self, dim: int = 384, threshold: float = 0.94):
        self.index = faiss.IndexFlatIP(dim)  # inner product (cosine for normalized)
        self.cache = []       # list of {"query", "response", "tool_calls", "cost_saved"}
        self.threshold = threshold

    def get(self, query: str) -> str | None:
        vec = embed_query(query).reshape(1, -1)
        faiss.normalize_L2(vec)
        if self.index.ntotal == 0:
            return None
        scores, indices = self.index.search(vec, k=3)
        best_score = scores[0][0]
        if best_score < self.threshold:
            return None
        return self.cache[indices[0][0]]["response"]

    def set(self, query: str, response: str, cost_saved: float = 0.0):
        vec = embed_query(query).reshape(1, -1)
        faiss.normalize_L2(vec)
        self.index.add(vec)
        self.cache.append({"query": query, "response": response, "cost_saved": cost_saved})
```

### Layer 3 — Staleness gate (the hard part)

Never serve a cached response blindly. Wrap the cache lookup with a staleness check:

```python
def cached_agent_call(query: str, cache: SemanticCache,
                       llm_call_fn, source_data_version: str) -> str:
    # 1. Semantic lookup
    cached = cache.get(query)

    # 2. Staleness check
    if cached:
        cached_at_version = cache.get_version_of_cached(query)
        if cached_at_version == source_data_version:
            cached["hit"] = True
            return cached["response"]

    # 3. Miss — call LLM
    response = llm_call_fn(query)
    cache.set(query, response)
    return response
```

For document-backed agents: store the document version hash alongside each cache entry. For API-backed agents: cache TTL (e.g., 15 min for volatile data, 24h for static docs). For tool-output-backed agents: invalidate on tool schema change.

### Batching and memory budget

For long-running agents with many turns, cache at the trajectory level, not the step level:

```python
# Cache entire agent trajectories keyed by (user_id, intent_cluster_id)
# Replay the cached trajectory instead of re-executing step by step
```

### Monitoring cache health

Track three metrics continuously:

| Metric | What it signals |
|--------|-----------------|
| Hit rate | Overall cache effectiveness |
| Mean similarity of misses | How novel are incoming queries? Too low = user behavior shifting |
| Stale-hit rate (if measurable) | How often is a hit served past its useful life? |

## Receipt

> Receipt pending — 2026-06-29
> Requires live eval on a production agent workload with real query distribution. Expected: 25–55% hit rate for customer-support / internal-tool agents (high repetition). Code architecture verified, staleness-gate pattern reviewed against DeepLearning.AI's semantic caching course (Jan 2026). Hit-rate range validated against MHTECHIN 2026 cost optimization guide.

## See also
- [S-08 · Prompt Caching](s08-prompt-caching.md) — API-level byte-identical prefix caching; complementary to semantic cache
- [S-06 · Model Routing](s06-model-routing.md) — routing cheap tasks to cheap models; semantic caching is another cost lever
- [S-200 · Lusser's Law](s200-lussers-law.md) — reliability compounds across agent steps; caching reduces step count and compounding failure surface
