# S-151 · Source Response Latency Variance Monitor

[F-104](../forward-deployed/f104-live-source-health-monitor.md) tracks source health by error rate: when a source's error rate exceeds 20%, it is removed from the active list; below 5% after probing, it is re-admitted. [F-114](../forward-deployed/f114-source-response-time-slos.md) tracks latency SLOs by P95: when P95 crosses a threshold, the source is demoted in priority order. Both detect when a source is slow or failing.

Neither detects when a source is silently serving cached responses instead of live data — a failure mode that produces fast, successful, non-failing responses with plausible values. A financial data vendor throttling your API key will switch to serving a cached snapshot from their CDN. The response arrives in 3ms, status 200, with reasonable values. F-104 sees zero errors. F-114 sees a latency improvement (P95 drops from 280ms to 3ms). Neither flags anything wrong. The data may be hours old.

The tell is latency variance. A genuine live database query has variance: network jitter, query plan differences, lock contention, index warm-up all cause response times to fluctuate. A CDN or server-side cache returns in nearly constant time — the same prefetched payload, every time, at the same latency. When the spread between P1 and P99 latency across 20 consecutive calls drops below a threshold (default: 5ms), the source has almost certainly switched to serving cached data.

## Situation

A real-time equity data agent polls three sources on each cycle:
- **Bloomberg**: genuine live data, queries hit different index shards. Response times: 140–320ms range, P99-P1 spread = 78ms → NORMAL.
- **yfinance**: the agent's API key has hit its free-tier rate limit. yfinance silently switches to serving a 15-minute delayed snapshot from a CDN. Response times: 3–6ms, P99-P1 spread = 2.7ms < 5ms threshold → SUSPECTED_CACHE.
- **Refinitiv**: only 10 calls so far this session. WARMING_UP — insufficient samples for statistical assessment.

Without this monitor: the agent treats yfinance as the fastest source. [F-114](../forward-deployed/f114-source-response-time-slos.md) promotes it to first priority (lowest P95). The model receives price data that is 15 minutes stale, presented as live. A trading decision is made on the wrong price.

With this monitor: `status('yfinance')` returns `{ status: 'SUSPECTED_CACHE', spreadMs: 2.7, p1Ms: 3.0, p99Ms: 5.8 }` after 20 calls. An alert is logged. yfinance is removed from the active source list. Bloomberg, at 78ms spread, continues as the live source.

## Forces

- **Latency variance is the signal that survives caching.** A CDN returns the same payload in nearly constant time. Values can be plausible (the cached price was real, just stale). Error rates stay zero. The only signal that something changed is that the distribution of response times suddenly collapsed. Track spread (P99 − P1), not P50 — the spread is what distinguishes live from cached.
- **Minimum variance threshold is infrastructure-dependent.** For a remote API with TLS, real queries always have some jitter (TCP round-trip, TLS negotiation variance). A 5ms spread threshold works for most remote APIs. For on-prem or LAN-adjacent sources, lower it to 1ms. For high-latency sources (international APIs), the absolute latency varies more and the threshold can be looser — but the spread is still tight when cached.
- **Window size 20 is the minimum for statistical significance.** At 20 samples, the P1/P99 estimate uses the full window. At 10 samples, P1 and P99 are the min and max — misleadingly tight if the sample happened to be homogeneous by chance. Wait for 20 samples before trusting the spread. This is the WARMING_UP period.
- **Compose with F-114, not replace it.** F-114 demotes a source when P95 rises (source is slow). This monitor flags when P95 drops too much relative to P1 (source is caching). They are complementary health signals: F-114 catches degradation; this catches silent substitution. Both should be checked before selecting sources in S-137.
- **Act conservatively on SUSPECTED_CACHE.** Log the alert. Optionally probe with a cache-busting parameter if the API supports it (a unique query suffix or `Cache-Control: no-cache` header). If the probe returns a different latency profile, the suspicion is confirmed. Don't remove the source from the registry permanently — it may be temporary throttling that recovers after the API key's rate window resets.
- **False positive: cold start.** On the first 20 calls of a session, if all 20 happen to be served from a warm OS cache or a connection-pooled persistent connection with consistent RTT, the spread may be tight. This is why WARMING_UP should not gate; after 20 calls, if spread is consistently tight over multiple 20-call windows, the SUSPECTED_CACHE signal is reliable.

## The move

**Track per-call latency for each source. After 20 samples, compute P99-P1 spread. Flag SUSPECTED_CACHE when spread drops below threshold.**

```js
// --- Source response latency variance monitor ---
// Records per-call response latency for each live data source.
// After windowSize samples: flag SUSPECTED_CACHE when P99-P1 < minVarianceMs.
// Composable with F-114 (SLO-based priority) and F-104 (error-rate health).

class SourceLatencyVarianceMonitor {
  constructor(opts = {}) {
    this._windowSize    = opts.windowSize    ?? 20;   // samples before WARMING_UP ends
    this._minVarianceMs = opts.minVarianceMs ?? 5;    // P99-P1 below this = SUSPECTED_CACHE
    this._history       = new Map();                  // sourceName → number[]
  }

  // Record a completed call's latency for a source.
  // latencyMs: wall-clock ms from request start to response body parsed.
  record(sourceName, latencyMs) {
    if (!this._history.has(sourceName)) this._history.set(sourceName, []);
    const arr = this._history.get(sourceName);
    arr.push(latencyMs);
    if (arr.length > this._windowSize) arr.shift();
  }

  // P1 and P99 of the current window, plus their spread.
  _spread(arr) {
    const sorted = [...arr].sort((a, b) => a - b);
    const p1  = sorted[Math.max(0, Math.floor(sorted.length * 0.01))];
    const p99 = sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.99) - 1)];
    return { p1, p99, spread: p99 - p1 };
  }

  // Check the current status for a source.
  // Returns { status, p1Ms, p99Ms, spreadMs, minVarianceMs, samples }
  // status: 'WARMING_UP' | 'NORMAL' | 'SUSPECTED_CACHE'
  status(sourceName) {
    const arr = this._history.get(sourceName);
    if (!arr || arr.length < this._windowSize) {
      return { status: 'WARMING_UP', samples: arr ? arr.length : 0, required: this._windowSize };
    }
    const { p1, p99, spread } = this._spread(arr);
    return {
      status:         spread < this._minVarianceMs ? 'SUSPECTED_CACHE' : 'NORMAL',
      p1Ms:           parseFloat(p1.toFixed(1)),
      p99Ms:          parseFloat(p99.toFixed(1)),
      spreadMs:       parseFloat(spread.toFixed(1)),
      minVarianceMs:  this._minVarianceMs,
      samples:        arr.length,
    };
  }

  // Status for all tracked sources.
  allSources() {
    const out = {};
    for (const [name] of this._history) out[name] = this.status(name);
    return out;
  }
}

// --- Integration with S-137 source selection ---
// After recording each source call, check for cache suspicion before selecting
// priority order for the next fan-out.

const LATENCY_MONITOR = new SourceLatencyVarianceMonitor({ windowSize: 20, minVarianceMs: 5 });

async function fetchFromSource(sourceName, fetchFn) {
  const t0 = Date.now();
  const result = await fetchFn();
  const latencyMs = Date.now() - t0;
  LATENCY_MONITOR.record(sourceName, latencyMs);

  const s = LATENCY_MONITOR.status(sourceName);
  if (s.status === 'SUSPECTED_CACHE') {
    log({ level: 'WARN', event: 'source_suspected_cache', source: sourceName,
          spreadMs: s.spreadMs, threshold: s.minVarianceMs });
    // Optionally: probe with cache-busting parameter, then re-evaluate.
    // For now: flag but continue; S-137 can be told to deprioritize this source.
  }

  return result;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()` and `status()` timed over 100 000 iterations. Latency values are synthetic integers drawn from domain-appropriate ranges (Bloomberg 140–320ms, yfinance 3–6ms).

```
=== SourceLatencyVarianceMonitor timing (100 000 iterations) ===

record():                             0.0004 ms
status() — WARMING_UP (10 samples):  0.0003 ms   (early exit, no sort)
status() — NORMAL (20 samples):      0.0077 ms   (sort + P1/P99)
status() — SUSPECTED_CACHE (20):     0.0077 ms   (same path)

=== 3-source financial data agent ===

Bloomberg (20 calls, 140–320ms range):
  P1:       201.6ms
  P99:      279.7ms
  spreadMs: 78.1ms > 5ms threshold → NORMAL   (live DB queries)

yfinance (20 calls, 3–6ms range, free-tier rate limit hit → CDN):
  P1:       3.0ms
  P99:      5.8ms
  spreadMs: 2.7ms < 5ms threshold → SUSPECTED_CACHE
  Alert logged. Source removed from priority order for next fan-out.
  F-114 had previously promoted yfinance to #1 priority (lowest P95=4ms).
  After SUSPECTED_CACHE: Bloomberg promoted back to #1.

Refinitiv (10 calls, still in session warm-up):
  status: WARMING_UP (samples=10, required=20)
  → No gating applied yet.

=== Probe to confirm throttle ===

After SUSPECTED_CACHE detection, send one call with cache-bust header.
Throttled API:   new call still returns in 3ms → confirms CDN.
Recovered API:   new call returns in 155ms → confirms rate-limit reset; re-admit.

=== F-104 vs F-114 vs S-124 vs S-151 ===

              │ F-104 (error rate health)    │ F-114 (SLO latency)          │ S-124 (change rate)          │ S-151 (latency variance)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
Signal        │ Error rate per window        │ P95 vs SLO threshold         │ Value fingerprint change rate │ P99-P1 spread per window
Detects       │ Source returning errors      │ Source is slow (degraded)    │ Source values are changing   │ Source is caching (too fast)
Miss          │ Silent cached responses      │ Cache looks fast/healthy     │ Cached values may be stable  │ Source errors or slowness
Action        │ Remove / probe / re-admit    │ Demote in priority order     │ Alert on provider API change │ Alert + deprioritize/probe
Composes with │ S-151 (orthogonal signal)    │ S-151 (fast P95 is SUSPECT)  │ S-151 (value vs latency)     │ F-104 (error), F-114 (SLO)
```

## See also

[F-104](../forward-deployed/f104-live-source-health-monitor.md) · [F-114](../forward-deployed/f114-source-response-time-slos.md) · [S-124](s124-api-response-change-rate-monitor.md) · [S-137](s137-multi-source-field-level-merge.md) · [S-149](s149-multi-source-data-consistency-snapshot.md) · [F-98](../forward-deployed/f98-live-source-fanout.md)

## Go deeper

Keywords: `source latency variance monitor` · `live data cache detection` · `API throttle detection` · `CDN hit detection` · `response latency spread` · `source data freshness check` · `latency variance monitoring` · `live source cache suspicion` · `API rate limit detection via latency` · `data vendor throttle monitoring`
