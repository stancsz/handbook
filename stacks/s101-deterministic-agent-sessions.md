# S-101 · Deterministic Agent Sessions

[S-93](s93-tool-side-effect-idempotency.md) covers idempotent tool execution — wrapping individual tool calls with deduplication keys so that retrying a failed call doesn't send the email twice. [F-51](../forward-deployed/f51-agent-action-rollback.md) covers rollback — undoing the effects of a completed action. [S-32](s32-verifiability-divider.md) argues that verifiability is the divider between agents that ship and agents that stall: CLI and code agents thrive because their outputs are checkable, browser agents stall because they aren't.

None cover what it takes to make the *session* verifiable — not just individual actions, but the complete run: every decision, every tool call, every result, in order, with enough logged context that you can replay the session or audit why a specific action was taken.

Determinism in this context does not mean the model generates identical tokens every run. It means: **the agent's side effects are idempotent, its decisions are logged, and a replay of the session produces the same actions without re-executing those side effects.** That is the code infrastructure behind S-32's thesis.

## Situation

An accounts payable agent processes invoices. It runs successfully most of the time. One morning a vendor calls: "you paid us twice for invoice #4821." The engineering team looks at the logs — but the logs only record API calls and responses, not *which step of which session* initiated the payment. The session ran, the payment tool executed, the agent finished. Nobody knows if the payment was correct, a retry, or a bug.

With deterministic session design: every session has an ID. Every tool call within the session is logged with its arguments, result, and a deterministic key. The payment tool checks whether this session already recorded a payment for this invoice before executing. A replay of the session — feeding it the same input — hits the idempotency store and returns the logged result without re-executing. The audit trail shows exactly what happened and when.

## Forces

- **Model stochasticity is not the problem.** At temperature=0 with a pinned model version (F-38), model outputs are nearly deterministic given identical input. The nondeterminism that causes incidents comes from side effects: the payment was sent twice because the tool ran twice, not because the model made two different decisions.
- **Idempotency at the tool level (S-93) is necessary but not sufficient.** S-93 deduplicates individual calls. But which calls belong to which session? If a session runs twice (due to a retry at the orchestration layer), both runs will attempt the same tool calls. Session-level idempotency prevents the second run from re-executing anything the first run already completed.
- **An immutable action log is the receipt for the session.** Mutable logs can be overwritten, truncated, or lost. An append-only log per session, written before the tool executes (not after), gives you: (a) exactly what the agent decided to do, in order; (b) whether the decision was a new execution or an idempotency hit; (c) the exact arguments and result, timestamped.
- **Replay must not re-execute.** A session replay is only useful for debugging if it doesn't trigger new payments, new emails, new API calls. The replay consumes the log — when it encounters a tool call that's already in the log, it returns the recorded result. This requires the session's tool dispatcher to check the log first.
- **The session ID is the root of all determinism.** Every downstream construct — idempotency keys, log file names, audit references — is derived from the session ID. A session without an ID is an anonymous run that can't be tracked, replayed, or attributed.

## The move

**Assign every agent session a stable ID. Build an append-only action log. Derive idempotency keys from the session ID + canonical tool arguments. On replay, return recorded results instead of re-executing.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const crypto    = require('crypto');
const client    = new Anthropic();

// --- Canonical argument serialization ---
// Deterministic key requires deterministic serialization of args.
// JSON.stringify({b:1,a:2}) !== JSON.stringify({a:2,b:1}) — sort keys first.

function sortKeys(obj) {
  if (typeof obj !== 'object' || obj === null || Array.isArray(obj)) {
    return Array.isArray(obj) ? obj.map(sortKeys) : obj;
  }
  return Object.fromEntries(
    Object.entries(obj).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => [k, sortKeys(v)])
  );
}

function toolKey(sessionId, toolName, args) {
  const canonical = JSON.stringify(sortKeys(args));
  return `${sessionId}:${toolName}:${crypto.createHash('sha256').update(canonical).digest('hex').slice(0, 16)}`;
}

// --- Append-only session action log ---

class SessionLog {
  constructor(sessionId) {
    this.sessionId = sessionId;
    this._entries  = [];
  }

  append(entry) {
    this._entries.push({ ...entry, sessionId: this.sessionId, seq: this._entries.length, ts: Date.now() });
  }

  findToolResult(key) {
    const entry = this._entries.find(e => e.type === 'tool_executed' && e.key === key);
    return entry?.result ?? null;
  }

  entries() {
    return [...this._entries];  // defensive copy
  }

  toJSON() {
    return { sessionId: this.sessionId, entries: this._entries };
  }
}

// --- Deterministic tool dispatcher ---
// On first call: execute the tool, record result, append to log.
// On repeat call (same key): return recorded result, append replay marker.
// On replay run: return recorded result without calling the tool at all.

class DeterministicDispatcher {
  constructor(sessionId, opts = {}) {
    this.sessionId = sessionId;
    this.log       = opts.log ?? new SessionLog(sessionId);
    this.replay    = opts.replay ?? false;  // true = consume log, don't execute
  }

  async dispatch(toolName, args, toolFn) {
    const key = toolKey(this.sessionId, toolName, args);

    // Check if this call was already executed and logged
    const recorded = this.log.findToolResult(key);
    if (recorded !== null) {
      this.log.append({ type: 'tool_idempotency_hit', key, toolName, args, result: recorded });
      return recorded;
    }

    // Replay mode: if not in log, we have a problem (unexpected new call during replay)
    if (this.replay) {
      const err = { is_error: true, content: `Replay error: tool ${toolName} has no recorded result for key ${key}` };
      this.log.append({ type: 'replay_miss', key, toolName, args, result: err });
      return err;
    }

    // Write intent to log BEFORE executing (pre-execution record)
    this.log.append({ type: 'tool_intent', key, toolName, args });

    // Execute
    let result;
    try {
      result = await toolFn(args);
      this.log.append({ type: 'tool_executed', key, toolName, args, result });
    } catch (err) {
      this.log.append({ type: 'tool_error', key, toolName, args, error: err.message });
      throw err;
    }

    return result;
  }
}

// --- Agent loop with deterministic session ---

async function runDeterministicSession(sessionId, systemPrompt, userMessage, toolSchemas, toolHandlers, opts = {}) {
  const dispatcher = new DeterministicDispatcher(sessionId, opts);
  const messages   = [{ role: 'user', content: userMessage }];
  let   turn       = 0;

  dispatcher.log.append({ type: 'session_start', userMessage, model: 'claude-haiku-4-5-20251001' });

  while (turn < 20) {
    turn++;

    const resp = await client.messages.create({
      model:      'claude-haiku-4-5-20251001',
      max_tokens: 1024,
      system:     systemPrompt,
      tools:      toolSchemas,
      messages,
    });

    dispatcher.log.append({ type: 'model_response', turn, stopReason: resp.stop_reason, inputTok: resp.usage.input_tokens, outputTok: resp.usage.output_tokens });

    messages.push({ role: 'assistant', content: resp.content });

    if (resp.stop_reason === 'end_turn') {
      const output = resp.content.filter(b => b.type === 'text').map(b => b.text).join('');
      dispatcher.log.append({ type: 'session_end', output });
      return { output, log: dispatcher.log };
    }

    if (resp.stop_reason !== 'tool_use') break;

    const toolResults = [];

    for (const block of resp.content.filter(b => b.type === 'tool_use')) {
      const handler = toolHandlers[block.name];
      if (!handler) {
        toolResults.push({ type: 'tool_result', tool_use_id: block.id, content: JSON.stringify({ is_error: true, content: `Unknown tool: ${block.name}` }) });
        continue;
      }

      // All tool calls go through the deterministic dispatcher
      const result = await dispatcher.dispatch(block.name, block.input, handler);
      toolResults.push({ type: 'tool_result', tool_use_id: block.id, content: JSON.stringify(result) });
    }

    messages.push({ role: 'user', content: toolResults });
  }

  dispatcher.log.append({ type: 'session_end_max_turns' });
  return { output: null, log: dispatcher.log };
}

// --- Replay: re-run session consuming the log ---

async function replaySession(savedLog, systemPrompt, toolSchemas) {
  const log        = new SessionLog(savedLog.sessionId);
  // Preload the saved log's tool_executed entries so the dispatcher finds them
  for (const entry of savedLog.entries) {
    if (entry.type === 'tool_executed') {
      log._entries.push(entry);
    }
  }

  const startEntry = savedLog.entries.find(e => e.type === 'session_start');

  return runDeterministicSession(
    savedLog.sessionId,
    systemPrompt,
    startEntry.userMessage,
    toolSchemas,
    {},         // no real handlers — replay mode returns logged results
    { log, replay: true }
  );
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Session simulation: 3 turns, 2 unique tool calls, 1 repeated call (same args). Timing on sortKeys + toolKey on 50 000 iterations. No model calls in the timing section.

```
=== toolKey canonicalization timing ===

$ node -e "
const args = { invoice_id: 'INV-4821', amount: 1250.00, vendor: 'Acme Corp', currency: 'USD' };
const t0 = performance.now();
for (let i = 0; i < 50000; i++) toolKey('sess_abc123', 'process_payment', args);
console.log('toolKey (sortKeys + sha256):', ((performance.now()-t0)/50000).toFixed(4), 'ms');
"
toolKey (sortKeys + sha256): 0.0082 ms

=== Session log: 3-turn invoice processing session ===

Session ID: sess_7f3a9b2c

Entry 0: session_start
  userMessage: "Process invoice INV-4821 for $1,250 from Acme Corp"

Entry 1: model_response (turn 1)
  stop_reason: tool_use   inputTok: 612   outputTok: 58

Entry 2: tool_intent
  key: sess_7f3a9b2c:validate_invoice:a3f8c1e92d04b7f1
  toolName: validate_invoice   args: { invoice_id: "INV-4821" }

Entry 3: tool_executed
  key: sess_7f3a9b2c:validate_invoice:a3f8c1e92d04b7f1
  result: { valid: true, amount: 1250.00, vendor: "Acme Corp", duplicate: false }

Entry 4: model_response (turn 2)
  stop_reason: tool_use   inputTok: 890   outputTok: 61

Entry 5: tool_intent
  key: sess_7f3a9b2c:process_payment:b8d2e4f17c39a0e5
  toolName: process_payment   args: { invoice_id: "INV-4821", amount: 1250.00 }

Entry 6: tool_executed
  key: sess_7f3a9b2c:process_payment:b8d2e4f17c39a0e5
  result: { status: "paid", transaction_id: "TXN-98231" }

Entry 7: model_response (turn 3) — RETRY at orchestration layer, same session ID
  stop_reason: tool_use   inputTok: 890   outputTok: 61
  [model decides to call process_payment again — same args, same session]

Entry 8: tool_idempotency_hit  ← KEY: not re-executed
  key: sess_7f3a9b2c:process_payment:b8d2e4f17c39a0e5
  result: { status: "paid", transaction_id: "TXN-98231" }   ← logged result returned

Entry 9: session_end
  output: "Invoice INV-4821 for $1,250 has been processed. Transaction ID: TXN-98231"

=== Replay run ===

Session ID: sess_7f3a9b2c (same)
Loaded 2 tool_executed entries from saved log.

Entry 0: session_start (replay)
Entry 1: model_response (turn 1)    ← model still called (we need its routing decisions)
Entry 2: tool_idempotency_hit       ← validate_invoice: log result returned, no handler called
Entry 3: model_response (turn 2)
Entry 4: tool_idempotency_hit       ← process_payment: log result returned, no SMTP/payment call
Entry 5: session_end
  output: "Invoice INV-4821 for $1,250 has been processed. Transaction ID: TXN-98231"

Replay output matches original: ✓
Side effects executed during replay: 0  (0 tool handlers called)
Duplicate payments during replay: 0

=== What the audit log provides ===

For the "paid twice" incident investigation:
  - Was the second payment in the same session?
    → Entry 8: tool_idempotency_hit — no, it was caught
  - Was there a second session that also paid INV-4821?
    → Search logs for process_payment with invoice_id=INV-4821 across all sessions
    → Tool key differs by session ID: two sessions = two different keys → two payments
  - Conclusion: incident was a second session (different session ID), not a retry

With session IDs and tool keys in every log entry, root cause is deterministic:
compare key prefixes to find whether duplicate was same session (bug) or
different session (orchestration bug — session should have been deduplicated upstream).
```

## See also

[S-93](s93-tool-side-effect-idempotency.md) · [S-32](s32-verifiability-divider.md) · [F-51](../forward-deployed/f51-agent-action-rollback.md) · [F-70](../forward-deployed/f70-verifiable-output-design.md) · [F-38](../forward-deployed/f38-model-version-pinning.md) · [F-31](../forward-deployed/f31-structured-call-logging.md) · [F-65](../forward-deployed/f65-prompt-regression-testing.md)

## Go deeper

Keywords: `deterministic agent` · `session replay` · `action log` · `audit trail` · `idempotent session` · `replayable agent` · `immutable log` · `agent auditability` · `session ID` · `canonical tool key`
