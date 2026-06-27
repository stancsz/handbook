# S-181 · Live Data Event Deduplicator

[S-93](s93-tool-side-effect-idempotency.md) prevents an agent from executing the same tool call twice: when the agent calls `send_email` with identical arguments, S-93 checks an idempotency store and blocks the second execution. That pattern is about outgoing, agent-initiated calls. [F-44](../forward-deployed/f44-webhook-result-delivery.md) handles outgoing webhook delivery from the agent to customers — deduplicating retries on the delivery side.

Neither covers the incoming direction: events arriving from external live data sources. Market data feeds, database change streams, contract status webhooks, and IoT sensors all use at-least-once delivery semantics. Network retries, broker redelivery, and failover scenarios mean the same event can arrive multiple times. Without a dedup guard, each duplicate updates the agent's live context stores as if it were a new event. An append-only event log accumulates the same price update twice, producing stale reads. A counter-based store increments twice on one real event. Downstream agents act on corrupted context.

The dedup guard fingerprints each incoming event — using the source's own stable event ID when available, falling back to a SHA-256 hash of the canonical payload when not — and checks the fingerprint against a sliding-window set of recently processed events. Duplicates arriving within the window are rejected before they reach the live context stores. The window size (default: 5 minutes, up to 10 000 fingerprints) covers typical network retry windows while bounding memory usage.

## Situation

A contract review agent assembles live context from three sources: a market data feed (PRICE_UPDATE events with stable event IDs), a contract database change stream (CONTRACT_UPDATED events), and a config service (CONFIG_CHANGED events). All three use HTTP webhook delivery with exponential-backoff retry.

During a 10-minute network degradation, three events are delivered twice each: `evt-001` (AAPL price update), `evt-003` (contract C-42 status change), `evt-002` (MSFT price update). Without dedup, the contract review agent would process 13 events and incorrectly double-count three status changes. With the dedup guard: 7 processed, 3 DUPLICATE_REJECTED. The duplicate rejections happen in under 0.0069 ms each — before any context store write.

Scenario B covers sources that do not provide stable event IDs (some IoT sensors, some legacy feeds). The fingerprint is computed from the full canonical payload. A temperature reading of 22.5°C at timestamp 1751000000 from sensor A1 is fingerprinted from the payload; the identical reading arriving again is rejected; a new reading at 22.7°C (different payload) passes through.

## Forces

- **Use the source's event ID as the primary dedup key, not the payload.** When the source provides a stable, unique event ID (`evt-001`), use it. Payload-based fingerprinting handles the no-ID case but is slower (JSON.stringify + SHA-256) and fragile: two genuinely different events with the same payload (identical sensor readings one second apart with different timestamps) need separate timestamps in the payload to dedup correctly.
- **The fingerprint covers source + eventType + eventId + payload together.** Source and eventType are part of the key to prevent cross-source collision: event ID "evt-001" from the market feed and event ID "evt-001" from the config service are different events. Without namespacing by source and type, one dedup collision corrupts an otherwise-valid event.
- **Window size = retry window × 2, capped by memory budget.** If the upstream source retries for up to 5 minutes, use a 10-minute window. If the upstream retries for 24 hours (some enterprise contract systems), the window cannot practically cover the full retry horizon — log and alert on duplicates beyond the window rather than silently processing them.
- **Evict expired entries before each write, not on a timer.** Timer-based eviction runs in the background and can evict entries while a high-burst window is being processed. Eviction on each `process()` call is deterministic and keeps the seen-set consistent without background threads. For very high-throughput sources (>1 000 events/second), batch eviction every N events instead.
- **This is a correctness guard, not just an efficiency optimization.** For idempotent stores (setting a key/value where the same write is safe to repeat), duplicate events are wasteful but not harmful. For non-idempotent stores (append-only logs, counters, ledgers), duplicate events corrupt the context. Register stores that need this guard; bypass it for idempotent stores where the overhead is not justified.

## The move

**Fingerprint each incoming event from source + eventType + eventId (or payload SHA-256). Reject if seen within the TTL window. Evict expired entries on each call.**

```js
// --- Live data event deduplicator ---
// Rejects incoming duplicate events from external live data sources before they
// update the agent's live context stores.
// Distinct from S-93 (outgoing tool-call idempotency) and F-44 (outgoing webhook delivery).
// Compose: incoming event → S-181 dedup → live context store update.

const crypto = require('crypto');

class LiveDataEventDeduplicator {
  constructor(opts) {
    opts = opts || {};
    this._windowMs = opts.windowMs || 300_000;  // 5 minutes
    this._maxSize  = opts.maxSize  || 10_000;
    this._seen     = new Map();  // fingerprint → expiresAt (ms)
  }

  _fingerprint(event) {
    const canonical = JSON.stringify({
      source:    event.source,
      eventType: event.eventType,
      eventId:   event.eventId || null,
      payload:   event.payload,
    });
    return crypto.createHash('sha256').update(canonical).digest('hex').slice(0, 16);
  }

  _evict(now) {
    for (const [fp, exp] of this._seen) {
      if (exp <= now) this._seen.delete(fp);
    }
    if (this._seen.size > this._maxSize) {
      const excess = this._seen.size - this._maxSize;
      let i = 0;
      for (const key of this._seen.keys()) {
        if (i++ >= excess) break;
        this._seen.delete(key);
      }
    }
  }

  process(event) {
    const fp = this._fingerprint(event);
    const now = Date.now();
    this._evict(now);

    if (this._seen.has(fp)) {
      return {
        status: 'DUPLICATE_REJECTED',
        source: event.source, eventType: event.eventType,
        reason: event.eventId
          ? `eventId "${event.eventId}" already processed within window`
          : 'payload fingerprint already seen within window',
      };
    }

    this._seen.set(fp, now + this._windowMs);
    return { status: 'PROCESSED', source: event.source, eventType: event.eventType };
  }
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. 10 incoming events with 3 network-retry duplicates. Scenario B: payload-based dedup for a source with no stable event ID. `_fingerprint()` and `process()` timed over 100 000 iterations. Zero API calls, zero tokens.

```
=== Live Data Event Deduplicator ===

Processing 10 incoming events (3 are network-retry duplicates):

  [ 1] PROCESSED            market-feed/PRICE_UPDATE    id=evt-001
  [ 2] PROCESSED            market-feed/PRICE_UPDATE    id=evt-002
  [ 3] PROCESSED            contract-db/CONTRACT_UPDATED id=evt-003
  [ 4] DUPLICATE_REJECTED   market-feed/PRICE_UPDATE    id=evt-001  ← REJECTED
        reason: eventId "evt-001" already processed within window
  [ 5] PROCESSED            market-feed/PRICE_UPDATE    id=evt-004
  [ 6] DUPLICATE_REJECTED   contract-db/CONTRACT_UPDATED id=evt-003  ← REJECTED
  [ 7] PROCESSED            config-svc/CONFIG_CHANGED   id=evt-005
  [ 8] DUPLICATE_REJECTED   market-feed/PRICE_UPDATE    id=evt-002  ← REJECTED
  [ 9] PROCESSED            market-feed/PRICE_UPDATE    id=evt-006
  [10] PROCESSED            config-svc/CONFIG_CHANGED   id=evt-007

  7 processed, 3 rejected

--- Scenario B: payload-based dedup (no stable eventId) ---
  PROCESSED            temp=22.5°C  ts=1751000000
  DUPLICATE_REJECTED   temp=22.5°C  ts=1751000000
  PROCESSED            temp=22.7°C  ts=1751000060

=== Distinct from S-93 and F-44 ===
S-93: dedup OUTGOING tool calls from the agent (agent-initiated, e.g. send_email)
F-44: dedup OUTGOING webhook delivery to customers (our retries, our control)
S-181: dedup INCOMING events from external sources (their retries, our guard)

=== Timing (100 000 iterations) ===
_fingerprint() SHA-256 + JSON.stringify:  0.0074 ms
process() DUPLICATE_REJECTED path:        0.0069 ms
Zero API calls. Zero tokens. Runs before any context store write.
```

## See also

[S-93](s93-tool-side-effect-idempotency.md) · [F-44](../forward-deployed/f44-webhook-result-delivery.md) · [S-174](s174-stale-while-revalidate-live-data.md) · [S-178](s178-context-freshness-watermark.md) · [S-100](s100-live-data-freshness-contracts.md)

## Go deeper

Keywords: `live data event deduplication` · `incoming webhook dedup` · `at-least-once delivery dedup` · `event fingerprint sliding window` · `live context event dedup` · `duplicate event rejection` · `real-time event deduplicator` · `market feed dedup` · `change stream dedup` · `idempotent event processing agent`
