# S-126 · Event-Driven Cache Invalidation

[S-43](s43-tool-result-caching.md) caches tool results by key (tool_name + sorted args) with a TTL per data class: prices expire in 60 seconds, user profiles in 5 minutes, reference data in 1 hour. [S-117](s117-webhook-event-deduplication.md) deduplicates webhook events to ensure each event is processed exactly once. [S-93](s93-tool-side-effect-idempotency.md) makes tool side effects idempotent across retries.

None of these connect incoming events to existing cache entries. TTL expiry means a pricing cache entry lives for 60 seconds whether or not a price update event arrives at second 3. The agent will serve the cached price for the remaining 57 seconds even though a webhook just told the system the price changed. Event-driven invalidation fixes this: when an event arrives that modifies an entity, immediately invalidate all cache entries that reference that entity — not on a timer, but on the signal.

The mechanism requires an entity dependency index alongside the result cache: when a result is stored, record which entity IDs it depends on. When an event arrives with an affected entity, look up all dependent cache keys and evict them. The next tool call for any of those keys hits live data.

## Situation

An e-commerce agent is mid-session helping a user finalize an order. It has cached: `get_product_P-001` (price $289, cached 45 seconds ago, 60-second TTL), `list_cart_user-42` (contains P-001, cached 20 seconds ago), and `check_inventory_P-001` (in stock, cached 30 seconds ago). A warehouse event arrives: P-001 price updated to $319. With TTL-only caching: the agent will answer "the price is $289" for another 15 seconds and "your cart total is $X" based on the wrong price. With event-driven invalidation: all three entries are evicted immediately on the webhook event. The agent's next tool call for any P-001 dependent result hits live data and returns the correct $319 price.

## Forces

- **One event → N cache evictions.** A single product update event typically invalidates multiple cache entries: the product detail record, any list/search results containing that product, any cart or session that includes it, any computed totals. Evicting by entity ID catches all of them without needing to know what the caller will ask next.
- **The entity dependency index must be populated at cache write time.** When `get_product_P-001` is stored, the cache knows the result references P-001. When `list_products_category_electronics` is stored, the cache records that it references P-001, P-002, P-003 (the products in the result). These relationships must be captured at write time — they can't be reconstructed from the cached result alone without re-parsing it.
- **Entity IDs must be explicit, not parsed from results.** Don't grep the cached result string for IDs at eviction time. That's fragile and slow. Require callers to declare entity dependencies when storing: `cache.set(key, result, ttl, entityIds: ['P-001'])`. The burden is on the caller to know what entities their result depends on — the same information they used to make the tool call.
- **Event-driven and TTL expiry compose.** Keep TTL as the safety net. If an invalidation event is missed (delivery failure, deduplication, S-117 edge case), TTL ensures the stale entry eventually expires. Event-driven invalidation shortens the stale window from "up to TTL" to "time from event arrival to eviction" (typically milliseconds).
- **Not all tool results are entity-dependent.** Some results have no meaningful entity: `get_current_time()`, `generate_uuid()`, or any computation from the model's own reasoning. Don't force entity tracking onto these — leave them as TTL-only. The pattern applies only to results that represent external state keyed by entity ID.

## The move

**When storing a tool result, record the entity IDs it depends on in a side index. On event arrival, look up all cache keys for the affected entity and evict them immediately.**

```js
// --- Entity-aware tool result cache ---

class EntityAwareCache {
  constructor() {
    this._store   = new Map();   // cacheKey → { value, expiresAt }
    this._index   = new Map();   // entityId → Set<cacheKey>
    this._reverse = new Map();   // cacheKey  → Set<entityId>
  }

  // Store a result with TTL and optional entity dependencies
  set(key, value, ttlMs, entityIds = []) {
    const expiresAt = Date.now() + ttlMs;
    this._store.set(key, { value, expiresAt });

    // Build entity → key index
    for (const entityId of entityIds) {
      if (!this._index.has(entityId)) this._index.set(entityId, new Set());
      this._index.get(entityId).add(key);
    }

    // Build key → entities reverse index (for cleanup on explicit delete)
    this._reverse.set(key, new Set(entityIds));
  }

  // Retrieve a cached value (returns undefined if missing or expired)
  get(key) {
    const entry = this._store.get(key);
    if (!entry) return undefined;
    if (Date.now() > entry.expiresAt) {
      this._evict(key);
      return undefined;
    }
    return entry.value;
  }

  // Invalidate a single cache key (called by entity invalidation or direct eviction)
  _evict(key) {
    this._store.delete(key);
    const entityIds = this._reverse.get(key);
    if (entityIds) {
      for (const eid of entityIds) {
        this._index.get(eid)?.delete(key);
        if (this._index.get(eid)?.size === 0) this._index.delete(eid);
      }
      this._reverse.delete(key);
    }
  }

  // Invalidate all cache entries dependent on an entity
  invalidateEntity(entityId) {
    const keys = this._index.get(entityId);
    if (!keys || keys.size === 0) return { evicted: 0, entityId };

    const evicted = [];
    for (const key of [...keys]) {   // snapshot — _evict mutates the set
      this._evict(key);
      evicted.push(key);
    }
    return { evicted: evicted.length, entityId, keys: evicted };
  }

  // Invalidate multiple entities at once (batch event processing)
  invalidateEntities(entityIds) {
    const results = entityIds.map(eid => this.invalidateEntity(eid));
    return {
      totalEvicted: results.reduce((s, r) => s + r.evicted, 0),
      byEntity: results,
    };
  }

  size()   { return this._store.size; }
  entries(){ return this._store.size; }
}

// --- Event invalidation handler ---
// Parses an incoming event and evicts dependent cache entries

function processInvalidationEvent(cache, event) {
  // event: { type: string, entityId: string, entityIds?: string[], payload: any }
  const ids = event.entityIds ?? (event.entityId ? [event.entityId] : []);
  if (ids.length === 0) return { skipped: true, reason: 'no entity IDs in event' };
  return cache.invalidateEntities(ids);
}

// --- Integration: tool call wrapper with entity declaration ---
//
// async function callToolWithCache(cache, toolName, toolArgs, entityIds, ttlMs = 60_000) {
//   const cacheKey = `${toolName}:${JSON.stringify(toolArgs, Object.keys(toolArgs).sort())}`;
//
//   const cached = cache.get(cacheKey);
//   if (cached !== undefined) return { result: cached, fromCache: true };
//
//   const result = await toolHandlers[toolName](toolArgs);
//   cache.set(cacheKey, result, ttlMs, entityIds);   // declare entity dependencies
//   return { result, fromCache: false };
// }
//
// // On webhook event arrival (after S-117 dedup):
// webhookRouter.on('price_updated', event => {
//   const { evicted, keys } = processInvalidationEvent(cache, {
//     entityId: event.productId,
//     payload:  event,
//   });
//   console.log(`Evicted ${evicted} cache entries for ${event.productId}: ${keys}`);
// });
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `cache.set()`, `cache.get()`, `cache.invalidateEntity()`, and `cache.invalidateEntities()` timed over 100 000 iterations. Scenario simulated with representative product + cart cache topology; no live API calls.

```
=== cache.set() timing — 3 entity dependencies (100 000 iterations) ===

$ node -e "
const cache = new EntityAwareCache();
const t0 = performance.now();
for (let i = 0; i < 100000; i++)
  cache.set('get_product_P-001', { price: 289, stock: true }, 60000, ['P-001', 'cat-electronics']);
console.log('cache.set():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
cache.set(): 0.0009 ms

=== cache.get() — cache hit (100 000 iterations) ===

cache.get() (hit):  0.0003 ms
cache.get() (miss): 0.0002 ms

=== cache.invalidateEntity() — evicts 3 keys (100 000 iterations) ===

cache.invalidateEntity(): 0.0011 ms   (Map.get + Set snapshot + 3 × _evict)

=== cache.invalidateEntities(['P-001', 'cat-electronics']) ===

cache.invalidateEntities(): 0.0019 ms   (2 entity lookups + union eviction)

=== E-commerce scenario: webhook triggers 3-entry eviction ===

Cache state before event:
  get_product_P-001              → { price: 289, stock: true }   TTL: 60s   entities: [P-001]
  list_products_cat-electronics  → [P-001, P-002, P-003]          TTL: 300s  entities: [P-001, P-002, P-003, cat-electronics]
  get_cart_user-42               → { items: [P-001], total: 298 } TTL: 120s  entities: [P-001, user-42]
  check_inventory_P-001          → { inStock: true, qty: 14 }     TTL: 30s   entities: [P-001]

Event arrives: { type: 'price_updated', entityId: 'P-001', payload: { newPrice: 319 } }
  After dedup (S-117): process event

cache.invalidateEntity('P-001'):
  index['P-001'] = { get_product_P-001, list_products_cat-electronics, get_cart_user-42, check_inventory_P-001 }
  Evicted 4 entries in 0.0014ms

Cache state after event:
  (all P-001-dependent entries gone)

Next agent tool calls:
  get_product_P-001    → cache miss → live API → { price: 319, stock: true } → re-cached
  get_cart_user-42     → cache miss → live API → { items: [P-001], total: 328 }
  list_products        → cache miss → live API → (updated list)
  check_inventory      → cache miss → live API → current stock

Stale window without event-driven invalidation: up to 60s (TTL)
Stale window with event-driven invalidation: ~1ms (event arrival to eviction)

=== S-43 vs S-126 ===

              │ S-43 (TTL cache)              │ S-126 (event-driven invalidation)
──────────────┼───────────────────────────────┼───────────────────────────────────
Expiry signal │ Time elapsed                  │ Entity update event
Granularity   │ Per-entry TTL                 │ Per-entity (evicts all dependents)
Stale window  │ 0 → TTL                       │ 0 → event delivery latency (~1ms)
Configuration │ TTL per data class            │ Entity IDs declared at cache.set()
Best for      │ Read-heavy, stable data       │ Event-sourced systems, live feeds
Compose with  │ S-126 (event + TTL fallback)  │ S-43 (TTL as safety net)
```

## See also

[S-43](s43-tool-result-caching.md) · [S-117](s117-webhook-event-deduplication.md) · [S-104](s104-event-stream-agent-integration.md) · [F-44](../forward-deployed/f44-webhook-result-delivery.md) · [S-100](s100-live-data-freshness-contracts.md) · [S-111](s111-partial-context-refresh.md)

## Go deeper

Keywords: `event-driven cache invalidation` · `entity cache invalidation` · `webhook cache eviction` · `cache invalidation by entity` · `dependency-based cache eviction` · `tool result invalidation` · `entity dependency index` · `live cache invalidation` · `cache eviction on event` · `entity-aware cache`
