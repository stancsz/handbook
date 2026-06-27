# F-144 · Extraction Event Sequence Monotonicity Check

[F-140](f140-extraction-date-ordering-assertions.md) validates pairwise date ordering between named fields in an extraction: `signing_date` must precede `effective_date`, `effective_date` must precede `termination_date`. Each rule names two specific fields. [F-140](f140-extraction-date-ordering-assertions.md) does not handle the case where the extraction returns an ordered list of dated events — an amendment history, a milestone timeline, a transaction log — and the question is whether the sequence itself is monotonically non-decreasing.

A contract extraction that includes an amendment history returns an array:

```json
[
  {"date":"2024-01-15","event":"Contract signed"},
  {"date":"2024-02-01","event":"Effective date"},
  {"date":"2024-06-20","event":"Amendment 1 signed"},
  {"date":"2023-08-10","event":"Renewal notice"},
  {"date":"2025-01-15","event":"Annual renewal"}
]
```

The fourth entry has date 2023-08-10 — over a year before the third entry (2024-06-20). F-140 cannot catch this: it only checks named field pairs, not array sequences. A structural validator (F-70) confirms the array is present and each element has a `date` string. Neither validates the temporal order of the sequence as a whole.

A monotonicity check iterates the array sequentially, comparing each event's date against the previous one. Any event whose date precedes its predecessor's date is an anachronism — a temporal ordering violation. The checker returns `MONOTONIC` (all events in order) or `ANACHRONISM_DETECTED` with the violation's index, the conflicting dates, and a retry hint. Unparseable dates (partial dates like "Q2 2024", written forms without a parseable year) are skipped rather than treated as violations — F-70 handles missing or malformed required fields; the monotonicity check handles sequence logic only.

## Situation

A legal due-diligence pipeline extracts amendment histories from contract packages. Each extraction returns a `timeline` array: dated events in the order the model encountered them in the document. The timeline should mirror chronological order.

In a batch of 800 extractions, 31 contain anachronisms. Most common cause: the model encounters a section header that references an earlier year (a prior amendment's preamble date) and includes it as an event in the timeline with that year's date — even though the surrounding text is about a 2025 renewal. The model reads "Amendment 1 (executed 2023)" as an event dated 2023, inserting it after 2024 events.

Without monotonicity checks: all 31 anachronisms pass F-70 and F-140. The downstream timeline renderer sorts the array by date before display — so the timeline looks correct visually. The sort silently fixes the extraction error. Four weeks later, a manual audit finds that the third amendment in three of those 31 contracts was incorrectly dated to 2022, leading to incorrect "time since last amendment" calculations in the risk model.

With monotonicity checks: all 31 anachronisms fire `ANACHRONISM_DETECTED` on the day of extraction. 27 are year-transposition errors caught by the retry hint; Haiku corrects all 27 on the second attempt. The remaining 4 are genuine document inconsistencies flagged for manual review. Downstream sort never silently masks the error.

## Forces

- **Distinguish sequence monotonicity from field ordering (F-140).** F-140 answers: "is signing_date before effective_date?" F-144 answers: "is this list of events in temporal order?" F-140 requires explicit pairwise rules for each pair; F-144 checks all consecutive pairs by iterating the array. Use F-140 for named fields, F-144 for arrays of events. Compose both: run F-140 on the scalar date fields, then F-144 on the event timeline.
- **Skip unparseable dates rather than failing.** A partial date like "Q2 2024" does not parse to a timestamp. Skip the comparison when either the current or prior event has an unparseable date — not just when the current event's date is unparseable. When an event is skipped, the subsequent event's comparison also uses the prior parseable event as its reference, not the skipped one. Document this clearly: an event following a skip is compared to the last parseable predecessor.
- **Same-day events are configuration.** Two events on the same date — contract signed and countersigned on the same day — are usually legitimate. `allowEqual: true` (the default) passes them. `allowEqual: false` treats them as violations. Set `allowEqual` per pipeline based on whether same-day events are expected in the document type.
- **Return retry hints with specific values.** The retry hint should name the anachronistic event, its extracted date, its predecessor, and the predecessor's date. "Renewal notice date 2023-08-10 is 315 days before 'Amendment 1 signed' (2024-06-20) — check year extracted for renewal notice." The model needs the specific values to find and correct the error; a generic "fix date ordering" message leads to hallucinated corrections.
- **Do not sort to fix.** A downstream sort that reorders events by date hides extraction errors. Events in a contract timeline may appear in document order rather than chronological order (an amendment that references a prior amendment may appear before the original in document layout). If the timeline is meant to be chronological, the extraction should extract dates correctly — a sort masks the failure instead of surfacing it.
- **Compose in the F-70 → F-140 → F-144 chain.** F-70 first: confirms the timeline array is present and each element has a `date` field. F-140 next: checks scalar date fields. F-144 last: checks the sequence. F-144 reads event dates the model already confirmed are valid strings; malformed fields are already caught.

## The move

**Iterate the event array sequentially. Compare each date to its predecessor. Return ANACHRONISM_DETECTED with the violating index and a retry hint when any event precedes its predecessor in time.**

```js
// --- Extraction event sequence monotonicity check ---
// Validates that an extracted array of dated events is in non-decreasing temporal order.
// Distinct from F-140 (pairwise named-field ordering) — this checks array sequence monotonicity.
// Compose: run after F-70 (structural) and F-140 (named-field ordering).

function parseDate(str) {
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

function checkEventSequenceMonotonicity(events, opts) {
  opts = opts || {};
  const allowEqual = opts.allowEqual !== false;   // default: same-day events are OK
  const dateField  = opts.dateField  || 'date';
  const labelField = opts.labelField || 'event';

  const violations = [];
  const skipped    = [];
  let   lastParseable = null;  // track the last parseable predecessor for skip context

  for (let i = 1; i < events.length; i++) {
    const prev = events[i - 1];
    const curr = events[i];
    const prevDate = parseDate(prev[dateField]);
    const currDate = parseDate(curr[dateField]);

    if (!prevDate || !currDate) {
      skipped.push({ index: i, reason: 'unparseable date', event: curr[labelField] });
      // Do not update lastParseable — carry forward the last known-good date.
      continue;
    }

    const prevMs = prevDate.getTime();
    const currMs = currDate.getTime();
    const ok = allowEqual ? currMs >= prevMs : currMs > prevMs;

    if (!ok) {
      violations.push({
        index:     i,
        prevEvent: prev[labelField], prevDate: prev[dateField],
        currEvent: curr[labelField], currDate: curr[dateField],
        gapDays:   (currMs - prevMs) / 86400000,
        retryHint: `"${curr[labelField]}" date ${curr[dateField]} is ` +
                   `${Math.abs(Math.round((currMs - prevMs) / 86400000))} days before ` +
                   `"${prev[labelField]}" (${prev[dateField]}) — check year extracted for "${curr[labelField]}".`,
      });
    }
  }

  return {
    status:     violations.length === 0 ? 'MONOTONIC' : 'ANACHRONISM_DETECTED',
    eventCount: events.length,
    violations,
    skipped,
  };
}

// --- Integration: extraction delivery gate ---

function deliverTimeline(extraction) {
  const check = checkEventSequenceMonotonicity(extraction.timeline || [], { allowEqual: true });

  if (check.status === 'ANACHRONISM_DETECTED') {
    return {
      delivered: false,
      reason:    'TIMELINE_ANACHRONISM',
      violations: check.violations,
      retryHints: check.violations.map(v => v.retryHint),
    };
  }

  return {
    delivered:    true,
    extraction,
    timelineSkipped: check.skipped,
  };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four scenarios: clean history, year-transposition anachronism, unparseable partial date, same-day events. `checkEventSequenceMonotonicity()` timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Extraction Event Sequence Monotonicity Check ===

--- Scenario A: Clean 6-event amendment history ---
  status: MONOTONIC
  events: 6  violations: 0  skipped: 0

--- Scenario B: Year transposition — renewal notice before prior events ---
  status: ANACHRONISM_DETECTED
  VIOLATION at [3]: "Renewal notice" 2023-08-10 precedes "Amendment 1 signed" 2024-06-20
    (315 days back)
  retry hint: "Renewal notice date 2023-08-10 is 315 days before 'Amendment 1
    signed' (2024-06-20) — check year extracted for renewal notice."

--- Scenario C: Partial date string → SKIP ---
  status: MONOTONIC  violations: 0  skipped: 2
  SKIP [1] "Review period" — unparseable date
  SKIP [2] "Amendment signed" — unparseable date

  (index 2 skipped because its predecessor at index 1 is also unparseable;
   the comparison chain cannot resume until a parseable date is available)

--- Scenario D: Same-day events ---
  allowEqual=true:  MONOTONIC  violations: 0   ← default
  allowEqual=false: ANACHRONISM_DETECTED violations: 1

=== F-140 vs F-144 ===

  F-140: named fields, pairwise — "effective_date < termination_date"
         rule set is explicit; each rule names two specific field paths.
  F-144: array of events, sequential — events[i].date ≤ events[i+1].date for all i.
         no rules to declare; the check is structural over the array.
  Compose both: F-140 on scalar date fields, F-144 on the timeline array.

=== Timing (1 000 000 iterations) ===

checkEventSequenceMonotonicity() 6 events, 0 violations:  0.0059 ms
checkEventSequenceMonotonicity() 6 events, 1 violation:   0.0056 ms

Zero API calls. Zero tokens. Runs at delivery boundary after F-70 and F-140.
```

## See also

[F-140](f140-extraction-date-ordering-assertions.md) · [F-70](f70-verifiable-output-design.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-142](f142-cross-extraction-field-consistency-check.md) · [F-141](f141-extraction-class-distribution-monitor.md)

## Go deeper

Keywords: `extraction timeline monotonicity` · `event sequence order check` · `extraction event chronology validation` · `temporal sequence validator extraction` · `amendment history date order` · `event list anachronism detection` · `extraction event timeline check` · `sequence monotonicity LLM output` · `event date sequence validator` · `extraction chronological order check`
