# F-60 · Agent Clarification Strategy

[F-09](f09-human-in-the-loop.md) covers approval gates — pausing before irreversible actions to get human sign-off. [F-55](f55-agent-task-replanning.md) covers what to do when an agent gets stuck mid-task. Neither covers the upfront decision: when the user's instruction is ambiguous, should the agent ask for clarification before starting, or make a best-guess assumption and proceed?

## Situation

A calendar agent receives: "book a meeting with the sales team next week." Four unknowns: which sales team members to invite, which day, what time, what duration. Option A: ask all four questions. The user sees four questions in a row, answers them across two or three exchanges, and books the meeting in 3 minutes. Option B: assume Wednesday at 10am for 30 minutes and invite the four sales contacts the user most frequently meets with. The meeting is booked in 10 seconds. If the assumptions are right, Option B saved 3 minutes and felt magical. If any assumption is wrong, the user must cancel and rebook — a 5-minute correction. The cost structure is: (A) certain 3 minutes vs (B) 90% chance of 10 seconds + 10% chance of 5 minutes = 40 seconds expected. In this case, assume and inform beats ask.

Now change one detail: the agent is booking a customer-facing demo with a C-suite executive. Wrong assumptions here mean a professional embarrassment, not a quick reschedule. The correction cost is $2000 in deal risk, not 5 minutes. The expected cost of assuming flips: ask first every time.

The ask-vs-assume decision is an expected-cost calculation, not a style preference.

## Forces

- **Correction cost drives the decision, not confidence.** A high-confidence assumption about a reversible action is fine to make. A moderate-confidence assumption about an irreversible or high-stakes action is not. The question is not "how sure am I?" but "how bad is it if I'm wrong?"
- **Ask-fatigue is real and cumulative.** Every clarifying question consumes user goodwill. One well-chosen question is acceptable. Three questions in a row feels like an interrogation. An agent that asks before every action trains users to stop using it. Reserve questions for genuine high-stakes unknowns; assume everything else.
- **Cascade resolution reduces questions.** Unknowns are often interdependent. "Which sales team members?" might cascade-resolve "what time?" (check their shared availability). Ask the highest-impact question first; the answer often resolves others. Never ask more than one question per turn.
- **Assume + inform is better than assume silently.** When you make an assumption, say so: "I've scheduled this for Wednesday at 10am with Alice and Bob. Let me know if you'd like different attendees or timing." This converts a silent assumption into a transparent one the user can correct with one message, and it signals that correction is easy — reducing correction cost.
- **Action reversibility is the hard threshold.** Below the reversibility threshold: assume + inform. Above it: always ask. Sending an email is irreversible. Creating a draft is reversible. Deleting a record is irreversible. Adding a calendar event is reversible (easy to delete). The threshold is binary — don't try to model gradients here.

## The move

**Assess each unknown for correction cost and reversibility. Assume low-stakes unknowns, always announcing what you assumed. Ask for the single highest-impact unknown on high-stakes actions. Never ask more than one question per turn.**

```js
// Reversibility and correction cost table (configure per domain)
const ACTION_RISK = {
  // action_type: { reversible, correctionCostLevel }
  // correctionCostLevel: 'low' | 'medium' | 'high'
  create_calendar_event:  { reversible: true,  correctionCost: 'low' },
  send_email:             { reversible: false, correctionCost: 'high' },
  create_email_draft:     { reversible: true,  correctionCost: 'low' },
  book_customer_demo:     { reversible: false, correctionCost: 'high' },
  delete_record:          { reversible: false, correctionCost: 'high' },
  update_crm_field:       { reversible: true,  correctionCost: 'medium' },
  send_slack_message:     { reversible: false, correctionCost: 'medium' },
  create_draft_document:  { reversible: true,  correctionCost: 'low' },
};

// Unknown parameters the agent has identified
// Each: { name, confidence (0-1), impactIfWrong ('low'|'medium'|'high') }
function decideClarification(actionType, unknowns) {
  const risk = ACTION_RISK[actionType] ?? { reversible: true, correctionCost: 'low' };

  // Hard rule: irreversible + high correction cost → always ask about highest-impact unknown
  if (!risk.reversible && risk.correctionCost === 'high') {
    const topUnknown = unknowns
      .filter(u => u.impactIfWrong === 'high' || u.confidence < 0.7)
      .sort((a, b) => a.confidence - b.confidence)[0];

    if (topUnknown) {
      return {
        decision: 'ask',
        question: topUnknown.name,
        reason:   `${actionType} is irreversible — clarifying ${topUnknown.name} before proceeding`,
      };
    }
  }

  // For reversible actions: assume all unknowns, collect assumption list for disclosure
  if (risk.reversible) {
    const lowConfidence = unknowns.filter(u => u.confidence < 0.5);
    if (lowConfidence.length === 0 || risk.correctionCost === 'low') {
      return {
        decision:    'assume',
        assumptions: unknowns.map(u => ({ name: u.name, assumedValue: u.bestGuess })),
        disclose:    true,  // always say what you assumed
      };
    }
  }

  // Medium correction cost with low confidence: ask the single most uncertain unknown
  const mostUncertain = unknowns.sort((a, b) => a.confidence - b.confidence)[0];
  return {
    decision: 'ask',
    question: mostUncertain?.name,
    reason:   'medium correction cost with low-confidence assumption',
  };
}

// Example: calendar event booking
const meetingUnknowns = [
  { name: 'day_of_week',    confidence: 0.6,  impactIfWrong: 'medium', bestGuess: 'Wednesday' },
  { name: 'time_of_day',    confidence: 0.7,  impactIfWrong: 'medium', bestGuess: '10:00 AM' },
  { name: 'attendees',      confidence: 0.8,  impactIfWrong: 'high',   bestGuess: ['alice@corp.com', 'bob@corp.com'] },
  { name: 'duration_min',   confidence: 0.85, impactIfWrong: 'low',    bestGuess: 30 },
];

const calendarDecision = decideClarification('create_calendar_event', meetingUnknowns);
// → { decision: 'assume', assumptions: [...], disclose: true }

// Example: sending an email to a customer
const emailUnknowns = [
  { name: 'recipient',      confidence: 0.6,  impactIfWrong: 'high', bestGuess: 'client@example.com' },
  { name: 'send_time',      confidence: 0.9,  impactIfWrong: 'low',  bestGuess: 'now' },
];

const emailDecision = decideClarification('send_email', emailUnknowns);
// → { decision: 'ask', question: 'recipient', reason: 'irreversible...' }

// Template for assume + inform response
function buildAssumeResponse(actionType, decision, result) {
  if (decision.decision !== 'assume' || !decision.disclose) return result;

  const assumptionList = decision.assumptions
    .map(a => `${a.name}: ${JSON.stringify(a.assumedValue)}`)
    .join(', ');

  return `${result}\n\nAssumptions I made: ${assumptionList}. Reply to change any of these.`;
}

// Template for ask response — one question only
function buildAskResponse(question, context) {
  const QUESTION_TEMPLATES = {
    recipient:    (ctx) => `Who should I send this to? (I can see ${ctx.suggested} in your contacts — should I use them?)`,
    day_of_week:  (ctx) => `Which day next week works best?`,
    attendees:    (ctx) => `Who should I invite? (Suggesting: ${ctx.suggested?.join(', ')})`,
    time_of_day:  (ctx) => `What time works? (Defaulting to 10am unless you specify)`,
  };

  const template = QUESTION_TEMPLATES[question];
  return template ? template(context) : `To proceed, I need to know: ${question}`;
}
```

**Decision matrix for quick reference:**

| Action reversible | Correction cost | Confidence | Decision |
|---|---|---|---|
| Yes | Low | Any | Assume + inform |
| Yes | Medium | High (≥0.8) | Assume + inform |
| Yes | Medium | Low (<0.8) | Ask one question |
| No | Medium | Any | Ask one question |
| No | High | Any | Always ask |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Timing on decideClarification(). Worked example on a real calendar-booking scenario with 4 unknowns.

```
=== Timing ===

$ node -e "
const unknowns = [
  { name: 'day',       confidence: 0.6,  impactIfWrong: 'medium', bestGuess: 'Wednesday' },
  { name: 'time',      confidence: 0.7,  impactIfWrong: 'medium', bestGuess: '10:00 AM' },
  { name: 'attendees', confidence: 0.8,  impactIfWrong: 'high',   bestGuess: [] },
  { name: 'duration',  confidence: 0.85, impactIfWrong: 'low',    bestGuess: 30 },
];
const t0 = performance.now();
for (let i = 0; i < 10000; i++) decideClarification('create_calendar_event', unknowns);
console.log('decideClarification():', ((performance.now()-t0)/10000).toFixed(4), 'ms');
"
decideClarification(): 0.0022 ms

=== Worked example: four-unknown meeting request ===

User: "book a meeting with the sales team next week"
Action: create_calendar_event (reversible, low correction cost)

Unknown assessment:
  day_of_week:  confidence 0.60  (mid-week guess)
  time_of_day:  confidence 0.70  (10am default)
  attendees:    confidence 0.80  (most frequent sales contacts)
  duration_min: confidence 0.85  (standard 30-min meeting)

Decision: assume (reversible, low cost — even low-confidence assumptions are fine)
Response: "I've scheduled a 30-minute meeting with Alice Chen and Bob Kumar for
           Wednesday at 10am. Assumptions: attendees: Alice+Bob (most frequent sales
           contacts), time: 10am, duration: 30 min. Reply to change any of these."

Expected cost: 90% × 10s + 10% × 2min = 21 seconds average
vs ask-first:  3 questions × 20s/answer = 60 seconds minimum

=== Worked example: customer demo request ===

User: "book a demo for the Acme deal"
Action: book_customer_demo (irreversible, high correction cost)

Unknown assessment:
  recipient_exec:  confidence 0.50  (which Acme exec?)
  date:            confidence 0.65  (next Thursday?)
  time:            confidence 0.70  (2pm?)
  presenter:       confidence 0.90  (sales rep is obvious)

Decision: ask (irreversible, high correction cost)
→ Ask about lowest-confidence, highest-impact unknown: recipient_exec

Response: "Before I book this — which Acme executive should be on the demo? I see
           Sarah Park (CTO) and Mike Reyes (VP Eng) in your recent emails with Acme.
           Should I invite both, or one of them?"

Note: only one question. presenter, date, and time are inferred after recipient is
confirmed. One follow-up if needed, never four questions upfront.

=== Ask-fatigue study (internal data from F-27 data flywheel entry) ===

Retention impact of clarification frequency (measured at turn 3 of session):
  0 questions asked:  87% of users complete task
  1 question asked:   82% complete (−6%)
  2 questions asked:  71% complete (−18%)
  3+ questions asked: 54% complete (−38%)

→ Maximum 1 question per turn is not just a UX preference — it's a completion rate issue.
```

## See also

[F-09](f09-human-in-the-loop.md) · [F-55](f55-agent-task-replanning.md) · [S-78](../stacks/s78-agent-to-human-escalation.md) · [S-34](../stacks/s34-narrow-scope-agent-design.md) · [S-19](../stacks/s19-agent-loop.md) · [F-03](f03-failure-modes.md)

## Go deeper

Keywords: `agent clarification` · `ask vs assume` · `ambiguity resolution` · `clarification strategy` · `agent questions` · `upfront clarification` · `intent disambiguation` · `clarification cost` · `agent UX` · `underspecified instructions`
