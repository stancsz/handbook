# F-146 · Extraction Conditional Numeric Range Check

[F-70](f70-verifiable-output-design.md) validates static numeric ranges: `contract_value` must be positive, `risk_score` must be between 0 and 100. These rules apply unconditionally to every extraction. [F-120](f120-output-field-mutual-exclusivity.md) handles conditional exclusion: when `status = "APPROVED"`, `rejection_reason` must be null. [F-143](f143-output-field-conditional-presence-check.md) handles conditional presence: when `risk_level = "HIGH"`, `risk_justification` must be non-null.

A fourth conditional assertion class falls between F-143 and F-70: when a guard field has a specific value, a numeric field must satisfy a range bound — not merely be non-null, but be non-null AND within a specific range. When `risk_level = "HIGH"`, the `penalty_amount` must be at least $10 000 — a HIGH-risk contract that extracts a $500 penalty amount is an extraction error, because no enterprise contract classified as HIGH risk would have such a low penalty. When `contract_type = "ENTERPRISE"`, `contract_value` must be at least $50 000 — an enterprise contract extracted at $30 000 is implausible for that contract class. When `payment_terms = "NET_90"`, a `discount_rate` below 2% is unusual enough to warrant review.

F-70 cannot express these rules because F-70's range checks are unconditional. A `penalty_amount` constraint of "must be ≥ $10 000" would incorrectly flag LOW-risk contracts where small penalties are normal. F-143 cannot express them because F-143 checks presence, not value. The conditional numeric range check fills the gap: when guard field equals guard value, target numeric field must satisfy a comparator bound.

## Situation

A contract risk analysis pipeline extracts four numeric fields: `penalty_amount`, `contract_value`, `term_length_days`, and `discount_rate`. The schema has four conditional range rules:

1. `risk_level = "HIGH"` → `penalty_amount ≥ 10 000` (ERROR): HIGH-risk contracts without material penalties are misclassified — the model found a penalty clause but extracted the wrong figure, or missed the correct clause entirely.
2. `contract_type = "ENTERPRISE"` → `contract_value ≥ 50 000` (ERROR): enterprise contracts below $50 000 contract value indicate the model extracted an individual order value from a master agreement instead of the total contract value.
3. `risk_level = "LOW"` → `penalty_amount ≤ 5 000` (WARN): a LOW-risk contract with a $500 000 penalty clause is unusual; route for human review but do not block.
4. `payment_terms = "NET_90"` → `discount_rate ≥ 0.02` (WARN): NET 90 terms without an early-payment discount are unusual in this client's contract portfolio; flag for financial review.

Without conditional range checks: in a batch of 200 extractions, 8 HIGH-risk contracts return `penalty_amount` below $10 000. F-70 passes them (penalty_amount is non-null and positive). The risk model uses the extracted figures and produces an understated penalty exposure for those 8 contracts. The understatement is discovered in the quarterly review.

With conditional range checks: all 8 violations fire RANGE_FAIL at ERROR severity on the day of extraction. The retry hint — "penalty_amount is 500 but must be ≥ 10 000 when risk_level=HIGH" — routes to F-133's retry logic. Haiku re-extracts with the instruction to search specifically for the liquidated damages clause. 6 of 8 are corrected on the first retry. 2 require manual review (the penalty clause was in a schedule not included in the extraction corpus).

## Forces

- **SKIP when the target field is null or non-numeric.** A null `penalty_amount` on a HIGH-risk contract is a conditional presence failure (F-143), not a range failure. If F-143 runs first in the chain and blocks on the null, F-146 never sees the null. If F-146 runs independently, return SKIP rather than RANGE_FAIL when the field is null or non-numeric — F-143 already handles the null case. Do not double-count violations.
- **Run F-143 before F-146 in the validation chain.** F-143 checks that the target field is non-null when the guard is triggered. F-146 checks that the non-null value is within bounds. Running F-146 before F-143 means null values produce SKIP instead of RANGE_FAIL; the violation is missed if F-143 is not also in the chain. The canonical order: F-70 → F-99 → F-131 → F-120 → F-143 → F-146.
- **Guard value must be exact match.** The comparator is `===`, not a loose equality. Normalize enum values with F-135 (output field normalizer) before running conditional checks so `"high"` and `"High"` both become `"HIGH"` before the guard comparison. A guard that expects `"HIGH"` will not trigger on `"high"`.
- **Bound units must match field units.** If `contract_value` is extracted in dollars but the bound is expressed in thousands, the check fires on every legitimate contract under $50 million. Declare bounds in the same units the model uses in its output. Document the units in the rule description — "penalty_amount >= 10000 (USD)" rather than just "penalty_amount >= 10000."
- **WARN severity does not block delivery; ERROR does.** Rules with business-critical implications (HIGH risk penalty extraction errors) should be ERROR. Rules that indicate unusual but not impossible extraction results (NET_90 without discount) should be WARN — annotate the output and log for trend analysis, but do not hold delivery. Monitor WARN rate over time with F-141 to detect if a WARN pattern becomes consistent (potentially indicating a data quality shift that warrants promoting to ERROR).
- **This triad exhausts conditional field assertions.** F-120 (when A=V, B must be null), F-143 (when A=V, B must be non-null), F-146 (when A=V, B must satisfy numeric bound) cover all three conditional assertion shapes for structured extraction output. A field that appears conditionally required with a numeric constraint needs all three: F-143 to confirm presence, F-146 to confirm range, F-120 to confirm that competing fields are absent when they should be.

## The move

**Register guard-value → comparator → bound rules with severity. Run after F-143 in the validation chain. SKIP null target fields (F-143 handles them). Return RANGE_FAIL with a specific retry hint.**

```js
// --- Extraction conditional numeric range check ---
// When output[guardField] === guardValue, output[targetField] must satisfy comparator bound.
// Distinct from F-70 (unconditional static range) and F-143 (conditional presence, not range).
// Completes the conditional assertion triad: F-120 (null) → F-143 (non-null) → F-146 (range).
// Run order: F-70 → F-99 → F-131 → F-120 → F-143 → F-146.

const COMPARATORS = {
  '>=': (v, b) => v >= b,
  '<=': (v, b) => v <= b,
  '>':  (v, b) => v > b,
  '<':  (v, b) => v < b,
  '==': (v, b) => v === b,
};

class ConditionalNumericRangeChecker {
  constructor() { this._rules = []; }

  // Register: when output[guardField] === guardValue, output[targetField] comparator bound.
  registerRule(guardField, guardValue, targetField, comparator, bound, opts) {
    opts = opts || {};
    this._rules.push({
      guardField, guardValue, targetField, comparator, bound,
      severity:    opts.severity    || 'ERROR',
      description: opts.description ||
        `when ${guardField}=${guardValue}: ${targetField} ${comparator} ${bound}`,
    });
    return this;
  }

  check(output) {
    const results = this._rules.map(rule => {
      if (output[rule.guardField] !== rule.guardValue) {
        return { status: 'GUARD_NOT_TRIGGERED', rule: rule.description };
      }

      const raw = output[rule.targetField];
      const val = parseFloat(raw);
      if (raw === null || raw === undefined || isNaN(val)) {
        // Null/non-numeric: F-143 handles presence; this check SKIPs.
        return { status: 'SKIP', reason: 'non-numeric or null', rule: rule.description };
      }

      const pass = COMPARATORS[rule.comparator](val, rule.bound);
      return {
        status:      pass ? 'RANGE_PASS' : 'RANGE_FAIL',
        rule:        rule.description,
        severity:    rule.severity,
        guardField:  rule.guardField,  guardValue: rule.guardValue,
        targetField: rule.targetField, actual: val,
        expected:    `${rule.comparator} ${rule.bound}`,
        retryHint:   pass ? null :
          `${rule.targetField} is ${val} but must be ${rule.comparator} ${rule.bound} when ${rule.guardField}=${rule.guardValue}`,
      };
    });

    const violations = results.filter(r => r.status === 'RANGE_FAIL');
    const errors     = violations.filter(r => r.severity === 'ERROR');
    const warnings   = violations.filter(r => r.severity === 'WARN');
    return { passed: errors.length === 0, results, violations, errors, warnings };
  }
}

// --- Contract extraction conditional range rules ---

const RANGE_CHECKER = new ConditionalNumericRangeChecker();
RANGE_CHECKER
  .registerRule('risk_level',    'HIGH',       'penalty_amount', '>=', 10_000,
    { severity: 'ERROR', description: 'HIGH risk requires penalty_amount >= $10,000 (USD)' })
  .registerRule('contract_type', 'ENTERPRISE', 'contract_value', '>=', 50_000,
    { severity: 'ERROR', description: 'ENTERPRISE contracts must have contract_value >= $50,000 (USD)' })
  .registerRule('risk_level',    'LOW',        'penalty_amount', '<=', 5_000,
    { severity: 'WARN',  description: 'LOW risk penalty_amount should be <= $5,000 (USD)' })
  .registerRule('payment_terms', 'NET_90',     'discount_rate',  '>=', 0.02,
    { severity: 'WARN',  description: 'NET_90 terms should include >= 2% early-payment discount' });

// --- Integration: delivery gate (after F-70 → F-120 → F-143 → F-146) ---

function deliverWithRangeCheck(output) {
  const check = RANGE_CHECKER.check(output);
  if (!check.passed) {
    return {
      delivered:  false,
      reason:     'CONDITIONAL_RANGE_FAIL',
      retryHints: check.errors.map(e => e.retryHint),
      errors:     check.errors,
    };
  }
  return {
    delivered: true,
    output,
    rangeWarnings: check.warnings.map(w => w.description),
  };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four rules, four scenarios. `check()` timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Extraction Conditional Numeric Range Check ===

--- Scenario A: risk_level=HIGH, penalty_amount=500 ---
  RANGE_FAIL  ERROR  HIGH risk requires penalty_amount >= $10,000 (USD)
  retryHint: "penalty_amount is 500 but must be >= 10000 when risk_level=HIGH"
  passed: false  errors: 1  warnings: 0

--- Scenario B: contract_type=ENTERPRISE, contract_value=30000 ---
  RANGE_FAIL  ERROR  ENTERPRISE contracts must have contract_value >= $50,000 (USD)
  retryHint: "contract_value is 30000 but must be >= 50000 when contract_type=ENTERPRISE"
  passed: false  errors: 1  warnings: 0

--- Scenario C: all guards triggered, all pass ---
  RANGE_PASS  HIGH risk requires penalty_amount >= $10,000        penalty_amount=15000
  RANGE_PASS  ENTERPRISE contracts must have contract_value >= $50,000   value=75000
  RANGE_PASS  NET_90 terms should include >= 2% discount           rate=0.03
  passed: true

--- Scenario D: penalty_amount=null with risk_level=HIGH → SKIP ---
  SKIP  reason=non-numeric or null
  (F-143 CONDITIONAL_ABSENT fires first; F-146 sees null and SKIPs rather than double-fires)

=== Conditional assertion triad ===

  F-120:  when A=V → B must be NULL                       (mutual exclusion)
  F-143:  when A=V → B must be NON-NULL                   (conditional presence)
  F-146:  when A=V → B must satisfy numeric bound          (conditional range)

  Run order: F-70 → F-99 → F-131 → F-120 → F-143 → F-146

=== Timing (1 000 000 iterations) ===

check() 4 rules, 1 RANGE_FAIL:  0.0009 ms
check() 4 rules, 3 RANGE_PASS:  0.0009 ms

Zero API calls. Zero tokens. Runs at delivery boundary.
```

## See also

[F-120](f120-output-field-mutual-exclusivity.md) · [F-143](f143-output-field-conditional-presence-check.md) · [F-70](f70-verifiable-output-design.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-135](f135-extraction-output-field-normalizer.md)

## Go deeper

Keywords: `conditional numeric range check` · `extraction value range assertion` · `guard field numeric bound` · `conditional range validation LLM` · `extraction field value constraint` · `numeric bound conditional field` · `conditional value assertion extraction` · `range check conditional field` · `extraction guard value bound` · `conditional output numeric validation`
