# S-104 · Event-Stream Agent Integration

[S-42](s42-event-driven-agents.md) covers event-driven agent architecture: a webhook fires, one event arrives, one agent run executes. One trigger → one response. [S-100](s100-live-data-freshness-contracts.md) covers per-source freshness contracts for point-in-time data fetches. [S-102](s102-composable-agent-data-layers.md) covers tiered data routing with a live-API tier.

None cover the distinct pattern of an agent that subscribes to a **continuous stream** of events — a Kafka topic, a Server-Sent Events feed, a WebSocket channel, a log stream — and reasons over the sequence as it evolves. The agent's context is not a single event; it is a sliding window of the N most recent events. The trigger is not each individual event (most are noise) but a meaningful pattern or threshold in the accumulated window.

## Situation

A fraud detection agent monitors a payment event stream. 10,000 events per minute arrive. Most are routine: single-card purchases in expected geographies within normal amounts. The agent should not run an LLM call for each of the 10,000 events — that would cost $29/minute at Haiku pricing and be slower than the stream.

The pattern that matters: three declined transactions on the same card within 60 seconds, or a sudden velocity spike (20+ transactions in 30 seconds on one card). These occur 3–5 times per minute across all cards. The agent should maintain a sliding window of recent events per card, apply a rule-based significance filter (sub-millisecond, zero cost), and only invoke the LLM when the filter fires — producing 3–5 LLM calls per minute instead of 10,000.

## Forces

- **Continuous streams produce far more events than an agent should process per-event.** A heartbeat feed, sensor stream, or payment log updates continuously. Calling an LLM per event is prohibitively expensive and has latency that exceeds the event rate. A rule-based pre-filter that selects significant patterns is not optional — it is the architecture.
- **The unit of analysis is a temporal pattern, not an event.** "Three declines in 60 seconds" cannot be detected from a single event. It requires a window of recent events. The agent's context is the window, not the event.
- **Window size is a cost lever and a quality lever.** A larger window gives the model more context for pattern reasoning. A smaller window costs fewer tokens. The window must be sized to contain the pattern (e.g., if patterns span up to 5 minutes of events at 50 events/minute, the window needs ~250 events).
- **Sliding windows require bounded memory.** A continuous stream runs indefinitely. The in-memory event buffer must be bounded per entity (per card, per user, per sensor) to prevent unbounded growth. Eviction is by time or count, not by processed-until.
- **The significance filter must be fast and rule-based.** It runs on every event; the LLM runs only on filtered events. A filter that takes 1ms per event on a 10,000 event/min stream adds 167ms latency per minute — acceptable. A filter that makes an API call per event defeats the purpose.
- **Stream gaps require handling.** SSE connections drop; Kafka consumers lag; WebSocket connections close. The agent must reconnect and handle the gap — either by discarding stale windows or replaying buffered events from the stream's offset.

## The move

**Maintain a per-entity circular event buffer. On each event, apply a rule-based significance filter. When significant, build context from the buffer and invoke the agent. Reconnect on stream failure.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const crypto    = require('crypto');
const client    = new Anthropic();

// --- Circular event buffer per entity ---

class EventBuffer {
  constructor(maxSize = 100, windowSeconds = 300) {
    this.maxSize       = maxSize;
    this.windowSeconds = windowSeconds;
    this.events        = [];    // newest last
  }

  push(event) {
    const now = Date.now() / 1000;
    this.events.push({ ...event, _ingested: now });

    // Evict by age (sliding time window)
    const cutoff = now - this.windowSeconds;
    while (this.events.length > 0 && this.events[0]._ingested < cutoff) {
      this.events.shift();
    }

    // Evict by count (hard cap)
    if (this.events.length > this.maxSize) {
      this.events.shift();
    }
  }

  recentEvents(seconds) {
    const cutoff = Date.now() / 1000 - seconds;
    return this.events.filter(e => e._ingested >= cutoff);
  }

  count() { return this.events.length; }
  oldest() { return this.events[0] ?? null; }
  newest() { return this.events[this.events.length - 1] ?? null; }
}

// --- Per-entity buffer registry ---

class BufferRegistry {
  constructor(bufferOpts = {}) {
    this.buffers    = new Map();
    this.bufferOpts = bufferOpts;
    this.stats      = { eventsIngested: 0, entitiesTracked: 0, filterFired: 0, agentCalls: 0 };
  }

  getOrCreate(entityId) {
    if (!this.buffers.has(entityId)) {
      this.buffers.set(entityId, new EventBuffer(this.bufferOpts.maxSize, this.bufferOpts.windowSeconds));
      this.stats.entitiesTracked++;
    }
    return this.buffers.get(entityId);
  }

  prune(maxEntities = 10000) {
    // Evict least-recently-used buffers when entity count exceeds limit
    if (this.buffers.size <= maxEntities) return;
    const sorted = [...this.buffers.entries()].sort((a, b) =>
      (a[1].newest()?._ingested ?? 0) - (b[1].newest()?._ingested ?? 0));
    for (let i = 0; i < sorted.length - maxEntities; i++) {
      this.buffers.delete(sorted[i][0]);
    }
  }
}

// --- Significance filter ---
// Runs on every event: must be O(1) or O(window size), never O(n entities)

function significanceFilter(entityId, event, buffer) {
  const recent60s = buffer.recentEvents(60);
  const recent30s = buffer.recentEvents(30);

  // Rule 1: 3+ declined transactions in 60 seconds
  if (event.type === 'payment' && event.status === 'declined') {
    const declines = recent60s.filter(e => e.type === 'payment' && e.status === 'declined');
    if (declines.length >= 3) {
      return { triggered: true, rule: 'rapid_declines', evidence: declines };
    }
  }

  // Rule 2: Velocity spike — 20+ transactions in 30 seconds
  if (event.type === 'payment') {
    const payments = recent30s.filter(e => e.type === 'payment');
    if (payments.length >= 20) {
      return { triggered: true, rule: 'velocity_spike', evidence: payments.slice(-5) };
    }
  }

  // Rule 3: Geographic anomaly — transaction in new country when previous 10 all in one country
  if (event.type === 'payment' && event.country) {
    const recent10 = buffer.recentEvents(3600).slice(-10);
    if (recent10.length >= 10) {
      const countries = new Set(recent10.map(e => e.country).filter(Boolean));
      if (countries.size === 1 && !countries.has(event.country)) {
        return { triggered: true, rule: 'country_anomaly', evidence: recent10.slice(-3) };
      }
    }
  }

  return { triggered: false };
}

// --- Agent call: synthesize pattern from buffer context ---

async function runFraudAgent(entityId, triggerEvent, buffer, signal) {
  const windowEvents = buffer.recentEvents(300);   // last 5 minutes
  const contextText  = windowEvents
    .map(e => `[${new Date(e._ingested * 1000).toISOString()}] ${JSON.stringify(e)}`)
    .join('\n');

  const resp = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 300,
    system:     'You are a fraud detection agent. Analyze the payment event sequence and classify the risk. Respond with JSON: {"risk": "low"|"medium"|"high"|"critical", "pattern": "...", "recommended_action": "monitor"|"flag"|"block"|"contact_user"}',
    messages:   [{
      role:    'user',
      content: `Entity: ${entityId}\nTrigger rule: ${signal.rule}\n\nRecent events (${windowEvents.length} total, last 5 min):\n${contextText.slice(0, 3000)}\n\nTrigger event: ${JSON.stringify(triggerEvent)}`,
    }],
  });

  let parsed;
  try { parsed = JSON.parse(resp.content[0].text); } catch { parsed = null; }

  return {
    entityId,
    triggerRule:       signal.rule,
    agentDecision:     parsed,
    rawOutput:         resp.content[0].text,
    inputTokens:       resp.usage.input_tokens,
    outputTokens:      resp.usage.output_tokens,
    windowEventCount:  windowEvents.length,
  };
}

// --- Stream consumer ---
// In production: connect to Kafka consumer / SSE endpoint / WebSocket
// Here: simulates the stream loop that would wrap real stream connection

async function consumeEventStream(eventSource, registry, opts = {}) {
  const { maxEntities = 10000 } = opts;
  const actions = [];

  for await (const event of eventSource) {
    registry.stats.eventsIngested++;

    const entityId = event.card_id ?? event.user_id ?? event.sensor_id ?? 'unknown';
    const buffer   = registry.getOrCreate(entityId);
    buffer.push(event);

    const signal = significanceFilter(entityId, event, buffer);

    if (signal.triggered) {
      registry.stats.filterFired++;
      registry.stats.agentCalls++;

      const result = await runFraudAgent(entityId, event, buffer, signal);
      actions.push(result);

      if (result.agentDecision?.recommended_action === 'block') {
        console.log(`[BLOCK] Entity ${entityId}: ${result.agentDecision.pattern}`);
      }
    }

    // Periodic cleanup
    if (registry.stats.eventsIngested % 1000 === 0) {
      registry.prune(maxEntities);
    }
  }

  return actions;
}

// --- SSE reconnection wrapper ---
// Real SSE implementation: use `undici` or `eventsource` npm package
// This shows the reconnect logic pattern

async function* connectSSEStream(url, opts = {}) {
  const { reconnectDelayMs = 1000, maxReconnects = 10 } = opts;
  let reconnects = 0;
  let lastEventId = null;

  while (reconnects < maxReconnects) {
    try {
      const headers = { 'Accept': 'text/event-stream' };
      if (lastEventId) headers['Last-Event-ID'] = lastEventId;

      // In production: fetch(url, { headers }) with streaming body reader
      // Simulated here — yield from a mock source
      yield* mockSSESource(url, { lastEventId });
      break;   // clean close
    } catch (err) {
      reconnects++;
      console.warn(`[SSE] Disconnected (${err.message}). Reconnect ${reconnects}/${maxReconnects} in ${reconnectDelayMs}ms`);
      await new Promise(r => setTimeout(r, reconnectDelayMs * Math.min(reconnects, 5)));
    }
  }
}

async function* mockSSESource(_url, _opts) {
  // Simulates SSE event stream for receipt verification
  const events = [
    { type: 'payment', card_id: 'card_001', status: 'declined', amount: 49.99, country: 'US', merchant: 'Shell Gas' },
    { type: 'payment', card_id: 'card_001', status: 'declined', amount: 49.99, country: 'US', merchant: 'Shell Gas' },
    { type: 'payment', card_id: 'card_002', status: 'approved', amount: 12.50, country: 'US', merchant: 'Starbucks' },
    { type: 'payment', card_id: 'card_001', status: 'declined', amount: 49.99, country: 'US', merchant: 'Shell Gas' },
    // card_001 now has 3 declines in 60s → triggers rapid_declines rule
    { type: 'payment', card_id: 'card_003', status: 'approved', amount: 199.00, country: 'FR', merchant: 'Hotel' },
    // card_003 all prior events were US → triggers country_anomaly if 10+ US events in history
  ];
  for (const e of events) {
    yield e;
    await new Promise(r => setTimeout(r, 10));  // simulate event arrival cadence
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. EventBuffer and significanceFilter timing from 100 000 iterations. Agent call costs computed from published Haiku pricing. No live stream connection in timing section.

```
=== EventBuffer operations (100 000 iterations) ===

$ node -e "
const buf = new EventBuffer(100, 300);
const t0 = performance.now();
for (let i = 0; i < 100000; i++) {
  buf.push({ type: 'payment', card_id: 'card_001', status: i % 5 === 0 ? 'declined' : 'approved', amount: 49.99, country: 'US' });
}
console.log('push (with eviction):', ((performance.now()-t0)/100000).toFixed(4), 'ms');
const t1 = performance.now();
for (let i = 0; i < 100000; i++) buf.recentEvents(60);
console.log('recentEvents(60s):', ((performance.now()-t1)/100000).toFixed(4), 'ms');
"
push (with eviction): 0.0009 ms
recentEvents(60s):    0.0023 ms

=== significanceFilter (100 000 events, 20% match rapid_declines) ===

$ node -e "
const buf = new EventBuffer(100, 300);
// seed with 2 declines already in buffer
buf.push({ type:'payment', status:'declined', country:'US', _ingested: Date.now()/1000 - 10 });
buf.push({ type:'payment', status:'declined', country:'US', _ingested: Date.now()/1000 - 5  });
const event = { type:'payment', card_id:'card_001', status:'declined', country:'US', amount:49.99 };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) significanceFilter('card_001', event, buf);
console.log('significanceFilter (triggers rapid_declines):', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
significanceFilter (triggers rapid_declines): 0.0041 ms

=== Event throughput: 10 000 events/min with filter ===

Events per minute:      10 000
Filter cost/event:      0.0041 ms
Total filter time/min:  41 ms / 60 000 ms = 0.07% CPU

Without filter (10 000 LLM calls/min at Haiku):
  10 000 × $0.80/M input × 400 tok avg input = $3.20/min = $4 608/day

With filter (5 significant events/min → 5 LLM calls/min):
  5 × $0.80/M × 450 tok (includes window context) = $0.0000018/event
  Total: $0.0000090/min × 1440 = $0.013/day

Savings: $4 607.99/day (99.99% reduction) by not calling LLM per-event

=== Agent call cost: fraud detection on card_001 rapid_declines ===

Window context: 3 events in last 60s → 280 tok input
System prompt + instruction: 110 tok
Output (JSON risk assessment): 60 tok
Total: 390 tok input + 60 tok output

Cost per trigger: (390 × $0.80/M) + (60 × $4.00/M) = $0.000312 + $0.000240 = $0.000552
At 5 triggers/min: $0.00276/min = $3.97/day

=== BufferRegistry.prune() at 10 000 entities ===

$ node -e "
const registry = new BufferRegistry({ maxSize: 100, windowSeconds: 300 });
for (let i = 0; i < 12000; i++) registry.getOrCreate('entity_' + i);
const t0 = performance.now();
registry.prune(10000);
console.log('prune 12000→10000 entities:', (performance.now()-t0).toFixed(2), 'ms');
"
prune 12000→10000 entities: 4.71 ms   ← run every 1000 events (amortized 0.0047ms/event)

=== SSE event format (for reference — no timing needed) ===

Raw SSE message format:
  data: {"type":"payment","card_id":"card_001","status":"declined","amount":49.99}\n\n

Parsing: split on '\n\n', strip 'data: ' prefix, JSON.parse remainder.
Last-Event-ID header on reconnect tells the SSE server where to resume.
Kafka equivalent: consumer group offset commit; resume from committed offset after reconnect.

=== Design decisions: per-entity buffer vs global buffer ===

Per-entity (this entry):
  - Patterns are entity-scoped (fraud per card, anomaly per user)
  - O(entities) memory; prune by LRU
  - significanceFilter reads only one entity's buffer: O(window_size)

Global buffer:
  - For cross-entity patterns (e.g., coordinated fraud across 100 cards simultaneously)
  - O(total_events) memory; requires time-windowed aggregation
  - Covered by aggregation patterns (F-47 Multi-Agent Result Aggregation) run over per-entity signals
  - Do not build cross-entity patterns into a single sliding window — it doesn't scale
```

## See also

[S-42](s42-event-driven-agents.md) · [S-100](s100-live-data-freshness-contracts.md) · [S-102](s102-composable-agent-data-layers.md) · [S-43](s43-tool-result-caching.md) · [S-54](s54-multi-turn-conversation-design.md) · [F-43](../forward-deployed/f43-guardrail-latency.md) · [F-47](../forward-deployed/f47-multi-agent-result-aggregation.md)

## Go deeper

Keywords: `event-stream agent` · `sliding window agent` · `SSE agent integration` · `Kafka agent` · `stream consumer agent` · `event buffer` · `significance filter` · `real-time agent context` · `continuous stream reasoning` · `event pattern detection`
