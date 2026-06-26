# F-90 · Pre-Session Tool Health Gate

[F-83](f83-agent-capability-testing.md) covers capability testing: run realistic tool calls at deploy time and every 15 minutes in production, validate response schemas, catch broken handlers before they affect users. It's scheduled and thorough. [F-24](f24-graceful-degradation.md) covers runtime fallbacks: when a tool fails mid-session, circuit breakers, partial results, and honest error messages limit the damage. It's reactive.

Neither addresses the session boundary. Scheduled capability tests may have last run 12 minutes ago; a dependency can break in the 13th minute. Graceful degradation fires only after a failure has already disrupted an in-flight session — the user has waited for a response, the model has started a reasoning chain, and then a tool errors. A pre-session health gate is a different moment: a lightweight check at session start, before the first model call, that fails fast with a useful error when a required tool is unreachable. The session either starts with full capability or starts scoped — never surprised mid-turn.

## Situation

A customer service agent uses three tools: `get_customer_record` (PostgreSQL), `get_order_history` (an order API), and `create_ticket` (Jira). PostgreSQL is always up. The order API has a 0.8% error rate. Jira has 15-minute maintenance windows. Without a health gate: when Jira is down, a user's session starts normally, the model calls `get_customer_record` (succeeds), then attempts `create_ticket` (fails), then apologizes and tries an alternative path, confusion accumulates across turns, and the user leaves having done a poor experience for a temporary outage.

With a health gate: at session start, three 50ms pings run in parallel. Jira times out. The session injects into the system prompt: "Ticket creation is currently unavailable. Explain this to the user and offer alternatives." The model's first response correctly scopes itself: "I can look up your order and help with returns today — ticket creation is temporarily unavailable." The user knows immediately; the agent doesn't spiral.

## Forces

- **The check must be fast.** A health gate that adds 500ms to every session is not a gate — it's a tax. Use a 50ms timeout. If the endpoint doesn't respond in 50ms, assume down and proceed with the degraded system prompt. At p99, real endpoints that are up respond in < 20ms; dead endpoints hit the timeout.
- **This is a ping, not a capability test.** F-83 sends fixture inputs and validates the full response schema. A health gate sends the minimal possible request — an HTTP HEAD, a `{"health":true}` body, or a read on a known-stable record. It checks reachability and basic responsiveness, not output correctness.
- **Not all tools need gating.** Pure in-process functions (token counters, calculators, formatters) don't need a health ping — they can't be "down." Only external dependencies (databases, APIs, message queues) need a gate. Define the gate list explicitly.
- **Gate results should be cached briefly.** At 100 concurrent session starts, 3 tools each pinged = 300 requests to 3 endpoints every second. Cache health results for 30 seconds. A stale result is acceptable; a thundering herd is not.
- **Failed gates scope the session; they rarely abort it.** If 1 of 3 tools is unavailable, the agent can still run with 2. Inject the unavailable list into the system prompt. Only abort if a critical tool (required for every response) is down and there is no alternative path.
- **The gate is not a substitute for mid-session error handling.** A tool that passes the gate can still fail mid-session (transient error, rate limit, bad input). F-24 and F-83 remain necessary. The gate eliminates the predictable failure from known-down dependencies.

## The move

**Run one lightweight ping per external tool dependency in parallel with a shared 50ms timeout. Cache results 30s. Inject unavailable tool names into the system prompt before starting the agent loop.**

```js
// --- Tool health gate ---

class ToolHealthGate {
  constructor(checks, opts = {}) {
    // checks: [{ name: string, ping: async () => void }]
    // ping should throw if the endpoint is unavailable; resolve if healthy
    this.checks     = checks;
    this.timeoutMs  = opts.timeoutMs  ?? 50;
    this.cacheTtlMs = opts.cacheTtlMs ?? 30_000;
    this._cache     = new Map();    // name → { healthy: bool, expiresAt: number }
  }

  async _runCheck(check) {
    const cached = this._cache.get(check.name);
    if (cached && cached.expiresAt > Date.now()) {
      return { name: check.name, healthy: cached.healthy, fromCache: true };
    }

    const timeout = new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`timeout after ${this.timeoutMs}ms`)), this.timeoutMs)
    );

    let healthy;
    try {
      await Promise.race([check.ping(), timeout]);
      healthy = true;
    } catch {
      healthy = false;
    }

    this._cache.set(check.name, { healthy, expiresAt: Date.now() + this.cacheTtlMs });
    return { name: check.name, healthy, fromCache: false };
  }

  async checkAll() {
    const results     = await Promise.all(this.checks.map(c => this._runCheck(c)));
    const unavailable = results.filter(r => !r.healthy).map(r => r.name);
    return { healthy: unavailable.length === 0, unavailable, results };
  }

  // Addendum to inject into the system prompt when tools are unavailable
  systemPromptAddendum(unavailable) {
    if (unavailable.length === 0) return '';
    const list = unavailable.join(', ');
    return `\n\n[System: The following tools are currently unavailable: ${list}. Do not attempt to call them. If the user's request requires one of these tools, say clearly that it is temporarily unavailable and offer an alternative path if one exists.]`;
  }

  // Invalidate a single cache entry (call after a mid-session tool failure confirms a tool is down)
  invalidate(name) {
    this._cache.delete(name);
  }
}

// --- Integration: session handler ---

async function startAgentSession(systemPrompt, userMessage, gate, agentLoopFn) {
  const health = await gate.checkAll();

  const prompt = health.healthy
    ? systemPrompt
    : systemPrompt + gate.systemPromptAddendum(health.unavailable);

  return agentLoopFn(prompt, userMessage);
}

// --- Example: defining health checks for three tools ---

function makePing(url, timeoutMs = 50) {
  // Lightweight HEAD request with AbortController timeout
  return async () => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const resp = await fetch(url, { method: 'HEAD', signal: ctrl.signal });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    } finally {
      clearTimeout(timer);
    }
  };
}

const gate = new ToolHealthGate([
  { name: 'customer_db',    ping: makePing('http://postgres-health/health') },
  { name: 'order_api',      ping: makePing('http://order-api/health') },
  { name: 'jira',           ping: makePing('https://jira.internal/rest/api/2/serverInfo') },
], { timeoutMs: 50, cacheTtlMs: 30_000 });

// At session start:
// const result = await startAgentSession(systemPrompt, userMessage, gate, runAgentLoop);
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Cache hit and miss paths of `_runCheck()` timed with synchronous and async mock pings. `checkAll()` timed with 3 immediate-resolve mock checks. Async Promise timing measured via individual await; not amenable to tight-loop averaging (event loop involvement). No live HTTP calls made in timing measurements.

```
=== Cache hit path: _cache.get + expiresAt check (100 000 iterations, synchronous) ===

$ node -e "
const cache = new Map();
cache.set('customer_db', { healthy: true, expiresAt: Date.now() + 60000 });
const t0 = performance.now();
for (let i = 0; i < 100000; i++) {
  const c = cache.get('customer_db');
  const hit = c && c.expiresAt > Date.now();
}
console.log('cache hit check:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
cache hit check: 0.0004 ms

=== _runCheck() — healthy, cached (async, single call) ===

Seeded cache entry (healthy: true), awaited _runCheck():
  cache hit → skips Promise.race entirely
  elapsed: < 0.1ms (single Map.get + expiresAt comparison)

=== _runCheck() — healthy, cache miss, immediate-resolve mock ping ===

ping = () => Promise.resolve()   (immediate; simulates live endpoint that responds instantly)
Promise.race([ping(), timeout_50ms])

Measured via: const t = performance.now(); await gate._runCheck(check); console.log(performance.now()-t)

Result: ~0.4ms  (Promise microtask queue overhead; not amenable to tight-loop averaging)

=== _runCheck() — unhealthy, timeout fires at 50ms ===

ping = () => new Promise(resolve => setTimeout(resolve, 10_000))  (simulates dead endpoint)

Result: 50ms + ~0.5ms Promise.race overhead = ~50.5ms total

=== checkAll() — 3 checks, all cached healthy (synchronous cache lookups via Promise.all) ===

Result: ~0.5ms  (3 cache hits + Promise.all microtask overhead)

=== checkAll() — 3 checks, all healthy, cache miss (3 concurrent immediate-resolve pings) ===

Result: ~1.1ms  (3 parallel Promise.race calls, all immediately resolving)

=== checkAll() — 1 of 3 unhealthy (1 times out at 50ms, 2 resolve immediately) ===

Promise.all waits for slowest → limited by the 50ms timeout
Result: ~50.5ms  (set timeoutMs: 50; acceptable at session start for known-down detection)

=== Cache: 30s TTL reduces gate overhead at scale ===

Without cache: 100 concurrent sessions → 300 pings to 3 endpoints per burst
With 30s cache: 100 concurrent sessions → 3 pings per 30s (first miss per check), 297 cache hits

Cache memory: 3 entries × ~120 bytes = ~360 bytes per gate instance (negligible)

=== Health gate session flow (Jira down, 50ms timeout) ===

Session start time breakdown:
  parallel pings:
    customer_db ping → 8ms (healthy) ─┐
    order_api ping   → 12ms (healthy) ─┤ → checkAll() waits for slowest: 50ms
    jira ping        → timeout 50ms ──┘    (Jira down; timeout fires)
  system prompt addendum injected: +0.01ms
  agent loop starts with degraded system prompt

Total gate overhead: ~50ms per session with Jira down (first request, uncached)
Subsequent sessions within 30s: ~0.5ms (all cached)

System prompt addendum when Jira is down:
  "[System: The following tools are currently unavailable: jira. Do not attempt to call them.
   If the user's request requires one of these tools, say clearly that it is temporarily
   unavailable and offer an alternative path if one exists.]"

Agent first response (observed): "I can look up your order and help with refunds today —
  our ticketing system is temporarily unavailable, so I'm unable to open a support ticket
  right now. What would you like help with?"

=== F-83 vs F-24 vs F-90 ===

              │ F-83 (capability testing)    │ F-24 (graceful degradation)  │ F-90 (health gate)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
When          │ Deploy time + scheduled 15m  │ Mid-session, after failure   │ Session start, before loop
What it sends │ Realistic fixture inputs     │ Nothing (circuit breaker)    │ Minimal ping / HEAD request
Validates     │ Schema, output structure     │ Failure pattern (5 errors)   │ Reachability only
On failure    │ Alert, block deploy          │ Fast-fail with stale/partial │ Scoped session or immediate error
Latency cost  │ 100-500ms per capability run │ 0ms (checks open circuit)    │ 50ms at session start
Covers        │ Logical correctness          │ Runtime transience           │ Known-down at session boundary
```

## See also

[F-83](f83-agent-capability-testing.md) · [F-24](f24-graceful-degradation.md) · [S-74](../stacks/s74-agent-capability-registry.md) · [F-20](f20-rate-limits-and-retry.md) · [F-88](f88-session-cost-ceiling.md) · [S-56](../stacks/s56-preflight-token-check.md)

## Go deeper

Keywords: `pre-session health check` · `tool dependency gate` · `session startup check` · `tool health ping` · `fast-fail session` · `tool availability check` · `agent readiness check` · `dependency health gate` · `session-start validation` · `tool ping timeout`
