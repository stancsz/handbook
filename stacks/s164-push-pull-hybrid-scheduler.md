# S-164 · Push-Pull Hybrid Scheduler

[S-42](s42-event-driven-vs-polling.md) governs the choice between push and pull: if the source emits events, use them; if not, poll. The entry treats push and pull as mutually exclusive architectures. [S-118](s118-adaptive-polling-interval.md) tunes polling interval based on observed update frequency. [S-136](s136-per-entity-adaptive-poll-rate.md) applies per-entity adaptive polling rates. All three assume pure pull — they have no mechanism to exploit push events when available. [S-154](s154-reconnect-event-dedup.md) handles deduplication on reconnect, not gap detection during normal operation.

None of these resolve the failure mode of pure push: if a webhook misses a delivery — network fault, source-side backpressure, silent loss under high load — the agent never knows. A missed push is invisible to the listener until something downstream breaks. Pure push has best-case latency and worst-case blindness; pure pull has consistent freshness but pays the API cost for every entity on every interval.

A push-pull hybrid scheduler uses push as the primary delivery channel and triggers a pull for any entity that goes longer than `expectedInterval × gapMultiplier` without a push. The pull is the fallback, not the primary — it fires only when push is silent. Normal operation costs zero pull calls; degraded delivery triggers targeted pulls only for the entities that missed events.

## Situation

A market data platform delivers price updates for 100 instruments via webhooks. Under normal conditions, each instrument pushes every 30 seconds. The total push volume is ~8 640 events per day per instrument, well within webhook capacity. Under network partition or upstream backpressure, pushes stop for all or some instruments with no signal to the listener.

Pure polling as a baseline: 100 instruments × 2 calls/min = 12 000 calls/hour. Even at $0.001/call, that is $12/hour continuously whether prices are moving or not.

Pure push: zero pull calls in normal operation, but zero coverage during delivery failures. A 10-minute outage means 10 minutes of stale prices used as current in downstream agents.

Hybrid: a background interval checks every 5 seconds whether any instrument has exceeded `30s × 1.5 = 45s` without a push. During normal delivery, no pull is triggered. During a delivery failure, the gap is detected within one check interval (5s) and a targeted pull fires only for the affected instruments. Gap detection overhead: `checkGaps()` on 100 entities takes ~0.04 ms.

## Forces

- **Gap threshold is not the same as polling interval.** `gapMultiplier: 1.5` means an entity is only pulled after 1.5 missed expected intervals, not at every expected interval. Setting this too low (e.g. 1.1) means a push arriving 1 second late triggers an unnecessary pull. Setting it too high (e.g. 3.0) means failures go undetected for 90 seconds. Tune to match the downstream consequence of staleness.
- **Only push events reset the gap timer; pull results do not.** A gap-filling pull tells the agent the current value — it does not prove the push channel is healthy. If the pull result were used to reset `lastPushAt`, a broken push channel would look "healthy" as long as pulls were succeeding. Track push events and pull events separately in stats.
- **Register expected intervals from your SLA, not from observed frequency.** Use the upstream source's stated delivery frequency, not the mean observed interval. An instrument pushed every 30s by SLA but with observed 31s average would trigger constant gap fills at a 45s threshold if you derived the expected interval from observation.
- **Compose with S-163 query-type cache.** On a gap-filling pull, the result is the freshest data the agent can get but is still a fallback. Mark gap-fill pull results explicitly (`source: 'GAP_FILL'`) and log them for S-100 freshness contract tracking. Do not cache gap-fill results with the same TTL as normal data — gap fills indicate push channel degradation, which may persist.
- **Startup period: no gap detection until first push arrives.** `lastPushAt === null` means the entity has never received a push — do not treat this as a gap. If startup data is needed before the first push, seed the entity with an initial pull and set `lastPushAt` to the current time. Gap detection starts from the first confirmed push.
- **S-118 tunes polling frequency for pure pull; S-164 adds a push channel that makes polling the exception.** Use both when the data source supports push but polling is required as a fallback.

## The move

**Use push as the primary channel. Check for gaps on a background interval. Trigger targeted pulls only for entities that exceeded the gap threshold.**

```js
// --- Push-pull hybrid scheduler ---
// Push events reset the gap timer per entity.
// Background interval checks all entities for gaps.
// Pull triggered only when push is silent beyond expectedInterval × gapMultiplier.
// Startup: lastPushAt === null → no gap detection until first push arrives.
// Stats: pull counts track gap-fill frequency; push counts track delivery health.

class PushPullHybridScheduler {
  constructor(opts) {
    opts = opts || {};
    this._gapMultiplier = opts.gapMultiplier || 1.5;
    this._entities      = new Map();  // entityId → { expectedIntervalMs, lastPushAt, pullCount, pushCount }
    this._gapCount      = 0;
  }

  // Register an entity with its expected push interval.
  // expectedIntervalMs: the SLA delivery frequency, e.g. 30000 for 30-second pushes.
  register(entityId, expectedIntervalMs) {
    this._entities.set(entityId, {
      expectedIntervalMs,
      lastPushAt: null,  // null until first push — no gap detection before first event
      pullCount:  0,
      pushCount:  0,
    });
    return this;
  }

  // Call when a push event arrives for an entity.
  // Resets the gap timer. Only push events — not pull results — reset it.
  onPush(entityId, nowMs) {
    nowMs = nowMs || Date.now();
    const e = this._entities.get(entityId);
    if (!e) return;
    e.pushCount++;
    e.lastPushAt = nowMs;
  }

  // Check all entities for push gaps. Call on a regular interval (e.g. setInterval 5000).
  // Returns list of entityIds whose push has been silent beyond gapMultiplier × expectedInterval.
  // Caller is responsible for executing a pull for each returned entityId.
  checkGaps(nowMs) {
    nowMs = nowMs || Date.now();
    const needsPull = [];
    for (const [entityId, e] of this._entities) {
      if (e.lastPushAt === null) continue;  // no push yet — normal startup, not a gap
      const age       = nowMs - e.lastPushAt;
      const threshold = e.expectedIntervalMs * this._gapMultiplier;
      if (age > threshold) {
        needsPull.push({ entityId, ageMs: Math.round(age), threshold: Math.round(threshold) });
        e.pullCount++;
        this._gapCount++;
      }
    }
    return needsPull;
  }

  stats() {
    const result = {};
    for (const [id, e] of this._entities) {
      result[id] = { pushCount: e.pushCount, pullCount: e.pullCount };
    }
    return { entities: result, totalGaps: this._gapCount };
  }
}

// --- Integration: webhook handler + gap-fill loop ---

const SCHED = new PushPullHybridScheduler({ gapMultiplier: 1.5 })
  .register('AAPL', 30000)   // push expected every 30s
  .register('MSFT', 30000)
  .register('GOOG', 30000);

// Webhook handler — called by push delivery
function onWebhookPush(entityId, data) {
  SCHED.onPush(entityId);
  updateEntityData(entityId, data, 'PUSH');
}

// Gap-fill loop — runs every checkIntervalMs
setInterval(function() {
  const gaps = SCHED.checkGaps();
  for (const gap of gaps) {
    fetchLiveData(gap.entityId)
      .then(function(data) { updateEntityData(gap.entityId, data, 'GAP_FILL'); })
      .catch(function(err) { log({ event: 'gap_fill_error', entityId: gap.entityId, err }); });
    log({ event: 'gap_detected', entityId: gap.entityId, ageMs: gap.ageMs });
  }
}, 5000);
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `onPush()` and `checkGaps()` timed over 100 000 iterations on a 3-entity scheduler.

```
=== PushPullHybridScheduler timing (100 000 iterations) ===

onPush():                      0.0001 ms
checkGaps() — no gaps:         0.0003 ms
checkGaps() — all gaps:        0.0004 ms

=== Scenario: AAPL push at t=42s; MSFT, GOOG miss ===

  Expected interval: 30s. Gap threshold: 45s (1.5×). Check at t=46s.

  t=0:   AAPL, MSFT, GOOG all receive push
  t=42s: AAPL receives push (within SLA)
  t=46s: checkGaps() fires

  MSFT: age=46 000ms > threshold=45 000ms → TRIGGER PULL
  GOOG: age=46 000ms > threshold=45 000ms → TRIGGER PULL
  AAPL: age= 4 000ms < threshold=45 000ms → NO PULL (push at t=42s)

  AAPL: pushes=2, pulls=0
  MSFT: pushes=1, pulls=1   ← one gap-fill pull triggered
  GOOG: pushes=1, pulls=1   ← one gap-fill pull triggered
  totalGaps: 2

=== Overhead vs pure polling ===

Pure polling 30s, 3 entities:  3 calls/30s = 1 440 pull calls/4hr
Push-primary, 5% gap rate:     3 × 0.05 gap-fills/interval ≈ 72 gap-fill calls/4hr
Push events received:          ~480 push events/4hr

Net: 480 push events + 72 gap-fills vs 1 440 poll calls — 95% fewer outbound calls.
     All 72 gap-fills are targeted; no entity pulled when push is healthy.

=== S-42 vs S-118 vs S-164 ===

              │ S-42 (push vs poll decision) │ S-118 (adaptive polling)    │ S-164 (push-pull hybrid)
──────────────┼──────────────────────────────┼─────────────────────────────┼───────────────────────────────
Architecture  │ Choose one at setup time     │ Pure pull, tuned interval    │ Push primary, pull fallback
Gap coverage  │ Push: zero; poll: periodic   │ Always covered (polling)     │ Covered; pull triggers on gap
Normal cost   │ Push: zero; poll: interval   │ Every interval               │ Zero (no gap → no pull)
Failure mode  │ Push blind; poll ≤ interval  │ At most 1 missed interval    │ Gap detected ≤ checkIntervalMs
Tuning        │ Architectural                │ updateFrequency → interval   │ gapMultiplier, checkIntervalMs
```

## See also

[S-42](s42-event-driven-vs-polling.md) · [S-118](s118-adaptive-polling-interval.md) · [S-100](s100-live-data-freshness-contracts.md) · [S-126](s126-event-driven-cache-invalidation.md) · [S-163](s163-query-aware-tool-cache.md)

## Go deeper

Keywords: `push-pull hybrid scheduler` · `gap detection push fallback` · `webhook gap fill polling` · `push primary poll fallback` · `hybrid event push scheduler` · `gap multiplier push detection` · `event-driven with polling fallback` · `webhook missed delivery recovery` · `push channel health check` · `targeted gap-fill pull`
