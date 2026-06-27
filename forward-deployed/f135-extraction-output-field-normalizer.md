# F-135 · Extraction Output Field Normalizer

[F-70](f70-structured-output-validation.md) validates required fields, types, and enums: a `risk_level` field not in `['HIGH', 'MEDIUM', 'LOW']` is a violation. [F-131](f131-output-field-string-pattern-validator.md) validates string field formats: a `clause_id` not matching `CL-\d+` is a violation. Both report what is wrong. Neither fixes values that are semantically correct but lexically off: `"High risk"` means `HIGH`, `"United States of America"` means `US` — these are extraction failures from a format perspective, not from a meaning perspective. The model understood the document; it just didn't know the canonical form.

The gap between "the model understood it" and "F-70 accepts it" is the normalization layer. Without it, a correctly extracted value fails enum validation and routes to F-133 (escalation policy) — which retries the extraction. The retry is unnecessary: the value is not wrong, only unlabeled. Running normalization before validation converts correct-but-informal values to their canonical forms, eliminating a class of false validation failures at zero model cost.

An extraction output field normalizer registers per-field match rules — string (case-insensitive exact) or RegExp — each mapped to a canonical form. Before F-70 validation, the normalizer applies these rules to every field in the extraction output. Fields with no registered rule pass through unchanged. Fields that match are replaced with the canonical value. The original and canonical values are logged for drift monitoring.

## Situation

A contract extraction pipeline uses Haiku to extract a 6-field schema from bilateral agreements: `clause_id`, `termination_fee`, `parties`, `risk_level`, `effective_date`, `governing_law`. F-70 validates the output; the `risk_level` enum is `['HIGH', 'MEDIUM', 'LOW']` and `governing_law` enum is `['US', 'GB', 'DE', 'FR']`.

Production logs show that Haiku returns valid-meaning values in non-canonical forms 8% of the time:

- `risk_level`: `"High risk"` (17 occurrences), `"medium"` (12), `"Low Risk"` (9) — all semantically correct, all enum failures.
- `governing_law`: `"United States"` (23 occurrences), `"U.S.A."` (8), `"England and Wales"` (6) — same issue.

Without normalization, these route to F-133's retry escalation: 75 Haiku retries × $0.0008 = $0.06/day, plus 15 Sonnet upgrades × $0.0030 = $0.045/day. Total: $0.105/day for values the pipeline already has correct.

With normalization before F-70: 75 values converted to canonical form in ~0.002ms each, enum validation passes, no retry triggered. The $0.105/day in unnecessary retries is eliminated. The normalizer cost is zero model calls.

## Forces

- **Register from observed extraction output, not from the enum list.** The normalizer's rules come from what the model actually returns — found in production logs or a test run over a sample corpus. Start with strings that appear in your extraction logs and map them to the canonical form. Do not try to enumerate every possible paraphrase in advance; build the rule list from observed failures.
- **String rules are case-insensitive exact match; RegExp rules are for prefix and pattern variants.** `"High risk"` → `"HIGH"` is a string rule: one specific form to one canonical. `"United States"` through `"United States of America"` is a prefix family best handled by `/^united states/i`. Use strings for known exact forms; use RegExp when the variant has multiple suffix forms.
- **Normalization runs before validation; logging runs after normalization.** Log every normalization event — field, original value, canonical value — to a drift monitor. If `risk_level` normalizations spike, the model's output distribution is drifting away from the canonical form. That drift is a signal that the extraction prompt needs updating, not the normalizer.
- **Compose in order: normalize → F-70 → F-131 → F-133.** Normalization converts "correct meaning, wrong form." F-70 catches "wrong meaning" failures (missing required fields, wrong types, invalid enums after normalization). F-131 catches format failures (patterns). F-133 escalates the remainder. Running normalization first shrinks the set of failures that reach the escalation tier.
- **Do not normalize fields with structured values.** `termination_fee: "24 500 000"` has a unit problem — that is F-99's job (numeric unit normalization). `parties: ["Alpha Corp.", "Alpha Corporation"]` has a deduplication problem. The field normalizer handles string enum fields. Use F-99 for numeric units; handle array fields separately if needed.
- **F-134 ensemble voting produces the plurality value, not the canonical value.** After F-134 votes, the result may still be `"High risk"` (MAJORITY, 2/3 agree). Run the normalizer after the voter, before F-70. The sequence is: `extractWithEnsemble → normalize → validate → F-133`.

## The move

**Register match rules per field. Run normalize() before F-70 validation. Log all normalizations for drift monitoring.**

```js
// --- Extraction output field normalizer ---
// Converts "correct meaning, wrong form" values to canonical forms before F-70 validation.
// register(field, rules): each rule is { match: string|RegExp, canonical: string }.
// String match: case-insensitive exact. RegExp: tested as-is (include 'i' flag if needed).
// normalize(output): applies rules to all registered fields; passes others through.
// Returns { output, normalized: [{field, original, canonical}] }
// Compose: normalize → F-70 validate → F-133 escalate (if still failing).

class ExtractionFieldNormalizer {
  constructor() {
    this._rules = new Map();  // field → [{ match, canonical }]
  }

  register(field, rules) {
    this._rules.set(field, rules);
    return this;
  }

  normalizeField(field, value) {
    if (typeof value !== 'string') return { original: value, canonical: value, matched: false };
    const rules = this._rules.get(field);
    if (!rules) return { original: value, canonical: value, matched: false };
    for (var i = 0; i < rules.length; i++) {
      var r = rules[i];
      if (r.match instanceof RegExp) {
        if (r.match.test(value)) return { original: value, canonical: r.canonical, matched: true };
      } else {
        if (value.toLowerCase() === r.match.toLowerCase()) return { original: value, canonical: r.canonical, matched: true };
      }
    }
    return { original: value, canonical: value, matched: false };
  }

  normalize(output) {
    var result  = {};
    var changed = [];
    var fields  = Object.keys(output);
    for (var i = 0; i < fields.length; i++) {
      var f = fields[i];
      var n = this.normalizeField(f, output[f]);
      result[f] = n.canonical;
      if (n.matched) changed.push({ field: f, original: n.original, canonical: n.canonical });
    }
    return { output: result, normalized: changed };
  }
}

// --- Configuration: rules built from observed extraction output ---

const NORMALIZER = new ExtractionFieldNormalizer()
  .register('risk_level', [
    { match: 'high risk',   canonical: 'HIGH'   },
    { match: 'high',        canonical: 'HIGH'   },
    { match: 'medium risk', canonical: 'MEDIUM' },
    { match: 'medium',      canonical: 'MEDIUM' },
    { match: 'low risk',    canonical: 'LOW'    },
    { match: 'low',         canonical: 'LOW'    },
  ])
  .register('governing_law', [
    { match: /^united states/i, canonical: 'US' },
    { match: /^u\.?s\.?a?\.?$/i, canonical: 'US' },
    { match: /^united kingdom/i, canonical: 'GB' },
    { match: /^england/i,        canonical: 'GB' },
    { match: /^u\.?k\.?$/i,      canonical: 'GB' },
  ]);

// --- Integration: normalize → validate → escalate ---

async function extractAndValidate(document, schema) {
  const raw      = await extractOnce('claude-haiku-4-5-20251001', document, schema);

  // Step 1: normalize before validation
  const { output, normalized } = NORMALIZER.normalize(raw);
  if (normalized.length > 0) {
    log({ event: 'extraction_normalized', fields: normalized });
  }

  // Step 2: F-70 → F-131 validation chain
  const validated = validateExtraction(output);

  // Step 3: F-133 escalation if validation still fails
  if (validated.status !== 'PASS') {
    return escalate(output, validated, schema);
  }
  return { output, attempt: 1, normalized };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `normalizeField()` and `normalize()` timed over 100 000 iterations. 2 fields registered with string and RegExp rules. 6-field contract extraction output used as test input.

```
=== ExtractionFieldNormalizer timing (100 000 iterations) ===

normalizeField() string match:  0.0003 ms
normalizeField() regex match:   0.0002 ms
normalizeField() no rule:       0.0001 ms
normalize() 6-field output:     0.0018 ms

=== Scenario: 6-field contract extraction ===

Before normalization:
  clause_id:       "CL-042"
  termination_fee: "24500000"
  parties:         ["Alpha Corp", "Beta LLC"]
  risk_level:      "High risk"
  effective_date:  "2026-01-15"
  governing_law:   "United States of America"

After normalization:
  clause_id:       "CL-042"          (unchanged)
  termination_fee: "24500000"        (unchanged)
  parties:         ["Alpha Corp", "Beta LLC"]  (unchanged)
  risk_level:      "HIGH"            ← "High risk" → "HIGH"
  effective_date:  "2026-01-15"      (unchanged)
  governing_law:   "US"              ← "United States of America" → "US"

=== F-70 enum validation: before vs after normalization ===

Enum: risk_level ∈ {HIGH, MEDIUM, LOW}; governing_law ∈ {US, GB, DE, FR}

Before normalize:
  risk_level:   "High risk"               → FAIL (not in enum)
  governing_law: "United States of America" → FAIL (not in enum)

After normalize:
  risk_level:   "HIGH" → PASS
  governing_law: "US"  → PASS

=== Cost: normalization vs retry escalation (1 000 extractions/day, 7.5% informal rate) ===

Without normalizer:
  75 informal values/day → 75 Haiku retries × $0.0008 = $0.06
  15 persist to Sonnet upgrade × $0.003              = $0.045
  Total:                                               $0.105/day

With normalizer:
  75 informal values normalized at 0.002 ms each → $0.00/day model cost
  Retries eliminated:                              $0.105/day saved

=== F-99 vs S-88 vs F-131 vs F-135 ===

F-99 (unit normalizer):    currency/date/% strings → numeric: "$1.5M" → 1500000
S-88 (arg coercer):        normalizes tool INPUT args before dispatch — not extraction output
F-131 (pattern validator): validates format, reports violations — does not fix values
F-135 (field normalizer):  normalizes extraction OUTPUT enum strings before F-70 enum check
```

## See also

[F-70](f70-structured-output-validation.md) · [F-131](f131-output-field-string-pattern-validator.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-134](f134-extraction-ensemble-voter.md) · [F-99](f99-numeric-unit-normalizer.md)

## Go deeper

Keywords: `extraction output field normalizer` · `enum alias normalization` · `canonical form before validation` · `extraction informal value normalization` · `pre-validation field canonicalization` · `enum value normalization` · `extraction string normalization` · `alias to canonical extraction` · `before F-70 normalization` · `extraction output canonicalization`
