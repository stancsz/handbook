# F-140 · Extraction Date Ordering Assertions

[F-70](f70-verifiable-output-design.md) validates structural integrity: required fields are present, types are correct, enum values are in range. It confirms `effective_date` is a non-null string; it does not check that `effective_date` is before `termination_date`. [F-92](f92-agent-output-arithmetic-invariants.md) checks arithmetic invariants: totals, rates, sums. These are numeric comparisons within the same field or across numeric fields. [F-99](f99-numeric-unit-consistency-check.md) normalizes representation consistency: `"$24.5M"` and `24500000` should use the same format token. None of these check whether two date fields in the same extraction are in the correct temporal order.

Date ordering violations are a distinct failure class. A model extracting a contract may return `effective_date: 2026-02-01` and `termination_date: 2025-12-31` — the termination date is in the past relative to the effective date, which is logically impossible for a valid contract. This is not a type error (both are valid date strings), not an arithmetic violation (no numeric sum), not a format inconsistency (both use ISO 8601). It is a temporal ordering violation: the model read dates from two different sections of the document and transposed the years, or pulled one date from a superseded draft.

Extraction date ordering assertions register ordering rules — each declaring an `earlier` field and a `later` field, with a severity and description. The checker parses both field values as dates and compares them. PASS: ordering holds. FAIL: ordering is violated (REVERSED or EQUAL). SKIP: one or both fields are absent or unparseable — not a failure, since F-70 handles missing required fields and F-99 handles format normalization.

## Situation

A contract extraction pipeline returns a 6-field date schema: `signing_date`, `effective_date`, `termination_date`, `renewal_date`, `last_amended_date`, `notice_deadline`. Three ordering rules govern these fields:

1. `signing_date` < `effective_date` (WARN: contract cannot be effective before it is signed)
2. `effective_date` < `termination_date` (ERROR: contract cannot terminate before it becomes effective)
3. `effective_date` < `renewal_date` (WARN: renewal must be after effective date)

A batch of 500 contracts reveals two failure patterns:

**Pattern 1: Year transposition.** The model extracts `effective_date: 2026-02-01` and `termination_date: 2025-02-01`. The source document's termination clause uses "2025" in a context the model misread as the termination year — it was the year a prior amendment was signed. F-70 accepts both dates as valid ISO strings. F-140 returns `FAIL: effective_date < termination_date REVERSED`.

**Pattern 2: Amendment confusion.** The model extracts `signing_date: 2026-03-15` for the date of an amendment, and `effective_date: 2026-02-01` for the original agreement. The signing date of the amendment is after the effective date of the original contract — a WARN that prompts review: is this the original signing date or an amendment signing date?

With date ordering assertions: both violations are caught at the delivery boundary. Pattern 1 (ERROR severity) is blocked and routed to F-133 retry. Pattern 2 (WARN severity) is delivered with a `dateOrderWarnings` annotation for the downstream reviewer.

## Forces

- **SKIP is not a failure.** Many contract fields are optional: `renewal_date` is null on non-renewable contracts, `last_amended_date` is absent if never amended. When either field in an ordering rule is null or absent, skip the rule rather than treating it as a violation. F-70 has already confirmed that required fields are present. Don't double-check F-70's job.
- **Parse dates at the assertion layer, not at the schema layer.** Date values in extracted output arrive in varied formats: ISO 8601 (`2026-02-01`), written (`February 1, 2026`), abbreviated (`Feb 2026`, `Q1 2026`). The assertion checker should normalize before comparing. A `Date.parse()` call handles most formats. For partial dates (`Feb 2026`, `Q1 2026`), expand to the first day of the period before ordering — a date given as "Q1 2026" means no later than 2026-01-01 for ordering purposes.
- **EQUAL is a violation for most ordering rules.** `effective_date === termination_date` means the contract is effective and terminated on the same day — logically valid only for same-day contracts, which should be explicitly noted. For extraction purposes, treat EQUAL as a FAIL with `violation: 'EQUAL'` and let the downstream reviewer decide. Configure equality tolerance per rule if needed.
- **Return field values in the FAIL result for debugging.** The retry hint for F-133 should include the actual values: "effective_date is 2026-02-01 but termination_date is 2025-12-31 — contract cannot terminate before it becomes effective. Check that the correct year was extracted for each date." The matched values are what the human reviewer needs to locate the error in the source document.
- **Severity belongs in the rule, not the engine.** `effective_date < termination_date` is ERROR because a reversed termination date invalidates the entire contract analysis — it is a structural extraction failure. `signing_date < effective_date` is WARN because a retroactively effective agreement (effective before signing) is legally unusual but not impossible. Declare severity per rule; the engine propagates it without interpretation.
- **Compose at the end of the validation chain.** Run F-70 (structure) → F-92 (arithmetic) → F-99 (units) → F-140 (date order), in that sequence. F-70 catches missing fields before F-140 tries to parse them. F-99 normalizes format inconsistencies before F-140 compares values. Date ordering is the final semantic check before delivery.

## The move

**Register ordering rules with severity. Parse dates. Return PASS/FAIL/SKIP per rule. Block on ERROR-severity failures; annotate WARN-severity passes.**

```js
// --- Extraction date ordering assertions ---
// Checks that date fields in extracted output are in the correct temporal order.
// Zero token cost. Runs at delivery boundary, after F-70/F-92/F-99 validation.
// status: PASS | FAIL (REVERSED or EQUAL) | SKIP (field absent or unparseable)
// Severity: ERROR (block delivery) | WARN (annotate and pass through)

// Parse date values from extracted output.
// Handles ISO 8601 and Date.parse()-compatible written forms.
function parseDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  const parsed = Date.parse(String(value).trim());
  return isNaN(parsed) ? null : new Date(parsed);
}

// Check a single ordering rule. Returns { status, rule, ... }.
function checkOrderingRule(output, rule) {
  const earlierVal = output[rule.earlier];
  const laterVal   = output[rule.later];

  if (earlierVal == null || laterVal == null) {
    return {
      status:      'SKIP',
      rule:        `${rule.earlier} < ${rule.later}`,
      reason:      'field_absent',
      absentField: earlierVal == null ? rule.earlier : rule.later,
    };
  }

  const earlierDate = parseDate(earlierVal);
  const laterDate   = parseDate(laterVal);

  if (!earlierDate || !laterDate) {
    return {
      status:      'SKIP',
      rule:        `${rule.earlier} < ${rule.later}`,
      reason:      'unparseable_date',
      unparseable: !earlierDate ? rule.earlier : rule.later,
    };
  }

  if (earlierDate < laterDate) {
    return {
      status:      'PASS',
      rule:        `${rule.earlier} < ${rule.later}`,
      severity:    rule.severity,
      description: rule.description,
    };
  }

  return {
    status:       'FAIL',
    rule:         `${rule.earlier} < ${rule.later}`,
    severity:     rule.severity,
    description:  rule.description,
    earlierField: rule.earlier,
    earlierValue: earlierVal,
    laterField:   rule.later,
    laterValue:   laterVal,
    violation:    earlierDate > laterDate ? 'REVERSED' : 'EQUAL',
  };
}

// Check all rules. Returns { passed, results, errors, warnings }.
function checkDateOrdering(output, rules) {
  const results  = rules.map(r => checkOrderingRule(output, r));
  const failures = results.filter(r => r.status === 'FAIL');
  const errors   = failures.filter(r => r.severity === 'ERROR');
  const warnings = failures.filter(r => r.severity === 'WARN');
  return { passed: errors.length === 0, results, errors, warnings };
}

// --- Contract date ordering rules ---

const CONTRACT_DATE_RULES = [
  { earlier: 'signing_date',   later: 'effective_date',   severity: 'WARN',  description: 'Contract cannot be effective before it is signed' },
  { earlier: 'effective_date', later: 'termination_date', severity: 'ERROR', description: 'Contract cannot terminate before it becomes effective' },
  { earlier: 'effective_date', later: 'renewal_date',     severity: 'WARN',  description: 'Renewal date must be after effective date' },
];

// --- Integration: delivery gate ---

function deliverWithDateCheck(output) {
  const check = checkDateOrdering(output, CONTRACT_DATE_RULES);

  if (check.errors.length > 0) {
    // Build retry hint for F-133
    const hint = check.errors
      .map(e => `${e.earlierField} is ${e.earlierValue} but ${e.laterField} is ${e.laterValue} — ${e.description}.`)
      .join(' ');
    return { delivered: false, reason: 'DATE_ORDER_ERROR', retryHint: hint, errors: check.errors };
  }

  if (check.warnings.length > 0) {
    // Annotate and deliver
    return {
      delivered: true,
      output,
      dateOrderWarnings: check.warnings.map(w => ({
        rule: w.rule,
        message: `${w.earlierField} (${w.earlierValue}) is not before ${w.laterField} (${w.laterValue})`,
      })),
    };
  }

  return { delivered: true, output };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Four scenarios. `checkDateOrdering()` timed over 100 000 iterations on 3-rule set. Zero API calls, zero tokens.

```
=== Extraction Date Ordering Assertions — 3-rule contract schema ===

--- Scenario A: PASS — all orderings correct ---

  signing=2026-01-10, effective=2026-02-01, termination=2028-02-01, renewal=2027-12-01

  signing_date < effective_date    → PASS
  effective_date < termination_date → PASS
  effective_date < renewal_date    → PASS
  delivered: true

--- Scenario B: FAIL ERROR — termination before effective ---

  effective=2026-02-01, termination=2025-12-31  (model transposed year)

  signing_date < effective_date    → PASS
  effective_date < termination_date → FAIL (REVERSED) ERROR
  effective_date < renewal_date    → PASS
  delivered: false
  retryHint: "effective_date is 2026-02-01 but termination_date is 2025-12-31 —
              Contract cannot terminate before it becomes effective."

--- Scenario C: FAIL WARN — signing after effective ---

  signing=2026-03-15 (amendment signing), effective=2026-02-01

  signing_date < effective_date    → FAIL (REVERSED) WARN
  effective_date < termination_date → PASS
  effective_date < renewal_date    → SKIP (field_absent: renewal_date)
  delivered: true (WARN only)
  dateOrderWarnings: [{ rule: "signing_date < effective_date",
    message: "signing_date (2026-03-15) is not before effective_date (2026-02-01)" }]

--- Scenario D: SKIP renewal — renewal_date is null (optional field) ---

  signing=2026-01-10, effective=2026-02-01, termination=2028-02-01, renewal=null

  signing_date < effective_date    → PASS
  effective_date < termination_date → PASS
  effective_date < renewal_date    → SKIP (field_absent: renewal_date)
  delivered: true

=== Timing (100 000 iterations) ===

checkDateOrdering() 3 rules PASS:         0.0081 ms
checkDateOrdering() 3 rules FAIL (1 err): 0.0087 ms
checkOrderingRule() single rule PASS:     0.0024 ms

=== F-70 → F-92 → F-99 → F-140: validation chain ===

F-70  (structure):    required fields present, types correct, enums valid
F-92  (arithmetic):   total = sum(items), rates sum to 1.0
F-99  (units):        "$24.5M" and "24500000" use consistent representation
F-140 (date order):   effective_date < termination_date (semantic, not structural)

Each layer catches what the prior layers cannot. Run in sequence;
block on ERROR at each layer before advancing to the next.

=== F-92 vs F-99 vs F-140 ===

              │ F-92 (arithmetic invariants) │ F-99 (unit consistency)     │ F-140 (date ordering)
──────────────┼──────────────────────────────┼─────────────────────────────┼──────────────────────────────────
Checks        │ total = sum(line_items)      │ "$24.5M" vs "24500000"      │ effective_date < termination_date
Field count   │ Multi-field numeric sum      │ Per-field representation     │ Pairwise date comparison
Data type     │ Numbers                      │ Strings (format tokens)      │ Dates (parsed from strings)
Catches       │ Wrong totals, wrong rates    │ Mixed format in same output  │ Dates in wrong temporal order
Zero tokens   │ Yes                          │ Yes                          │ Yes
```

## See also

[F-70](f70-verifiable-output-design.md) · [F-92](f92-agent-output-arithmetic-invariants.md) · [F-99](f99-numeric-unit-consistency-check.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-136](f136-extraction-lifecycle-audit-record.md)

## Go deeper

Keywords: `date ordering assertion` · `temporal consistency check` · `extraction date validation` · `effective date termination date check` · `date order violation` · `date field ordering` · `temporal ordering extraction` · `contract date consistency` · `date sequence validation` · `signing date effective date check`
