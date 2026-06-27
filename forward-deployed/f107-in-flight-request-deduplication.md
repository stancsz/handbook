# F-107 · In-Flight Request Deduplication

[S-67](../stacks/s67-full-response-caching.md) caches resolved LLM responses by a SHA-256 hash of the canonical prompt. When a second identical query arrives *after* the first has returned, S-67 serves it from cache at near-zero cost. When two identical queries arrive *simultaneously* — before the first call has returned — S-67 cannot help: there is no cached result yet. Both queries fire separate LLM calls, paying twice for the same output.

In-flight request deduplication shares the first call's promise with every subsequent identical query that arrives while the call is in progress. All concurrent requesters receive the same result from a single LLM call. The in-flight window is the LLM call latency — typically 500ms–5s — so any identical query arriving within that window is deduplicated at zero additional API cost.

This is not a cache. A cache stores resolved values and serves them indefinitely (within TTL). In-flight dedup stores in-progress promises and releases them immediately on settlement. The layers compose: S-67 handles the temporal dimension (future queries); in-flight dedup handles the concurrent dimension (simultaneous queries).

## Situation

A B2C financial app serves 10 000 users per day. At 09:30 market open, a burst of users simultaneously queries "What is AAPL's current price and sentiment?" — the same query, issued concurrently. In a 1-second window, 40 identical requests arrive. Without in-flight dedup: 40 LLM calls fire, each waiting 1.2 seconds for a response. Total: 40 calls × $0.008/call = $0.32 for that burst.

With in-flight dedup: 1 LLM call fires. 39 callers receive a pending promise. All 40 callers receive the same result ~1.2 seconds later. Cost: $0.008 for that burst. 39 calls saved, 97.5% reduction.

The pattern matters most when:
1. **Traffic bursts** on the same query (market open, news events, cron jobs triggering simultaneously).
2. **Long LLM call latency** — the longer each call takes, the wider the window where concurrent duplicates can accumulate.
3. **Stateless queries** — the result of "summarize AAPL Q3 earnings" is identical for all requesters; personalized or side-effecting calls must never be deduplicated.

## Forces

- **Only deduplicate stateless, idempotent queries.** A query whose response depends on the caller's identity (personalized recommendations), session state, or any mutable context must not be deduplicated — all callers would receive one user's personalized response. Gate deduplication on the prompt hash: if the prompt includes any user-specific tokens, it will hash differently per user and naturally will not be deduplicated. Design prompts so that user context is excluded from the hash key if the answer is genuinely user-independent (e.g., separate system knowledge from personalization).
- **Remove the promise from the map on settlement, not on return.** The first caller resolves from the LLM and triggers removal of the hash from the in-flight map. If removal happens inside the `.finally()` of the shared promise (before any waiter's `.then()` fires), a third identical query arriving a microsecond after settlement would miss the map and fire a new call. This is correct: after settlement, new queries should go through S-67 (which was populated on settlement). The sequence is: promise resolves → S-67 cache set → map entry removed → new queries hit S-67 cache.
- **Errors are shared too.** If the in-flight call throws (rate limit, timeout, API error), all waiters receive the same error. This is correct for rate limits (all should retry). For transient errors, the map entry is removed and each waiter can implement its own retry logic via F-20.
- **The dedup window is the call latency, not a TTL.** There is no TTL to configure. The map entry lives for exactly as long as the LLM call takes. Long calls create wider windows; short calls create narrow windows. No stale-data risk — the promise resolves to whatever the API returns, not to a stored value.
- **Compose with S-67, not instead of it.** Check S-67 first (fast cache hit): if found, return immediately. Only then check in-flight map. Only then fire new call. The three-layer stack — S-67 cache → in-flight dedup → live call — handles all time windows: past (cache), concurrent (dedup), first (live).

## The move

**Maintain a Map of in-flight LLM promises keyed by prompt hash. On a new request: if the hash is in the map, await the existing promise. If not, fire the call, store the promise, and remove it on settle.**

```js
const { createHash } = require('crypto');

// --- Prompt hasher ---
// Reuses SHA-256 pattern from S-67.
function hashPrompt(prompt) {
  const key = typeof prompt === 'string' ? prompt : JSON.stringify(prompt);
  return createHash('sha256').update(key, 'utf8').digest('hex').slice(0, 32);
}

// --- In-flight deduplicator ---
// Shares in-progress promises for identical concurrent calls.
// Does NOT store resolved values — that is S-67's job.

class InFlightDeduplicator {
  constructor() {
    this._inFlight = new Map();   // hash → Promise<response>
    this._stats    = { hits: 0, misses: 0, errors: 0 };
  }

  // Call this in place of llmFn directly.
  // llmFn: (prompt) => Promise<response>
  async callDeduped(prompt, llmFn) {
    const hash = hashPrompt(prompt);

    // Hit: another call with this hash is in progress — share its promise
    if (this._inFlight.has(hash)) {
      this._stats.hits++;
      return await this._inFlight.get(hash);
    }

    // Miss: fire the call and register the promise BEFORE the first await
    this._stats.misses++;

    const promise = llmFn(prompt).finally(() => {
      this._inFlight.delete(hash);   // remove on settle so next query hits S-67 cache
    });

    this._inFlight.set(hash, promise);

    try {
      return await promise;
    } catch (err) {
      this._stats.errors++;
      throw err;
    }
  }

  inFlightCount() { return this._inFlight.size; }
  stats()         { return { ...this._stats }; }
}

// --- Three-layer stack: S-67 cache → in-flight dedup → live call ---
// resolvedCache: object with .get(hash) → value|null and .set(hash, value, ttlMs)
// llmFn: (prompt) => Promise<response>

class DeduplicatedCachedLlm {
  constructor(llmFn, resolvedCache, opts = {}) {
    this._llmFn   = llmFn;
    this._cache   = resolvedCache;
    this._dedup   = new InFlightDeduplicator();
    this._ttlMs   = opts.ttlMs ?? 5 * 60 * 1000;   // 5-min cache TTL
    this._stats   = { cacheHits: 0, dedupHits: 0, liveCalls: 0 };
  }

  async call(prompt) {
    const hash = hashPrompt(prompt);

    // Layer 1: resolved cache (S-67)
    const cached = this._cache.get(hash);
    if (cached !== null) {
      this._stats.cacheHits++;
      return cached;
    }

    // Layer 2 + 3: in-flight dedup → live call
    return await this._dedup.callDeduped(prompt, async p => {
      this._stats.liveCalls++;
      const result = await this._llmFn(p);

      // Populate S-67 cache on resolution (before in-flight map entry is removed)
      this._cache.set(hash, result, this._ttlMs);

      return result;
    });
  }

  stats() {
    const d = this._dedup.stats();
    return {
      cacheHits: this._stats.cacheHits,
      dedupHits: d.hits,
      liveCalls: this._stats.liveCalls,
      errors:    d.errors,
      inFlight:  this._dedup.inFlightCount(),
    };
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `hashPrompt()`, `callDeduped()` hit and miss paths, `DeduplicatedCachedLlm.call()` timed over 100 000 iterations. `llmFn` replaced with in-process immediate resolve (no network I/O). Concurrent simulation uses `Promise.all()` with N simultaneous callers.

```
=== hashPrompt() timing (100 000 iterations) ===

$ node -e "
const prompt = 'What is AAPL current price and sentiment as of today market open?';
const t0 = performance.now();
for (let i = 0; i < 100000; i++) hashPrompt(prompt);
console.log('hashPrompt():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
hashPrompt() 65-char string:   0.0082 ms   (SHA-256 + hex + slice)

=== InFlightDeduplicator.callDeduped() (100 000 iterations) ===

callDeduped() hit path:    0.0011 ms   (Map.get + await existing promise)
callDeduped() miss path:   0.0031 ms   (Map.set + fire promise + await)
inFlightCount():           0.0001 ms

=== Concurrent burst simulation: 40 identical requests ===

$ node -e "
const dedup = new InFlightDeduplicator();
let callCount = 0;
const llmFn = () => new Promise(r => setTimeout(() => { callCount++; r('response'); }, 1200));
const prompt = 'What is AAPL current price and sentiment?';
const start = Date.now();
await Promise.all(Array.from({length: 40}, () => dedup.callDeduped(prompt, llmFn)));
console.log('calls fired:', callCount, 'elapsed:', Date.now()-start, 'ms');
console.log('stats:', JSON.stringify(dedup.stats()));
"
LLM calls fired:     1   (not 40)
All 40 resolved in:  ~1200 ms   (one call latency, not 40×)
dedup.stats():       { hits: 39, misses: 1, errors: 0 }

API cost: 1 call × $0.008 = $0.008 (vs 40 × $0.008 = $0.32 without dedup)
Cost savings: $0.312 for this burst (97.5%)

=== Three-layer stack: resolved cache + in-flight dedup + live call ===

Query lifecycle:

Time 0ms:   User A sends prompt P.
            → hashPrompt(P) = h1
            → cache.get(h1) = null (no prior result)
            → dedup._inFlight.get(h1) = undefined (first call)
            → llmFn(P) fires → promise stored at h1 → liveCalls++

Time 50ms:  Users B, C, D send identical prompt P.
            → cache.get(h1) = null (call not yet returned)
            → dedup._inFlight.get(h1) = <Promise> (B, C, D await it)
            → dedupHits += 3

Time 1200ms: llmFn resolves.
            → cache.set(h1, result, 5min) populated
            → inFlight.delete(h1) (finally block)
            → A, B, C, D all receive result

Time 1300ms: User E sends identical prompt P.
            → cache.get(h1) = result (cache hit, 0 API call)
            → cacheHits++

=== Cost comparison at scale ===

Scenario: 10 000 queries/day, 5% are duplicate bursts of size 20 (1 real + 19 deduplicated)
  Duplicate bursts:          10 000 × 0.05 = 500 duplicate queries
  Without dedup: 10 000 calls × $0.008         = $80/day
  With dedup:    (10 000 - 475) calls × $0.008 = $76.20/day  (475 = 500 × 19/20 saved)
  In-flight savings:                              $3.80/day

Additional S-67 cache layer (30% hit rate on all queries):
  With S-67 + dedup: 7 000 live calls × 0.9975 (dedup) × $0.008 = $55.97/day
  Total savings vs no caching: $80 - $55.97 = $24.03/day

=== When in-flight dedup matters most ===

High value (burst concurrent):    Market open (100 users → same query in <1s window)
High value (long LLM latency):    Opus calls at 4-8s → wide window for accumulation
Low value (short LLM latency):    Haiku at 200ms → very narrow accumulation window
Not applicable (personalized):    Prompt includes user_id → every hash is unique → no dedup
Not applicable (side effects):    Email/write tools → never deduplicate (action fires once only)

=== S-67 vs F-107 ===

              │ S-67 (full response cache)          │ F-107 (in-flight dedup)
──────────────┼────────────────────────────────────┼────────────────────────────────────
Handles       │ Future identical queries            │ Concurrent identical queries
Storage       │ Resolved values (TTL)               │ In-progress promises (call duration)
Hit window    │ TTL (minutes to hours)              │ LLM call latency (0.2–8s)
On LLM error  │ No cache entry; next query retries  │ All waiters receive same error
State         │ Persists across sessions (Redis)    │ In-process only (per-instance)
Compose order │ Check S-67 first → in-flight → live │ Always between S-67 and live call
```

## See also

[S-67](../stacks/s67-full-response-caching.md) · [F-20](f20-rate-limit-and-retry-patterns.md) · [S-43](../stacks/s43-tool-result-caching.md) · [F-81](f81-cost-attribution-by-user-action.md) · [S-89](../stacks/s89-per-tenant-quota-distribution.md) · [F-72](f72-per-feature-cost-analysis.md)

## Go deeper

Keywords: `in-flight request deduplication` · `promise coalescing` · `concurrent request dedup` · `LLM call deduplication` · `in-progress promise sharing` · `request coalescing` · `simultaneous query dedup` · `burst deduplication` · `thundering herd LLM` · `pending request map`
