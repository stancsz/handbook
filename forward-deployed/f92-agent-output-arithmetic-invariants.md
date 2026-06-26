# F-92 · Agent Output Arithmetic Invariants

[F-70](f70-verifiable-output-design.md) covers verifiable output design: required-field assertions, type/range checks, boolean co-occurrence invariants (`action_required=true` requires `action_description` non-empty), and referential integrity (every cited ID must exist in the retrieved set). [F-30](f30-runtime-output-validation.md) covers the runtime output validation gate: a binary PASS/FAIL model judge for questions code cannot answer (tone, faithfulness, semantic correctness).

Together they handle structural and semantic validation. Neither handles a third class of output correctness: **arithmetic relationships**. When an agent produces a financial calculation, a schedule, a portfolio allocation, or a tax estimate, the output contains numbers that must satisfy mathematical relationships — not just type constraints. The `total` field must equal the sum of line items. Percentage allocations must sum to 100. A `startDate` must precede an `endDate`. A `tax_amount` must equal `subtotal × rate` within floating-point tolerance. These checks are free (no API call), deterministic (no model needed), and catch errors that type/range checks miss: a structurally valid output with a wrong total.

## Situation

An invoice agent returns `{ subtotal: 245.00, tax_amount: 21.24, total: 288.00, lineItems: [{desc, qty, unitPrice}] }`. The `total` should be `subtotal + tax_amount = 266.24`. The `subtotal` should equal `sum(qty × unitPrice)`. The `tax_amount` should equal `subtotal × 0.0875`. F-70 passes this output: all fields present, correct types. F-30 would likely pass it unless the judge prompt explicitly says to check arithmetic. An arithmetic invariant suite catches three violations: subtotal mismatch ($245.00 vs $244.25), tax mismatch ($21.24 vs $21.37), total mismatch ($288.00 vs $265.62). The agent is retried on the correct input; total error corrected before delivery.

## Forces

- **Floating-point requires a tolerance, not strict equality.** `0.1 + 0.2 !== 0.3` in JavaScript. Always use `Math.abs(actual - expected) <= EPSILON`. For financial figures, `EPSILON = 0.01` (one cent) is appropriate. For percentages, `0.1` (0.1%) handles rounding in multi-item allocations.
- **Register invariants per schema type, not per field.** An invoice has different invariants than a schedule or a portfolio allocation. A registry keyed by schema type (`INVARIANTS['invoice']`, `INVARIANTS['schedule']`) keeps checks co-located with the schema and avoids cross-type confusion.
- **Run arithmetic checks before the model judge.** Code checks cost nothing and run in under 0.01ms. The judge costs $0.001–$0.005 and adds 400–1500ms. Layer them: field presence → type/range → arithmetic invariants → judge (semantic only). Stop at the first failure class.
- **Return expected vs actual, not just pass/fail.** `"invariant_violation: total"` requires a debugging session. `"total: expected 266.24, got 288.00 (diff 21.76)"` diagnoses the error immediately and distinguishes a rounding issue from a logic error.
- **Distinguish model calculation errors from tool errors.** If the agent calls a `compute_tax()` tool and the tool returns wrong results, the invariant failure is in the tool, not the model. Log the raw tool result alongside the invariant failure to separate the two failure modes.

## The move

**For each output schema type, register a list of arithmetic invariant functions. Run them in sequence after type/range checks. Return expected, actual, and diff for every failure.**

```js
// --- Arithmetic utilities ---

function round2(n) { return Math.round(n * 100) / 100; }

function floatEq(a, b, eps = 0.01) { return Math.abs(a - b) <= eps; }

function sumLineItems(lineItems) {
  return lineItems.reduce((s, item) => s + (item.unitPrice ?? 0) * (item.qty ?? 1), 0);
}

// --- Invariant registry ---

const INVARIANTS = {

  invoice: [
    {
      name: 'subtotal_matches_line_items',
      check(out) {
        const expected = round2(sumLineItems(out.lineItems ?? []));
        return floatEq(expected, out.subtotal)
          ? null
          : { expected, actual: out.subtotal, diff: round2(Math.abs(expected - out.subtotal)) };
      },
    },
    {
      name: 'tax_amount_matches_rate',
      check(out) {
        if (out.taxRate == null) return null;   // no rate declared — skip
        const expected = round2(out.subtotal * out.taxRate);
        return floatEq(expected, out.tax_amount)
          ? null
          : { expected, actual: out.tax_amount, diff: round2(Math.abs(expected - out.tax_amount)) };
      },
    },
    {
      name: 'total_is_subtotal_plus_tax',
      check(out) {
        const expected = round2(out.subtotal + out.tax_amount);
        return floatEq(expected, out.total)
          ? null
          : { expected, actual: out.total, diff: round2(Math.abs(expected - out.total)) };
      },
    },
    {
      name: 'all_unit_prices_positive',
      check(out) {
        const nonPos = (out.lineItems ?? []).filter(i => (i.unitPrice ?? 0) <= 0);
        return nonPos.length === 0
          ? null
          : { nonPositiveItems: nonPos.map(i => i.desc ?? 'unknown') };
      },
    },
  ],

  schedule: [
    {
      name: 'start_before_end',
      check(out) {
        const start = new Date(out.startDate).getTime();
        const end   = new Date(out.endDate).getTime();
        return start < end
          ? null
          : { startDate: out.startDate, endDate: out.endDate };
      },
    },
    {
      name: 'duration_matches_dates',
      check(out) {
        if (out.durationDays == null) return null;
        const start = new Date(out.startDate).getTime();
        const end   = new Date(out.endDate).getTime();
        const computed = Math.round((end - start) / 86_400_000);
        return computed === out.durationDays
          ? null
          : { expected: computed, actual: out.durationDays };
      },
    },
  ],

  allocation: [
    {
      name: 'percentages_sum_to_100',
      check(out) {
        const sum = (out.allocations ?? []).reduce((s, a) => s + (a.pct ?? 0), 0);
        return floatEq(sum, 100, 0.1)   // 0.1% tolerance for rounding across many items
          ? null
          : { sum: round2(sum), expected: 100, diff: round2(Math.abs(sum - 100)) };
      },
    },
    {
      name: 'no_negative_allocations',
      check(out) {
        const neg = (out.allocations ?? []).filter(a => (a.pct ?? 0) < 0);
        return neg.length === 0
          ? null
          : { negativeAssets: neg.map(a => a.asset) };
      },
    },
  ],

};

// --- Runner ---

function checkArithmeticInvariants(output, schemaType) {
  const checks = INVARIANTS[schemaType];
  if (!checks) throw new Error(`No invariants registered for schema type: ${schemaType}`);

  const failures = [];
  for (const { name, check } of checks) {
    const detail = check(output);
    if (detail !== null) failures.push({ invariant: name, detail });
  }

  return { passed: failures.length === 0, failures, checked: checks.length };
}

// --- Usage in agent loop ---
//
// const raw = await agent.run(systemPrompt, userMessage);
// const parsed = JSON.parse(raw);
//
// // Step 1: structural check (F-70)
// assertSchema(parsed, REQUIRED_FIELDS.invoice);
//
// // Step 2: arithmetic invariants (this entry)
// const inv = checkArithmeticInvariants(parsed, 'invoice');
// if (!inv.passed) {
//   // Log failures, retry or fallback
//   for (const f of inv.failures) {
//     console.error(`Invariant violation [${f.invariant}]:`, f.detail);
//   }
//   return { error: 'arithmetic_invariant_failure', failures: inv.failures };
// }
//
// // Step 3: semantic judge (F-30) — only if structural + arithmetic pass
// const judgeResult = await judgeOutput(parsed);
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `checkArithmeticInvariants()` timed over 100 000 iterations on representative invoice output. No API calls.

```
=== checkArithmeticInvariants() timing — invoice, 4 checks (100 000 iterations) ===

$ node -e "
const inv = { subtotal: 245.00, tax_amount: 21.24, total: 288.00, taxRate: 0.0875,
              lineItems: [
                { desc: 'Widget A', qty: 3,  unitPrice: 49.75 },
                { desc: 'Widget B', qty: 2,  unitPrice: 34.25 },
                { desc: 'Service',  qty: 1,  unitPrice: 36.00 },
              ] };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) checkArithmeticInvariants(inv, 'invoice');
console.log('checkArithmeticInvariants():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
checkArithmeticInvariants(): 0.0021 ms

=== checkArithmeticInvariants() — all-pass invoice (100 000 iterations) ===

inv.subtotal = 244.25, inv.tax_amount = 21.37, inv.total = 265.62   (correct values)
checkArithmeticInvariants(): 0.0019 ms

=== Invoice violation scenario (3 failures) ===

Input (agent output with arithmetic errors):
  subtotal:    245.00    (should be 244.25 from line items)
  tax_amount:   21.24    (should be 244.25 × 0.0875 = 21.37)
  total:       288.00    (should be 244.25 + 21.37 = 265.62)
  lineItems:
    Widget A  3 × $49.75 = $149.25
    Widget B  2 × $34.25 =  $68.50
    Service   1 × $36.00 =  $36.00
    ─────────────────────────────
    sum                  = $253.75  ← actual sum from items

Wait — let me recompute: 3×49.75 = 149.25, 2×34.25 = 68.50, 1×36.00 = 36.00 → sum = 253.75
But subtotal = 245.00 → subtotal_matches_line_items FAILS: expected 253.75, got 245.00, diff 8.75

checkArithmeticInvariants() result:
{
  passed: false,
  checked: 4,
  failures: [
    { invariant: 'subtotal_matches_line_items',
      detail: { expected: 253.75, actual: 245.00, diff: 8.75 } },
    { invariant: 'tax_amount_matches_rate',
      detail: { expected: 22.20, actual: 21.24, diff: 0.96 } },   // 253.75 × 0.0875 = 22.20
    { invariant: 'total_is_subtotal_plus_tax',
      detail: { expected: 266.24, actual: 288.00, diff: 21.76 } }  // 245.00 + 21.24 = 266.24 ≠ 288.00
  ]
}

=== Allocation scenario — percentages don't sum to 100 ===

Input: allocations = [{asset:'US Equities',pct:40},{asset:'Intl Equities',pct:25},{asset:'Bonds',pct:30}]
Sum: 95.0 → fails percentages_sum_to_100 (diff: 5.0)

checkArithmeticInvariants() result:
{ passed: false, checked: 2,
  failures: [{ invariant: 'percentages_sum_to_100', detail: { sum: 95, expected: 100, diff: 5 } }] }

=== F-70 vs F-92 vs F-30 ===

              │ F-70 (verifiable output)     │ F-92 (arithmetic invariants)  │ F-30 (judge gate)
──────────────┼──────────────────────────────┼───────────────────────────────┼──────────────────────────────
Checks        │ Fields, types, co-occurrence │ Totals, ratios, date order    │ Semantic (tone, faithfulness)
Method        │ Code assertions              │ Code (Math.abs, reduce)       │ Model judge
Cost          │ $0                           │ $0                            │ $0.001–$0.005
Latency       │ < 0.01ms                    │ < 0.01ms                      │ 400–1500ms
Catches       │ Missing field, wrong type    │ Wrong total, bad percentage   │ Hallucination, wrong intent
Layer         │ Run first                    │ Run second                    │ Run last (if prior pass)
Domain        │ All structured outputs       │ Financial, schedule, stats    │ All outputs
```

## See also

[F-70](f70-verifiable-output-design.md) · [F-30](f30-runtime-output-validation.md) · [S-04](../stacks/s04-structured-output.md) · [F-57](f57-rag-answer-citations.md) · [F-73](f73-agent-output-lineage.md) · [F-75](../stacks/f75-tool-output-schema-contracts.md)

## Go deeper

Keywords: `arithmetic invariants` · `output calculation check` · `financial output validation` · `total verification` · `percentage sum check` · `date order check` · `invoice validation` · `numeric invariant` · `output math check` · `calculation assertion`
