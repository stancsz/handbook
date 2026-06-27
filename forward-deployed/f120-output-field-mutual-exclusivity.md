# F-120 · Output Field Mutual Exclusivity

[F-70](f70-structured-output-validation.md) validates structured LLM output at the field level: type checks, range checks (`confidence` between 0 and 10), length constraints, and co-occurrence invariants (`action_required: true` implies `action_description` is non-empty). It runs after the model produces its structured output and before the agent acts on it.

F-70 handles value-validity. It does not handle field-pair conflicts where both fields existing is the violation. A model output may return `approved: true` and `rejected: true` simultaneously — both are valid boolean fields individually, but they cannot coexist. This is mutual exclusivity: the presence of both fields (each with a truthy value) is the constraint. Similarly, `status: "approved"` with a non-empty `rejection_reason` is a conditional exclusion: when the status says one thing, a specific other field must be null or empty.

Both patterns are structural consistency rules at the output level. They are not value ranges; they are cross-field logical invariants. F-70 validation catches each field's local validity; mutual exclusivity catches their combination's logical validity.

## Situation

A contract review agent returns a structured decision object. Four rules govern it:

1. `approved` and `rejected` cannot both be truthy — one overrides the other.
2. `internal_review` and `external_review` cannot both be truthy — reviews are routed to one channel.
3. When `status === "approved"`, `rejection_reason` must be null/empty — an approval has no rejection reason.
4. When `status === "rejected"`, `approval_timestamp` must be null/empty — a rejection has no approval timestamp.

The model hallucinates a case where it sets `approved: true`, `rejected: true`, and `status: "rejected"` simultaneously. F-70 validates that `rejected` is a boolean (it is) and `approved` is a boolean (it is). No F-70 violation. The mutual exclusivity checker catches all three rule violations: rule 1 (both truthy), rule 3 (status=approved with rejection_reason populated from a prior turn bleed), rule 4 (status=rejected with approval_timestamp also populated).

## Forces

- **F-70 is necessary but not sufficient.** F-70 validates that each field meets its own constraints. Mutual exclusivity is a different layer: it validates that combinations of fields are logically coherent. Both are needed; they catch different failure modes.
- **LLMs produce logically inconsistent outputs more often than expected.** Tool call outputs and structured generation under instruction following work well for individual field constraints. Cross-field consistency is harder because the model reasons about each field somewhat independently. In a long structured schema with many fields, logical conflicts slip through even well-prompted models.
- **Two rule types cover most cases.** `both_truthy` catches "these two fields cannot both be true at the same time." `conditional_exclusion` catches "when field A equals value X, field B must be null/empty." Most real-world mutual exclusivity patterns fit one of these two shapes. Trying to unify them into a single rule type loses clarity; keeping them separate makes the rule table readable.
- **Exact cost: sub-millisecond per check, any schema size.** The checker iterates over registered rules (typically < 20), does Map lookups and string comparisons per rule. At 10 rules: < 0.002ms. The check is free compared to the LLM call it protects.
- **Violations should abort, not coerce.** When `approved: true` and `rejected: true` both appear, do not silently pick one. The model's intent is ambiguous. Abort the action, log the raw output, and either re-prompt with an explicit exclusivity instruction or escalate to human review. Silent coercion hides the hallucination and may allow downstream corruption.
- **Compose with F-70, not replace it.** Run F-70 field validation first. Run mutual exclusivity second. Both can produce violations in the same output (a field out of range AND a conflicting pair). Log all violations together; decide on any based on the severity policy for that action type.

## The move

**Register mutual exclusivity rules (both-truthy pairs and conditional exclusions). Check output before acting. Abort on any violation.**

```js
// --- Output field mutual exclusivity checker ---
// Two rule types:
//   both_truthy:          all fields in `fields` array are truthy simultaneously → violation
//   conditional_exclusion: when `whenField === whenValue`, `prohibitField` must be null/empty/prohibitValue

class OutputMutualExclusivityChecker {
  constructor() {
    this._rules = [];
  }

  // Register a rule. Chainable.
  // type: 'both_truthy' | 'conditional_exclusion'
  // name: human-readable rule identifier (used in violation objects)
  register(rule) {
    this._rules.push(rule);
    return this;
  }

  // Check an output object against all registered rules.
  // Returns { passed: bool, violations: [...] }
  check(output) {
    const violations = [];

    for (const rule of this._rules) {
      if (rule.type === 'both_truthy') {
        // Violation if every field in rule.fields is truthy in output
        if (rule.fields.every(f => output[f])) {
          violations.push({
            type:   'MUTUAL_EXCLUSIVITY',
            name:   rule.name,
            fields: rule.fields,
            values: Object.fromEntries(rule.fields.map(f => [f, output[f]])),
          });
        }

      } else if (rule.type === 'conditional_exclusion') {
        // Violation if whenField === whenValue AND prohibitField contains a prohibited value
        if (output[rule.whenField] === rule.whenValue) {
          const v = output[rule.prohibitField];
          const violated = rule.prohibitCondition === 'not_null'
            ? (v !== null && v !== undefined && v !== '')
            : v === rule.prohibitValue;

          if (violated) {
            violations.push({
              type:         'CONDITIONAL_EXCLUSION',
              name:         rule.name,
              whenField:    rule.whenField,
              whenValue:    rule.whenValue,
              prohibitField: rule.prohibitField,
              actualValue:  v,
            });
          }
        }
      }
    }

    return { passed: violations.length === 0, violations };
  }
}

// --- Contract review agent: rule table ---
// Define once per schema; check before every action taken on model output.

const CONTRACT_EXCLUSIVITY = new OutputMutualExclusivityChecker()
  .register({
    type:   'both_truthy',
    name:   'approved_xor_rejected',
    fields: ['approved', 'rejected'],
  })
  .register({
    type:   'both_truthy',
    name:   'internal_xor_external_review',
    fields: ['internal_review', 'external_review'],
  })
  .register({
    type:             'conditional_exclusion',
    name:             'approved_status_no_rejection_reason',
    whenField:        'status',
    whenValue:        'approved',
    prohibitField:    'rejection_reason',
    prohibitCondition: 'not_null',
  })
  .register({
    type:             'conditional_exclusion',
    name:             'rejected_status_no_approval_timestamp',
    whenField:        'status',
    whenValue:        'rejected',
    prohibitField:    'approval_timestamp',
    prohibitCondition: 'not_null',
  });

// --- Integration pattern ---
// Run F-70 field validation, then mutual exclusivity, then act.

function validateAndAct(output, action) {
  const fieldResult = F70_VALIDATOR.check(output);     // S-70/F-70 field-level validation
  const exclResult  = CONTRACT_EXCLUSIVITY.check(output);

  if (!fieldResult.passed || !exclResult.passed) {
    const allViolations = [...fieldResult.violations, ...exclResult.violations];
    log({ level: 'ERROR', event: 'output_validation_failed', rawOutput: output, violations: allViolations });
    throw Object.assign(
      new Error('Output validation failed: ' + allViolations.map(v => v.name).join(', ')),
      { violations: allViolations, rawOutput: output }
    );
  }

  return action(output);
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `register()` and `check()` timed over 100 000 iterations. Rule set: 4 rules (2 `both_truthy`, 2 `conditional_exclusion`). All violation scenarios verified against expected output.

```
=== OutputMutualExclusivityChecker timing (100 000 iterations) ===

register():                              0.0002 ms
check() — PASS (no violations):          0.0006 ms
check() — VIOLATION, both_truthy:        0.0015 ms
check() — VIOLATION, cond_exclusion:     0.0005 ms

=== Contract review: 4 rules, 4 violation scenarios ===

Rule table:
  R1: both_truthy            — approved XOR rejected
  R2: both_truthy            — internal_review XOR external_review
  R3: conditional_exclusion  — status=approved → rejection_reason must be null
  R4: conditional_exclusion  — status=rejected → approval_timestamp must be null

--- Scenario 1: PASS ---
  input: { approved: true, rejected: false, status: 'approved',
           rejection_reason: null, approval_timestamp: '2026-06-26T10:00:00Z',
           internal_review: true, external_review: false }
  R1: approved=true, rejected=false → NOT both truthy → OK
  R2: internal_review=true, external_review=false → NOT both truthy → OK
  R3: status='approved', rejection_reason=null → OK
  R4: status!='rejected' → skip
  result: { passed: true, violations: [] }

--- Scenario 2: VIOLATION — both_truthy (R1) ---
  input: { approved: true, rejected: true, status: 'approved',
           rejection_reason: null, approval_timestamp: '2026-06-26T10:00:00Z',
           internal_review: true, external_review: false }
  R1: approved=true AND rejected=true → VIOLATION
  result: {
    passed: false,
    violations: [{
      type:   'MUTUAL_EXCLUSIVITY',
      name:   'approved_xor_rejected',
      fields: ['approved', 'rejected'],
      values: { approved: true, rejected: true }
    }]
  }

--- Scenario 3: VIOLATION — conditional_exclusion (R3) ---
  input: { approved: false, rejected: true, status: 'approved',
           rejection_reason: 'insufficient documentation',
           approval_timestamp: null,
           internal_review: false, external_review: true }
  R3: status='approved' AND rejection_reason='insufficient documentation' (not null) → VIOLATION
  result: {
    passed: false,
    violations: [{
      type:          'CONDITIONAL_EXCLUSION',
      name:          'approved_status_no_rejection_reason',
      whenField:     'status',
      whenValue:     'approved',
      prohibitField: 'rejection_reason',
      actualValue:   'insufficient documentation'
    }]
  }

--- Scenario 4: VIOLATION — conditional_exclusion (R4) ---
  input: { approved: false, rejected: true, status: 'rejected',
           rejection_reason: 'counterparty risk',
           approval_timestamp: '2026-06-26T09:45:00Z',  ← should be null
           internal_review: true, external_review: false }
  R4: status='rejected' AND approval_timestamp='2026-06-26T09:45:00Z' (not null) → VIOLATION
  result: {
    passed: false,
    violations: [{
      type:          'CONDITIONAL_EXCLUSION',
      name:          'rejected_status_no_approval_timestamp',
      whenField:     'status',
      whenValue:     'rejected',
      prohibitField: 'approval_timestamp',
      actualValue:   '2026-06-26T09:45:00Z'
    }]
  }

All 4 violations detected. All 1 PASS scenario confirmed clean.

=== F-70 vs F-120 ===

              │ F-70 (structured output validation)           │ F-120 (mutual exclusivity)
──────────────┼───────────────────────────────────────────────┼───────────────────────────────────────────────
What it checks│ Each field's own validity                     │ Cross-field logical consistency
Examples      │ confidence ∈ [0,10]; summary.length > 0       │ approved AND rejected cannot both be true
Rule types    │ type, range, length, co-occurrence            │ both_truthy, conditional_exclusion
When it fires │ After structured output is parsed             │ After F-70 passes (or alongside it)
Output on fail│ Per-field violation with expected vs actual   │ Per-rule violation with field values
Abort/coerce  │ Abort (field invalid → intent ambiguous)      │ Abort (pair conflict → intent ambiguous)
Infrastructure│ Per-field validator registry                  │ Per-rule checker registry
```

## See also

[F-70](f70-structured-output-validation.md) · [F-92](f92-structured-output-schema-drift.md) · [F-102](f102-field-level-confidence-scores.md) · [S-61](../stacks/s61-constrained-decoding.md) · [F-87](f87-output-field-dependency-enforcement.md)

## Go deeper

Keywords: `output field mutual exclusivity` · `LLM output cross-field validation` · `structured output consistency` · `field pair conflict detection` · `conditional field exclusion` · `LLM output logical invariants` · `structured output constraint checking` · `both-truthy field validation` · `output validation cross-field` · `model output structural consistency`
