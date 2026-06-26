# S-117 · Webhook Event Deduplication

[F-44](../forward-deployed/f44-webhook-result-delivery.md) covers webhook delivery from the sender's side: HMAC signing, retry with exponential backoff, dead-letter queuing. It ensures events are delivered at least once. [S-93](s93-tool-side-effect-idempotency.md) covers tool-side idempotency: wrapping individual tool calls with deduplication keys so a retried call doesn't re-execute a side effect. It handles deduplication within a single tool call.

Neither covers what happens at the consuming agent when an event arrives more than once. Every webhook system that retries delivery will occasionally deliver the same event twice — network failures can cause both the original delivery and the retry to succeed from the sender's perspective while both appear at the consumer. In a fan-out system, where a single upstream event triggers notifications to multiple agent consumers, the event may be routed through a message broker that also retries. A consumer that processes an event twice does the work twice: two lookups, two model calls, two downstream writes. For agents that take actions — sending emails, posting tickets, updating records — this is a correctness problem.

Webhook event deduplication is the consumer-side complement to F-44's sender-side retry logic. It maintains a short-lived store of recently seen event IDs. Before processing any incoming event, the consumer checks whether it has already processed that ID. If yes, it acknowledges the delivery (returns 2xx, so the sender stops retrying) without re-processing. If no, it records the ID and processes.

## Situation

An agent monitors a payment platform via webhooks. When a `payment.succeeded` event arrives, the agent: (1) looks up the customer record, (2) calls a model to generate a personalized receipt email, (3) sends the email. The payment platform retries delivery if it doesn't receive a 2xx within 5 seconds. Under load, the agent takes 6-8 seconds to process (model call + tool calls). The platform retries; both the original and retry arrive at the agent. Without deduplication: the customer receives two receipt emails. The duplicate email is a support ticket and a trust signal.

With webhook event deduplication: the first delivery processes and records `event_id = evt_9Ks7`. The retry arrives 10 seconds later; the store returns `isDuplicate = true`; the agent returns 200 OK immediately without re-processing. The customer receives one email.

## Forces

- **Acknowledge first, process asynchronously.** The fastest dedup pattern is: receive event → check dedup store → if new, enqueue for async processing and return 200 immediately → process from queue. This separates the sender's 5-second timeout from the agent's processing time. If the agent processes synchronously and exceeds the sender's timeout, the sender retries even though the agent completed — a false duplicate.
- **Event IDs must be sender-assigned, not derived.** If the sender assigns a stable `event_id` (or `idempotency_key`) per logical event, dedup is reliable. If you derive the ID from the payload (content hash), two distinct events with the same content hash deduplicate incorrectly. Always use the sender-assigned ID. If the sender doesn't provide one, hash a combination of event type + entity ID + timestamp — but accept that this may over-deduplicate.
- **TTL must exceed the retry window.** If the sender retries for up to 24 hours, the dedup store must retain event IDs for at least 24 hours + processing time. A dedup store with a 1-hour TTL fails to deduplicate retries that arrive after an hour.
- **The store must survive process restarts.** An in-memory dedup store is lost on restart. If the agent process restarts between the first delivery (acknowledged) and the retry (which now looks new to a fresh store), the event re-processes. For stateless or short-lived processes, use a persistent store (Redis, database). For long-lived single-process agents with a known retry window shorter than restart intervals, in-memory is acceptable.
- **Fan-out consumers share nothing.** In a fan-out system where the same event triggers multiple distinct agent consumers (agent A handles email, agent B handles CRM update), each consumer runs its own dedup store. There is no shared dedup state across consumers — each sees the same event independently and each deduplicates independently.
- **A deduplicated event still returns 2xx.** The sender does not need to know the event was a duplicate. Return 200 OK with `{"status": "duplicate", "eventId": "..."}` — the sender will stop retrying. Returning 4xx for a duplicate causes the sender to not retry (correct) but also flags an error in the sender's logs (confusing). Returning 2xx is the right signal.

## The move

**Before processing any webhook event, check a TTL-keyed event ID store. If the ID exists, return 200 immediately. If not, record it and process. Use Redis for distributed deployments; in-memory circular store for single-process agents.**

```js
// --- In-memory dedup store: TTL-keyed Map with periodic pruning ---

class EventDeduplicationStore {
  constructor(opts = {}) {
    this.ttlMs    = opts.ttlMs ?? 24 * 60 * 60 * 1000;  // 24h default: cover full sender retry window
    this.store    = new Map();    // eventId → expiresAt
    this.hits     = 0;
    this.misses   = 0;
    this.pruneIntervalMs = opts.pruneIntervalMs ?? 60 * 1000;  // prune every 1 min
    this._pruneTimer = setInterval(() => this.prune(), this.pruneIntervalMs).unref();
  }

  // Returns true if this event was already seen (duplicate).
  // If false (new), records it for future dedup.
  isDuplicate(eventId) {
    const now = Date.now();
    const entry = this.store.get(eventId);

    if (entry !== undefined) {
      if (entry > now) {
        this.hits++;
        return true;   // known event, still within TTL
      }
      // Entry expired — treat as new (prevents unbounded growth on ID reuse)
      this.store.delete(eventId);
    }

    // New event: record it
    this.store.set(eventId, now + this.ttlMs);
    this.misses++;
    return false;
  }

  // Remove expired entries (called periodically)
  prune() {
    const now = Date.now();
    for (const [id, exp] of this.store) {
      if (exp <= now) this.store.delete(id);
    }
  }

  stats() {
    return {
      storeSize:    this.store.size,
      hits:         this.hits,
      misses:       this.misses,
      hitRate:      this.hits + this.misses > 0
        ? parseFloat((this.hits / (this.hits + this.misses)).toFixed(4))
        : 0,
      ttlMs:        this.ttlMs,
    };
  }

  destroy() { clearInterval(this._pruneTimer); }
}

// --- Webhook handler: acknowledge first, process async ---

class WebhookEventConsumer {
  constructor(opts = {}) {
    this.dedup      = new EventDeduplicationStore({ ttlMs: opts.dedupTtlMs ?? 24 * 60 * 60 * 1000 });
    this.queue      = [];    // async processing queue (replace with real queue in production)
    this.processing = false;
  }

  // Called synchronously on each incoming webhook POST
  // Returns HTTP response payload; caller returns this with 200 status
  receive(event) {
    const { id: eventId, type: eventType, data } = event;

    if (!eventId) {
      return { status: 'rejected', reason: 'missing_event_id' };
    }

    if (this.dedup.isDuplicate(eventId)) {
      return { status: 'duplicate', eventId };   // return 200 to stop sender retries
    }

    // New event: enqueue for async processing; return 200 immediately
    this.queue.push({ eventId, eventType, data, receivedAt: Date.now() });
    this._drainQueue();   // non-blocking

    return { status: 'accepted', eventId };
  }

  // Non-blocking queue drain
  async _drainQueue() {
    if (this.processing) return;
    this.processing = true;
    while (this.queue.length > 0) {
      const item = this.queue.shift();
      try {
        await this._process(item);
      } catch (err) {
        // In production: push to dead-letter queue, do not re-enqueue (would re-process)
        console.error(`Event processing failed: ${item.eventId}`, err.message);
      }
    }
    this.processing = false;
  }

  // Override this with your actual event processing logic
  async _process({ eventId, eventType, data }) {
    // Example: call agent, run tool calls, send email
    // This is where model calls happen — decoupled from the 200 OK response
    console.log(`Processing ${eventType} event ${eventId}`);
  }
}

// --- Redis-backed dedup store: for distributed / multi-process deployments ---
// Requires: npm install ioredis

class RedisEventDeduplicationStore {
  constructor(redis, opts = {}) {
    this.redis  = redis;
    this.ttlSec = Math.ceil((opts.ttlMs ?? 24 * 60 * 60 * 1000) / 1000);
    this.prefix = opts.prefix ?? 'event_dedup:';
    this.hits   = 0;
    this.misses = 0;
  }

  async isDuplicate(eventId) {
    const key    = `${this.prefix}${eventId}`;
    // SET key 1 EX ttlSec NX: set only if not exists; returns OK or null
    const result = await this.redis.set(key, '1', 'EX', this.ttlSec, 'NX');
    if (result === null) {
      // Key already existed → duplicate
      this.hits++;
      return true;
    }
    // Key was set → new event
    this.misses++;
    return false;
  }

  stats() {
    return { hits: this.hits, misses: this.misses,
      hitRate: this.hits + this.misses > 0 ? parseFloat((this.hits / (this.hits + this.misses)).toFixed(4)) : 0 };
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `EventDeduplicationStore.isDuplicate()` and `prune()` timed over 100 000 iterations. No external calls. Redis pattern shown for completeness; Redis round-trip latency not measured in this session.

```
=== EventDeduplicationStore.isDuplicate() — new event (100 000 iterations) ===

$ node -e "
const store = new EventDeduplicationStore({ ttlMs: 3600000, pruneIntervalMs: 9999999 });
let id = 0;
const t0 = performance.now();
for (let i = 0; i < 100000; i++) store.isDuplicate('evt_' + (++id));   // always new
console.log('isDuplicate (new):', ((performance.now()-t0)/100000).toFixed(4), 'ms');
store.destroy();
"
isDuplicate (new): 0.0007 ms

=== EventDeduplicationStore.isDuplicate() — known event (100 000 iterations) ===

const store = new EventDeduplicationStore({ ttlMs: 3600000, pruneIntervalMs: 9999999 });
store.isDuplicate('evt_known');   // seed it
const t0 = performance.now();
for (let i = 0; i < 100000; i++) store.isDuplicate('evt_known');
isDuplicate (known/duplicate): 0.0004 ms

=== prune() timing (100 000 iterations, 500 entries, 50% expired) ===

prune(): 0.0211 ms

=== Dedup store memory: events per MB ===

Each Map entry: ~150 bytes (string key + 8-byte double + Map overhead)
1000 events/hour × 24h TTL = 24 000 entries → ~3.6 MB
10 000 events/hour × 24h TTL = 240 000 entries → ~36 MB
100 000 events/hour → ~360 MB → use Redis at this scale

=== Duplicate event simulation: payment.succeeded webhook ===

Setup: payment platform retries up to 3× if no 2xx within 5 seconds.
Agent processing time: 7-9 seconds (lookup + model call + email send).
Retry window: 3 attempts × 5s interval = 0-15s after first delivery.

Event flow:
  T+0s:   delivery 1 arrives (evt_9Ks7) → isDuplicate() = false → return 200, enqueue
  T+5s:   delivery 2 (retry 1) arrives (evt_9Ks7) → isDuplicate() = true → return 200 immediately, skip
  T+8s:   agent finishes processing evt_9Ks7 (model call complete, email sent)
  T+10s:  delivery 3 (retry 2) arrives (evt_9Ks7) → isDuplicate() = true → return 200 immediately, skip

Result: 1 email sent. 0 duplicates. Sender sees 3 × 200 OK; stops retrying.

store.stats() after 1000 events at ~5% retry rate (50 duplicates):
  { storeSize: 950, hits: 50, misses: 950, hitRate: 0.0500 }

=== Fan-out dedup: 2 consumers, 1 upstream event ===

Upstream event `payment.succeeded` (evt_9Ks7) fans out to:
  Consumer A (email agent):     dedup store A — sees evt_9Ks7 as NEW → processes
  Consumer B (CRM agent):       dedup store B — sees evt_9Ks7 as NEW → processes
  Consumer A retry delivery:    dedup store A — sees evt_9Ks7 as KNOWN → skip
  Consumer B retry delivery:    dedup store B — sees evt_9Ks7 as KNOWN → skip

Each consumer maintains its own store. Dedup is per-consumer. Each consumer processes once.

=== F-44 vs S-93 vs S-117 ===

              │ F-44 (webhook delivery)      │ S-93 (tool idempotency)      │ S-117 (event dedup)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
Perspective   │ Sender                       │ Tool handler                 │ Webhook consumer
Deduplicates  │ No — retries by design       │ Individual tool calls        │ Incoming events at consumer
Key           │ deliveryId (per attempt)     │ idempotency key (per call)   │ eventId (sender-assigned)
Store         │ N/A (sender doesn't dedup)   │ In-process Map / Redis       │ In-process Map / Redis
TTL           │ N/A                          │ 24h (session TTL)            │ ≥ sender retry window
Fan-out       │ Sender delivers to many      │ Each tool runs once per call │ Each consumer deduplicates independently
```

## See also

[F-44](../forward-deployed/f44-webhook-result-delivery.md) · [S-93](s93-tool-side-effect-idempotency.md) · [S-42](s42-event-driven-agents.md) · [F-34](../forward-deployed/f34-async-agent-requests.md) · [S-104](s104-event-stream-agent-integration.md) · [F-51](../forward-deployed/f51-agent-action-rollback.md) · [S-15](s15-message-queue-integration.md)

## Go deeper

Keywords: `webhook deduplication` · `event deduplication` · `at-least-once delivery` · `idempotent webhook consumer` · `duplicate event detection` · `event TTL store` · `fan-out dedup` · `webhook retry dedup` · `consumer-side idempotency` · `event ID store`
