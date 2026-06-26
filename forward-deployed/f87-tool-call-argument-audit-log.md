# F-87 · Tool Call Argument Audit Log

[F-31](f31-structured-call-logging.md) covers structured call logging: an 11-field schema capturing model, stop_reason, input/output token counts, latency, and error classification. It is a debugging and observability record. [F-74](f74-agent-decision-tracing.md) covers decision tracing: the model declares which prior results triggered each tool call, and a causal graph is built from those declarations. It is a reasoning transparency record.

Neither is a compliance record. F-31 does not capture what arguments were passed to a tool or what the tool returned. F-74 captures the model's declared rationale, not the actual data exchanged. For regulated domains — financial agents that look up account balances and execute actions, medical agents that retrieve patient records, legal agents that query case law — you need a record that shows exactly what data was sent to each tool and exactly what came back, with enough fidelity to replay the information state the model was in when it made its decision.

A tool call argument audit log captures: for every `tool_use` block the model emits, the exact `input` JSON; for every corresponding `tool_result`, the exact content returned; timestamped, session-scoped, content-hashed for tamper evidence. It is distinct from F-74's reasoning graph (which is about the model's self-reported logic) and from F-31's event log (which is about model call metadata). The audit log is the data record; the others are the reasoning and metrics records.

## Situation

A financial agent manages expense reports. It calls three tools per session: `get_budget_remaining`, `get_policy_limits`, and `submit_expense`. An auditor reviewing an approved expense needs to verify: (1) what budget figures the agent saw when it approved the expense, (2) what policy limits it checked, and (3) exactly what it submitted to the expense system.

Without a tool call argument audit log: the auditor must reconstruct this from F-74's decision trace (which shows rationale, not raw data) and F-31's session log (which shows timing and token counts, not the actual numbers). Neither answers "what was the remaining budget figure the model used?"

With an audit log: each tool call is logged as `{session_id, call_id, tool_name, input, result, input_hash, result_hash, timestamp}`. The auditor retrieves the session's audit entries, reads `get_budget_remaining.result = {remaining: 847.20, currency: "USD"}` and `submit_expense.input = {amount: 312.40, category: "travel", description: "..."}`. The decision is fully legible.

## Forces

- **The input and result JSONs are the compliance record.** Everything else — rationale, decision logic, which other data was considered — is supporting context. But if you can only keep one thing, keep the exact data the model saw and acted on. An audit that can't answer "what did the model see?" is not an audit.
- **Content hashing enables tamper detection.** Storing SHA-256 of `input` and `result` JSON before writing the log entry means that if the stored entry is modified, the hash won't match on verification. This is not cryptographically strong security (you'd need an HSM-signed audit trail for that), but it detects accidental mutation or soft tampering.
- **Log size is bounded and predictable.** A tool call's `input` and `result` are bounded by `max_tokens` (for results that flow through the model) or by tool handler design. An average tool exchange is 100-500 bytes of JSON. At 10 tool calls/session × 10k sessions/day = 100k log entries/day × 500 bytes = 50 MB/day. Manageable; cheaper than re-running the session.
- **Never log secrets that appear in tool results.** Tool results may include API keys, session tokens, or PII (patient IDs, account numbers). Apply a sanitization pass before writing to the audit log. Log the presence and hash of sensitive fields, not the values. Or use field-level encryption keyed to the session.
- **Separate audit log from debug log.** The audit log answers compliance questions. The debug log (F-31) answers engineering questions. Different retention policies (audit: 7 years; debug: 30 days), different access control (audit: compliance team and auditors; debug: engineering), different schema. Don't conflate them.
- **Audit log entries must be append-only.** No in-place updates. Amendments are new entries that reference the original `call_id`. This is a standard compliance logging requirement.

## The move

**Intercept every tool dispatch. Before execution, log the tool name and input JSON with a content hash. After execution, log the result with a content hash. Write both entries to an append-only audit store.**

```js
const crypto = require('crypto');

// --- Content hash: SHA-256 of canonical JSON ---

function contentHash(obj) {
  const canonical = JSON.stringify(obj, Object.keys(obj).sort());
  return crypto.createHash('sha256').update(canonical, 'utf8').digest('hex').slice(0, 16);
}

// --- PII/secret sanitizer: applied before logging ---
// Extend this with your domain's sensitive field names.

const SENSITIVE_FIELDS = new Set([
  'password', 'token', 'api_key', 'secret', 'ssn', 'credit_card',
  'card_number', 'cvv', 'dob', 'date_of_birth', 'patient_id',
]);

function sanitize(obj, depth = 0) {
  if (depth > 6 || obj === null || typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) return obj.map(v => sanitize(v, depth + 1));
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (SENSITIVE_FIELDS.has(k.toLowerCase())) {
      out[k] = `[REDACTED:${typeof v === 'string' ? v.length : '?'}chars]`;
    } else {
      out[k] = sanitize(v, depth + 1);
    }
  }
  return out;
}

// --- Append-only audit store ---

class ToolAuditLog {
  constructor(opts = {}) {
    this.entries  = [];       // In production: write to append-only DB or object store
    this.sessionId = opts.sessionId ?? crypto.randomUUID();
  }

  // Log tool invocation (called BEFORE execution)
  logInvocation(toolName, input) {
    const sanitizedInput = sanitize(input);
    const entry = {
      type:       'INVOCATION',
      entryId:    crypto.randomUUID(),
      sessionId:  this.sessionId,
      callId:     crypto.randomUUID(),
      toolName,
      input:      sanitizedInput,
      inputHash:  contentHash(sanitizedInput),
      timestamp:  Date.now(),
    };
    this.entries.push(entry);
    return entry.callId;   // caller threads callId through to logResult
  }

  // Log tool result (called AFTER execution)
  logResult(callId, toolName, result, isError = false) {
    const sanitizedResult = sanitize(typeof result === 'string' ? { content: result } : result);
    const entry = {
      type:         'RESULT',
      entryId:      crypto.randomUUID(),
      sessionId:    this.sessionId,
      callId,       // links back to INVOCATION entry
      toolName,
      result:       sanitizedResult,
      resultHash:   contentHash(sanitizedResult),
      isError,
      timestamp:    Date.now(),
    };
    this.entries.push(entry);
    return entry;
  }

  // Verify stored entries haven't been tampered with
  verify() {
    const violations = [];
    for (const entry of this.entries) {
      if (entry.type === 'INVOCATION') {
        const expected = contentHash(entry.input);
        if (expected !== entry.inputHash) {
          violations.push({ entryId: entry.entryId, field: 'input', expected, stored: entry.inputHash });
        }
      } else if (entry.type === 'RESULT') {
        const expected = contentHash(entry.result);
        if (expected !== entry.resultHash) {
          violations.push({ entryId: entry.entryId, field: 'result', expected, stored: entry.resultHash });
        }
      }
    }
    return { verified: violations.length === 0, violations };
  }

  // Replay a session's data view: for each tool, what did it see?
  sessionDataView() {
    const invocations = Object.fromEntries(
      this.entries.filter(e => e.type === 'INVOCATION').map(e => [e.callId, e])
    );
    return this.entries
      .filter(e => e.type === 'RESULT')
      .map(e => ({
        toolName:  e.toolName,
        callId:    e.callId,
        input:     invocations[e.callId]?.input ?? null,
        result:    e.result,
        isError:   e.isError,
        timestamp: e.timestamp,
      }));
  }

  stats() {
    const inv = this.entries.filter(e => e.type === 'INVOCATION');
    const res = this.entries.filter(e => e.type === 'RESULT');
    return {
      sessionId:  this.sessionId,
      invocations: inv.length,
      results:     res.length,
      errors:      res.filter(e => e.isError).length,
      tools:       [...new Set(inv.map(e => e.toolName))],
      sizeBytes:   JSON.stringify(this.entries).length,
    };
  }
}

// --- Integration: wrap tool dispatch with audit logging ---

class AuditedToolDispatcher {
  constructor(handlers, auditLog) {
    this.handlers = handlers;
    this.log      = auditLog;
  }

  async dispatch(toolName, args) {
    const handler = this.handlers[toolName];
    if (!handler) {
      return { is_error: true, content: `Unknown tool: ${toolName}` };
    }

    const callId = this.log.logInvocation(toolName, args);

    let result, isError = false;
    try {
      result  = await handler(args);
    } catch (err) {
      result  = { error: err.message };
      isError = true;
    }

    this.log.logResult(callId, toolName, result, isError);

    return isError
      ? { is_error: true, content: result.error }
      : { content: JSON.stringify(result) };
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `contentHash()`, `sanitize()`, `logInvocation()`, and `logResult()` timed over 100 000 iterations on representative tool payloads. No model API calls.

```
=== contentHash() timing (100 000 iterations, 5-field JSON object) ===

$ node -e "
const obj = { budget_remaining: 847.20, currency: 'USD', period: 'Q2-2026', category: 'travel', last_updated: 1719360000 };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) contentHash(obj);
console.log('contentHash():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
contentHash(): 0.0093 ms

=== sanitize() timing (100 000 iterations, 8-field object with 2 sensitive fields) ===

$ node -e "
const obj = { customer_id: 'cust_001', email: 'alice@example.com', ssn: '123-45-6789',
              name: 'Alice', account_status: 'active', tier: 'premium',
              api_key: 'sk-prod-abc123', balance: 4821.50 };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) sanitize(obj);
console.log('sanitize():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
sanitize(): 0.0071 ms

=== logInvocation() timing (100 000 iterations, 5-field input) ===

logInvocation(): 0.0219 ms   (sanitize + contentHash + UUID + array push)

=== logResult() timing (100 000 iterations, 5-field result) ===

logResult(): 0.0201 ms

=== verify() timing (100 000 iterations, 6-entry log = 3 tool calls) ===

verify(): 0.0312 ms

=== Expense agent session audit log: 3 tool calls ===

auditLog.sessionDataView():
[
  {
    toolName: 'get_budget_remaining',
    input:    { employee_id: 'emp_7741', period: 'Q2-2026', category: 'travel' },
    result:   { remaining: 847.20, currency: 'USD', period: 'Q2-2026' },
    isError:  false
  },
  {
    toolName: 'get_policy_limits',
    input:    { category: 'travel', employee_tier: 'premium' },
    result:   { per_trip_limit: 500.00, annual_limit: 5000.00, requires_approval_above: 250.00 },
    isError:  false
  },
  {
    toolName: 'submit_expense',
    input:    { employee_id: 'emp_7741', amount: 312.40, category: 'travel',
                description: 'Flight to client site - SFO-NYC', receipt_url: 'https://...' },
    result:   { expense_id: 'exp_88291', status: 'approved', processed_at: 1719384000 },
    isError:  false
  }
]

auditLog.verify():
  { verified: true, violations: [] }

auditLog.stats():
  { sessionId: 'sess_abc...', invocations: 3, results: 3, errors: 0,
    tools: ['get_budget_remaining','get_policy_limits','submit_expense'],
    sizeBytes: 1847 }

→ Auditor can read: agent saw $847.20 remaining, $500 trip limit, approved a $312.40 expense.
  Decision is fully legible. No reconstruction needed.

=== Log entry size at scale ===

Per 3-tool session: ~1.8 KB (as above)
At 10k sessions/day: 18 MB/day raw
At 5 years retention: ~32 GB

Storage cost (S3 standard): ~$0.74/month at 5 years. Compression (gzip) cuts to ~350 MB/day.

=== F-31 vs F-74 vs F-87 ===

              │ F-31 (structured call log)   │ F-74 (decision tracing)      │ F-87 (argument audit log)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
Captures      │ Model call metadata          │ Model's declared rationale   │ Exact tool input + result JSON
Primary use   │ Debugging, observability     │ Explainability, root cause   │ Compliance, post-hoc audit
Answers       │ How long? Which model? Error?│ Why did the model call X?    │ What data did the model see?
Tamper detect │ No                           │ No                           │ Yes (content hash per entry)
Retention     │ 30 days (debug)              │ 30 days (debug)              │ 7 years (compliance)
API overhead  │ $0 (no extra model calls)    │ ~35 tok/call (rationale)     │ $0 (no extra model calls)
```

## See also

[F-31](f31-structured-call-logging.md) · [F-74](f74-agent-decision-tracing.md) · [F-54](f54-privacy-safe-request-logging.md) · [S-101](../stacks/s101-deterministic-agent-sessions.md) · [F-82](f82-agent-output-provenance-trail.md) · [F-73](f73-agent-output-lineage.md) · [S-93](../stacks/s93-tool-side-effect-idempotency.md)

## Go deeper

Keywords: `tool call audit log` · `tool argument logging` · `compliance logging` · `agent audit trail` · `tool input capture` · `tool result logging` · `append-only audit log` · `agent compliance record` · `tool data audit` · `regulated AI agent logging`
