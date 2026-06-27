# F-151 · Extraction Field Enum Validation

[F-131](f131-extraction-output-field-pattern-validation.md) validates that a field's value matches a declared regex pattern — it is a format check. A value of "NET_45" passes the pattern `/^[A-Z0-9_]+$/` cleanly. [F-135](f135-extraction-output-field-normalizer.md) converts values to canonical form: "net 30" → "NET_30", "UNITED STATES" → "US". But if the model returns "NET_45", F-135 cannot map it to a valid form because "NET_45" is already canonical — it is simply not a member of the allowed set.

The gap is value membership. An extraction schema declares that `payment_terms` must be one of `["NET_30", "NET_60", "NET_90", "IMMEDIATE", "MILESTONE"]`. A model that returns "NET_45" has produced a structurally valid, canonically formatted string that happens not to be a valid enum member. F-131 passes it (correct format). F-135 produces it (canonical case). No check in the chain catches it unless you add an explicit enum validation step.

The enum validator registers per-field allowed sets. After checking each extracted value against the set (O(1) Set lookup), it falls back to Levenshtein edit distance only on failures — the slow path runs only when it is needed. "NET_45" finds closest match "NET_30" or "NET_60" (both edit distance 2 from "NET_45"). "USA" finds "US" (edit distance 1). The retry hint names the invalid value, lists all allowed values, and names the closest match with its edit distance — giving the model a specific correction target rather than a generic failure message.

## Situation

A contract extraction pipeline declares four enum-constrained fields: `payment_terms` (5 allowed values), `jurisdiction` (6 allowed values), `contract_type` (5 allowed values), `renewal_type` (3 allowed values, WARN severity — optional field). After F-135 normalization runs, values are in canonical uppercase form.

Scenario B: `payment_terms = "NET_45"`. F-131 passes it (format valid). F-135 outputs it unchanged (already canonical). F-151 rejects it: INVALID_VALUE, closest match "NET_30" (edit distance 2). Retry hint: "payment_terms "NET_45" is not a valid value; allowed: [NET_30, NET_60, NET_90, IMMEDIATE, MILESTONE]; closest match: "NET_30" (edit distance 2)."

Scenario C: `jurisdiction = "USA"` (common model output when training data used "USA" frequently), `renewal_type = "ANNUAL"`. F-151 catches both: `jurisdiction` as ERROR (closest "US", edit distance 1), `renewal_type` as WARN (closest "MANUAL", edit distance 2 — "ANNUAL" is not close to any valid renewal type, so the hint signals a possible wrong-field extraction). `passed: false` due to the ERROR; delivery is blocked for `jurisdiction` correction but not halted by the WARN.

Scenario D: all four fields null — all SKIP. Null presence is F-143's domain; the enum validator does not double-fire on null fields.

## Forces

- **Run after F-135 (normalizer), before F-143 (conditional presence).** F-135 puts values in the canonical form the allowed set expects. Running F-151 before F-135 would miss values like "net_30" (not in set uppercase, would INVALID_VALUE, but after normalization is valid). Run after F-131 (format) as well — there is no benefit to enum-checking a malformed string.
- **Levenshtein runs only on INVALID_VALUE — keep the fast path fast.** Valid and null fields take the O(1) Set lookup path (0.0011 ms per call across 4 fields). Invalid fields add Levenshtein (0.0392 ms with 1 INVALID_VALUE). This is acceptable: enum violations are rare in a well-tuned pipeline; the slow path fires only on the failures that need correction guidance.
- **SKIP null fields — do not double-fire with F-143.** If `payment_terms` is null, F-143 handles it (conditional presence). F-151 should return SKIP and not fire INVALID_VALUE on a null. The error classes are distinct and the retry hints are different: F-143 says "this field is required when X is true"; F-151 says "this field's value is not a valid member of the allowed set."
- **Set WARN severity for optional or informational enum fields.** A field that enriches downstream processing but is not required for delivery (renewal_type, risk_category, document_subtype) should use WARN severity. It is logged and flagged for improvement but does not block delivery. ERROR severity is for fields whose invalid value would corrupt downstream processing (payment_terms fed to a payment scheduler, jurisdiction fed to a compliance router).
- **The closest match is a suggestion, not a correction.** Do not silently replace "NET_45" with "NET_30" in the output — you do not know whether the closest match is the right one. Surface it in the retry hint so the model can confirm the correction. If edit distance to the closest match exceeds 3, the closest match is probably not meaningful — include it but note in the hint that it is a loose match.

## The move

**Register per-field allowed sets. Check each extracted value against the set. Return SKIP / VALID / INVALID_VALUE with Levenshtein closest match and retry hint. Chain: F-131 → F-135 → F-151 → F-143.**

```js
// --- Extraction field enum validation ---
// Validates extracted field values against declared allowed sets.
// Distinct from F-131 (format/regex), F-135 (normalization), F-143 (conditional presence).
// Chain: F-70 → F-131 → F-135 (normalize first) → F-151 (enum) → F-143 → F-147 → F-150.
// SKIP null fields; use Levenshtein on the slow path (INVALID_VALUE only).

function editDistance(a, b) {
  const m = a.length, n = b.length;
  const dp = Array.from({ length: m + 1 }, (_, i) =>
    [i, ...Array(n).fill(0)]
  );
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = a[i-1] === b[j-1]
        ? dp[i-1][j-1]
        : 1 + Math.min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1]);
  return dp[m][n];
}

class ExtractionEnumValidator {
  constructor() { this._rules = []; }

  registerField(field, allowedValues, opts) {
    opts = opts || {};
    this._rules.push({
      field, allowedValues,
      allowedSet: new Set(allowedValues.map(v => v.toUpperCase())),
      severity: opts.severity || 'ERROR',
    });
    return this;
  }

  check(output) {
    const results = this._rules.map(rule => {
      const raw = output[rule.field];
      if (raw === null || raw === undefined || raw === '') {
        return { status: 'SKIP', field: rule.field };
      }
      if (rule.allowedSet.has(String(raw).toUpperCase())) {
        return { status: 'VALID', field: rule.field, value: raw };
      }
      // Slow path: find closest allowed value
      let best = null, bestDist = Infinity;
      for (const av of rule.allowedValues) {
        const d = editDistance(String(raw).toUpperCase(), av.toUpperCase());
        if (d < bestDist) { bestDist = d; best = av; }
      }
      return {
        status:       'INVALID_VALUE',
        field:        rule.field,
        value:        raw,
        severity:     rule.severity,
        allowedValues: rule.allowedValues,
        closestMatch: best,
        editDistance: bestDist,
        retryHint:    `${rule.field} "${raw}" is not a valid value; ` +
                      `allowed: [${rule.allowedValues.join(', ')}]; ` +
                      `closest match: "${best}" (edit distance ${bestDist})`,
      };
    });
    const violations = results.filter(r => r.status === 'INVALID_VALUE');
    const errors     = violations.filter(r => r.severity === 'ERROR');
    return { passed: errors.length === 0, results, violations,
             errors, warnings: violations.filter(r => r.severity === 'WARN') };
  }
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four registered enum fields; four scenarios. `check()` timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Extraction Field Enum Validation ===

--- Scenario A: All fields valid ---
  VALID          payment_terms="NET_30"
  VALID          jurisdiction="US"
  VALID          contract_type="SERVICE"
  VALID          renewal_type="AUTO"
  passed: true

--- Scenario B: payment_terms "NET_45" not in allowed set ---
  INVALID_VALUE  payment_terms="NET_45"  ERROR
    retryHint: "payment_terms "NET_45" is not a valid value; allowed: [NET_30, NET_60,
                NET_90, IMMEDIATE, MILESTONE]; closest match: "NET_30" (edit distance 2)"
  VALID          jurisdiction="US"
  VALID          contract_type="SERVICE"
  SKIP           renewal_type="null"
  passed: false  errors: 1

--- Scenario C: jurisdiction "USA" (ERROR) + renewal_type "ANNUAL" (WARN) ---
  VALID          payment_terms="NET_60"
  INVALID_VALUE  jurisdiction="USA"  ERROR
    retryHint: "jurisdiction "USA" is not a valid value; allowed: [US, UK, EU, CA, AU,
                OTHER]; closest match: "US" (edit distance 1)"
  VALID          contract_type="VENDOR"
  INVALID_VALUE  renewal_type="ANNUAL"  WARN
    retryHint: "renewal_type "ANNUAL" is not a valid value; allowed: [AUTO, MANUAL, NONE];
                closest match: "MANUAL" (edit distance 2)"
  passed: false  errors: 1  warnings: 1

--- Scenario D: All null — all SKIP ---
  SKIP           payment_terms
  SKIP           jurisdiction
  SKIP           contract_type
  SKIP           renewal_type
  passed: true  (SKIP is not a violation — F-143 handles null presence separately)

=== F-131 vs F-135 vs F-151 ===
F-131: "NET_45" PASSES /^[A-Z0-9_]+$/ pattern check   (format valid)
F-135: "NET_45" → "NET_45" unchanged                   (already canonical)
F-151: "NET_45" INVALID_VALUE — not in allowed set     (value membership fails)

=== Timing (1 000 000 iterations) ===
check() 4 fields, all VALID/SKIP:           0.0011 ms
check() 4 fields, 1 INVALID_VALUE (ERROR):  0.0392 ms
check() 4 fields, 2 violations (E+W):       0.0493 ms
Levenshtein runs only on INVALID_VALUE. VALID/SKIP are O(1) Set lookup.
Zero API calls. Zero tokens. Runs at delivery boundary.
```

## See also

[F-131](f131-extraction-output-field-pattern-validation.md) · [F-135](f135-extraction-output-field-normalizer.md) · [F-143](f143-output-field-conditional-presence-check.md) · [F-70](f70-verifiable-output-design.md) · [F-150](f150-extraction-mutual-field-completeness-check.md)

## Go deeper

Keywords: `extraction enum validation` · `allowed values check extraction` · `field value membership LLM` · `enum field validator extraction` · `Levenshtein closest match extraction` · `invalid enum value extraction` · `extraction field allowed set` · `enumerated field validation` · `extraction value set check` · `closest enum match retry hint`
