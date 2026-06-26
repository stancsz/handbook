# F-38 · Model Version Pinning

Every major model API offers two ways to reference a model: by alias (`claude-sonnet-4-6`) or by dated snapshot (`claude-sonnet-4-5-20251001`). Aliases are convenient and always route to the latest model — which means the system you deployed last month may be running against a different model today, with no change in your code. This is a deployment discipline problem, not an AI problem. Pin to a snapshot in production. Upgrade on a schedule.

## Situation

A team deploys a contract review tool against `claude-opus-4-8` (the alias). Four weeks later, a provider alignment update changes how the model handles instruction conflicts — adding unsolicited caveats more aggressively. Review summaries now include "Note: consult a lawyer before acting on this analysis" in 70% of outputs, up from 15%. Clients escalate. Root cause: the team did not pin. They are running a different model than the one they tested. Recovery: find the pre-update snapshot ID, pin, redeploy. One week lost.

## Forces

- **Aliases are a deployment anti-pattern in production.** `claude-sonnet-4-6` is a pointer. The pointed-to model can change without notice, without a changelog, without a breaking change flag. The API does not tell you the model changed between calls.
- **Model updates are not versioned like software.** Providers do not publish changelogs for capability or alignment updates. Silent changes — safety posture, tone, instruction priority — are routine. [F-26](f26-behavioral-drift-detection.md) can detect them after the fact. Pinning prevents the incident.
- **Even pinned snapshots EOL.** Snapshot IDs are retired when providers deprecate model generations. Plan upgrade cycles. Don't let an EOL notice force an emergency migration — those are untested.
- **Upgrade testing is not optional.** Run your eval suite against the new snapshot before promoting it to production. A new snapshot may improve average performance while regressing specific behaviors your system depends on.
- **Staging and production must pin to the same snapshot.** If they diverge, your staging tests are testing the wrong thing.

## The move

**Pin to a dated snapshot in all production environments. Maintain an upgrade log. Test new snapshots against your eval suite before cutting over. Pair with F-26 as your early-warning layer.**

**Model registry — single source of truth:**

```js
// config/models.js — all model references flow through here
const MODELS = {
  // Pin dated snapshots in production — never aliases
  // Update here only after eval suite passes on the new snapshot
  primary:   'claude-sonnet-4-5-20251001', // last upgraded 2025-10-01, score +1.8%
  fast:      'claude-haiku-4-5-20251001',  // last upgraded 2025-10-01, score -0.3% (within gate)
  reasoning: 'claude-opus-4-7-20251015',   // last upgraded 2025-10-15, score +2.1%

  // Embedding — version matters: scores are not comparable across generations
  embed: 'text-embedding-3-small',
};

// Every model call imports from here — one file to update, propagates everywhere
module.exports = MODELS;
```

**Upgrade log (tracked in version control):**

```markdown
# models-upgrade-log.md

| Date       | Role      | Old snapshot        | New snapshot        | Eval (old) | Eval (new) | Delta  | Reason     |
|------------|-----------|---------------------|---------------------|------------|------------|--------|------------|
| 2025-10-01 | primary   | -20250801           | -20251001           | 87.3%      | 89.1%      | +1.8%  | Scheduled  |
| 2025-10-01 | fast      | -20250601           | -20251001           | 91.5%      | 91.2%      | -0.3%  | EOL notice |
| 2025-10-15 | reasoning | -20250801           | -20251015           | 82.1%      | 84.2%      | +2.1%  | Scheduled  |
```

**Upgrade procedure:**

```
1. Provider announces new snapshot (or your EOL monitor fires)
2. Branch: update config/models.js fast.candidate = 'new-snapshot-id'
3. Run eval: npm run eval -- --model fast.candidate
4. Gate: all dimensions within -2% of current snapshot → proceed
         Any dimension drops >2% → hold; investigate; escalate to provider
5. Shadow deploy to staging for 1 week (F-22 shadow period)
6. Promote: update models.js, remove .candidate, commit, tag
7. Append row to models-upgrade-log.md
```

**EOL monitoring:**

```js
// Add known EOL dates from provider announcements; update quarterly
const SNAPSHOT_EOL_DATES = {
  // 'claude-haiku-4-5-20250601': '2026-01-01', // example
};

function warnEol() {
  const now = Date.now();
  for (const [snapshot, eol] of Object.entries(SNAPSHOT_EOL_DATES)) {
    const daysLeft = Math.floor((new Date(eol) - now) / 86400000);
    if (daysLeft < 60) {
      console.warn(`[MODEL EOL] ${snapshot} retires in ${daysLeft} days — start upgrade`);
    }
  }
}

// Run at deploy time and once daily in your healthcheck
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Token overhead of version pinning = 0 (model name is request metadata, not prompt context). Upgrade procedure is process-level; costs shown are illustrative order-of-magnitude estimates, not independently tested.

```
=== Token overhead of pinning ===

Alias:    'claude-sonnet-4-6'          → 0 tokens in prompt
Snapshot: 'claude-sonnet-4-5-20251001' → 0 tokens in prompt

Version pinning has zero inference cost. It is a free, purely organizational choice.

=== Cost of NOT pinning (incident scenario) ===

Silent model update detected after: 3 days (F-26 daily judge alerts)
Investigation to identify root cause:  ~1 week (no snapshot = no comparison point)
Redeploy after pinning:               ~1 day

Engineering time lost: ~10 person-days at $150/hr = ~$12 000/incident

Pinning cost: zero. Incident investigation cost: four figures minimum.

=== Eval gate dimensions (upgrade approval) ===

Dimension             Old score   New score   Delta    Gate (fail if < -2%)
Task accuracy         87.3%       89.1%       +1.8%    PASS
Format compliance     94.1%       93.8%       -0.3%    PASS
Tone consistency      91.0%       90.4%       -0.6%    PASS
Caveat injection      14.2%       15.1%       +0.9%    PASS (lower is better)

All pass → upgrade approved → deploy.
```

The gate threshold of -2% is not universal — calibrate to your application's sensitivity. A medical or legal tool may hold at -0.5%. A customer FAQ bot may tolerate -3%. What matters is that the threshold exists and is checked before every promotion.

## See also

[F-26](f26-behavioral-drift-detection.md) · [F-22](f22-cicd-for-ai-pipelines.md) · [F-07](f07-evaluation-driven-development.md) · [S-65](../stacks/s65-multi-model-pipelines.md) · [S-06](../stacks/s06-model-routing.md) · [R-01](../frontier/r01-model-landscape.md)

## Go deeper

Keywords: `model version pinning` · `snapshot ID` · `model upgrade` · `EOL deprecation` · `alias vs snapshot` · `upgrade cadence` · `model governance` · `deployment stability` · `provider updates` · `model registry`
