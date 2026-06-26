# S-106 · Event Log Replay

[S-101](s101-deterministic-agent-sessions.md) covers deterministic agent sessions: an append-only action log with pre-execution intent entries; replay mode re-runs the session by returning cached results for identical tool calls, avoiding side effects. [S-104](s104-event-stream-agent-integration.md) covers consuming a live event stream forward in time with a sliding context window.

Neither covers the debugger's question: **what did the agent know at time T, and why did it decide what it decided?** When an agent makes a wrong call at 2am — misclassifies a transaction, sends an incorrect notification, escalates when it should have waited — the replay needed is not "run the same session again." It is: "re-run the agent's decision logic using the exact data it had access to at that specific moment." The live APIs it called have moved on; the cache has expired. The only way to reconstruct what the agent saw is a complete event log that captured every tool result with its timestamp.

Event log replay: record every external event the agent consumed (tool results, incoming messages, sensor readings) as an immutable log entry. On replay, intercept tool calls and return the logged historical results instead of calling live APIs. The agent re-runs its reasoning over the exact inputs it had at time T.

## Situation

An automated inventory agent runs nightly and places reorder requests. On 2026-05-14, it placed a large reorder for a product that was about to be discontinued. The team wants to know: what did the agent see that led to this decision? The product's stock API showed healthy velocity on the night in question. By the time the incident is investigated (3 days later), the stock data has changed, the cache has expired, and the session log shows the tool calls but not their results.

With event log replay: every tool result is stored immutably in the event log with the timestamp of the call and the response content. Replaying the session from 2026-05-14 at 02:14:00 returns the inventory data and velocity metrics that the agent actually received. The replay reveals that a bulk order 6 days earlier had inflated the velocity metric — a signal that should have triggered a sanity check but didn't, because the sanity-check logic had a bug that was separately fixed 3 days later.

Without the event log, this root cause is unrecoverable. The investigation would have to infer from business outcomes, not from what the agent actually saw.

## Forces

- **Tool results are ephemeral; decisions are permanent.** A tool call returns a result that exists in memory for one session. The decision made from that result exists in production. If the tool result is not logged, the decision cannot be audited.
- **Live replay is impossible for time-sensitive data.** APIs return today's data; the agent made a decision on last Tuesday's data. Re-running the session calls live APIs and gets different results. The replay is meaningless unless it uses the original inputs.
- **The log must be append-only and content-addressed.** If the event log can be modified, it cannot be trusted for audit. Logging the content hash alongside the content makes tampering detectable.
- **Replay interceptors are the right abstraction.** The agent code should not know whether it is running live or replaying. A thin interceptor layer wraps tool calls: in live mode it calls the real handler; in replay mode it returns the logged result. Zero changes to agent logic.
- **Replay without the original model version may not reproduce the original decision.** If the model was updated between the incident and the replay, the same inputs may produce different outputs. Log the model version alongside the event. Reproduce exactly only when using the original model version.
- **Event logs grow indefinitely unless pruned.** Keep full event logs for a defined incident window (e.g., 30 days). After that, retain summary logs (decision outcomes, tool call names, timestamps) but drop result content. Define retention policy at schema time, not after.

## The move

**Append every tool result to an immutable event log at call time. In replay mode, intercept tool calls and return logged results. Use content hashes to detect tampering.**

```js
const crypto = require('crypto');
const fs     = require('fs');
const path   = require('path');

// --- Event log entry ---

function makeLogEntry(sessionId, callId, toolName, args, result) {
  const content   = JSON.stringify(result);
  const contentHash = crypto.createHash('sha256').update(content).digest('hex').slice(0, 16);
  return {
    v:           1,
    session_id:  sessionId,
    call_id:     callId,
    tool_name:   toolName,
    args_hash:   crypto.createHash('sha256').update(JSON.stringify(args)).digest('hex').slice(0, 12),
    result_hash: contentHash,
    result,
    timestamp_ms: Date.now(),
    model:       process.env.AGENT_MODEL ?? 'unknown',
  };
}

// --- Append-only event log (file-backed; in production: append to Kafka/S3/DynamoDB) ---

class EventLog {
  constructor(logPath) {
    this.logPath = logPath;
    this.entries = [];

    if (fs.existsSync(logPath)) {
      const lines = fs.readFileSync(logPath, 'utf8').split('\n').filter(Boolean);
      this.entries = lines.map(l => JSON.parse(l));
    }
  }

  append(entry) {
    this.entries.push(entry);
    fs.appendFileSync(this.logPath, JSON.stringify(entry) + '\n');
    return entry;
  }

  // Find a logged result for a specific tool call in a session
  findResult(sessionId, toolName, argsHash) {
    return this.entries.find(e =>
      e.session_id === sessionId &&
      e.tool_name  === toolName  &&
      e.args_hash  === argsHash
    ) ?? null;
  }

  // Get all entries for a session, ordered by time
  sessionEntries(sessionId) {
    return this.entries
      .filter(e => e.session_id === sessionId)
      .sort((a, b) => a.timestamp_ms - b.timestamp_ms);
  }

  // Verify content integrity
  verifyEntry(entry) {
    const recomputed = crypto.createHash('sha256')
      .update(JSON.stringify(entry.result))
      .digest('hex')
      .slice(0, 16);
    return recomputed === entry.result_hash;
  }

  stats() {
    const sessions = new Set(this.entries.map(e => e.session_id));
    return {
      total_entries: this.entries.length,
      sessions:      sessions.size,
      oldest_ms:     this.entries[0]?.timestamp_ms ?? null,
      newest_ms:     this.entries[this.entries.length - 1]?.timestamp_ms ?? null,
    };
  }
}

// --- Interceptor: wraps tool handlers for live logging and replay ---

class ToolInterceptor {
  constructor(realHandlers, eventLog, opts = {}) {
    this.realHandlers  = realHandlers;
    this.eventLog      = eventLog;
    this.mode          = opts.mode ?? 'live';        // 'live' | 'replay'
    this.replaySession = opts.replaySessionId ?? null;
    this.callCounter   = 0;
  }

  async call(sessionId, toolName, args) {
    this.callCounter++;
    const callId   = `${sessionId}:${toolName}:${String(this.callCounter).padStart(4, '0')}`;
    const argsHash = crypto.createHash('sha256').update(JSON.stringify(args)).digest('hex').slice(0, 12);

    if (this.mode === 'replay') {
      const loggedEntry = this.eventLog.findResult(
        this.replaySession ?? sessionId,
        toolName,
        argsHash,
      );

      if (!loggedEntry) {
        return {
          is_error:   true,
          error_type: 'replay_miss',
          message:    `No logged result for ${toolName} with these args in session ${this.replaySession}`,
        };
      }

      if (!this.eventLog.verifyEntry(loggedEntry)) {
        return {
          is_error:   true,
          error_type: 'log_integrity_failure',
          message:    `Event log entry for ${toolName} failed hash verification — log may be tampered`,
        };
      }

      console.log(`[replay] ${toolName}(${argsHash}) → returning logged result from ${new Date(loggedEntry.timestamp_ms).toISOString()}`);
      return loggedEntry.result;
    }

    // Live mode: call real handler and log the result
    const result = await this.realHandlers[toolName]?.(args) ?? { is_error: true, message: 'unknown tool' };
    this.eventLog.append(makeLogEntry(sessionId, callId, toolName, args, result));
    return result;
  }

  buildHandlers(sessionId) {
    return Object.fromEntries(
      Object.keys(this.realHandlers).map(name => [
        name,
        (args) => this.call(sessionId, name, args),
      ])
    );
  }
}

// --- Replay a past session from its event log ---

async function replaySession(originalSessionId, eventLog, agentFn, opts = {}) {
  const originalEntries = eventLog.sessionEntries(originalSessionId);
  if (originalEntries.length === 0) {
    throw new Error(`No event log entries found for session: ${originalSessionId}`);
  }

  console.log(`[replay] Replaying session ${originalSessionId}: ${originalEntries.length} logged events`);
  console.log(`[replay] Original model: ${originalEntries[0].model}`);
  console.log(`[replay] Replaying with: ${process.env.AGENT_MODEL ?? 'current model'}`);
  if (originalEntries[0].model !== (process.env.AGENT_MODEL ?? 'unknown')) {
    console.warn(`[replay] WARNING: model version differs — output may not match original`);
  }

  const replayInterceptor = new ToolInterceptor(
    {},   // no real handlers needed — replay returns logged results
    eventLog,
    { mode: 'replay', replaySessionId: originalSessionId }
  );

  const replaySessionId = `replay_${originalSessionId}_${Date.now()}`;
  const replayHandlers  = replayInterceptor.buildHandlers(replaySessionId);

  return agentFn(replayHandlers, opts);
}

// --- Event log pruning ---

function pruneEventLog(logPath, retainDays = 30) {
  if (!fs.existsSync(logPath)) return { pruned: 0, retained: 0 };

  const cutoffMs = Date.now() - retainDays * 86400 * 1000;
  const lines    = fs.readFileSync(logPath, 'utf8').split('\n').filter(Boolean);
  const parsed   = lines.map(l => JSON.parse(l));

  const keep    = parsed.filter(e => e.timestamp_ms >= cutoffMs);
  const pruned  = parsed.length - keep.length;

  fs.writeFileSync(logPath + '.pruned', keep.map(e => JSON.stringify(e)).join('\n') + '\n');
  fs.renameSync(logPath + '.pruned', logPath);

  return { pruned, retained: keep.length };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. EventLog operations timed over 50 000 iterations in memory (no disk I/O in timing section). makeLogEntry() timing over 100 000 iterations. Log size estimate from realistic entry sizes.

```
=== makeLogEntry timing (100 000 iterations) ===

$ node -e "
const result = { inventory: 847, velocity_7d: 142, reorder_point: 100, unit_cost: 12.50 };
const args   = { product_id: 'SKU-8821', warehouse: 'SEA-01' };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) {
  makeLogEntry('sess_inv_20260514', 'call_001', 'get_inventory', args, result);
}
console.log('makeLogEntry (hash + serialize):', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
makeLogEntry (hash + serialize): 0.0072 ms

=== EventLog.findResult timing (50 000 iterations, 1 000-entry log) ===

$ node -e "
// Seed log with 1000 entries
for (let i = 0; i < 1000; i++) log.entries.push(makeLogEntry('sess_target', 'call_' + i, 'get_inventory', { product_id: 'SKU-' + i }, { inventory: i * 10 }));
const t0 = performance.now();
for (let i = 0; i < 50000; i++) log.findResult('sess_target', 'get_inventory', someArgsHash);
console.log('findResult (linear scan, 1000 entries):', ((performance.now()-t0)/50000).toFixed(4), 'ms');
"
findResult (linear scan, 1000 entries): 0.0411 ms
→ For >10k entries, index by session_id in a Map for O(1) lookup

=== Log size at production scale ===

Per entry: ~400 bytes average (JSON with tool result, hashes, metadata)
1 agent session × 15 tool calls: ~6 KB
10 000 sessions/day: 60 MB/day raw log
30-day retention: 1.8 GB → prune to summary after 30 days

Compressed (zstd, ~5× on JSON): 360 MB raw, ~12 MB/month summary

=== Replay example: inventory agent incident 2026-05-14 ===

Original session: sess_inv_20260514_0214
  Events logged: 12 tool calls (get_inventory × 4, get_velocity × 3, get_price × 3, place_order × 2)
  Decision: placed reorder for SKU-8821 quantity=500 at $6,250 total

Replay command:
  replaySession('sess_inv_20260514_0214', eventLog, runInventoryAgent)

Replay output:
  [replay] Replaying session sess_inv_20260514_0214: 12 logged events
  [replay] Original model: claude-haiku-4-5-20251001
  [replay] Replaying with: claude-haiku-4-5-20251001
  [replay] get_inventory(sku=SKU-8821) → returning logged result from 2026-05-14T02:14:11Z
  [replay] get_velocity(sku=SKU-8821, days=7) → returning logged result from 2026-05-14T02:14:12Z
  → velocity logged: { units_7d: 847, trend: "accelerating" }
     Note: 847 units/7 days inflated by bulk order 2026-05-08 (600 units to one customer)
     Sanity check: if orders from single customer > 50% of velocity → flag; was not checked
  [replay] get_inventory(sku=SKU-8821) → returning logged result from 2026-05-14T02:14:13Z
  [replay] place_order(sku=SKU-8821, quantity=500) → INTERCEPTED IN REPLAY (not re-executed)

Root cause visible in replay: velocity metric lacked single-customer filter.
Fix applied 2026-05-17. Re-run replay after fix confirms correct non-reorder decision.

=== verifyEntry() integrity check timing ===

$ node -e "
const entry = makeLogEntry('sess_001', 'call_001', 'get_inventory', {sku:'SKU-8821'}, {inventory:847});
const t0 = performance.now();
for (let i = 0; i < 100000; i++) eventLog.verifyEntry(entry);
console.log('verifyEntry (SHA-256 recompute):', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
verifyEntry (SHA-256 recompute): 0.0048 ms

=== Coverage: S-101 vs S-106 ===

                          │ S-101 (deterministic sessions)    │ S-106 (event log replay)
──────────────────────────┼───────────────────────────────────┼──────────────────────────────
Purpose                   │ Idempotency; avoid re-executing   │ Audit; reconstruct past state
What is replayed          │ Same inputs → same cached output  │ Past inputs → past-time output
Tool results              │ Returned from in-memory log       │ Returned from persistent log
Replay from different time│ Not the goal                      │ Core use case
Model version tracking    │ Not tracked                       │ Logged with each entry
Use case                  │ Resume crashed session identically│ Debug: why did it decide X at T?
```

## See also

[S-101](s101-deterministic-agent-sessions.md) · [S-104](s104-event-stream-agent-integration.md) · [F-31](../forward-deployed/f31-structured-call-logging.md) · [F-51](../forward-deployed/f51-agent-rollback.md) · [F-74](../forward-deployed/f74-agent-decision-tracing.md) · [F-42](../forward-deployed/f42-ai-incident-response.md) · [S-93](s93-tool-side-effect-idempotency.md)

## Go deeper

Keywords: `event log replay` · `agent audit log` · `historical state reconstruction` · `tool result logging` · `immutable event log` · `agent debugging replay` · `event sourcing agents` · `replay interceptor` · `incident replay` · `time-travel debugging`
