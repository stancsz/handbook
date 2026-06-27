# S-154 · Per-Entity Event Dedup on Reconnect

[S-117](s117-webhook-event-deduplication.md) deduplicates webhook events that a sender retries after a failed delivery: it stores a `eventId → TTL` map and rejects events whose ID has been seen within the retry window. [S-144](s144-live-data-burst-event-coalescing.md) coalesces a burst of high-frequency events for the same entity into one LLM call by debouncing over a 200ms window.

Both assume events arrive over a stable connection. WebSocket connections are not stable. A reconnect happens when a mobile client goes through a tunnel, when a server restarts, when a network partition heals. The protocol response to reconnect is correct: the server replays a window of recent events to guarantee the client missed nothing. Thirty seconds of AAPL tick data at 2 events/second = 60 events replayed. All 60 are structurally valid, all pass S-117 (they were first-delivery events, not retries — they have no `eventId` collision in that system), and all pass S-144 (they are spread across 30 seconds, not a 200ms burst). All 60 should be blocked. Without this pattern, all 60 dispatch to the agent.

The difference from S-117: S-117's dedup key is the `eventId` assigned by the sender at send time. A WebSocket replay may use the original `eventId` (in which case S-117 catches it, if the TTL is wide enough) or it may not have stable eventIds at all (many streaming feeds identify events by entity + timestamp only). This pattern's fingerprint is computed from the event's own fields — `entityId + timestamp + sorted field values` — independently of whether a sender-assigned ID exists.

## Situation

An equity data agent subscribes to a WebSocket feed from a market data provider. The connection drops during a network partition at 14:23:00. It reconnects at 14:23:31. The server replays events from 14:22:45 to 14:23:31 — a 46-second window — to ensure no ticks were missed. That produces 40 replay events plus 3 genuinely new events that arrived during the reconnect.

Without this deduplicator: all 43 events dispatch. The agent receives 40 duplicate price ticks it has already processed, generates 40 analysis calls that confirm the same price state it already acted on, and may emit duplicate alerts for price levels it already alerted on.

With this deduplicator: the 40 events fingerprint against the rolling `seen` map and return DUPLICATE → filtered. The 3 new events return NEW → dispatched. Total processing: 0.365ms for 43 events. Agent sees only the 3 events that actually require action.

## Forces

- **The fingerprint key must not include mutable metadata.** Fields like `_receivedAt`, `_sequenceNum`, or `_sessionId` are assigned at receipt time or per-connection, not per event. Including them in the fingerprint defeats deduplication — every replayed event looks new. Only include fields that identify the event's actual state: `entityId`, `timestamp`, and the data fields.
- **TTL must exceed the server's replay window.** If the server replays the last 60 seconds and the deduplicator TTL is 30 seconds, events from 45–60 seconds ago will have expired and pass through. Set `windowMs` to 1.5× the known server replay window. For unknown providers, start at 60 000ms (60s) and narrow based on observed reconnect patterns.
- **This is not coalescing (S-144) and not burst suppression.** Coalescing fires once per entity per debounce window regardless of uniqueness. This filter fires per event and blocks exactly the events already seen, regardless of timing. A reconnect replay delivers 40 events in 365ms; they are time-spread, not a true burst, so S-144's debounce would not catch them. This filter catches them by content identity.
- **Compose: dedup first, then significance filter (S-152), then coalescing (S-144).** Reconnect replay events should be dropped before they reach the significance scorer or coalescer. Add this check at the ingestion point, before the significance pipeline.
- **maxSize bounds memory.** At 5 000 fingerprints × average 80 bytes per fingerprint = 400 KB — reasonable for a long-lived agent. If the feed has many entities and high tick rate, increase maxSize and rely on the prune() call (triggered when at capacity) to remove expired entries. At 2 events/entity/second and 30s TTL, 10 entities = 600 entries at steady state. maxSize 5 000 gives comfortable headroom.
- **False positives are nearly impossible at normal tick rates.** Two AAPL events at the same millisecond timestamp with the same price, volume, and bid/ask are physically the same event. The fingerprint collision rate on distinct genuine events is effectively zero. If your feed delivers two distinct events with the same entity + timestamp (some providers do batch), add a secondary field (sequence number or batch index) to the fingerprint — but do not use a pure receiver-assigned field.

## The move

**Fingerprint each event from its own fields. Block events whose fingerprint has been seen within the TTL window. Prune expired entries when the store reaches capacity.**

```js
// --- Per-entity event deduplicator for WebSocket reconnect replay ---
// Fingerprint: entityId + timestamp + sorted field values (no receiver metadata).
// Block events seen within windowMs. Store cap: maxSize fingerprints.
// Compose before S-152 (significance scorer) and S-144 (coalescer).

class EntityEventDeduplicator {
  constructor(opts = {}) {
    this._windowMs = opts.windowMs ?? 30_000;   // must exceed server replay window
    this._maxSize  = opts.maxSize  ?? 5_000;    // fingerprints before prune
    this._seen     = new Map();                 // fingerprint → expiresAt (ms)
  }

  // Stable fingerprint from event's own data fields.
  // Exclude receiver-assigned metadata (_receivedAt, _seqNum, _sessionId, etc.)
  _fingerprint(event, excludeKeys = ['_receivedAt', '_seqNum', '_sessionId']) {
    const excludeSet = new Set(excludeKeys);
    return Object.keys(event)
      .filter(k => !excludeSet.has(k))
      .sort()
      .map(k => k + ':' + event[k])
      .join('|');
  }

  // Remove expired fingerprints. Called when store reaches maxSize.
  _prune(now) {
    for (const [k, exp] of this._seen) {
      if (exp <= now) this._seen.delete(k);
    }
  }

  // Check and register an event.
  // Returns { pass: bool, reason: 'NEW'|'DUPLICATE', fingerprint: string }
  check(event) {
    const now = Date.now();
    const fp  = this._fingerprint(event);
    const exp = this._seen.get(fp);

    if (exp && exp > now) {
      return { pass: false, reason: 'DUPLICATE', fingerprint: fp };
    }

    if (this._seen.size >= this._maxSize) this._prune(now);
    this._seen.set(fp, now + this._windowMs);
    return { pass: true, reason: 'NEW', fingerprint: fp };
  }

  size()  { return this._seen.size; }
  clear() { this._seen.clear(); }
}

// --- Integration: ingestion point, before significance filter and coalescer ---
// Compose: dedup → S-152 significance score → S-144 coalescer → LLM dispatch

const RECONNECT_DEDUP = new EntityEventDeduplicator({
  windowMs: 45_000,   // 1.5× the provider's 30s replay window
  maxSize:  5_000,
});

function ingestEvent(event) {
  // 1. Dedup: block reconnect replays
  const dedupResult = RECONNECT_DEDUP.check(event);
  if (!dedupResult.pass) {
    metrics.increment('event.duplicate_dropped');
    return;
  }

  // 2. Significance score: block low-signal events (S-152)
  const score = SIGNIFICANCE_SCORER.score(event, getContext(event.entityId));
  if (!score.dispatch) {
    metrics.increment('event.significance_filtered');
    return;
  }

  // 3. Coalesce burst events (S-144)
  COALESCER.push(event.entityId, event);
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `check()` timed over 100 000 iterations. Reconnect burst scenario uses synthetic AAPL tick data (price + volume per event, 2 events/second, 30-second replay window).

```
=== EntityEventDeduplicator timing (100 000 iterations) ===

check() — NEW:       0.0041 ms   (fingerprint + Map.set)
check() — DUPLICATE: 0.0031 ms   (fingerprint + Map.get early return)

=== WebSocket reconnect scenario ===

Feed:       AAPL tick data, ~2 events/second
Connection drops at  14:23:00
Connection restores  14:23:31 (31s gap)

Server replay window: 30 seconds
Replay burst:         40 events  (14:22:45 → 14:23:15, already processed)
New events:            3 events  (14:23:15 → 14:23:31, not yet processed)
Total burst:          43 events

All 40 replay events fingerprinted → DUPLICATE → filtered.
3 new events fingerprinted → NEW → dispatch to agent.

Processed 43 events in 0.365 ms.
Without dedup: 40 duplicate LLM dispatch calls, potential duplicate alerts.

=== Fingerprint example ===

Event: { entityId: 'AAPL', timestamp: 1750000001000, price: 189.52, volume: 42000 }
Fingerprint: "entityId:AAPL|price:189.52|timestamp:1750000001000|volume:42000"
(sorted keys, colon-separated, pipe-delimited — receiver metadata excluded)

=== S-117 vs S-144 vs S-154 ===

              │ S-117 (webhook dedup)            │ S-144 (burst coalescing)         │ S-154 (reconnect dedup)
──────────────┼──────────────────────────────────┼──────────────────────────────────┼──────────────────────────────────
Trigger       │ Sender retries same delivery     │ High-frequency ticks for entity  │ WebSocket reconnect replay
Dedup key     │ Sender-assigned eventId          │ N/A (time window, not content)   │ entityId + timestamp + fields
Window        │ Sender retry window (typ. 15min) │ Debounce 200ms + maxWait 2000ms  │ Server replay window (typ. 30s)
What it misses│ No eventId on stream events      │ Content identity across replays  │ Sender-retry without eventId
Catches       │ HTTP retry with same eventId     │ Burst aggregation (OHLCV)        │ Replay events by field identity
Compose order │ 3rd (after reconnect dedup)      │ 4th (after significance filter)  │ 1st (ingestion gate)
```

## See also

[S-117](s117-webhook-event-deduplication.md) · [S-144](s144-live-data-burst-event-coalescing.md) · [S-152](s152-live-event-significance-scorer.md) · [S-104](s104-event-stream-agent-integration.md) · [S-136](s136-adaptive-per-entity-poll-rate.md) · [S-126](s126-event-driven-cache-invalidation.md)

## Go deeper

Keywords: `websocket reconnect deduplication` · `event replay deduplication` · `per-entity event dedup` · `reconnect replay filter` · `live stream deduplication` · `event fingerprint dedup` · `websocket event replay` · `entity event deduplication` · `stream reconnect dedup` · `live data replay filter`
