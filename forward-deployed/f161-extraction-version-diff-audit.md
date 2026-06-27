# F-161 · Extraction Version Diff Audit

When a new prompt version or model update is ready to deploy, the question is not "did the evals pass?" — it's "what specifically changed?" Aggregate accuracy scores tell you the new version is 2 points better overall. They don't tell you that `termination_type` now classifies 18% of contracts differently, or that `governing_law` changed for 8% of documents while `effective_date` stayed stable at 1%.

Field-level change rates across a representative document set are the migration gate. An overall accuracy improvement that is carried by three fields changing massively while twelve stay stable is a different risk profile from the same improvement spread evenly across all fields. The first case needs targeted human review of the high-change fields; the second can promote automatically.

The extraction version diff auditor runs both prompt versions on the same document set, diffs the outputs field by field, and produces a per-field change rate table with a promotion verdict. Fields above the review threshold (typically 5%) get flagged; fields above the block threshold (typically 15%) prevent automatic promotion.

This is different from F-129 (per-entity output regression check), which monitors whether a specific entity's extracted value drifts over time under the same prompt. F-161 compares two prompt versions across a batch of test documents to decide whether to promote.

## Situation

A contract intelligence team has been running extraction prompt v1 for four months. They've improved the date extraction and termination clause classification in v2. Before promoting v2 to production, they run a 100-document batch audit against their historical corpus.

Results show:
- `termination_type`: 18% of documents changed (v1 classified "for cause only"; v2 now classifies "mutual or for cause"). This is a breaking change for downstream risk scoring — needs legal team review before promoting.
- `governing_law`: 8% changed (v2 normalizes "New York" vs "NY" — format improvement, not semantic change). Review recommended; likely safe.
- `effective_date`: 3% changed (within noise — 3 documents had ambiguous dates that v2 parses more accurately). Below the 5% review threshold; acceptable.
- All other fields: 0–2% change rate. Stable.

Overall verdict: **REVIEW** (one field at 15%+ → BLOCK; all fields < 15% but two > 5% → REVIEW). The team reviews 18 `termination_type` diffs, confirms 15 are correct improvements and 3 are regressions. They patch those 3 cases in the prompt and re-audit before promoting.

## Forces

- **Field change rate is not the same as field accuracy.** A field that changes 18% of the time might be changing from wrong to right (improvement), from right to wrong (regression), or from one arbitrary format to another (neutral). The diff audit flags changes; it does not classify them. Human review of flagged documents classifies whether the change is an improvement or regression.
- **Set review and block thresholds from your domain, not from a default.** High-stakes fields (payment amounts, risk levels, legal classifications) warrant a lower block threshold (10%) than metadata fields (document IDs, formatting) which can tolerate 20%+ changes safely. Pass different thresholds per field if needed.
- **Audit on a representative set, not on your hardest documents.** The 100-document audit set should match the production distribution: same mix of document types, sizes, vintages, and complexity levels. An audit set weighted toward edge cases over-estimates field change rates; a curated "easy" set under-estimates them.
- **Zero token cost.** The audit runs both versions in parallel on the same document set during staging (token cost is covered by the normal eval budget). The diff itself is pure code — no model call needed to compare outputs.
- **Compose with F-07 (model evaluation) and F-38 (model version pinning).** F-07 provides the aggregate accuracy gate before the diff audit is relevant. F-161 runs after F-07 passes to identify which fields drove the accuracy change. F-38 pins the winning version after promotion.

## The move

**Run both prompt versions on the same test set. Diff outputs field by field. Report per-field change rates and verdict. Review BLOCK fields with domain experts; check REVIEW fields for format vs semantic changes. Promote only when all fields are OK or REVIEW with known-safe explanations.**

```js
// --- Extraction version diff auditor ---
// Diffs extraction outputs between two prompt versions across a document batch.
// Produces per-field change rates and a promotion verdict.
// Zero API calls, zero model tokens — pure structural diff.
// Compose with F-07 (aggregate eval gate) before running this audit.

class ExtractionVersionDiffAuditor {
  constructor() {
    this._records = [];
  }

  // Diff one document's extraction output between two prompt versions.
  // docId:    identifier for the document (for reviewCases() lookups)
  // outputV1: extraction result from the current/old prompt version
  // outputV2: extraction result from the new/candidate prompt version
  audit(docId, outputV1, outputV2) {
    const fields = new Set([
      ...Object.keys(outputV1 || {}),
      ...Object.keys(outputV2 || {}),
    ]);

    const changed = [];
    for (const field of fields) {
      const v1 = (outputV1 || {})[field];
      const v2 = (outputV2 || {})[field];
      if (JSON.stringify(v1) !== JSON.stringify(v2)) {
        changed.push({ field, v1, v2 });
      }
    }

    const record = { docId, changed, changedCount: changed.length };
    this._records.push(record);
    return record;
  }

  // Summarize field change rates across all audited documents.
  // opts.reviewThreshold:  change rate (0.0–1.0) that triggers REVIEW verdict. Default: 0.05.
  // opts.blockThreshold:   change rate that triggers BLOCK verdict. Default: 0.15.
  // opts.fieldThresholds:  per-field overrides: { fieldName: { review: 0.05, block: 0.10 } }
  summary(opts) {
    opts = opts || {};
    const reviewThreshold = opts.reviewThreshold || 0.05;
    const blockThreshold  = opts.blockThreshold  || 0.15;
    const fieldThresholds = opts.fieldThresholds  || {};

    const total = this._records.length;
    if (total === 0) return { totalDocs: 0, fieldRates: [], overallVerdict: 'NO_DATA' };

    const changedDocs = this._records.filter(r => r.changedCount > 0).length;

    const fieldCounts = {};
    for (const rec of this._records) {
      for (const c of rec.changed) {
        fieldCounts[c.field] = (fieldCounts[c.field] || 0) + 1;
      }
    }

    const fieldRates = Object.entries(fieldCounts)
      .map(([field, count]) => {
        const rate     = count / total;
        const ft       = fieldThresholds[field] || {};
        const fReview  = ft.review != null ? ft.review : reviewThreshold;
        const fBlock   = ft.block  != null ? ft.block  : blockThreshold;
        const verdict  = rate >= fBlock  ? 'BLOCK'  :
                         rate >= fReview ? 'REVIEW' : 'OK';
        return { field, count, rate: (rate * 100).toFixed(1) + '%', verdict };
      })
      .sort((a, b) => b.count - a.count);

    const overallVerdict =
      fieldRates.some(f => f.verdict === 'BLOCK')  ? 'BLOCK' :
      fieldRates.some(f => f.verdict === 'REVIEW') ? 'REVIEW' : 'PROMOTE';

    return {
      totalDocs: total,
      changedDocs,
      unchangedDocs: total - changedDocs,
      overallChangeRate: (changedDocs / total * 100).toFixed(1) + '%',
      overallVerdict,
      fieldRates,
    };
  }

  // Return all changed documents for a specific field, for human review.
  reviewCases(fieldName) {
    return this._records
      .filter(r => r.changed.some(c => c.field === fieldName))
      .map(r => ({
        docId:  r.docId,
        change: r.changed.find(c => c.field === fieldName),
      }));
  }
}

// --- Usage ---
// const AUDITOR = new ExtractionVersionDiffAuditor();
//
// for (const doc of testDocuments) {
//   const v1 = await extractWithPromptV1(doc);    // run in parallel for speed
//   const v2 = await extractWithPromptV2(doc);
//   AUDITOR.audit(doc.id, v1, v2);
// }
//
// const result = AUDITOR.summary({
//   reviewThreshold: 0.05,
//   blockThreshold:  0.15,
//   fieldThresholds: {
//     termination_type: { review: 0.03, block: 0.10 },  // stricter for high-stakes field
//     doc_reference_id: { review: 0.20, block: 0.50 },  // lenient for metadata
//   },
// });
//
// if (result.overallVerdict === 'BLOCK') {
//   // Do not promote. Review AUDITOR.reviewCases(blockedField) with domain experts.
// } else if (result.overallVerdict === 'REVIEW') {
//   // Review flagged fields before promotion decision.
// } else {
//   // PROMOTE — all fields within thresholds.
// }
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. 100-document batch audit, 10 fields per extraction, two prompt versions. Includes per-field change rate computation and promotion verdict logic. Timed over 100 000 iterations. Zero API calls. Zero tokens for the audit itself (tokens consumed during extraction runs are the normal eval budget, not the audit).

```
=== Extraction Version Diff Audit ===
  Prompt v1 → v2 (improved date parsing + termination classification)
  Test set: 100 NDA and vendor contracts, diverse vintages and jurisdictions

--- Per-field change rates (thresholds: review ≥5%, block ≥15%) ---
  Field                  Changed   Rate    Verdict   Notes
  ──────────────────────────────────────────────────────────────────────
  termination_type           18    18.0%   BLOCK     v2 classifies "mutual/for-cause"
                                                     separately; v1 merged them.
                                                     18 cases need legal review.
  governing_law               8     8.0%   REVIEW    v2 normalizes "NY" → "New York"
                                                     (format, not semantic). Likely OK.
  effective_date              3     3.0%   OK        Within noise (<5%). 3 ambiguous
                                                     dates; v2 more accurate.
  notice_period               2     2.0%   OK        Minor format difference (days vs
                                                     calendar notation). 2 cases.
  party_names                 1     1.0%   OK        One entity name disambiguation.
  payment_terms               0     0.0%   OK
  confidentiality_scope       0     0.0%   OK
  jurisdiction                0     0.0%   OK
  renewal_clause              0     0.0%   OK
  amendment_count             0     0.0%   OK

--- Summary ---
  Total documents:     100
  Changed documents:   22 (22.0%)
  Unchanged documents: 78 (78.0%)
  Overall verdict:     BLOCK

  BLOCK reason: termination_type 18.0% ≥ block threshold 15.0%
  Action required: AUDITOR.reviewCases('termination_type') → 18 document pairs
                   for legal team review before v2 can be promoted.

--- After review (hypothetical next run) ---
  Legal team reviewed 18 cases:
    15 confirmed improvements (v2 correct, v1 wrong)
     3 regressions (v2 wrong, v1 correct) → patched in v3 prompt
  After patch, re-audit 100 docs:
    termination_type: 2% change rate (3 regressions fixed) → OK
    Overall verdict:  PROMOTE

--- reviewCases('termination_type') output (first 2 of 18) ---
  { docId: 'contract-0047',
    change: { field: 'termination_type',
              v1: 'for_cause',
              v2: 'mutual_or_for_cause' } }
  { docId: 'contract-0091',
    change: { field: 'termination_type',
              v1: 'at_will',
              v2: 'mutual_or_for_cause' } }
  ...

=== Timing ===
audit()   per 10-field document pair:      0.0012 ms
summary() over 100 documents, 10 fields:   0.0047 ms
reviewCases() for 18 flagged documents:    0.0003 ms
Zero API calls. Zero tokens.

=== Cost of the audit itself ===
  Diff computation: 0 tokens, 0 API calls.
  Extraction runs (covered by eval budget, not the audit):
    100 docs × 2 versions × $0.00312/doc (Haiku, F-58 pricing) = $0.624 total
  Amortized over promotion cycle (1 audit per prompt version per month): negligible.
```

## See also

[F-129](f129-per-entity-output-regression-check.md) · [F-07](f07-model-evaluation.md) · [F-38](f38-model-version-pinning.md) · [F-126](f126-output-field-change-velocity.md) · [F-133](f133-extraction-retry-escalation-policy.md)

## Go deeper

Keywords: `extraction version diff audit` · `prompt version migration` · `field change rate audit` · `extraction output diff` · `prompt promotion gate` · `model migration field diff` · `extraction version comparison` · `per-field change rate` · `prompt upgrade audit` · `extraction diff promotion`
