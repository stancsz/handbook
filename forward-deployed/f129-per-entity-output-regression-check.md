# F-129 · Per-Entity Output Regression Check

[F-79](f79-semantic-regression-detection.md) compares outputs across two model deployments for a batch of inputs — it detects when a new deploy degrades quality relative to a baseline deploy. [F-126](f126-output-field-change-velocity.md) tracks how often each field's value flips across many production calls for the same entity template — it surfaces systematic instability without a reference value. [F-116](f116-per-field-extraction-error-rate-tracking.md) tracks the rate at which extracted values are structurally or semantically wrong.

None of these compare the current extraction for a specific entity against the last known value for that entity. When contract C-881 was analyzed in March, `recommended_action` was `REJECT` and `risk_level` was `HIGH`. In June, after an amendment, the same contract is re-analyzed. If it now returns `recommended_action: APPROVE`, that is a field-level change on a HIGH-consequence field for a specific entity — not a statistical drift across a template, not a deploy-time regression, and not necessarily an error. It may be a correct update reflecting the amendment. But it warrants review.

A per-entity output regression checker stores the last known extraction per entity and compares each new extraction against it. Changes to HIGH-consequence fields trigger a `REGRESSION_ALERT`. Changes to LOW-consequence fields produce a `CHANGED` status (logged, not paged). Stable extractions return `STABLE`. First-time extractions return `NO_BASELINE` and immediately become the baseline.

## Situation

A contract analysis pipeline re-extracts three contracts on a monthly review cycle. Baselines from March:

- C-881: `{ jurisdiction: 'New York', risk_level: 'HIGH', recommended_action: 'REJECT', contract_language: 'EN' }`
- C-883: `{ governing_law_clause_id: 'CL-42', risk_level: 'MEDIUM', contract_language: 'EN' }`

June extractions:

- C-882: first extraction, no baseline — stores immediately.
- C-881: `recommended_action` changed from `REJECT` to `APPROVE`. This is a HIGH-tier field. Status: `REGRESSION_ALERT`. Action: route to senior reviewer to confirm the amendment justifies the approval change.
- C-883: `contract_language` changed from `EN` to `FR`. This is a LOW-tier field — a language amendment. Status: `CHANGED`. Action: log for audit, no alert.

The alert on C-881 is not an assertion that the new value is wrong. The contract may have been genuinely amended to remove the disqualifying clauses. The alert says: *this specific contract just changed its approval recommendation — a human should confirm this is intentional before the contract proceeds.*

## Forces

- **Regression is not error.** A value change on a HIGH-tier field may be correct. The baseline was the right answer at the time it was extracted. The new value may be the right answer now. The checker flags the change for human review — it does not reject the output or block the workflow. This is a `REGRESSION_ALERT`, not a `VALIDATION_ERROR`.
- **Per-entity baseline vs. per-template flip rate.** F-126 detects when a field is statistically unstable across many calls for the same entity type — e.g., `risk_level` returning HIGH and MEDIUM alternately on 50 contracts from the same template. F-129 is different: it holds the March value for contract C-881 specifically and checks whether June's value for C-881 differs. The unit is the individual entity, not the template population.
- **Tier determines alert vs. log.** Not all field changes require human review. `contract_language: EN → FR` on a contract that was just amended with a French appendix is a valid, low-stakes change. `recommended_action: REJECT → APPROVE` on a contract entering the approval queue requires confirmation. Register field tiers to distinguish pages (HIGH) from log entries (LOW).
- **The baseline must be explicitly updated.** After a review confirms a HIGH-tier change is correct, call `store()` to update the baseline. If the checker is called again without updating, the same alert fires on every subsequent extraction until the baseline is updated. The update is a deliberate acknowledgment that the change was reviewed.
- **Does not replace per-call validation.** F-70 (structural validation), F-92 (arithmetic invariants), and F-102 (reference integrity) run per-call and can reject outputs. This checker runs after all per-call validations pass and only checks field-level stability against a historical baseline. Both layers are needed: per-call validation catches malformed outputs; the regression check catches correct-but-changed outputs.
- **First extraction is the baseline.** For new entities, there is no prior to compare against. `check()` on a first-time entity returns `NO_BASELINE`, stores the extraction as the new baseline, and returns without an alert. Subsequent extractions compare against this first extraction.

## The move

**Store extractions as baselines per entity. On each re-extraction, compare against the stored baseline. Alert on HIGH-tier field changes; log LOW-tier changes; skip per-call validation failures before checking regression.**

```js
// --- Per-entity output regression checker ---
// Stores last known extraction per entity.
// On each re-extraction, compares fields against stored baseline.
// REGRESSION_ALERT: one or more HIGH-tier fields changed.
// CHANGED: changes are all LOW or MEDIUM tier.
// STABLE: all field values match baseline.
// NO_BASELINE: first extraction — stored immediately.

class EntityOutputRegressionChecker {
  constructor(opts = {}) {
    this._tiers     = opts.tiers ?? {};   // fieldName → 'HIGH' | 'MEDIUM' | 'LOW'
    this._baselines = new Map();           // entityId → { output, storedAt }
  }

  // Store a validated extraction as the baseline for this entity.
  // Call after review confirms a REGRESSION_ALERT is intentional.
  store(entityId, output) {
    this._baselines.set(entityId, { output: { ...output }, storedAt: Date.now() });
  }

  // Compare new extraction to stored baseline.
  // Returns { status, entityId, changes, highChanges, baselineAge }
  check(entityId, newOutput) {
    if (!this._baselines.has(entityId)) {
      this.store(entityId, newOutput);
      return { status: 'NO_BASELINE', entityId, storedNow: true };
    }

    const baseline = this._baselines.get(entityId);
    const changes  = [];

    for (const [field, newVal] of Object.entries(newOutput)) {
      const oldVal = baseline.output[field];
      if (oldVal === undefined) {
        changes.push({
          field, old: null, new: newVal, change: 'NEW_FIELD',
          tier: this._tiers[field] ?? 'UNKNOWN',
        });
      } else if (String(newVal) !== String(oldVal)) {
        changes.push({
          field, old: oldVal, new: newVal, change: 'VALUE_CHANGED',
          tier: this._tiers[field] ?? 'UNKNOWN',
        });
      }
    }

    const highChanges = changes.filter(c => c.tier === 'HIGH');
    return {
      status:      highChanges.length > 0 ? 'REGRESSION_ALERT' : (changes.length > 0 ? 'CHANGED' : 'STABLE'),
      entityId,
      changes,
      highChanges,
      baselineAge: Math.floor((Date.now() - baseline.storedAt) / 1000),  // seconds
    };
  }

  hasBaseline(entityId)   { return this._baselines.has(entityId); }

  // Call after human review confirms a REGRESSION_ALERT is correct.
  updateBaseline(entityId, confirmedOutput) { this.store(entityId, confirmedOutput); }
}

// --- Integration: run after per-call validation, before downstream routing ---

const REGRESSION_CHECKER = new EntityOutputRegressionChecker({
  tiers: {
    recommended_action:       'HIGH',
    risk_level:               'HIGH',
    jurisdiction:             'HIGH',
    governing_law_clause_id:  'HIGH',
    contract_language:        'LOW',
    notice_period_days:       'MEDIUM',
  },
});

function processExtraction(entityId, output) {
  // 1. Per-call validation (F-70, F-92, F-102) runs first — return early on hard errors

  // 2. Regression check
  const regression = REGRESSION_CHECKER.check(entityId, output);

  if (regression.status === 'REGRESSION_ALERT') {
    log({
      event:       'extraction_regression_alert',
      entityId,
      highChanges: regression.highChanges,
    });
    routeToReview(entityId, regression);          // hold for human confirmation
    return { held: true, regression };
  }

  if (regression.status === 'CHANGED') {
    log({ event: 'extraction_changed', entityId, changes: regression.changes });
  }

  // 3. If STABLE or CHANGED (LOW/MEDIUM only), proceed normally
  return { held: false, output, regression };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `store()` and `check()` timed over 100 000 iterations on a 4-field extraction output.

```
=== EntityOutputRegressionChecker timing (100 000 iterations) ===

store() — 4 fields:               0.0006 ms
check() — STABLE, 4 fields:       0.0019 ms

=== Scenario A: C-882 — first extraction, no baseline ===

check('C-882', { jurisdiction: 'Delaware', risk_level: 'LOW',
                 recommended_action: 'APPROVE', contract_language: 'EN' }):
{
  status:    'NO_BASELINE',
  entityId:  'C-882',
  storedNow: true
}

Baseline for C-882 set. Subsequent checks compare against this extraction.

=== Scenario B: C-881 — recommended_action changed REJECT → APPROVE ===

Baseline (March): { jurisdiction: 'New York', risk_level: 'HIGH',
                    recommended_action: 'REJECT', contract_language: 'EN' }

check('C-881', { jurisdiction: 'New York', risk_level: 'HIGH',
                 recommended_action: 'APPROVE', contract_language: 'EN' }):
{
  status: 'REGRESSION_ALERT',
  entityId: 'C-881',
  changes: [
    { field: 'recommended_action', old: 'REJECT', new: 'APPROVE',
      change: 'VALUE_CHANGED', tier: 'HIGH' }
  ],
  highChanges: [
    { field: 'recommended_action', old: 'REJECT', new: 'APPROVE',
      change: 'VALUE_CHANGED', tier: 'HIGH' }
  ],
  baselineAge: 0
}

Action: held for review. Senior reviewer confirms amendment removed disqualifying clause.
updateBaseline('C-881', currentOutput) called. Next extraction will compare against APPROVE.

=== Scenario C: C-883 — only contract_language changed (LOW tier) ===

Baseline: { governing_law_clause_id: 'CL-42', risk_level: 'MEDIUM', contract_language: 'EN' }

check('C-883', { governing_law_clause_id: 'CL-42', risk_level: 'MEDIUM', contract_language: 'FR' }):
{
  status: 'CHANGED',
  entityId: 'C-883',
  changes: [
    { field: 'contract_language', old: 'EN', new: 'FR',
      change: 'VALUE_CHANGED', tier: 'LOW' }
  ],
  highChanges: [],
  baselineAge: 0
}

Action: logged for audit trail. No alert. Processing continues without hold.

=== F-79 vs F-126 vs F-116 vs F-129 ===

              │ F-79 (deploy regression)     │ F-126 (flip rate)            │ F-116 (error rate)          │ F-129 (entity regression)
──────────────┼──────────────────────────────┼──────────────────────────────┼─────────────────────────────┼──────────────────────────────
Baseline      │ Previous deploy output       │ None (statistical)           │ Ground truth label          │ Last known value for entity
Scope         │ All entities, batch          │ Many calls, same template    │ Many calls, per field        │ One entity, each re-extraction
Alert trigger │ Semantic degradation delta   │ Flip rate > threshold        │ Error rate > threshold      │ HIGH-tier field value changed
Signal type   │ Quality drop across deploy   │ Instability pattern          │ Wrong value rate            │ Entity-specific value change
Human review? │ No (automated comparison)    │ No (alert to prompt team)    │ No (per-field audit)        │ Yes (field change may be valid)
```

## See also

[F-79](f79-semantic-regression-detection.md) · [F-126](f126-output-field-change-velocity.md) · [F-116](f116-per-field-extraction-error-rate-tracking.md) · [F-70](f70-structured-output-validation.md) · [F-127](f127-extraction-field-null-rate-monitor.md) · [F-128](f128-cross-field-agreement-rate-tracker.md)

## Go deeper

Keywords: `per-entity output regression` · `extraction baseline comparison` · `structured output entity regression` · `LLM field change alert` · `per-entity field change detection` · `extraction regression check` · `entity-level output comparison` · `output field value change baseline` · `extraction field regression alert` · `per-entity golden baseline`
