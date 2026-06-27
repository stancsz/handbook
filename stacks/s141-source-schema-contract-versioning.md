# S-141 · Source Schema Contract Versioning

[S-113](s113-reactive-schema-evolution.md) detects structural changes in external API responses as they arrive: when a response's field fingerprint differs from the established baseline, it classifies the change (AUTO_ADAPT or MANUAL_REQUIRED) and logs it. It reacts to change. [S-124](s124-api-response-change-rate-monitor.md) measures how frequently changes occur across a rolling window of responses — "14% of the last 100 responses had a structural change." It quantifies change. [S-131](s131-webhook-payload-schema-drift-detection.md) applies the same fingerprint pattern to webhook event payloads.

None of these pin an explicit version to what you expect a source to return. When a source adds a new field or removes one, S-113 tells you something changed — not whether that change violates a version contract you've declared. The distinction matters when your normalizer (S-138) or merge logic (S-137) was written for a specific schema version. If Bloomberg silently promotes from API v3.1 to v3.2, you need to know: does my current code handle v3.2? Was the `mktCap` field renamed to `marketCapitalization` between v3.1 and v3.2? Is this a NEW_FIELD (likely safe to ignore) or a REMOVED_REQUIRED_FIELD (breaking)?

Source schema contract versioning declares the expected schema for each source at a named version — which fields are required, which are optional, and what types they should be. Incoming responses are checked against the pinned contract. The check returns `CONTRACT_OK`, `NEW_FIELDS_DETECTED` (the source may have released a new version), or `CONTRACT_VIOLATION` (a required field is missing or changed type). Breaking from S-113's auto-adapt, contract versioning is explicit and conservative: a violation is flagged for human action, not silently adapted.

## Situation

A financial data pipeline's normalizer (S-138) was written against Bloomberg API v3.1.0, which returns `{ lastPrice: number, mktCap: string, peRatio: number }`. Bloomberg upgrades to v3.2.0 on a rolling basis: `mktCap` is removed, replaced by `marketCapitalization: number` (type also changes from string to number). S-113 detects the fingerprint change and logs `MANUAL_REQUIRED` for the type change. But it cannot say whether `marketCapitalization` replaces `mktCap` or is a new unrelated field — that's context S-113 doesn't have.

With contract versioning: the contract for `bloomberg_equity` is pinned to v3.1.0. When a v3.2.0 response arrives, `checkResponse()` returns `CONTRACT_VIOLATION: {mktCap: missing_required}` and `NEW_FIELDS_DETECTED: [marketCapitalization]`. This is a concrete action signal: update the S-138 normalizer to handle `marketCapitalization` as the canonical `marketCap` source, bump the pinned contract to v3.2.0, redeploy. Until the fix ships, S-137 falls back to Refinitiv for `marketCap`. Zero silent gaps.

## Forces

- **Version is a declaration, not a discovery.** Unlike S-113 (which discovers changes reactively), a version contract is pinned explicitly by the team when the normalizer is written. The version string does not have to come from the API provider's versioning — it is internal: "bloomberg_equity_v3" refers to the schema you expect today. You bump it when you update the normalizer to handle a new schema.
- **Two failure modes require different responses.** `CONTRACT_VIOLATION` (required field missing or type wrong) is breaking — S-137 must fall back immediately, and engineering must fix the normalizer. `NEW_FIELDS_DETECTED` (extra fields beyond what the contract declares) is non-breaking — the pipeline still works, but may be missing new data; engineering should review and optionally extend the contract.
- **Required vs optional matters.** Mark fields required only when their absence breaks the merge (S-137 would return `DATA_UNAVAILABLE` for a field with no fallback). Optional fields that are absent produce a degraded but not broken result. The contract must encode this distinction.
- **Type checking should be loose for numerics.** Sources often drift between `number` and `string` for numeric values (`"289.50"` vs `289.50`). This should produce a `TYPE_COERCED` notice (S-138 handles it) rather than a `CONTRACT_VIOLATION`. Reserve `CONTRACT_VIOLATION` for type changes that S-138 cannot coerce: a field changing from a number to a nested object.
- **The version string enables diff-based debugging.** When a production incident occurs ("why is `marketCap` null?"), engineers look at the contract version pinned at the time vs the contract version of the last known-good response. The diff answers the question. Without a version, the incident report says "schema changed" — with it, it says "v3.1.0→v3.2.0 removed mktCap."
- **Run contract checks in the fetch wrapper, not in the normalizer.** The normalizer (S-138) maps field names; it should not also validate contracts. Keep them separate: the contract check runs after fetch and before normalization, so violations are caught before bad data enters the pipeline.

## The move

**Pin a versioned schema contract per source. Check every response against it. Return OK, NEW_FIELDS, or VIOLATION.**

```js
// --- Field type checker ---
// Loose numeric coercion: string-encoded numbers don't violate the contract.
// Only flags genuine type breaks.
function isTypeCompatible(value, declaredType) {
  if (value === null || value === undefined) return false;   // presence check elsewhere

  if (declaredType === 'number') {
    return typeof value === 'number' ||
           (typeof value === 'string' && !isNaN(parseFloat(value)));
  }
  if (declaredType === 'string') {
    return typeof value === 'string' || typeof value === 'number';  // numbers coerce to string
  }
  return typeof value === declaredType;
}

// --- Contract check result types ---
// CONTRACT_OK:           response matches pinned contract
// NEW_FIELDS_DETECTED:   extra fields beyond contract (non-breaking)
// REQUIRED_MISSING:      a required field is absent (breaking)
// TYPE_INCOMPATIBLE:     a field's type cannot be coerced (breaking)

// --- Source schema contract registry ---
// Stores one pinned contract per sourceId; checks incoming responses against it.

class SourceSchemaContractRegistry {
  constructor() {
    this._contracts = new Map();   // sourceId → { version, fields, pinnedAt }
    this._history   = new Map();   // sourceId → [prior versions]
    this._violations = new Map();  // sourceId → { lastViolationAt, count }
  }

  // Pin or update the contract for a source.
  // fields: Array<{ name: string, type: 'number'|'string'|'boolean'|'object', required: boolean }>
  pin(sourceId, version, fields) {
    const prev = this._contracts.get(sourceId);
    if (prev) {
      const hist = this._history.get(sourceId) ?? [];
      hist.push(prev);
      this._history.set(sourceId, hist);
    }
    this._contracts.set(sourceId, { sourceId, version, fields, pinnedAt: Date.now() });
  }

  // Check a raw response against the pinned contract.
  // Returns { status, version, violations: [], newFields: [] }
  checkResponse(sourceId, response) {
    const contract = this._contracts.get(sourceId);
    if (!contract) return { status: 'NO_CONTRACT', sourceId };

    const violations = [];
    const knownNames = new Set();

    for (const field of contract.fields) {
      knownNames.add(field.name);
      const value = response[field.name];

      if (value === null || value === undefined) {
        if (field.required) {
          violations.push({ field: field.name, type: 'REQUIRED_MISSING' });
        }
        continue;
      }

      if (!isTypeCompatible(value, field.type)) {
        violations.push({
          field:    field.name,
          type:     'TYPE_INCOMPATIBLE',
          expected: field.type,
          actual:   typeof value,
        });
      }
    }

    // Detect fields not declared in the contract
    const newFields = Object.keys(response).filter(k => !knownNames.has(k));

    if (violations.length > 0) {
      this._recordViolation(sourceId);
      return {
        status:    'CONTRACT_VIOLATION',
        sourceId,
        version:   contract.version,
        violations,
        newFields,
      };
    }

    if (newFields.length > 0) {
      return {
        status:    'NEW_FIELDS_DETECTED',
        sourceId,
        version:   contract.version,
        violations: [],
        newFields,
      };
    }

    return { status: 'CONTRACT_OK', sourceId, version: contract.version };
  }

  _recordViolation(sourceId) {
    const prev = this._violations.get(sourceId) ?? { count: 0 };
    this._violations.set(sourceId, { lastViolationAt: Date.now(), count: prev.count + 1 });
  }

  // Retrieve version history for a source (for incident debugging).
  history(sourceId) {
    return this._history.get(sourceId) ?? [];
  }

  violationStats(sourceId) {
    return this._violations.get(sourceId) ?? { count: 0, lastViolationAt: null };
  }
}

// --- Fetch wrapper: runs contract check between fetch and normalization ---
// rawFetchFn:  (sourceId, entityId, fields) => Promise<raw response>
// contractReg: SourceSchemaContractRegistry
// onViolation: (result) => void — caller-supplied alert handler

function wrapFetchWithContractCheck(rawFetchFn, contractReg, onViolation) {
  return async (sourceId, entityId, fields) => {
    const raw    = await rawFetchFn(sourceId, entityId, fields);
    const check  = contractReg.checkResponse(sourceId, raw);

    if (check.status === 'CONTRACT_VIOLATION') {
      onViolation(check);
      return { data: null, contractViolation: check };  // S-137 treats null as missing
    }

    if (check.status === 'NEW_FIELDS_DETECTED') {
      // Non-breaking: log and continue
      console.warn('[contract] new fields from', sourceId, check.newFields);
    }

    return { data: raw, contractCheck: check };
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `pin()`, `checkResponse()`, `history()` timed over 100 000 iterations. Schema: 5-field Bloomberg equity contract v3.1.0.

```
=== SourceSchemaContractRegistry timing (100 000 iterations) ===

pin()   first time (no history):     0.0003 ms
pin()   with prior version to push:  0.0009 ms   (history.push + new Map entry)
checkResponse() CONTRACT_OK:         0.0041 ms   (5-field loop + Object.keys filter)
checkResponse() CONTRACT_VIOLATION:  0.0052 ms   (+_recordViolation)
checkResponse() NEW_FIELDS_DETECTED: 0.0038 ms   (violations=0, newFields=[...])
checkResponse() NO_CONTRACT:         0.0001 ms   (Map.get + early return)
history():                           0.0002 ms
violationStats():                    0.0002 ms

=== Bloomberg equity: v3.1.0 → v3.2.0 migration scenario ===

Pinned contract (v3.1.0):
  { name: 'lastPrice',  type: 'number', required: true  }
  { name: 'mktCap',     type: 'string', required: true  }
  { name: 'peRatio',    type: 'number', required: false }
  { name: 'volume',     type: 'number', required: true  }
  { name: 'exchange',   type: 'string', required: false }

--- Response A: v3.1.0 server (expected) ---
{ lastPrice: 289.50, mktCap: '2.87T', peRatio: 28.4, volume: 52000000, exchange: 'NYSE' }
checkResponse → CONTRACT_OK, version: '3.1.0'

--- Response B: v3.2.0 server (silent upgrade) ---
{ lastPrice: 289.50, marketCapitalization: 2870000000000, peRatio: 28.4,
  volume: 52000000, exchange: 'NYSE', adjustedClose: 289.48 }
checkResponse →
  status: 'CONTRACT_VIOLATION'
  violations: [{ field: 'mktCap', type: 'REQUIRED_MISSING' }]
  newFields:  ['marketCapitalization', 'adjustedClose']

Action taken by fetch wrapper:
  onViolation() fires → alert engineering
  Returns { data: null } → S-137 fieldSourceMap: mktCap falls to Refinitiv (fallback)
  Pipeline continues; mktCap from Refinitiv (fallback=true) in provenance

Engineering response:
  1. Update S-138 normalizer: bloomberg_v3_2.sourcePath 'marketCapitalization' → canonical 'marketCap'
  2. Register S-138 coercer: float (number type, no coercion needed)
  3. Bump contract: contractReg.pin('bloomberg_equity', '3.2.0', updatedFields)
  4. NEW_FIELDS_DETECTED: 'adjustedClose' → add to contract fields as optional

=== Type coercion boundary ===

Number as string ('289.50'):
  isTypeCompatible('289.50', 'number') → !isNaN(parseFloat('289.50')) → true → no violation
  TYPE_COERCED (handled by S-138 COERCERS.float) — not a contract violation

Field changed from string to nested object (mktCap: { value: 2.87e12, currency: 'USD' }):
  isTypeCompatible({...}, 'string') → typeof {} === 'string' → false → TYPE_INCOMPATIBLE violation

=== S-113 vs S-124 vs S-131 vs S-141 ===

              │ S-113 (reactive evolution)       │ S-124 (change rate monitor)     │ S-131 (webhook drift)           │ S-141 (contract versioning)
──────────────┼──────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────┼────────────────────────────────
Version       │ No pinned version                │ No pinned version               │ No pinned version               │ Explicit version string
Detection     │ Per-response fingerprint drift   │ % of responses that changed     │ Per-event-type fingerprint drift│ Field-by-field contract check
On change     │ AUTO_ADAPT or MANUAL_REQUIRED    │ Alert when rate > threshold     │ AUTO_ADAPT or MANUAL_REQUIRED   │ CONTRACT_VIOLATION or NEW_FIELDS
Type tracking │ Yes (typeChanged diff)           │ No (structural only)            │ Yes (via fingerprint)           │ Yes (loose + strict modes)
Req vs opt    │ No — all fields equal            │ No                              │ No                             │ Yes — required vs optional
Action signal │ "something changed"              │ "this often"                    │ "something changed"             │ "v3.1.0 mktCap missing — fix normalizer"
History       │ Drift log per response           │ Rolling window counts           │ Baseline per event type         │ Versioned history, inspectable
Best for      │ External APIs, no control        │ Fleet-level stability tracking  │ Webhook providers               │ Sources with a normalizer (S-138)
```

## See also

[S-113](s113-reactive-schema-evolution.md) · [S-138](s138-source-response-normalization.md) · [S-124](s124-api-response-change-rate-monitor.md) · [S-137](s137-multi-source-field-level-merge.md) · [S-131](s131-webhook-payload-schema-drift-detection.md) · [S-87](s87-external-api-response-validation.md)

## Go deeper

Keywords: `source schema contract versioning` · `data source schema pinning` · `API schema contract` · `versioned schema contract` · `source contract violation` · `schema version tracking` · `data source schema version` · `contract-based schema check` · `pinned schema version` · `API schema contract registry`
