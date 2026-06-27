# S-175 · Cross-Session Tool Result Cache

[S-43](s43-tool-result-caching.md) caches tool results within a single session: when the same `get_contract(id=C-42)` call repeats in the same conversation, the cached result is returned without hitting the API. The cache lives in-memory for the lifetime of the session object. When the session ends, the cache is discarded. A new session for the same contract calls the same tool and pays the same cost. At one session per user and dozens of tool calls per session, this is efficient. At thousands of sessions per day all calling `get_contract` on the same hundred active contracts, the same hundred contract records are fetched thousands of times daily — the per-session cache provides no cross-session benefit.

A cross-session tool result cache stores tool results in a shared store — a process-level `Map` for a single-server deployment, a Redis instance for distributed deployments — with explicit TTL and tenant-scoped keys. Any session that calls the same tool with the same arguments and belongs to the same tenant gets the cached result regardless of which session originally fetched it. At 85% hit rate and 30 000 tool calls per day, 25 500 calls are served from cache at zero cost; only 4 500 calls go to the live API.

Three problems arise that don't exist in per-session caching: tenant isolation (keys must include a tenant identifier to prevent cross-tenant data leakage), cache stampede (when a popular key expires, many simultaneous sessions miss and all trigger fetches for the same key), and invalidation (when the underlying data changes, all cached values for the affected entity must be purged). Per-session caches expire naturally when the session ends; a shared cache persists and can serve stale data indefinitely if TTL and invalidation are wrong.

## Situation

A contract management SaaS serves 500 active tenants. Each tenant's sessions call `get_contract_metadata` frequently — 30 000 calls/day total. Contract metadata (parties, type, status, created_at) is stable for hours. Without cross-session caching: 30 000 API calls at $0.0005/call = $15.00/day.

With cross-session caching at 85% hit rate: 4 500 live calls at $0.0005 = $2.25/day. Savings: $12.75/day ($4 654/year). The 85% hit rate is realistic for stable reference data — multiple sessions across the same tenant accessing the same set of active contracts within a 5-minute window.

Three incidents that do not occur with per-session caching emerge:

**Stampede**: Contract C-99's cache entry expires at 14:30:00. At that moment, 40 sessions belonging to tenant_a simultaneously need C-99's metadata. Without stampede prevention: 40 API calls fire in parallel. With promise-based in-flight tracking: 1 call fires; 39 callers receive STAMPEDE_RESOLVED when the first call returns.

**Tenant isolation**: Tenant B calls `get_contract(id=C-42)`. Tenant A already has C-42 cached. Without tenant-scoped keys: tenant B hits tenant A's cache — a data leak. With tenant-scoped keys (`tenant_a:get_contract:{"id":"C-42"}` vs `tenant_b:get_contract:{"id":"C-42"}`): each tenant has its own isolated cache entry.

**Invalidation**: Contract C-42 is amended. All 500 sessions across all tenants that cached C-42's metadata receive stale data until TTL expires. Explicit invalidation on data change events (S-126) purges the cache immediately.

## Forces

- **Tenant isolation is not optional.** A shared cache keyed only by `tool_name:args_hash` returns tenant A's contract data to tenant B if they query the same contract ID. Prefix every key with the tenant identifier. If the tool itself is tenant-scoped (it can only return data belonging to the caller's tenant), key isolation is belt-and-suspenders; if the tool accepts cross-tenant IDs, key isolation is the only security boundary.
- **Stampede prevention uses a promise shared across concurrent callers.** The first caller for a cold key stores a pending Promise in an `inflight` map. Subsequent callers for the same key within that window await the same Promise rather than issuing their own API calls. When the Promise resolves, all callers receive the result. When it rejects, all callers see the error and may retry independently.
- **TTL must match data volatility, not session length.** Per-session caches are implicitly bounded by session duration (minutes). A shared cache with a 24-hour TTL on data that changes hourly serves stale answers for 23 hours. Set TTL by data class: reference data (user records, org settings) → 5 minutes; semi-static data (contract status, approval state) → 1 minute; dynamic data (live prices, inventory) → 10 seconds. Dynamic data may not be worth caching cross-session at all — use S-174 (stale-while-revalidate) for it instead.
- **LRU eviction prevents unbounded memory growth.** A process-level Map with no eviction policy grows until the process runs out of memory. Evict expired entries first on each cache write; if still above the size limit, evict the oldest entry (Map insertion order approximates LRU). For a Redis-backed cache, set `maxmemory-policy allkeys-lru` at the Redis level.
- **Never cache side-effecting tools cross-session.** S-43's rule applies doubly here: a cached `write_annotation` result served to a different session would be factually wrong — the annotation was written by session A, not session B. Maintain an explicit allowlist of cacheable (read-only) tools. Default-deny: only cache tools in the allowlist.
- **Compose with S-126 for invalidation on data change.** When a source system emits a data-change event for entity E, all cache keys matching `*:tool_name:*entity_id*` should be deleted. Pattern-delete on Redis (`SCAN` + `DEL`) or maintain an entity-to-key index for efficient invalidation. Without invalidation, cross-session caches serve stale data until TTL expiry; with invalidation, staleness is bounded by event propagation latency.

## The move

**Key by `tenantId:toolName:sortedArgsHash`. Prevent stampede with a shared in-flight Promise. Set TTL by data volatility class. Evict expired entries on write; evict LRU on size overflow.**

```js
// --- Cross-session tool result cache ---
// Shared across sessions; tenant-scoped keys prevent cross-tenant leakage.
// Stampede prevention: in-flight Map<key, Promise> shares first fetch with concurrent callers.
// Distinct from S-43 (session-local, per-conversation Map).
// Compose: S-175 (read path) → S-126 (invalidation on data change).

function hashArgs(args) {
  return JSON.stringify(args, Object.keys(args).sort());
}

const TTL = {
  REFERENCE:    300_000,   // 5 min  — user records, org settings, contract metadata
  SEMI_STATIC:   60_000,   // 1 min  — status, approval state
  DYNAMIC:       10_000,   // 10 s   — live prices (prefer S-174 for sub-second data)
};

class CrossSessionToolCache {
  constructor(opts) {
    opts = opts || {};
    this._maxSize    = opts.maxSize    || 1000;
    this._defaultTtl = opts.defaultTtl || TTL.REFERENCE;
    this._cache    = new Map();   // key → { value, fetchedAt, ttl }
    this._inflight = new Map();   // key → Promise (stampede prevention)
  }

  _key(tenantId, toolName, argsHash) {
    return `${tenantId}:${toolName}:${argsHash}`;
  }

  _evict() {
    const now = Date.now();
    for (const [k, v] of this._cache) {
      if (now - v.fetchedAt > v.ttl) this._cache.delete(k);
    }
    while (this._cache.size >= this._maxSize) {
      // Map iteration order is insertion order — oldest first.
      this._cache.delete(this._cache.keys().next().value);
    }
  }

  async get(tenantId, toolName, args, fetchFn, ttl) {
    const key = this._key(tenantId, toolName, hashArgs(args));
    const effectiveTtl = ttl !== undefined ? ttl : this._defaultTtl;
    const now = Date.now();

    const entry = this._cache.get(key);
    if (entry && now - entry.fetchedAt <= entry.ttl) {
      return { value: entry.value, source: 'HIT', ageMs: now - entry.fetchedAt };
    }

    // Stampede prevention: share in-flight promise.
    if (this._inflight.has(key)) {
      const value = await this._inflight.get(key);
      return { value, source: 'STAMPEDE_RESOLVED', ageMs: 0 };
    }

    const promise = (async () => fetchFn())();
    this._inflight.set(key, promise);
    const value = await promise;
    this._inflight.delete(key);

    this._evict();
    this._cache.set(key, { value, fetchedAt: Date.now(), ttl: effectiveTtl });
    return { value, source: 'MISS', ageMs: 0 };
  }

  // Call when a source data change event arrives for an entity.
  invalidate(tenantId, toolName, args) {
    this._cache.delete(this._key(tenantId, toolName, hashArgs(args)));
  }
}

// --- Integration: tool dispatch with cross-session cache ---

const TOOL_CACHE = new CrossSessionToolCache({ maxSize: 1000 });

// Cacheable read-only tools with their TTL class.
const CACHEABLE_TOOLS = {
  get_contract_metadata: TTL.REFERENCE,
  get_contract_status:   TTL.SEMI_STATIC,
  get_party_info:        TTL.REFERENCE,
};

async function callToolWithCache(tenantId, toolName, args, toolFn) {
  const ttl = CACHEABLE_TOOLS[toolName];
  if (ttl === undefined) {
    // Not in allowlist: call directly, never cache.
    return { value: await toolFn(args), source: 'UNCACHED' };
  }
  return TOOL_CACHE.get(tenantId, toolName, args, () => toolFn(args), ttl);
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. 4 cache entries, 5 test scenarios. Stampede prevention verified with concurrent Promise.all. Key-order invariance confirmed. `Map.get` + age check timed over 1 000 000 iterations.

```
=== Cross-Session Tool Result Cache ===

Session 1 (tenant_a): source=MISS   value.status=ACTIVE   (first call, cold key)
Session 2 (tenant_a): source=HIT    ageMs=0               (same session or new session, same tenant)
Session 3 (tenant_b): source=MISS   (tenant isolation: tenant_b key separate from tenant_a)
Stampede (C-99):      p1.source=MISS  p2.source=STAMPEDE_RESOLVED  (1 fetch, 2 callers)
Key-order invariant:  ra=MISS  rb=HIT  ({"id":"D-1","type":"NDA"} == {"type":"NDA","id":"D-1"})

Stats: { hits: 2, misses: 4, stampedePrevented: 1, evictions: 0, cacheSize: 4 }

=== Cost model (10 000 sessions/day, 3 tool calls/session) ===

                       Without cache    With cache (85% hit)
Live API calls/day        30 000             4 500
Cost/day                  $15.00/day         $2.25/day
Savings/day               —                  $12.75/day  ($4 654/year)

=== Timing (1 000 000 iterations) ===

Cache lookup (HIT path, Map.get + age check):  0.0039 ms
hashArgs() 2-field object:                     0.0032 ms
Live fetch: network-bound, not measured
```

## See also

[S-43](s43-tool-result-caching.md) · [S-174](s174-stale-while-revalidate-live-data.md) · [S-126](s126-event-driven-cache-invalidation.md) · [F-107](../forward-deployed/f107-in-flight-request-deduplication.md) · [S-73](s73-multi-tenant-ai-isolation.md)

## Go deeper

Keywords: `cross-session tool result cache` · `shared tool cache Redis` · `multi-session tool cache` · `tenant-scoped cache key` · `cache stampede prevention` · `shared tool result pool` · `LRU eviction tool cache` · `cross-session agent cache` · `tool cache invalidation` · `in-flight dedup shared cache`
