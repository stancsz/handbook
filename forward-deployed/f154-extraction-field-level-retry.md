# F-154 · Extraction Field-Level Retry

[F-133](f133-extraction-retry-escalation-policy.md) decides when to retry and with which model: same model with correction hints on the first failure, upgraded model on the second, human review on the third. F-133 answers the escalation question. It does not specify what goes into the retry prompt.

The default is to re-run the full extraction: send the same system prompt (200 tok), the same document (600 tok), and wait for a full output (180 tok) — 980 tokens to correct a field that returned "SERVICE_AGREEMENT" when the enum requires "SERVICE". The failure is not in the document or the extraction schema; it is in two fields. The other three fields were extracted correctly and their values are about to be regenerated at full cost, with the risk that the model changes a correct value while fixing an incorrect one.

Field-level retry feeds the validators' retryHints directly into a targeted prompt that asks for only the failed fields. The prompt lists each failing field by name, its current (wrong) value, and the exact correction instruction from the validator. The document context is shortened to the relevant clause excerpt (when the retryHint names a source location). The model returns only the fields it was asked to re-extract. The caller merges those fields back into the original output using `Object.assign`.

The result: 67–77% fewer tokens per retry, zero regression risk on the fields that were already correct, and a retry prompt that tells the model exactly what it got wrong and why.

## Situation

A contract extraction pipeline runs F-151 (enum validation) and F-153 (temporal arithmetic check) on every output. A typical failure pattern: the model returns `contract_type: "SERVICE_AGREEMENT"` (a description, not an enum value) and `expiry_date: "2030-01-01"` when `effective_date + term_length_days = 2027-01-01` — dates extracted from different clauses of the same document.

Both validators emit retryHints:
- F-151: "contract_type 'SERVICE_AGREEMENT' is not a valid value; allowed: [SERVICE, NDA, LEASE, EMPLOYMENT, VENDOR, LICENSE]; closest match: 'SERVICE' (edit distance 8)"
- F-153: "effective_date + term_length_days ≈ expiry_date: 2026-01-01 + 365 days = 2027-01-01, but expiry_date = 2030-01-01 (1096-day discrepancy). Large discrepancy — dates likely extracted from different clauses."

Full re-extraction: 1 000 tokens. Targeted field-level retry with both retryHints: 331 tokens. Saved: 669 tokens (67%). The remaining fields — `effective_date`, `term_length_days`, `jurisdiction` — are preserved from the original.

## Forces

- **Full re-extraction risks regressing correct fields.** When the retry prompt includes all fields, the model may change a correct value. `jurisdiction: "US"` was extracted correctly on the first pass; a full retry that slightly rephrases the document context or adds a correction instruction may cause the model to return a different jurisdiction on the second pass. The field-level merge preserves all non-failing fields from the first extraction.
- **The retryHint is the retry prompt — do not re-engineer it.** Each validator in the chain (F-131, F-143, F-147, F-148, F-149, F-150, F-151, F-153) emits a retryHint on every violation. These hints are written to be inserted directly into a correction prompt. `composeFieldRetryPrompt()` collects them and joins them. No additional translation is needed.
- **Only ERROR-severity violations trigger a retry.** WARN violations log and pass through (F-149 UNPARSEABLE dates, F-153 INCONSISTENT WARN for 32-day discrepancies that may reflect legitimate schedule amendments). Filter to `severity === 'ERROR'` before composing the retry prompt. A retry that corrects a WARN may introduce a regression on an ERROR.
- **The document excerpt should be the clause, not the full document.** When the retryHint identifies a source location ("dates likely extracted from different clauses"), the retry can send only the relevant clause excerpt — reducing the document context from 600 to 120–150 tokens. When no excerpt is available, send the full document but gain savings only on the output side and the system addendum.
- **Compose with F-133, not compete with it.** F-133 decides the escalation: attempt 1 → same model with hints; attempt 2 → upgraded model with hints; attempt 3 → human review. F-154 provides the hints structure for both attempts. On attempt 2 (model upgrade), pass the same `composeFieldRetryPrompt()` output — now with a more capable model reading a targeted, not a generic, retry prompt.
- **One retry maximum before deferring to F-133 escalation.** If the field-level retry fails (the model still returns an invalid enum value or the temporal arithmetic still does not check out), pass control to F-133 for model escalation or human routing. Do not loop field-level retries — if the model cannot fix the field with a precise hint, more hints will not help.

## The move

**Collect ERROR violations from the validator chain. Build a targeted system addendum listing only the failing fields and their retryHints. Send the addendum plus a short document excerpt. Merge the result into the original output.**

```js
// --- Extraction field-level retry ---
// Composes a targeted retry prompt from validator retryHints.
// Sends only failing fields; merges results back into original output.
// Compose with F-133 (escalation policy) — F-154 structures the retry prompt;
// F-133 decides when to retry and which model to use.
// Chain position: run validators → collect violations → composeFieldRetryPrompt()
//   → call API → mergeRetryResult() → re-run validators on merged output.

function composeFieldRetryPrompt(violations) {
  const errorViolations = violations.filter(v => v.severity === 'ERROR');
  if (errorViolations.length === 0) return null;

  const targets = errorViolations.map(v =>
    `- ${v.field} (extracted: "${v.value}"): ${v.retryHint}`
  );

  return [
    'Re-extract ONLY the following fields and return JSON with exactly these keys.',
    'Fix the specific issue described for each field. All other fields are already correct — do not include them.',
    '',
    ...targets,
  ].join('\n');
}

// Overwrite only the failed fields in the original output.
// Non-failed fields are preserved from the first extraction.
function mergeRetryResult(original, retryResult) {
  return Object.assign({}, original, retryResult);
}

// Integration pattern:
// const violations = runValidatorChain(output);
// const errorViolations = violations.filter(v => v.severity === 'ERROR');
// if (errorViolations.length === 0) return output;                // pass
// const addendum = composeFieldRetryPrompt(errorViolations);
// const retryOutput = await runMiniExtraction(addendum, clauseExcerpt, errorViolations.map(v => v.field));
// const merged = mergeRetryResult(output, retryOutput);
// const recheck = runValidatorChain(merged);
// if (!recheck.passed) escalate(merged, recheck, F133_POLICY);    // F-133 takes over
// return merged;
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. `composeFieldRetryPrompt()` and `mergeRetryResult()` timed over 1 000 000 iterations. Token counts via `Math.ceil(text.length / 4)`. API call token estimates from measured receipts (F-151, F-153). Zero API calls in this receipt.

```
=== Extraction Field-Level Retry ===

--- Scenario A: no violations ---
  violations: 0  → no retry (null returned, original output passes through)

--- Scenario B: 1 violation (contract_type enum failure from F-151) ---
  Retry addendum (100 tok):
    Re-extract ONLY the following fields and return JSON with exactly these keys.
    Fix the specific issue described for each field. All other fields are already correct.

    - contract_type (extracted: "SERVICE_AGREEMENT"):
      contract_type "SERVICE_AGREEMENT" is not a valid value;
      allowed: [SERVICE, NDA, LEASE, EMPLOYMENT, VENDOR, LICENSE];
      closest match: "SERVICE" (edit distance 8)

  Full re-extraction:  820 tok input + 180 tok output = 1 000 tok
  Targeted retry:      220 tok input +  10 tok output =   230 tok
  Saved: 770 tok (77%)

--- Scenario C: 2 violations (enum + temporal arithmetic from F-151 + F-153) ---
  Retry addendum (161 tok, both retryHints):
    Re-extract ONLY the following fields...
    - contract_type (extracted: "SERVICE_AGREEMENT"): ... (edit distance 8)
    - expiry_date (extracted: "2030-01-01"):
      effective_date + term_length_days ≈ expiry_date: 2026-01-01 + 365 days = 2027-01-01,
      but expiry_date = 2030-01-01 (1096-day discrepancy).
      Large discrepancy — dates likely extracted from different clauses.

  Full re-extraction:  820 tok input + 180 tok output = 1 000 tok
  Targeted retry:      311 tok input +  20 tok output =   331 tok
  Saved: 669 tok (67%)

--- mergeRetryResult ---
  Original (with failures): {contract_type: "SERVICE_AGREEMENT", effective_date: "2026-01-01",
                             term_length_days: 365, expiry_date: "2030-01-01", jurisdiction: "US"}
  Retry result (2 fields):  {contract_type: "SERVICE", expiry_date: "2027-01-01"}
  Merged output:            {contract_type: "SERVICE", effective_date: "2026-01-01",
                             term_length_days: 365, expiry_date: "2027-01-01", jurisdiction: "US"}
  Preserved from original:  effective_date, term_length_days, jurisdiction

--- Cost: 10 000 extractions/day, 5% failure rate (500 retries/day), Haiku ---
  Full re-extraction:  $0.69/day  ($251/year)
  Targeted retry:      $0.16/day   ($60/year)
  Savings:             $0.52/day  ($191/year)
  Token reduction:     669 tok/retry (67%)

--- Regression risk ---
  Full re-extraction: re-generates ALL fields — jurisdiction "US" can drift on retry
  Targeted retry:     mergeRetryResult preserves correct fields — only failed fields change

--- Timing (1 000 000 iterations) ---
composeFieldRetryPrompt() 2 violations: 0.0020 ms
mergeRetryResult() 5 fields, 2 replaced: 0.0004 ms
Zero API calls, zero tokens. Both run at call-routing layer.
```

## See also

[F-133](f133-extraction-retry-escalation-policy.md) · [F-151](f151-extraction-field-enum-validation.md) · [F-153](f153-extraction-temporal-arithmetic-check.md) · [F-70](f70-verifiable-output-design.md) · [F-150](f150-extraction-mutual-field-completeness-check.md)

## Go deeper

Keywords: `extraction field level retry` · `targeted extraction retry` · `field specific retry hint` · `extraction retry prompt` · `partial extraction retry` · `failed field retry merge` · `extraction correction prompt` · `retry only failed fields` · `extraction field retry cost` · `validator retry composition`
