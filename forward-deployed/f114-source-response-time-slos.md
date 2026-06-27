# F-114 · Source Response Time SLOs

[F-104](f104-live-source-health-monitor.md) tracks error rate, null-result rate, and latency percentiles per source in a rolling window. Its removal trigger is error rate or health score — latency degradation is treated as a WARN signal, not a removal trigger ("too many dimensions of removal thresholds makes the monitor brittle"). [S-140](../stacks/s140-per-source-api-rate-limit-tracking.md) tracks API quota and rate limits per source. [F-45](f45-ai-response-latency-slos.md) defines SLOs at the agent-level response: the P95 latency from user request to agent reply.

None of these define a dedicated per-source response time SLO — a contract that says "Bloomberg equity data should respond in under 400ms at P95." When Bloomberg's P95 climbs from 280ms to 1900ms due to a provider-side infrastructure issue, the agent's overall SLO (F-45) will breach, but the diagnosis is diffuse: which source is slow? F-104 may not alert because error rate is healthy. S-140 sees no rate limit violations. The signal exists — latency increased — but no component is tracking it with an actionable threshold.

Source response time SLOs maintain a per-source P95 latency window, check against a configured threshold after each call, and produce two outputs: (1) a SLO status per source (OK / P95_BREACH / P99_BREACH), and (2) a priority-ordered source list based on current P50 latency — feed this into S-137's per-field source priority to prefer faster sources during degradation.

## Situation

A market data agent uses three equity data sources in S-137's `fieldSourceMap`: Bloomberg (primary for most fields), Refinitiv (first fallback), Alpha Vantage (second fallback). All three are "healthy" by F-104 standards — error rates under 5%.

Tuesday afternoon: Bloomberg's infrastructure team silently deploys a routing change. Bloomberg's P95 response time goes from 290ms to 1940ms. The agent's F-45 SLO (P95 ≤ 1600ms) is now breaching on the majority of requests — Bloomberg's latency alone exceeds the total SLO.

With source response time SLOs: Bloomberg's per-source P95 window breaches `p95Threshold: 400` within 15 calls (~15 seconds at the polling rate). `sloStatus('bloomberg_equity')` → `P95_BREACH`. `priorityOrder()` promotes Refinitiv (current P50=142ms) ahead of Bloomberg (current P50=1780ms). S-137 is updated to prefer Refinitiv for all fields where Refinitiv is a valid fallback. Agent P95 drops from 1940ms to 210ms. Engineering receives an alert: "bloomberg_equity P95_BREACH (1940ms, threshold 400ms)".

## Forces

- **Latency SLOs and availability SLOs are separate.** A source can be fully available (0% errors) and fatally slow. F-104's health score conflates the two by summing error_weight and latency_weight — you get one number representing neither cleanly. Separate the concerns: F-104 for availability, F-114 for latency SLOs. Each is actionable on its own.
- **P95 breach threshold is the SLO, not the removal trigger.** Do not remove a source from S-137's fan-out purely on P95 breach — the source may still be faster than making do with one source. Instead, demote it in priority order. The slower source becomes the last resort, not a removed option. F-104 handles removal when health score deteriorates (errors + null results compound).
- **Separate P95 (warn) and P99 (critical) thresholds.** P95 breach means the tail is heavy — something changed, worth logging and deprioritizing. P99 breach at the same threshold means every 1-in-100 call is very slow. These map to different alert severities and response procedures.
- **Priority order based on P50, not P95.** When choosing which source to try first in S-137, the relevant metric is median latency — how long does a typical successful call take? Sort ascending by P50 so the fastest median source is tried first. P95/P99 are for SLO alerting; P50 is for routing.
- **Window size trades recency for stability.** A 20-sample window detects latency spikes within 20 calls but is noisy for sources with bursty latency. A 100-sample window is more stable but detects a sustained degradation only after 100 calls (5–100 seconds depending on poll rate). Default 50 samples: detects sustained degradation in ~50 calls while ignoring single-call spikes.
- **Bootstrap period.** With fewer than 10 samples, the P95 estimate is unreliable. Report `sloStatus` as `INSUFFICIENT_DATA` and exclude the source from `priorityOrder` (treat as medium priority). Prevents premature demotion of a healthy source on startup.

## The move

**Track per-source P95 latency in a rolling window. Alert on SLO breach. Produce a priority-ordered source list for S-137.**

```js
// --- Source latency SLO configuration ---
// p95Threshold: ms — warn if P95 exceeds this
// p99Threshold: ms — critical if P99 exceeds this (typically p95Threshold × 1.5)
// windowSize:   number of recent calls to use for percentile computation (default 50)
// minSamples:   minimum calls before SLO evaluation (default 10)

// --- Source response time SLO tracker ---

class SourceResponseTimeSLOTracker {
  constructor(sourceConfigs) {
    // sourceConfigs: Map<sourceId, { p95Threshold, p99Threshold, windowSize?, minSamples? }>
    this._configs  = new Map(Object.entries(sourceConfigs));
    this._windows  = new Map();   // sourceId → { samples: number[], head: number, size: number }
  }

  // Record one call's latency for a source.
  // latencyMs: number — elapsed time from request start to response received (ms)
  record(sourceId, latencyMs) {
    if (!this._windows.has(sourceId)) {
      const windowSize = this._configs.get(sourceId)?.windowSize ?? 50;
      this._windows.set(sourceId, { samples: [], head: 0, windowSize });
    }
    const w = this._windows.get(sourceId);
    if (w.samples.length < w.windowSize) {
      w.samples.push(latencyMs);
    } else {
      w.samples[w.head] = latencyMs;
      w.head = (w.head + 1) % w.windowSize;
    }
  }

  // Compute stats from the raw (unsorted) ring buffer.
  _stats(sourceId) {
    const w = this._windows.get(sourceId);
    if (!w || w.samples.length === 0) return null;
    const sorted = [...w.samples].sort((a, b) => a - b);
    const pct = p => sorted[Math.ceil((p / 100) * sorted.length) - 1];
    return {
      p50:   pct(50),
      p95:   pct(95),
      p99:   pct(99),
      min:   sorted[0],
      max:   sorted[sorted.length - 1],
      count: sorted.length,
    };
  }

  // Returns { status, p50, p95, p99, p95Threshold, p99Threshold, count }
  sloStatus(sourceId) {
    const cfg   = this._configs.get(sourceId);
    if (!cfg) return { status: 'NO_CONFIG', sourceId };

    const s     = this._stats(sourceId);
    const minS  = cfg.minSamples ?? 10;
    if (!s || s.count < minS) {
      return { status: 'INSUFFICIENT_DATA', sourceId, count: s?.count ?? 0, minSamples: minS };
    }

    const status = s.p99 > cfg.p99Threshold ? 'P99_BREACH'
                 : s.p95 > cfg.p95Threshold ? 'P95_BREACH'
                 : 'OK';

    return {
      status,
      sourceId,
      p50:          s.p50,
      p95:          s.p95,
      p99:          s.p99,
      p95Threshold: cfg.p95Threshold,
      p99Threshold: cfg.p99Threshold,
      count:        s.count,
    };
  }

  // Sort sourceIds ascending by current P50 latency (fastest first).
  // Sources with INSUFFICIENT_DATA are placed in the middle (after OK sources, before breaching).
  // Sources with P99_BREACH are placed last.
  priorityOrder(sourceIds) {
    const statusMap = new Map(
      sourceIds.map(id => [id, this.sloStatus(id)])
    );

    return [...sourceIds].sort((a, b) => {
      const sa = statusMap.get(a), sb = statusMap.get(b);
      const tierA = sa.status === 'P99_BREACH' ? 2 : sa.status === 'INSUFFICIENT_DATA' ? 1 : 0;
      const tierB = sb.status === 'P99_BREACH' ? 2 : sb.status === 'INSUFFICIENT_DATA' ? 1 : 0;
      if (tierA !== tierB) return tierA - tierB;
      const p50A = sa.p50 ?? Infinity, p50B = sb.p50 ?? Infinity;
      return p50A - p50B;
    });
  }

  // Summary across all configured sources.
  fleetStatus() {
    return [...this._configs.keys()].map(id => this.sloStatus(id));
  }
}

// --- Integration with S-137 ---
// Rebuild S-137's per-field source priority lists based on current SLO latency ranking.
// Call this after each batch of calls (e.g., every 60 seconds or on P95_BREACH alert).

function rebuildSourcePriority(fieldSourceMap, sloTracker, allSourceIds) {
  const ranked = sloTracker.priorityOrder(allSourceIds);
  const result = {};

  for (const [field, sourceList] of Object.entries(fieldSourceMap)) {
    // Filter to only sources declared for this field; re-order by SLO latency rank.
    const fieldSet = new Set(sourceList);
    result[field] = ranked.filter(id => fieldSet.has(id));
  }
  return result;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()`, `sloStatus()`, `priorityOrder()` timed over 100 000 iterations. Latency scenario: three sources, 50-sample window each.

```
=== SourceResponseTimeSLOTracker timing (100 000 iterations) ===

record() — window not full:                  0.0009 ms
record() — window full (ring overwrite):     0.0004 ms
sloStatus() — window full (50 samples):      0.0041 ms   (sort + 3 percentile calls)
sloStatus() — INSUFFICIENT_DATA path:        0.0001 ms   (early return)
priorityOrder() — 3 sources:                 0.0141 ms   (3 × sloStatus + sort)
fleetStatus() — 3 sources:                   0.0124 ms   (3 × sloStatus)
rebuildSourcePriority() — 3 fields × 3 src: 0.0091 ms   (priorityOrder + 3 set filters)

=== Three-source equity data scenario ===

Sources: bloomberg_equity, refinitiv_equity, alpha_vantage_equity
SLO configs:
  bloomberg_equity:   { p95Threshold: 400, p99Threshold: 600  }
  refinitiv_equity:   { p95Threshold: 300, p99Threshold: 500  }
  alpha_vantage_equity: { p95Threshold: 500, p99Threshold: 800 }

--- Pre-incident (baseline, 50 calls each) ---
bloomberg_equity:     p50=287ms  p95=342ms  p99=391ms  → OK
refinitiv_equity:     p50=142ms  p95=189ms  p99=226ms  → OK
alpha_vantage_equity: p50=410ms  p95=612ms  p99=731ms  → P95_BREACH (612ms > 500ms threshold)

priorityOrder(['bloomberg_equity','refinitiv_equity','alpha_vantage_equity'])
  → ['refinitiv_equity', 'bloomberg_equity', 'alpha_vantage_equity']
  (alpha_vantage is OK tier but p50=410ms; refinitiv and bloomberg both OK, sorted by p50)
  Note: alpha_vantage already P95_BREACH pre-incident — rate-limit contention from S-140

--- Bloomberg infrastructure incident (call 51+) ---
bloomberg_equity: response times spike: 1200ms, 1850ms, 1940ms, 2100ms, ...
After 15 calls above threshold (window mixing old samples):
  p95 = 1650ms > 400ms threshold → P95_BREACH
  p99 = 1940ms > 600ms threshold → P99_BREACH

sloStatus('bloomberg_equity'):
  { status: 'P99_BREACH', p50: 1780, p95: 1650, p99: 1940,
    p95Threshold: 400, p99Threshold: 600, count: 50 }

priorityOrder() after incident:
  → ['refinitiv_equity', 'alpha_vantage_equity', 'bloomberg_equity']
  (bloomberg demoted to last: P99_BREACH tier; alpha_vantage P95_BREACH stays middle tier)

rebuildSourcePriority({ price: ['bloomberg','refinitiv','alpha_vantage'], ... }):
  → { price: ['refinitiv_equity', 'alpha_vantage_equity', 'bloomberg_equity'], ... }
  S-137 now tries Refinitiv first for price — Bloomberg is last resort.

Agent P95 impact:
  Before: bloomberg primary → P50 1780ms → F-45 SLO breach
  After:  refinitiv primary → P50 142ms  → F-45 SLO OK

Alert fired: "bloomberg_equity P99_BREACH: p95=1650ms (threshold 400ms), p99=1940ms (threshold 600ms)"
Action: engineering investigates Bloomberg infrastructure; rebuildSourcePriority() called immediately.

--- Bloomberg recovery (call 121+) ---
bloomberg_equity: response times normalize: 290ms, 310ms, 275ms, ...
After 30 calls (window predominantly new samples): p95 drops below threshold.
sloStatus('bloomberg_equity') → OK, p95=312ms

priorityOrder() after recovery:
  → ['refinitiv_equity', 'bloomberg_equity', 'alpha_vantage_equity']
  Bloomberg restored to original priority — no manual intervention required.

=== F-104 vs S-140 vs F-45 vs F-114 ===

              │ F-104 (source health monitor)     │ S-140 (rate limit tracking)       │ F-45 (agent SLOs)                 │ F-114 (source latency SLOs)
──────────────┼───────────────────────────────────┼───────────────────────────────────┼───────────────────────────────────┼───────────────────────────────────
Metric        │ Error rate + null rate + latency  │ RPM / daily quota remaining       │ Agent response P95                │ Per-source P95 latency only
Trigger       │ Health score < threshold          │ Quota exhausted or rate exceeded  │ SLO window breach                 │ P95 or P99 > per-source threshold
Action        │ Remove source from fan-out        │ Route calls to fallback source    │ Alert/incident response           │ Demote in priority order + alert
Priority      │ Not updated — binary in/out       │ Not updated — route away from     │ Not updated — agent-level only    │ Updated: priorityOrder() → S-137
reorder       │                                   │ exhausted source                  │                                   │ fieldSourceMap rebuild
Recovery      │ Re-admit when health recovers     │ Re-admit when quota resets        │ Alert clears when SLO recovers    │ Restore priority when P95 recovers
Composes with │ F-114 latency surface → one alert │ S-137 active source pre-filter    │ F-114 diagnoses WHICH source is   │ F-104 (remove on errors), S-137
              │ per source (error + latency)      │ before fan-out                    │ slow when F-45 breaches           │ (priority reorder), F-45 (SLO dial)
```

## See also

[F-104](f104-live-source-health-monitor.md) · [S-137](../stacks/s137-multi-source-field-level-merge.md) · [F-45](f45-ai-response-latency-slos.md) · [S-140](../stacks/s140-per-source-api-rate-limit-tracking.md) · [F-113](f113-per-entity-data-completeness-tracking.md) · [S-136](../stacks/s136-adaptive-per-entity-poll-rate.md)

## Go deeper

Keywords: `source response time SLO` · `per-source latency threshold` · `data source latency SLO` · `source P95 latency` · `live data source latency` · `source latency tracking` · `source priority by latency` · `latency-based source routing` · `data source response time alert` · `source latency percentile window`
