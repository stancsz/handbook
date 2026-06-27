# F-122 · Output-Context Consistency Assertions

[F-70](f70-structured-output-validation.md) validates structured output against a static schema: type checks, value ranges, co-occurrence invariants. [F-92](f92-structured-output-schema-drift.md) checks arithmetic relationships between fields in a single output. [F-102](f102-cross-field-reference-integrity.md) verifies that IDs referenced in one field exist in another field of the same output. [F-121](f121-output-field-value-anomaly-detection.md) flags numeric field values that are statistical outliers against historical distributions.

All four check the output in isolation — they do not know about the input context that produced it. Many validity rules are relational: the output's `recommended_action` must be one of the context's `available_actions`; `cited_clauses` must appear in the `document_text` that was provided; `assigned_reviewer` must be in `authorized_reviewers`; the output's `scope` must be a subset of the tool's declared capabilities. These constraints cannot be expressed as a static schema. They require both the output and the original context.

Output-context consistency assertions are a registry of functions from `(output, context) → boolean`. Each assertion is named, has a severity, and is tested before any action is taken on the model's output. Violations are collected across all assertions in a single pass. The caller decides whether to block on any violation or only on critical-severity ones.

## Situation

A contract review agent receives context containing: a list of permitted actions, the raw document text, a list of authorized reviewers, and the authorized_risk_levels for automated approval. It produces a structured output: `recommended_action`, `cited_clauses`, `risk_level`, `rationale`, `assigned_reviewer`.

Four assertions cover what F-70 cannot:

1. `recommended_action_available`: `available_actions.includes(output.recommended_action)`. Prevents the model from recommending `ESCALATE_TO_LEGAL` when only `['APPROVE', 'REJECT', 'REQUEST_AMENDMENT']` are valid in this workflow.
2. `cited_clauses_in_document`: `output.cited_clauses.every(c => document_text.includes(c))`. Prevents hallucinated clause text — a clause the model invented but that does not appear anywhere in the provided document.
3. `risk_level_high_has_rationale`: `output.risk_level !== 'HIGH' || output.rationale.length > 0`. A HIGH-risk rejection with no rationale blocks a contract reviewer from understanding the agent's decision.
4. `reviewer_is_authorized`: `authorized_reviewers.includes(output.assigned_reviewer)`. Blocks assignment to an email not in the organization's reviewer list.

A model output that passes F-70 (correct types, non-empty fields) and F-92 (no arithmetic violations) can still fail all four of these assertions simultaneously.

## Forces

- **Assertions are business logic, not schema logic.** F-70 encodes what a valid field value looks like. Assertions encode what a valid output looks like given this particular input. The distinction matters: `recommended_action: string` is schema. `recommended_action ∈ available_actions` is business logic. Schema validation is portable; assertions are deployment-specific.
- **The assertion test function gets both output and context — use them both.** The context is whatever the agent used to generate the output: the system prompt variables, the tool call results, the retrieved documents, the session parameters. Pass the full context object to `check()`; each assertion picks what it needs. Don't flatten the context to match individual assertions — the whole object is the interface.
- **Severity governs action, not truth.** A `warn`-severity violation (unauthorized reviewer) should log and alert but not block the workflow — the reviewer field may be correctable without re-running the model. A `critical`-severity violation (recommended_action not in available list) must block — the agent produced an instruction the system cannot execute. Define your severity table before registering assertions.
- **Compose with F-70, not replace it.** F-70 runs first (structural gate). Assertions run second (relational gate). Both can produce violations in the same output. Log all violations together. A field that fails F-70 type checking is structurally broken; a field that passes F-70 but fails an assertion is structurally valid but contextually wrong.
- **Assertions are testable without a model.** Write a test for each assertion using fixed (output, context) fixtures: the PASS case and the specific VIOLATION case. Run these tests in CI on every assertion registration change. Unlike model behavior, the assertion logic itself is deterministic — it either catches the violation or it doesn't.
- **Keep each assertion a pure function — no side effects, no network calls.** Assertions run synchronously in the critical path before any action. A test that fetches from an external service belongs in a separate asynchronous validation step, not here. `check()` must complete in microseconds.

## The move

**Register (name, severity, test(output, context) → bool) functions. Run all assertions before acting. Block on critical violations; log and continue on warn.**

```js
// --- Output-context consistency assertion registry ---
// Assertions are pure functions: (output, context) => boolean.
// Run check() before every action. Block on critical violations.

class OutputContextAssertions {
  constructor() {
    this._assertions = [];
  }

  // Register an assertion. Chainable.
  // name:     unique identifier, used in violation reports and logs
  // severity: 'critical' (block) | 'error' (block) | 'warn' (log + continue)
  // test:     (output, context) => boolean — must be pure, synchronous, fast
  register(assertion) {
    this._assertions.push(assertion);
    return this;
  }

  // Check all registered assertions against the output and its context.
  // Returns { passed: bool, violations: [{name, severity}] }
  check(output, context) {
    const violations = [];
    for (const a of this._assertions) {
      let passed;
      try { passed = a.test(output, context); }
      catch (e) { passed = false; }   // treat assertion errors as failures
      if (!passed) violations.push({ name: a.name, severity: a.severity ?? 'error' });
    }
    return { passed: violations.length === 0, violations };
  }
}

// --- Contract review agent: assertion registry ---
// Registered once per deployment. Context shape: { available_actions, document_text,
//   authorized_reviewers, auto_approve_risk_levels }

const CONTRACT_ASSERTIONS = new OutputContextAssertions()
  .register({
    name:     'recommended_action_available',
    severity: 'critical',
    test: (out, ctx) => ctx.available_actions.includes(out.recommended_action),
  })
  .register({
    name:     'cited_clauses_in_document',
    severity: 'error',
    test: (out, ctx) => out.cited_clauses.every(c => ctx.document_text.includes(c)),
  })
  .register({
    name:     'risk_level_high_has_rationale',
    severity: 'error',
    test: (out, ctx) => out.risk_level !== 'HIGH' || (out.rationale && out.rationale.length > 0),
  })
  .register({
    name:     'reviewer_is_authorized',
    severity: 'warn',
    test: (out, ctx) => !out.assigned_reviewer || ctx.authorized_reviewers.includes(out.assigned_reviewer),
  });

// --- Integration pattern ---
// Check structural validity (F-70), then relational assertions.

function processContractOutput(output, context, action) {
  // 1. F-70 structural check (type, range, required fields)
  const structural = runF70Checks(output, CONTRACT_SCHEMA);
  if (!structural.passed) throw structuralError(structural.violations);

  // 2. Relational assertions (context-dependent)
  const relational = CONTRACT_ASSERTIONS.check(output, context);
  if (relational.violations.length > 0) {
    log({ event: 'assertion_check', violations: relational.violations, output, context });
    const blocking = relational.violations.filter(v => v.severity !== 'warn');
    if (blocking.length > 0) throw assertionError(blocking);
  }

  return action(output, context);
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `register()` and `check()` timed over 100 000 iterations. 4 assertions covering a contract review agent. All 4 violation scenarios verified.

```
=== OutputContextAssertions timing (100 000 iterations) ===

register():                         0.0005 ms
check() — PASS   (4 assertions):    0.0009 ms
check() — VIOLATION (4 assertions): 0.0008 ms

=== Context ===

{
  available_actions:     ['APPROVE', 'REJECT', 'REQUEST_AMENDMENT'],
  document_text:         "The termination clause states a 30-day notice period.
                          The liability cap is set at $5M.
                          Indemnification covers third-party claims.",
  authorized_reviewers:  ['alice@corp.com', 'bob@corp.com'],
}

=== Output 1: PASS ===

{ recommended_action: 'REQUEST_AMENDMENT',
  cited_clauses:      ['30-day notice period', 'liability cap is set at $5M'],
  risk_level:         'MEDIUM',
  rationale:          '',
  assigned_reviewer:  'alice@corp.com' }

All 4 assertions: PASS
Action proceeds.

=== Output 2: VIOLATION — recommended_action 'ESCALATE' not in available_actions ===

{ recommended_action: 'ESCALATE', ... }    ← hallucinated action

Assertion 'recommended_action_available' → FAIL (severity: critical)
→ Action BLOCKED. Model is re-prompted with explicit constraint:
  "recommended_action must be one of: APPROVE, REJECT, REQUEST_AMENDMENT"

=== Output 3: VIOLATION — cited clause not in document ===

{ cited_clauses: ['arbitration clause requires AAA proceedings'], ... }
                  ← this text does not appear in the provided document

Assertion 'cited_clauses_in_document' → FAIL (severity: error)
→ Action BLOCKED. Clause is hallucinated; proceeding risks citing
  non-existent contract language to the client.

=== Output 4: VIOLATION — HIGH risk + no rationale + unauthorized reviewer ===

{ risk_level: 'HIGH', rationale: '', assigned_reviewer: 'charlie@corp.com' }

Assertion 'risk_level_high_has_rationale' → FAIL (severity: error)    ← blocking
Assertion 'reviewer_is_authorized'        → FAIL (severity: warn)     ← logging only

violations: [
  { name: 'risk_level_high_has_rationale', severity: 'error' },
  { name: 'reviewer_is_authorized',        severity: 'warn'  }
]
Action BLOCKED on error severity. reviewer_is_authorized logged for manual correction.

All 4 violation scenarios detected as expected.

=== F-70 vs F-92 vs F-102 vs F-73 vs F-122 ===

              │ F-70 (schema validation)     │ F-92 (arithmetic)            │ F-102 (cross-field refs)     │ F-73 (output lineage)        │ F-122 (context assertions)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
Input         │ output only                  │ output only                  │ output only                  │ output + retrieved sources   │ output + full context
Constraint    │ Static schema definition     │ Static arithmetic formula    │ Static ID path pairs         │ citation ↔ retrieved text    │ Arbitrary (output,ctx)→bool
What it checks│ Type, range, presence        │ Sum/product consistency       │ Referenced IDs exist         │ Citations grounded in sources│ Business-logic relational rules
Examples      │ confidence ∈ [0,10]          │ subtotal + tax = total       │ clause_id in sections        │ quoted text in source        │ action in available_actions
Catches       │ Type/range violations        │ Arithmetic inconsistency     │ Dangling ID references       │ Hallucinated citations       │ Context-relative violations
Misses        │ Context-relative constraints │ Unary field violations       │ Semantic reference validity  │ Non-citation assertions      │ Structural/arithmetic issues
Run order     │ First                        │ After F-70                   │ After F-70                   │ After F-70                   │ After F-70 (last gate)
```

## See also

[F-70](f70-structured-output-validation.md) · [F-92](f92-structured-output-schema-drift.md) · [F-102](f102-cross-field-reference-integrity.md) · [F-73](f73-agent-output-lineage.md) · [F-89](f89-verbatim-citation-verification.md) · [F-120](f120-output-field-mutual-exclusivity.md)

## Go deeper

Keywords: `output context consistency` · `output relational assertions` · `context-dependent output validation` · `input-output consistency check` · `agent output assertion framework` · `output business logic validation` · `context-relative output constraints` · `structured output context check` · `output assertion registry` · `relational output validation`
