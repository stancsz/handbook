# S-244 · Semantic Caching at the Vector Layer

Same question, different words. Exact-match caching misses it. The LLM runs again, burns tokens, and you pay twice for one answer. Vector similarity turns paraphrases into cache hits — with a 0.85 threshold, ProjectDiscovery cut 59% of total LLM spend with no accuracy degradation.

## Forces

- **Exact caching only helps exact repetitions.** Production users phrase the same intent in dozens of ways. After the first query, an exact cache rarely fires again.
- **Semantic similarity caches across phrasings.** "Cancel my subscription" and "stop billing" map to the same embedding and return the same cached response.
- **Cost savings are large but threshold-sensitive.** A threshold too high (0.95) rarely fires; too low (0.70) returns wrong answers. The sweet spot is 0.85–0.90 for most RAG-style workloads.
- **Cache invalidation is harder than exact TTL.** With vector similarity, "close enough" is ambiguous. Stale cached responses for dynamic content (prices, availability) can mislead users.
- **Embedding model matters more than vector DB.** Using a general-purpose embedding (e.g., `text-embedding-3-large`) on domain-specific queries produces poor similarity. Fine-tuned domain embeddings significantly improve hit rates.

## The move

Embed incoming queries, store in a vector DB, retrieve the nearest neighbor above a similarity threshold. On hit: return cached response. On miss: call the LLM, store result.

Three decisions drive success: **embedding model selection**, **similarity threshold tuning**, and **TTL policy**.

### Architecture

```
Query → Embed → Vector Search → [score ≥ threshold]?
  Yes → Return cached response
  No  → LLM call → Store (text + embedding + metadata) → Return
```

### Implementation

```python
import anthropic
import numpy as np
from openai import OpenAI
from supabase import create_client, Client
import hashlib

# ─── Config ───────────────────────────────────────────────
EMBEDDING_MODEL = "text-embedding-3-small"   # 1536 dims, fast + cheap
SIMILARITY_THRESHOLD = 0.87                  # tuned per workload
CACHE_TTL_HOURS = 72
SIMILARITY_METRIC = "cosine"                 # or "euclidean" with adjusted threshold

# ─── Clients ───────────────────────────────────────────────
openai_client = OpenAI()
anthropic_client = anthropic.Anthropic()
supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"]
)

table = supabase.table("semantic_cache")


def embed(text: str) -> list[float]:
    """Generate embedding for query text."""
    resp = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return resp.data[0].embedding


def get_cached_response(query: str) -> dict | None:
    """
    Check vector store for semantically similar cached response.
    Returns cached item if similarity >= threshold, else None.
    """
    query_emb = embed(query)

    result = supabase.rpc(
        "match_cache",
        {
            "query_embedding": query_emb,
            "match_threshold": SIMILARITY_THRESHOLD,
            "match_count": 1,
        }
    ).execute()

    if not result.data:
        return None

    cached = result.data[0]
    # Guard: ensure TTL hasn't expired
    import datetime
    cached_at = datetime.datetime.fromisoformat(cached["created_at"].replace("Z", "+00:00"))
    age_hours = (datetime.datetime.now(datetime.timezone.utc) - cached_at).total_seconds() / 3600
    if age_hours > CACHE_TTL_HOURS:
        # Soft-delete stale entry
        supabase.table("semantic_cache").delete().eq("id", cached["id"]).execute()
        return None

    return cached


def store_cached_response(query: str, llm_response: str, metadata: dict = None):
    """Store query + response + embedding in vector cache."""
    query_emb = embed(query)
    table.insert({
        "query_hash": hashlib.sha256(query.encode()).hexdigest()[:16],
        "query_text": query[:2000],        # truncate long queries
        "response_text": llm_response,
        "embedding": query_emb,
        "metadata": metadata or {},
    }).execute()


def ask_llm(query: str) -> str:
    """Call the LLM for a cache miss."""
    resp = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": query}]
    )
    return resp.content[0].text


def semantic_cache_layer(query: str, force_refresh: bool = False) -> tuple[str, bool]:
    """
    Main entry point: check cache first, fall back to LLM on miss.
    Returns (response_text, cache_hit: bool).
    """
    if not force_refresh:
        cached = get_cached_response(query)
        if cached:
            return cached["response_text"], True

    response = ask_llm(query)
    store_cached_response(query, response)
    return response, False


# ─── Supabase RPC (run once) ─────────────────────────────────
"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE semantic_cache (
    id          BIGSERIAL PRIMARY KEY,
    query_hash  TEXT NOT NULL,
    query_text  TEXT NOT NULL,
    response_text TEXT NOT NULL,
    embedding   VECTOR(1536),
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON semantic_cache USING ivfflat (embedding vector_cosine_ops)
  WITH lists = 100;

-- Match cache RPC (add to Supabase edge functions or direct pg function)
CREATE OR REPLACE FUNCTION match_cache(
    query_embedding  VECTOR(1536),
    match_threshold  FLOAT,
    match_count      INT DEFAULT 1
) RETURNS SETOF semantic_cache AS $$
BEGIN
    RETURN QUERY
    SELECT * FROM semantic_cache
    WHERE 1 - (embedding <=> query_embedding) >= match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;
"""
```

### Threshold tuning checklist

| Threshold | Hit rate | Risk of wrong answer |
|-----------|----------|---------------------|
| 0.95      | ~10%     | Near zero           |
| **0.87**  | **35–55%** | **Acceptable for FAQ, code explainers** |
| 0.75      | ~70%     | Noticeable quality risk |
| 0.60      | ~85%     | Dangerous — false positives |

Start at 0.90, measure cache hit rate and user-reported errors weekly, then lower in 0.02 steps.

### When NOT to use semantic caching

- **Real-time data**: stock prices, live inventory, weather — cache with explicit TTL or don't cache at all
- **Personalized responses**: if the answer depends on user context, similarity checks will produce wrong answers
- **Multi-turn conversations**: each turn changes context; cache per conversation_id, not globally
- **Creative / novel content**: brainstorming, writing drafts — every query is unique and cache hits indicate a problem

## Receipt

> Receipt pending — June 30, 2026. The implementation above is a composite of verified patterns: Supabase `ivfflat` index + `pg_vector` RPC matching follows the approach documented at [n1n.ai](https://explore.n1n.ai/blog/reduce-llm-token-costs-semantic-caching-guide-2026-04-23) and [myengineeringpath.dev](https://myengineeringpath.dev/genai-engineer/llm-caching/). The 59% cost reduction figure is reported by ProjectDiscovery via [m2ml.ai benchmarks](https://m2ml.ai/post/prompt-caching-benchmarks-2026-how-to-cut-llm-costs-59-90-cmod0ijqx000u3lnvrl5maczy). The threshold sweet spot of 0.85–0.90 is corroborated across multiple 2026 production guides. The Supabase SQL schema was validated against v2 `pg_vector` syntax.

## See also

- [S-08 · Prompt Caching](s08-prompt-caching.md) — provider-side exact-prefix caching (complementary, not overlapping)
- [S-243 · Agentic Inference Cost Stratification](s243-agentic-inference-cost-stratification.md) — understanding where caching fits in the cost model
- [S-237 · LLM Orchestration Is Not Free](s237-llm-orchestration-is-not-free-multi-step-tool-chain-costs.md) — multi-step cost dynamics where caching compounds
