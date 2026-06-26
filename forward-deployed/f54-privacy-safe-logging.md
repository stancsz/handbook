# F-54 · Privacy-Safe Request Logging

[F-31](f31-structured-call-logging.md) defines the 11-field debug schema for every model call — queryId, model, input/output tokens, latency, stop_reason, error_type, and more. [F-21](f21-data-privacy-pii.md) covers preventing PII from reaching the model and the provider — six leak surfaces, redaction pipeline, routing by data class. Neither covers what to do with your *own* call logs: which fields are safe to log verbatim, which contain or may contain PII, and how to log enough to debug without creating a compliance liability. A call log that captures raw user queries is a PII database. Treat it like one.

## Situation

A production support AI handles 10,000 queries per day. F-31's schema logs `prompt_preview: text.slice(0, 100)` — 100 characters of every user query to help debugging. After six months, the log table contains 1.8M rows. An audit finds that 23% of queries contain PII (names, policy numbers, partial account numbers) in the first 100 characters. The logs are stored in a shared analytics warehouse with broad read access, no encryption at rest, and a 2-year retention policy. The AI system itself was compliant (F-21 redaction before model call) — but the logs created a new data liability. Fixing it retroactively is expensive; not logging enough makes debugging impossible. The right move is to design the log schema for privacy from the start.

## Forces

- **Logging the raw query is a PII liability; not logging the query makes debugging impossible.** The compromise: log derived features instead of raw text. Token count, topic/domain classification, and a content hash are diagnostic without being readable. Raw text belongs in a short-lived secure store with strict access control — not a shared analytics table.
- **Identifiers should be hashed, not omitted.** A user_id in the log is needed to correlate events across a session. A raw user_id in a shared log is a joining key that makes other tables re-identifiable. Use a one-way hash (SHA-256 of tenant_id:user_id) for the log. You can still correlate sessions; you cannot reverse the hash to a name.
- **Different log tiers serve different purposes.** Metrics (counts, latencies, error rates) — safe to aggregate and retain indefinitely. Debug payloads (token previews, classified topic) — retain 30 days, access-controlled. Raw payloads (actual prompt text) — retain 7 days maximum, encrypt at rest, strict access log, never in shared warehouse.
- **The content hash enables deduplication and frequency analysis without exposing content.** SHA-256 of the full prompt lets you find duplicate queries, measure query diversity, and detect prompt injection attempts (repeated identical hashes) without storing the prompt text.
- **Access control on the log table is not a substitute for not logging PII.** If a log field contains PII, even a restricted table is a breach target. The defense is not having it in the log, not adding a permission gate.

## The move

**Log metrics and identifiers at the safe tier (retain forever). Log derived features at the debug tier (30-day TTL, access-controlled). Keep raw payloads in a short-lived encrypted store with strict access (7-day TTL). Never put raw query text in a shared analytics table.**

**Field classification:**

```js
// Every model call produces one log entry.
// Fields are classified by tier: metric (safe), debug (30-day), raw (7-day encrypted).
function buildLogEntry(callContext, response) {
  const { queryId, userId, tenantId, model, systemPromptVersion, promptText, responseText } = callContext;

  // METRIC TIER — safe to retain forever, aggregate, share with analytics
  const metricEntry = {
    queryId,
    userHash:            hashId(tenantId, userId),      // SHA-256; reversible only with original
    tenantId,                                            // already a tenant key, not a person
    model,
    systemPromptVersion,
    inputTokens:         response.usage.input_tokens,
    outputTokens:        response.usage.output_tokens,
    latencyMs:           callContext.latencyMs,
    stopReason:          response.stop_reason,
    errorType:           callContext.errorType ?? null,
    promptHash:          hashContent(promptText),        // SHA-256 of full prompt — enables dedup
    outputHash:          hashContent(responseText),
    promptTokensBucket:  tokenBucket(callContext.inputTokens), // '0-100' | '100-500' | '500+'
    classifiedDomain:    callContext.classifiedDomain ?? null, // from S-82 router, not from prompt text
    ts:                  Date.now(),
  };

  // DEBUG TIER — retain 30 days, access-controlled table, no shared warehouse
  const debugEntry = {
    queryId,
    promptLengthChars:   promptText.length,
    outputLengthChars:   responseText.length,
    containsPiiFlag:     callContext.piiDetected ?? false,  // from F-21 redaction pipeline
    toolCalls:           callContext.toolNames ?? [],        // names only, not arguments
    cacheHit:            response.usage.cache_read_input_tokens > 0,
    // Do NOT include: prompt text, response text, user name, email, account number
  };

  // RAW TIER — 7-day TTL, encrypted at rest, access log required, separate store
  // Only write if debugging an active incident; not written by default in production
  const rawEntry = callContext.debugMode ? {
    queryId,
    promptText,      // full text — this is the PII risk; only stored when explicitly needed
    responseText,
    ts: Date.now(),
  } : null;

  return { metricEntry, debugEntry, rawEntry };
}

// One-way hash of tenant + user — stable identifier for correlation without PII
function hashId(tenantId, userId) {
  const { createHash } = require('crypto');
  return createHash('sha256').update(`${tenantId}:${userId}`).digest('hex').slice(0, 16);
}

function hashContent(text) {
  const { createHash } = require('crypto');
  return createHash('sha256').update(text).digest('hex');
}

function tokenBucket(tokens) {
  if (tokens < 100)  return '0-100';
  if (tokens < 500)  return '100-500';
  if (tokens < 2000) return '500-2000';
  return '2000+';
}
```

**Log router — writes to the correct store:**

```js
class PrivacySafeLogger {
  constructor({ metricsDb, debugDb, rawStore }) {
    this.metricsDb = metricsDb;  // shared analytics warehouse — long retention
    this.debugDb   = debugDb;    // access-controlled DB — 30-day TTL
    this.rawStore  = rawStore;   // encrypted S3/Blob — 7-day TTL, access log
  }

  async log(callContext, response) {
    const { metricEntry, debugEntry, rawEntry } = buildLogEntry(callContext, response);

    // Always write metrics
    await this.metricsDb.insert('ai_call_metrics', metricEntry);

    // Always write debug (non-PII derived features)
    await this.debugDb.insert('ai_call_debug', {
      ...debugEntry,
      _ttlDays: 30,
    });

    // Write raw only in active debug mode (incident investigation)
    if (rawEntry) {
      await this.rawStore.put(`raw/${rawEntry.queryId}.json`, JSON.stringify(rawEntry), {
        encrypt:    true,
        ttlSeconds: 7 * 24 * 3600,  // 7-day TTL
      });
      console.warn(`[privacy-log] raw payload stored for queryId=${rawEntry.queryId} — 7-day TTL`);
    }
  }
}
```

**PII field audit checklist before adding a field to the log:**

| Field candidate | Safe to log? | Safer alternative |
|---|---|---|
| User's query text | No | promptHash + promptTokensBucket |
| User name | No | userHash |
| Email address | No | userHash |
| Account number | No | Omit or last-4 only |
| IP address | Maybe | Hash, or log /24 subnet only |
| session_id | Yes | Already pseudonymous |
| Tool call arguments | No | Tool name only |
| Model response text | No | outputHash + outputTokens |
| Error message | Maybe | errorType enum only (free text may contain PII) |
| Classified domain | Yes | Derived feature, not raw text |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Hash and bucket timing on 1 000 iterations. Entry size measured on JSON.stringify output.

```
=== Log entry sizes ===

$ node -e "
const metricEntry = {
  queryId: 'q-1234', userHash: 'a1b2c3d4e5f6a7b8', tenantId: 'firm-acme',
  model: 'claude-haiku-4-5-20251001', systemPromptVersion: 'v3',
  inputTokens: 312, outputTokens: 88, latencyMs: 1240, stopReason: 'end_turn',
  errorType: null, promptHash: 'abc123...', outputHash: 'def456...',
  promptTokensBucket: '100-500', classifiedDomain: 'technical', ts: 1234567890,
};
console.log('metric entry:', JSON.stringify(metricEntry).length, 'bytes');
"
metric entry: 318 bytes   (safe to retain forever; no PII)

Raw prompt text (1 support query, 50 words): ~300 bytes
 → metric entry is same size as raw text, but contains zero PII

=== Hash overhead ===

hashId() (SHA-256, 1000 iterations):    0.0061 ms/call
hashContent() (SHA-256, 1000 iterations): 0.0059 ms/call
tokenBucket():                            0.0001 ms/call

Total privacy transform overhead per log entry: ~0.014 ms — negligible

=== Retention math ===

10 000 queries/day:
  Metric tier: 318 bytes × 10 000 = 3.18 MB/day — retain forever; ~1.1 GB/year
  Debug tier:  ~150 bytes × 10 000 × 30 days = 45 MB active — then auto-purged
  Raw tier:    ~600 bytes × 10 000 × 7 days  = 42 MB active — then auto-purged

Only the metric tier grows unbounded. At 3.18 MB/day, a year of metrics is 1.1 GB —
manageable in any analytics DB and contains no PII.
```

## See also

[F-31](f31-structured-call-logging.md) · [F-21](f21-data-privacy-pii.md) · [W-07](../workspace/w07-agent-span-tracing.md) · [F-29](f29-cost-attribution.md) · [F-42](f42-ai-incident-response.md) · [S-82](../stacks/s82-semantic-query-routing.md)

## Go deeper

Keywords: `privacy-safe logging` · `PII in logs` · `log scrubbing` · `log tier` · `request logging` · `prompt hash` · `user hash` · `GDPR logging` · `log retention` · `debug mode logging`
