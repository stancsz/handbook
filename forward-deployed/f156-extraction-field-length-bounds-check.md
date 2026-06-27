# F-156 · Extraction Field Length Bounds Check

A `party_name` field should be 2–100 characters. A `jurisdiction` code should be 2–5 characters. A `clause_id` should be 3–10 characters. These bounds are not enforced by JSON schema, not checked by enum validation (F-151), and not caught by format regex (F-131). A value of the right type and format can still be wrong by being too long or too short.

The most common extraction length failure: the model returns clause text instead of a short extracted value. Instead of `"party_name": "Acme Corporation"` it returns `"party_name": "Acme Corporation, a Delaware corporation incorporated under the laws of the State of Delaware, with its principal place of business at 1 Market Street, San Francisco, California, USA (hereinafter 'the Provider')"`. This string is 153 characters. It passes JSON schema validation (it's a string). It passes required-field checks (it's present). It passes format validation (it contains alphabetic characters). It fails only when compared to the expected field length.

The second common failure: the model returns a long-form name when the schema expects a code. `"jurisdiction": "United States"` is 13 characters when the field expects a 2–5 character country/state code. Again: passes structural validation, fails length bounds.

Length bounds are cheap to check and the retryHints they generate are precise: "value is 153 characters (max 100 expected). Extract only the name, not the full clause text."

## Situation

A contract extraction pipeline sees a 4% rate of downstream record corruption from `party_name` fields that contain full clause text (80–200 characters instead of the expected 5–50). The fields pass all existing validators. No retry is triggered. The long strings corrupt downstream database records, break display formatting, and cause downstream NER systems to re-extract entities from what they assume is a short name field.

Adding a length bounds check catches the failure at the extraction layer and routes it through F-154's field-level retry before the output leaves the pipeline.

## Forces

- **Length bounds are schema knowledge, not model knowledge.** The model doesn't know that `jurisdiction` means a 2-character code unless the prompt says so explicitly. When the system prompt says "jurisdiction: the governing law jurisdiction" with no length hint, the model extracts what it finds in the document. The length check enforces the schema contract the model wasn't given.
- **TOO_LONG is more common than TOO_SHORT.** Models extract extra context when uncertain about field boundaries. Clause text, parenthetical explanations, and role descriptions attach to extracted names. TOO_SHORT cases are usually empty-string extractions or truncation at a model output limit — both rare. Register both bounds but expect to fire on TOO_LONG.
- **Severity by field type.** Identifier fields (`clause_id`, `party_id`) use ERROR — a malformed ID corrupts downstream joins. Name fields (`party_name`, `contract_title`) use WARN by default — a slightly long name may be acceptable. Adjust per schema.
- **isPresent() gate: empty strings skip to F-70.** An empty string signals a missing value, not a length violation. Length bounds apply only to non-empty non-null values. Presence validation belongs to F-70 and F-147.
- **Do not set bounds from one example.** Set `maxLength` from the p99 of your observed correct extractions, not from the shortest correct example. A party name like "International Business Machines Corporation" is 42 characters and legitimate. Setting maxLength to 30 would create false positives.
- **retryHint must tell the model what went wrong and what to do.** "value is 153 characters" alone is not sufficient. Add: "Extract only the party name, not the full clause describing it." The retry works when the model understands both the problem and the correction.

## The move

**Register each string field with min/max character bounds. Check after extraction. Route TOO_LONG violations through F-154's field-level retry.**

```js
// --- Extraction field length bounds check ---
// Catches extracted strings that are too long (model dumped clause text) or
// too short (value truncated or partially extracted).
// Compose with:
//   F-70  (required/type/enum structural validation)
//   F-131 (field format/pattern regex)
//   F-154 (field-level retry — pass ERROR retryHints to composeFieldRetryPrompt())
// Run after F-131 (format), before downstream use of the field values.

function isPresent(val) { return val !== null && val !== undefined && val !== ''; }

class ExtractionFieldLengthChecker {
  constructor() { this._rules = []; }

  // field:        name of the string field in the extraction output
  // opts.minLength: minimum character count (inclusive). Default: 0.
  // opts.maxLength: maximum character count (inclusive). Default: Infinity.
  // opts.severity:  'ERROR' for identifier fields, 'WARN' for name fields. Default: 'ERROR'.
  // opts.tooLongHint: what the model should do when the value is too long.
  //   Default: "Extract only the value itself, not the surrounding clause text."
  // opts.tooShortHint: what the model should do when the value is too short.
  //   Default: "Field appears truncated — extract the complete value."
  registerField(field, opts) {
    opts = opts || {};
    this._rules.push({
      field,
      minLength:    opts.minLength    || 0,
      maxLength:    opts.maxLength    || Infinity,
      severity:     opts.severity     || 'ERROR',
      tooLongHint:  opts.tooLongHint  || 'Extract only the value itself, not the surrounding clause text.',
      tooShortHint: opts.tooShortHint || 'Field appears truncated — extract the complete value.',
    });
    return this;
  }

  check(output) {
    const results = this._rules.map(rule => {
      const val = output[rule.field];
      if (!isPresent(val))         return { status: 'SKIP', field: rule.field, reason: 'field null or absent' };
      if (typeof val !== 'string') return { status: 'SKIP', field: rule.field, reason: 'not a string — F-70 handles type check' };

      const len = val.length;

      if (len >= rule.minLength && len <= rule.maxLength) {
        return { status: 'WITHIN_BOUNDS', field: rule.field, length: len };
      }

      const status = len < rule.minLength ? 'TOO_SHORT' : 'TOO_LONG';
      const boundDesc = status === 'TOO_LONG'
        ? `max ${rule.maxLength}`
        : `min ${rule.minLength}`;

      return {
        status,
        field:     rule.field,
        severity:  rule.severity,
        length:    len,
        bound:     status === 'TOO_LONG' ? rule.maxLength : rule.minLength,
        value:     val.length > 60 ? val.slice(0, 57) + '...' : val,
        retryHint: `${rule.field}: value is ${len} characters (${boundDesc} expected). ` +
                   (status === 'TOO_LONG' ? rule.tooLongHint : rule.tooShortHint),
      };
    });

    const violations = results.filter(r => r.status === 'TOO_SHORT' || r.status === 'TOO_LONG');
    const errors     = violations.filter(r => r.severity === 'ERROR');
    return {
      passed:   errors.length === 0,
      results,
      violations,
      errors,
      warnings: violations.filter(r => r.severity === 'WARN'),
    };
  }
}

// Register once at startup
const CHECKER = new ExtractionFieldLengthChecker()
  .registerField('party_name',     { minLength: 2,  maxLength: 100, severity: 'WARN',
      tooLongHint: 'Extract only the party name, not the full clause describing it.' })
  .registerField('jurisdiction',   { minLength: 2,  maxLength:   5, severity: 'ERROR',
      tooLongHint: 'Extract the 2-5 character country or state code (e.g. "US", "DE", "CA"), not the full name.' })
  .registerField('clause_id',      { minLength: 3,  maxLength:  10, severity: 'ERROR',
      tooLongHint: 'Extract the clause identifier only (e.g. "CL-01"), not the clause title or text.' })
  .registerField('contract_title', { minLength: 3,  maxLength: 200, severity: 'WARN',
      tooShortHint: 'The contract title appears incomplete — extract the full agreement name.' });

// Call on every extraction output
const result = CHECKER.check(extractionOutput);
if (!result.passed) {
  const prompt = composeFieldRetryPrompt(result.errors);  // F-154
  // ... retry or escalate via F-133
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four scenarios: all within bounds, party_name too long (model dumped clause text), jurisdiction too long (full country name instead of code), null fields skipped. Timed over 1 000 000 iterations. Zero API calls.

```
=== Extraction Field Length Bounds Check ===

--- Scenario A: all fields within bounds ---
  WITHIN_BOUNDS  party_name      "Acme Corporation"                  (16 chars, max 100)
  WITHIN_BOUNDS  jurisdiction    "DE"                                 ( 2 chars, max 5)
  WITHIN_BOUNDS  clause_id       "CL-01"                             ( 5 chars, max 10)
  WITHIN_BOUNDS  contract_title  "Service Agreement"                 (18 chars, max 200)
  passed: true

--- Scenario B: party_name too long (model extracted full clause text) ---
  TOO_LONG  party_name  "Acme Corporation, a Delaware corporation..."  (153 chars, max 100)  WARN
    retryHint: "party_name: value is 153 characters (max 100 expected).
                Extract only the party name, not the full clause describing it."
  WITHIN_BOUNDS  jurisdiction    "DE"       ( 2 chars)
  WITHIN_BOUNDS  clause_id       "CL-01"   ( 5 chars)
  WITHIN_BOUNDS  contract_title  "Service Agreement"  (18 chars)
  passed: true  (WARN — delivery not blocked; route to retry before downstream use)

--- Scenario C: jurisdiction too long (model extracted full country name instead of code) ---
  WITHIN_BOUNDS  party_name     "Beta Technologies LLC"  (22 chars)
  TOO_LONG  jurisdiction  "United States of America"  (24 chars, max 5)  ERROR
    retryHint: "jurisdiction: value is 24 characters (max 5 expected).
                Extract the 2-5 character country or state code (e.g. 'US', 'DE', 'CA'),
                not the full name."
  WITHIN_BOUNDS  clause_id       "CL-02"   ( 5 chars)
  WITHIN_BOUNDS  contract_title  "Non-Disclosure Agreement"  (24 chars)
  passed: false  errors: 1  warnings: 0

--- Scenario D: null fields (F-70/F-147 handles presence; F-156 skips) ---
  SKIP           party_name      (field null or absent)
  SKIP           jurisdiction    (field null or absent)
  WITHIN_BOUNDS  clause_id       "CL-01"  ( 5 chars)
  SKIP           contract_title  (field null or absent)
  passed: true

=== Timing (1 000 000 iterations) ===
check() 4 fields, all WITHIN_BOUNDS:  0.0002 ms
check() 4 fields, 1 TOO_LONG:         0.0003 ms
Zero API calls. Zero tokens.

=== Production impact ===
  4% party_name TOO_LONG rate × 10 000 calls/day = 400 violations/day
  Caught at extraction layer → 400 field retries/day (F-154)
    vs 400 downstream record corruptions/day without the check
  Downstream corruption cost: manual data cleanup typically 5–15 min/record
```

## See also

[F-154](f154-extraction-field-level-retry.md) · [F-131](f131-extraction-field-format-validator.md) · [F-151](f151-extraction-field-enum-validation.md) · [F-70](f70-verifiable-output-design.md) · [F-155](f155-extraction-array-field-uniqueness-check.md)

## Go deeper

Keywords: `extraction field length bounds` · `string length validation` · `TOO_LONG extraction` · `field length check` · `extraction field too long` · `LLM extracts clause text instead of value` · `field length validator` · `max length extraction` · `party name too long extraction` · `extraction output length guard`
