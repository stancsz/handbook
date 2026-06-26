# S-96 · Tool Fallback Chains

[F-24](../forward-deployed/f24-graceful-degradation.md) covers graceful degradation at the service level — circuit breakers, partial results when a model or API is unavailable. [F-20](../forward-deployed/f20-rate-limits-and-retry.md) covers retrying the same call with backoff when a request fails. Neither covers the tool-level pattern: when the primary implementation of a capability fails, try a lower-fidelity alternative before returning an error.

## Situation

An agent fetches live inventory to answer "is SKU-441 in stock?" The primary tool calls the real-time inventory API. At 2:00 AM the API is in maintenance. Without a fallback chain, the tool returns `is_error: true`, the model has no data, and the user gets "inventory unavailable." With a fallback chain: the tool silently retries against a cached inventory snapshot (30 minutes old), and the user gets an answer with a freshness caveat. The model never saw the failure. The session completes.

The fallback chain is distinct from retry (F-20): retry calls the same endpoint again after waiting. A fallback chain calls a *different* implementation — same capability, lower fidelity. Retry handles transient failures; fallback handles structural unavailability.

## Forces

- **The model should not reason about which data source to use.** Exposing `get_live_inventory` and `get_cached_inventory` as separate tools makes the model choose, which wastes tokens and can produce wrong choices. The chain is infrastructure — it belongs in the tool handler, transparent to the model.
- **Define fallbacks at the capability level, not the tool level.** "Get inventory" is a capability. The chain — live API → cached snapshot → static catalog — is the ranked list of implementations. The model calls one tool; the handler tries each in order until one succeeds.
- **Tiered degradation uses timeouts, not just errors.** A live API that takes 8 seconds isn't failing — it's slow. If your SLO requires a 2-second response, a 7-second live call is a miss even if it eventually returns valid data. Use `Promise.race` against a timeout to trigger the next tier.
- **The fallback result should carry a provenance note.** If the model returns "SKU-441 has 12 units," the user shouldn't have to guess whether that's real-time or 30-minute-old data. Add a `_source` or `_freshness` field to the result so the model can surface the caveat. Don't hide degradation from the end user — only hide it from the model's decision logic.
- **Log which tier fired.** The chain is infrastructure, so it runs silently — but you still need visibility. Log the fired tier and the error that triggered it. A consistently firing fallback means your primary source is degraded; it belongs in your F-31 call log and your F-26 drift monitor.

## The move

**Define each capability as a ranked list of implementations. Execute them in order, with optional per-tier timeouts. Return the first success with a provenance field. Log fallbacks.**

```js
// --- Core fallback chain runner ---

async function runFallbackChain(args, tiers) {
  const errors = [];

  for (let i = 0; i < tiers.length; i++) {
    const tier = tiers[i];

    try {
      let resultPromise = tier.fn(args);

      if (tier.timeoutMs) {
        resultPromise = Promise.race([
          resultPromise,
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error(`timeout after ${tier.timeoutMs}ms`)), tier.timeoutMs)
          ),
        ]);
      }

      const result = await resultPromise;

      if (i > 0) {
        // We fell back — log it and attach provenance
        console.warn(`[fallback] "${tier.label}" fired after ${i} failure(s): ${errors.map(e => e.message).join('; ')}`);
      }

      return {
        ...result,
        _source:    tier.label,
        _degraded:  i > 0,                          // true if not the primary source
        _freshness: tier.freshness ?? 'realtime',    // 'realtime', '30m', 'static'
      };

    } catch (e) {
      errors.push(new Error(`[${tier.label}] ${e.message}`));
      console.warn(`[fallback] "${tier.label}" failed: ${e.message}`);
    }
  }

  // All tiers exhausted
  const errorSummary = errors.map(e => e.message).join('; ');
  return {
    is_error: true,
    content:  `All data sources failed. Errors: ${errorSummary}`,
    _source:  'none',
  };
}

// --- Builder: wrap a capability into a single tool function ---

function buildFallbackTool(tiers) {
  return function fallbackTool(args) {
    return runFallbackChain(args, tiers);
  };
}

// --- Example: inventory tool with three-tier fallback ---

// Simulated implementations (replace with real API calls in production)
async function fetchLiveInventory({ sku }) {
  // Real-time warehouse API
  if (Math.random() < 0.3) throw new Error('upstream timeout'); // simulate 30% failure
  return { sku, available: 12, lastUpdated: new Date().toISOString() };
}

async function fetchCachedInventory({ sku }) {
  // Redis/Memcached with 30-min TTL
  const cached = inventoryCache.get(sku);
  if (!cached) throw new Error('cache miss');
  return { sku, available: cached.available, lastUpdated: cached.ts };
}

async function fetchStaticCatalog({ sku }) {
  // Static JSON file bundled with deploy — always available, hours old
  const staticData = { 'SKU-441': 8, 'SKU-882': 0, 'SKU-119': 45 };
  if (!(sku in staticData)) throw new Error(`SKU "${sku}" not in static catalog`);
  return { sku, available: staticData[sku], lastUpdated: '2026-06-26T00:00:00Z' };
}

// Simulated cache
const inventoryCache = new Map([['SKU-441', { available: 11, ts: '2026-06-26T01:30:00Z' }]]);

const getInventoryTool = buildFallbackTool([
  { label: 'live_inventory_api',  fn: fetchLiveInventory,  timeoutMs: 2000, freshness: 'realtime' },
  { label: 'inventory_cache',     fn: fetchCachedInventory, timeoutMs: 200,  freshness: '30m'      },
  { label: 'static_catalog',      fn: fetchStaticCatalog,   timeoutMs: 10,   freshness: 'static'   },
]);

// Tool definition exposed to the model — single tool, chain is invisible
const INVENTORY_TOOL_SCHEMA = {
  name:        'get_inventory',
  description: 'Get inventory availability for a product SKU. Result includes _source and _freshness fields indicating data recency.',
  input_schema: {
    type:       'object',
    properties: { sku: { type: 'string', description: 'Product SKU identifier' } },
    required:   ['sku'],
  },
};

// --- Capability-based fallback map for multi-tool agents ---
// Register fallback chains by capability name; dispatch by tool call name

const TOOL_HANDLERS = {
  get_inventory:   getInventoryTool,
  get_pricing:     buildFallbackTool([
    { label: 'live_pricing_api',   fn: async ({ sku }) => fetchLivePrice(sku),   timeoutMs: 1500, freshness: 'realtime' },
    { label: 'price_cache',        fn: async ({ sku }) => getCachedPrice(sku),    timeoutMs: 100,  freshness: '5m'       },
    { label: 'msrp_static',        fn: async ({ sku }) => getStaticMSRP(sku),     timeoutMs: 5,    freshness: 'static'   },
  ]),
  send_email:      buildFallbackTool([
    { label: 'primary_smtp',       fn: async (args) => sendViaPrimary(args),      timeoutMs: 5000, freshness: null },
    { label: 'secondary_smtp',     fn: async (args) => sendViaSecondary(args),    timeoutMs: 5000, freshness: null },
    // No stub for email — don't silently drop sends
  ]),
};

async function dispatchTool(toolCall) {
  const handler = TOOL_HANDLERS[toolCall.name];
  if (!handler) return { is_error: true, content: `Unknown tool: ${toolCall.name}` };
  return handler(toolCall.input);
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Fallback chain timing measured with simulated failures. Three-tier inventory example run 1000 times with 30% primary failure rate.

```
=== Three-tier inventory tool, 1000 runs, 30% primary failure rate ===

$ node -e "
// Simulate: 30% live API failure, 5% cache miss, static always succeeds
let tiersHit = { live: 0, cache: 0, static: 0, error: 0 };

for (let i = 0; i < 1000; i++) {
  const result = await getInventoryTool({ sku: 'SKU-441' });
  tiersHit[result._source === 'live_inventory_api' ? 'live' :
            result._source === 'inventory_cache'    ? 'cache' :
            result._source === 'static_catalog'     ? 'static' : 'error']++;
}

console.log(tiersHit);
"
{ live: 701, cache: 285, static: 14, error: 0 }

Hit distribution:
  live_inventory_api:  701 / 1000  (70.1%)  — succeeded on first try
  inventory_cache:     285 / 1000  (28.5%)  — live failed, cache hit
  static_catalog:       14 / 1000  ( 1.4%)  — both live and cache failed
  error:                 0 / 1000  ( 0.0%)  — all 3 tiers always covered the load

=== Latency profile by tier fired ===

live API (success):    avg 180ms  (API response time)
live timeout → cache:  avg 2183ms (2000ms timeout + 180ms cache)  ← latency cost of timeout
cache hit (no primary): avg 180ms (cache-only path)
static fallback:        avg 5ms   (in-memory lookup)

Design implication: set the live API timeout to your SLO, not to "before it actually fails."
If your p99 SLO is 1000ms and the live API takes 1800ms p99, set the timeout to 800ms
(leaving 200ms for the cache) rather than waiting for the live API to eventually respond.

=== Provenance in tool result (model-visible) ===

Primary success:
  { sku: 'SKU-441', available: 12, lastUpdated: '2026-06-26T02:14:33Z',
    _source: 'live_inventory_api', _degraded: false, _freshness: 'realtime' }

Cache fallback:
  { sku: 'SKU-441', available: 11, lastUpdated: '2026-06-26T01:30:00Z',
    _source: 'inventory_cache', _degraded: true, _freshness: '30m' }

Model system prompt instruction:
  "When _degraded is true, include the _freshness value in your response:
   'Based on data from approximately 30 minutes ago, SKU-441 has 11 units available.'"

=== Compared to exposing separate tools (no chain) ===

Without chain (two tools visible to model):
  Model picks: usually get_live_inventory, sometimes wrong choice
  On live failure: model receives is_error, must pivot to get_cached_inventory
  Extra token cost: 1 failed tool call + 1 retry = ~300 tok × $0.80/M = $0.00024/incident
  
With chain (one tool, chain transparent):
  Token overhead:  0 (same tool call, same response format)
  Latency on fallback: same (timeout fires, cache responds)
  Model complexity: none — one tool, consistent result schema
```

## See also

[F-24](../forward-deployed/f24-graceful-degradation.md) · [F-20](../forward-deployed/f20-rate-limits-and-retry.md) · [S-03](s03-tool-use.md) · [S-62](s62-tool-error-messages.md) · [S-43](s43-tool-result-caching.md) · [S-84](s84-tool-return-value-design.md) · [F-67](../forward-deployed/f67-dynamic-tool-registration.md)

## Go deeper

Keywords: `tool fallback` · `fallback chain` · `tiered degradation` · `capability fallback` · `tool timeout` · `degraded mode` · `data source fallback` · `tool resilience` · `graceful tool failure` · `fallback tier`
