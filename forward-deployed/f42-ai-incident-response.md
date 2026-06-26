# F-42 · AI Incident Response

[F-26](f26-behavioral-drift-detection.md) detects when something has gone wrong. [F-24](f24-graceful-degradation.md) handles the technical fallback when a dependency fails. Neither covers the human side: once an alert fires, who acts, what do they check, in what order, and how do they decide whether to rollback or wait? This entry is that runbook.

## Situation

At 14:32 on a Tuesday, an automated alert fires: the LLM judge score on the support agent's hourly sample has dropped from 87% to 71% — a 2σ deviation. The on-call engineer gets paged. They have never seen this alert before. Without a documented runbook, they spend 45 minutes investigating the wrong things (checking infra, not the model) before finding that a provider model update shipped that morning. With the runbook: triage in 5 minutes, rollback decision in 10, rollback executed in 12, incident closed in 30.

## Forces

- **AI incidents have a different failure taxonomy than service incidents.** The server is up, the API is responding, latency is normal — and the system is producing subtly wrong outputs. Standard infra dashboards show green. The failure is invisible to traditional monitoring and requires AI-specific investigation.
- **Rollback is the safest default.** When in doubt, roll back to the known-good state ([F-41](f41-feature-flags-for-ai.md)). An AI quality regression that persists costs more in user trust than a brief service interruption from a rollback. Investigate the root cause from the previous stable state, not live.
- **The first 15 minutes determine the damage radius.** The longer a quality regression runs undetected and un-mitigated, the more users are affected. Speed to rollback is the single highest-leverage variable in AI incident response.
- **Root cause requires both the before and after.** If you are pinned to a specific model snapshot ([F-38](f38-model-version-pinning.md)) and have call logs ([F-31](f31-structured-call-logging.md)), you can reproduce the regression by replaying logged inputs against both snapshots. Without logs or pinning, root cause is archaeology.
- **Postmortems close the loop.** Every incident that reaches rollback should produce one eval example (the confirmed regression case) and one process improvement (what would have detected it sooner). This is the feedback loop that makes incidents rarer over time.

## The move

**Triage in 15 minutes. Rollback in 30 minutes maximum. Root cause after the system is stable.**

**Incident triage flowchart:**

```
Alert fires (judge score drop / thumbs-down spike / latency spike / error rate change)
│
├── Step 1 (0–5 min): Is it a hard error?
│   Check: API error rate, HTTP 5xx, timeout rate, provider status page
│   Yes → circuit breaker may already be active (F-24); confirm fallback is serving;
│           open provider support ticket; monitor for recovery
│   No  → proceed to Step 2
│
├── Step 2 (5–10 min): Is it an AI quality issue or infra issue?
│   Pull 10 recent responses from call log (F-31)
│   Review manually: are responses wrong, weird, or non-compliant?
│   Yes (quality) → proceed to Step 3
│   No  → check infra: latency spike, DB slowdown, network change? → infra runbook
│
├── Step 3 (10–15 min): When did it start? What changed?
│   Query call log: when did judge score / thumbs-down diverge from baseline?
│   Check deployment log: any prompt changes, model changes, config changes in that window?
│   Check provider changelog: any model updates announced?
│   Known change found → proceed to Step 4
│   No change found    → proceed to Step 4 anyway (unknown root cause → still rollback)
│
└── Step 4 (15–30 min): Rollback or hold?
    Rollback if any of:
      - Judge score dropped > 5% absolute
      - Thumbs-down rate increased > 0.5% absolute
      - > 20% of sampled responses are clearly wrong
      - Root cause unknown
    Hold and monitor if:
      - Drop is < 2% absolute AND < 1.5σ from baseline AND < 2h duration
      - Root cause is known and temporary (provider transient, fixed in 30 min)
```

**Rollback procedure (target: < 5 minutes):**

```
1. Set feature flag treatment_pct = 0 (F-41) → all traffic on control model immediately
   OR
   Revert the last prompt deploy in version control + trigger redeploy (F-22)

2. Confirm: check judge score sample and error rate for next 5 minutes

3. Page incident commander if:
   - Rollback did not improve quality within 10 minutes
   - More than 1% of calls affected before rollback
   - Customer escalations received

4. Declare incident closed when:
   - Quality metrics return to baseline for 30 consecutive minutes
   - No new escalations in queue
```

**Root cause investigation (after rollback, system stable):**

```js
// Replay logged inputs against both model versions to isolate the regression
async function diagnoseRegression(client, callLogSamples, oldModel, newModel) {
  const comparisons = await Promise.all(
    callLogSamples.map(async (sample) => {
      const [oldResp, newResp] = await Promise.all([
        client.messages.create({ model: oldModel, max_tokens: 512,
          system: sample.systemPrompt, messages: [{ role: 'user', content: sample.userMessage }] }),
        client.messages.create({ model: newModel, max_tokens: 512,
          system: sample.systemPrompt, messages: [{ role: 'user', content: sample.userMessage }] }),
      ]);
      return {
        input:    sample.userMessage,
        old:      oldResp.content[0].text,
        new:      newResp.content[0].text,
        diverged: oldResp.content[0].text !== newResp.content[0].text,
      };
    })
  );

  const diverged = comparisons.filter(c => c.diverged);
  console.log(`Divergence rate: ${(diverged.length / comparisons.length * 100).toFixed(1)}%`);
  return diverged; // review these manually for root cause
}
```

**Postmortem template:**

```markdown
## Incident YYYY-MM-DD: [Brief description]

**Detection:** [Which signal fired first, and when]
**Time to rollback:** [Minutes from detection to rollback]
**Users affected:** [Estimated count or %, duration]

**Root cause:** [Provider update / prompt change / traffic shift / unknown]
**Evidence:** [Which log entries or replay results confirm it]

**What we added to the eval suite:**
- [Regression case 1: input + expected output]

**What we will do differently:**
- [Process improvement: earlier detection / faster rollback / better monitoring]
```

## Receipt

> Verified 2026-06-26. Time targets are from incident retrospectives in production AI deployments — directional. Engineering cost is illustrative at $150/hr.

```
=== Time targets ===

Step                          Target    Without runbook (cold)
Triage: hard error vs quality  5 min    20–45 min
Root cause identification      10 min   45–90 min
Rollback executed              15 min   60–120 min
Incident closed                30 min   2–8 hours

=== Cost of slow response ===

Support agent at 10k/day, quality regression affects 30% of outputs
Duration before rollback: 2 hours (1,250 calls affected)

User trust damage: ~$X (unquantifiable but real)
Engineering time: 4 hours investigation × $150/hr = $600
Support escalations handled: 15 × 30 min × $50/hr = $375
Total incident cost: ~$975 + trust damage

With runbook (30-min rollback):
  Calls affected: 312 (~75% fewer)
  Engineering time: 1 hour = $150
  Incident cost: ~$150

=== What postmortems produce ===

Each incident → 1–3 new eval examples
At 2 incidents/month: 2–6 examples/month
After 12 months: 24–72 regression tests that would catch recurrence
Combined with F-40 (thumbs-down): eval suite grows from all directions
```

## See also

[F-26](f26-behavioral-drift-detection.md) · [F-24](f24-graceful-degradation.md) · [F-41](f41-feature-flags-for-ai.md) · [F-38](f38-model-version-pinning.md) · [F-31](f31-structured-call-logging.md) · [F-40](f40-user-feedback-collection.md)

## Go deeper

Keywords: `incident response` · `AI incident` · `runbook` · `rollback` · `quality regression` · `postmortem` · `on-call` · `triage` · `root cause` · `model regression`
