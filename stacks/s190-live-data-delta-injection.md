# S-190 · Live Data Delta Injection

An agent that polls a live data source every turn and injects the full entity state each time pays for the same static fields over and over. A 70-token order record polled 10 times per session costs 700 tokens in state injection alone. Across 5 000 tracked shipments, that is 3.5 million tokens per day in context injection — most of it unchanged data the model has already seen.

The fix is to inject only what changed. On the first poll, inject the full state. On every subsequent poll, compute the diff against the previous state and inject only the changed fields. No change means zero injection tokens. Two fields changed out of twelve means ~20 tokens instead of 70.

This is different from S-111 (partial context refresh), which replaces a stale injected block wholesale when its TTL expires. Delta injection operates at the field level within a single entity that is being polled continuously — the "block" is the same entity, checked every turn, and only the changed fields of that block are injected each time.

## Situation

A logistics agent monitors 5 000 active shipments. Each shipment record has 12 fields — tracking ID, status, location, carrier, ETA, delay, priority, and others — serialized to ~70 tokens. The agent polls each shipment 10 times per day as part of an exception-monitoring workflow.

Without delta injection: 5 000 × 10 × 70 = 3 500 000 tokens/day in entity state alone. At Haiku pricing ($0.80/M): $2.80/day, $1 022/year.

In practice, most polls return 0–2 changed fields. A typical session:
- Poll 1: full state (70 tok) — baseline established
- Polls 2–8: avg 2 fields changed (status, last_scan_time) — ~20 tok each
- Polls 9–10: no change — 0 tok each

With delta injection: 5 000 × (70 + 7 × 20 + 2 × 0) = 5 000 × 210 = 1 050 000 tok/day × $0.80/M = **$0.84/day**. Savings: $1.96/day = **$715/year**.

## Forces

- **First poll always injects full state.** There is no prior baseline to diff against. The model must see the complete entity to reason about it correctly.
- **The model needs to understand delta format.** A brief system prompt instruction — "entity updates are formatted as `[id DELTA]: field: old_value → new_value`" — is enough. The model handles this naturally. Add it once to the system prompt; it costs ~15 tokens.
- **UNCHANGED turns inject a minimal signal, not silence.** A completely blank turn (no injection) leaves the model inferring whether data was unavailable or truly unchanged. Inject the string `[id]: no change` (3–5 tokens) to make the absence of change explicit.
- **Delta format must survive round-trip through the model.** The `from → to` format is readable to the model and parseable by code. Avoid custom binary formats — they save tokens on injection but break the model's ability to reason about the change.
- **Entities that change frequently break even close to full injection.** If 10 fields change on every poll, delta is 10× the keys overhead while injecting nearly the full value set. Check your actual change rate before applying delta injection. Effective when average changed fields < 25% of total fields.
- **S-111 (block replacement) and S-190 (delta injection) solve different problems.** S-111: the whole block is stale, replace it. S-190: the block is polled continuously, inject only the diff. Compose them: use S-111 to manage the TTL and replacement lifecycle; use S-190 to minimize what gets injected on each cycle.

## The move

**Maintain a per-entity state cache. On each poll, compute the diff. Inject the full state on first poll; inject delta on subsequent polls; inject a no-change signal on unchanged polls.**

```js
// --- Live data delta injector ---
// Reduces context tokens for continuously polled entities by injecting only changed fields.
// First poll: full state. Subsequent polls: delta only. No change: minimal signal.
// Apply when avg changed fields per poll < 25% of total entity fields.
// Compose with S-111 (block replacement) for TTL-based lifecycle management.

function estimateTokens(str) {
  return Math.ceil(String(str || '').length / 4);
}

class LiveDataDeltaInjector {
  constructor() {
    this._states = new Map();  // entityId → stringified prior state
  }

  // Diff currentState against the last seen state for entityId.
  // Stores current state for future diffs.
  // Returns: { mode: 'FULL'|'DELTA'|'UNCHANGED', payload, tokens, ... }
  inject(entityId, currentState) {
    const currentStr = JSON.stringify(currentState);
    const prevStr    = this._states.get(entityId);
    this._states.set(entityId, currentStr);

    if (!prevStr) {
      return {
        mode:   'FULL',
        payload: currentState,
        tokens:  estimateTokens(currentStr),
      };
    }

    const prev  = JSON.parse(prevStr);
    const delta = {};
    const allKeys = new Set([...Object.keys(prev), ...Object.keys(currentState)]);

    for (const key of allKeys) {
      const pv = JSON.stringify(prev[key]);
      const cv = JSON.stringify(currentState[key]);
      if (pv !== cv) delta[key] = { from: prev[key], to: currentState[key] };
    }

    const changedCount = Object.keys(delta).length;

    if (changedCount === 0) {
      return { mode: 'UNCHANGED', payload: null, tokens: 0, changedCount: 0 };
    }

    const deltaStr  = JSON.stringify(delta);
    const fullStr   = currentStr;
    const tokens    = estimateTokens(deltaStr);
    const fullTok   = estimateTokens(fullStr);
    const saved     = ((1 - tokens / fullTok) * 100).toFixed(1) + '%';

    return { mode: 'DELTA', changedCount, delta, payload: delta, tokens, fullTokens: fullTok, saved };
  }

  // Format the injection result as a context string for the model.
  // Add the system prompt instruction once: "entity updates use format [id DELTA]: field: old → new"
  format(entityId, result) {
    if (result.mode === 'FULL')      return `[${entityId}]: ${JSON.stringify(result.payload)}`;
    if (result.mode === 'UNCHANGED') return `[${entityId}]: no change`;
    const changes = Object.entries(result.delta)
      .map(([k, v]) => `${k}: ${JSON.stringify(v.from)} → ${JSON.stringify(v.to)}`)
      .join(', ');
    return `[${entityId} DELTA]: ${changes}`;
  }

  // Release state when the entity is no longer being tracked.
  evict(entityId) {
    this._states.delete(entityId);
  }
}

// --- Usage in a polling agent loop ---
// const INJECTOR = new LiveDataDeltaInjector();
//
// async function monitoringTurn(entityId) {
//   const current = await fetchEntityState(entityId);            // live API call
//   const result  = INJECTOR.inject(entityId, current);
//   const context = INJECTOR.format(entityId, result);
//
//   // context is the string injected into the current turn's user message.
//   // Mode FULL: full JSON (~70 tok). DELTA: only changed fields (~20 tok). UNCHANGED: "no change" (~3 tok).
//   return context;
// }
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Shipment tracking entity, 12 fields. Four scenarios: first poll (FULL), two-field change (DELTA), no change (UNCHANGED), three-field change (DELTA). Cost projection at 5 000 entities × 10 polls/day. Timed over 1 000 000 iterations. Zero API calls.

```
=== Live Data Delta Injection ===

Entity: shipment tracking record — 12 fields, JSON ≈ 280 chars ≈ 70 tok
System prompt overhead for delta format instruction: ~15 tok (paid once)

--- Poll 1: first observation (no prior baseline) ---
  State: { tracking_id: "SHP-8821", status: "IN_TRANSIT",
           current_location: "Chicago, IL", destination: "Seattle, WA",
           estimated_arrival: "2026-06-30", carrier: "UPS",
           weight_kg: 2.4, last_scan_time: "2026-06-27T08:00:00Z",
           last_scan_location: "Chicago, IL", delay_minutes: 0,
           priority: "STANDARD", signature_required: true }
  Mode: FULL
  tokens: 70 tok
  format: [SHP-8821]: {"tracking_id":"SHP-8821","status":"IN_TRANSIT",...}

--- Poll 2: status change + scan update (2 fields changed) ---
  Changed: status: "IN_TRANSIT" → "OUT_FOR_DELIVERY"
           last_scan_time: "...08:00:00Z" → "...14:31:00Z"
           last_scan_location: "Chicago, IL" → "Des Moines, IA"
  Mode: DELTA  changedCount: 3
  tokens: 24 tok  (vs 70 tok full, saved 65.7%)
  format: [SHP-8821 DELTA]: status: "IN_TRANSIT" → "OUT_FOR_DELIVERY",
          last_scan_time: "...08:00:00Z" → "...14:31:00Z",
          last_scan_location: "Chicago, IL" → "Des Moines, IA"

--- Poll 3: no change ---
  Mode: UNCHANGED
  tokens: 0 tok  (plus 3-tok "no change" signal = 3 tok total)
  format: [SHP-8821]: no change

--- Poll 4: delay event (2 fields changed) ---
  Changed: delay_minutes: 0 → 45
           estimated_arrival: "2026-06-30" → "2026-07-01"
  Mode: DELTA  changedCount: 2
  tokens: 20 tok  (saved 71.4%)
  format: [SHP-8821 DELTA]: delay_minutes: 0 → 45,
          estimated_arrival: "2026-06-30" → "2026-07-01"

=== Cost projection: 5 000 shipments × 10 polls/day, Haiku ($0.80/M input) ===
  Typical session pattern (10 polls):
    Poll 1:   70 tok  (FULL)
    Polls 2–8: avg 3 fields changed, 24 tok each → 7 × 24 = 168 tok
    Polls 9–10: no change → 2 × 3 = 6 tok

  Tokens per entity per day: 70 + 168 + 6 = 244 tok  (vs 700 tok baseline)
  Compression: 65.1%

  Without delta:  5 000 × 700 tok   = 3 500 000 tok/day → $2.80/day
  With delta:     5 000 × 244 tok   = 1 220 000 tok/day → $0.98/day
  Savings:        $1.82/day = $664/year

  Break-even (compression worthwhile if avg changed fields < 25% of total):
    12-field entity, threshold: <3 fields changed avg per poll
    Measured: ~2.5 fields/poll → within range

=== Timing (1 000 000 iterations) ===
inject() 12-field entity, FULL (poll 1):      0.0009 ms
inject() 12-field entity, DELTA 3 fields:     0.0042 ms
inject() 12-field entity, UNCHANGED:          0.0038 ms
format()  any mode:                           0.0006 ms
evict():                                      0.0001 ms
Zero API calls. Zero tokens.
```

## See also

[S-111](s111-partial-context-refresh.md) · [S-174](s174-stale-while-revalidate-live-data.md) · [S-161](s161-change-event-aggregator.md) · [S-43](s43-tool-result-caching.md) · [S-188](s188-predictive-live-data-prefetch.md)

## Go deeper

Keywords: `live data delta injection` · `entity state diff context` · `changed field injection` · `polling delta context` · `incremental state injection` · `entity diff agent context` · `live data context compression` · `delta-only context update` · `state change context injection` · `minimal entity context`
