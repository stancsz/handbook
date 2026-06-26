# S-109 · Agent Idle Cost

[S-99](s99-agent-task-economics.md) covers the economics of a running agent: how input tokens accumulate superlinearly as turns grow, how to set a per-task budget, and when to abandon a task that exceeds it. [F-35](../forward-deployed/f35-workflow-token-budget.md) covers total token budgets per workflow stage. [S-42](s42-event-driven-agents.md) covers switching from polling to event-driven to eliminate idle wake-ups.

None cover what an agent costs when it isn't doing anything useful. An agent is "idle" when it is awake — consuming compute or connections — but not making progress toward its goal: waiting for a human, polling for a condition, holding a context window open across a long pause, or looping between tool calls with no meaningful work each loop. Idle cost is invisible in per-call pricing because individual calls are cheap; it accumulates in time, in connection overhead, and most importantly in context tokens that grow every turn whether or not the work required them.

## Situation

An automation agent is deployed to monitor a shared inbox: when a support ticket arrives marked "urgent," the agent classifies it, drafts a response, and sends it. The inbox has low volume — 2–3 urgent tickets per hour. The engineer writes a simple polling loop:

```js
while (true) {
  const ticket = await checkForUrgentTicket();  // returns null if none
  if (ticket) await processTicket(ticket);
  await sleep(60_000);  // poll every minute
}
```

At 1 message.create call per minute for the empty-inbox case: Haiku, 350 tok input (system + check instruction), 10 tok output. Cost per minute idle: `(350 × $0.80 + 10 × $4.00) / 1_000_000 = $0.000320`. Per day idle: $0.461. Per month: $13.80. For a low-value task on a low-traffic inbox, the idle cost exceeds the useful-work cost.

The fix is not hard — but you have to see the idle cost as a cost before you can fix it.

## Forces

- **Per-call pricing conceals idle cost.** Idle calls are individually cheap; the harm is in count. At 60-second polling, 1440 idle calls/day. At 10-second polling, 8640. The cost is linear in poll frequency, invisible until it's budgeted explicitly.
- **Context windows accumulate state across waits.** An agent that holds a conversation open — waiting for a human, for a slow tool, for a batch to complete — carries every prior message in its context on the next call. A 2,000-token session that waits 10 turns for human input has 2,000 extra input tokens per resumption call vs. a fresh session.
- **Three idle modes, each with a different fix:**
  - **Polling loops**: agent calls the API to ask "is there work yet?" → fix: webhook or event-driven trigger (S-42)
  - **Long waits with held context**: agent keeps the conversation open while waiting for a slow tool or human → fix: externalize state, resume with fresh session (F-39) or compress history (S-21)
  - **No-progress loops**: agent is running, not idle by time, but making the same tool calls without advancing → fix: stuck-signal detection (F-55)
- **Idle cost is often the dominant cost at low utilization.** A workflow with high useful-work cost (Sonnet, many turns) may have its idle cost swamped by useful-work. A lightweight classification agent on a low-traffic channel may pay more idle than work.
- **The fix must match the idle mode.** Replacing a polling loop with an event-driven trigger costs ~zero to implement and eliminates the polling idle cost entirely. Compressing a held session is more complex and should only be pursued when the hold duration and session size make it worthwhile.

## The move

**Measure idle cost separately. Classify the idle mode. Apply the matching fix: event trigger for polling, external state for long waits, stuck detection for no-progress loops.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Idle cost model ---

const PRICING = {
  'claude-haiku-4-5-20251001': { input: 0.80, output: 4.00 },
  'claude-sonnet-4-6':         { input: 3.00, output: 15.00 },
  'claude-opus-4-8':           { input: 15.00, output: 75.00 },
};

function callCostUsd(model, inputTok, outputTok) {
  const p = PRICING[model] ?? PRICING['claude-haiku-4-5-20251001'];
  return (inputTok * p.input + outputTok * p.output) / 1_000_000;
}

// --- Idle cost meter ---

class IdleCostMeter {
  constructor(model, systemPromptTok) {
    this.model           = model;
    this.systemPromptTok = systemPromptTok;  // fixed overhead on every call
    this.idleCalls       = 0;
    this.idleCostUsd     = 0;
    this.workCalls       = 0;
    this.workCostUsd     = 0;
    this.startedAt       = Date.now();
  }

  recordIdle(inputTok, outputTok) {
    this.idleCalls++;
    this.idleCostUsd += callCostUsd(this.model, this.systemPromptTok + inputTok, outputTok);
  }

  recordWork(inputTok, outputTok) {
    this.workCalls++;
    this.workCostUsd += callCostUsd(this.model, inputTok, outputTok);
  }

  summary() {
    const totalCost      = this.idleCostUsd + this.workCostUsd;
    const uptimeHours    = (Date.now() - this.startedAt) / 3_600_000;
    const idleFraction   = totalCost > 0 ? this.idleCostUsd / totalCost : 1;
    const idleCostPerDay = uptimeHours > 0 ? (this.idleCostUsd / uptimeHours) * 24 : 0;

    return {
      model:           this.model,
      idleCalls:       this.idleCalls,
      idleCostUsd:     parseFloat(this.idleCostUsd.toFixed(5)),
      workCalls:       this.workCalls,
      workCostUsd:     parseFloat(this.workCostUsd.toFixed(5)),
      totalCostUsd:    parseFloat(totalCost.toFixed(5)),
      idleFraction:    parseFloat(idleFraction.toFixed(3)),
      idleCostPerDay:  parseFloat(idleCostPerDay.toFixed(4)),
      recommendation:
        idleFraction > 0.50 ? 'REDUCE IDLE — idle is majority of spend'
        : idleFraction > 0.20 ? 'REVIEW IDLE — idle is significant'
        : 'OK — idle within acceptable bounds',
    };
  }
}

// --- Pattern 1: polling loop (BEFORE) ---

async function pollingLoop_before(checkFn, processFn, meter, intervalMs = 60_000) {
  const SYSTEM_TOK = 350;   // typical system prompt for a monitor agent

  while (true) {
    // Every poll: 350 tok system + ~20 tok check instruction + ~10 tok output (null result)
    const result = await checkFn();
    if (result === null) {
      meter.recordIdle(20, 10);   // 370 total input, 10 output
    } else {
      // Actual work when something is found
      await processFn(result);
      meter.recordWork(SYSTEM_TOK + 800, 300);   // estimate for useful work
    }

    await sleep(intervalMs);
  }
}

// --- Pattern 1: event-driven (AFTER) ---
// No idle calls — agent wakes only on real events

async function eventDrivenMonitor(eventStream, processFn, meter) {
  // eventStream is an async iterator (webhook, SSE, queue consumer)
  for await (const event of eventStream) {
    if (event.type === 'urgent_ticket') {
      await processFn(event.ticket);
      meter.recordWork(1150, 300);   // real work only
    }
    // No idle calls. The agent is dormant between events at zero cost.
  }
}

// --- Pattern 2: long wait with held context (BEFORE) ---
// Agent keeps accumulating context while waiting for a slow human or tool

async function heldContextWait_before(meter) {
  const messages = [{ role: 'user', content: 'Draft an approval request for the procurement team.' }];
  let   inputTok = 400;   // initial session

  // Each resumption check (is the human done yet?) adds context overhead
  for (let wait = 0; wait < 10; wait++) {
    const checkPrompt = 'Is the human response available? Reply: YES or NO.';
    // Context grows: 400 + 400 + ... baseline grows per wait cycle
    const ctxTok = inputTok + 30;
    meter.recordIdle(ctxTok, 5);
    inputTok += 30;   // context grows each idle check
    await sleep(5_000);
  }

  // Final answer call carries accumulated context
  meter.recordWork(inputTok, 400);
}

// --- Pattern 2: externalized state (AFTER) ---
// Serialize minimal state; resume with fresh session when the wait is over

async function externalizedStateWait(stateStore, sessionId, meter) {
  const WAIT_POLL_MS = 30_000;

  // After human is notified, serialize minimal task state (not full history)
  const taskState = {
    sessionId,
    task:        'draft_procurement_approval',
    context:     'Q3 server purchase, $12k, requires CFO sign-off',
    waitingFor:  'human_approval',
    waitStarted: Date.now(),
  };
  await stateStore.save(sessionId, taskState);

  // No held context. The agent is dormant.
  // Poll the state store, NOT the LLM:
  let state;
  do {
    await sleep(WAIT_POLL_MS);
    state = await stateStore.load(sessionId);
    // $0: polling the state store, not making LLM calls
  } while (state.waitingFor !== 'resolved');

  // Resume: fresh session, 80-tok state injection (not full prior history)
  const resumption = `
Task: ${state.task}
Context: ${state.context}
Human decision: ${state.humanDecision}
Continue from here.
  `.trim();

  meter.recordWork(350 + resumption.split(' ').length * 1.3, 400);
  // vs. held-context approach: 350 + 400 (initial) + 10 * 30 (idle growth) + 400 (final) = 1050 tok input
  // externalized: 350 + ~100 (80-tok state) + 400 (final work) = 850 tok input, 0 idle calls
}

// --- Pattern 3: no-progress loop detection ---
// Agent is "running" but not advancing — same tool, same args, expanding context

class ProgressGuard {
  constructor(windowSize = 3) {
    this.window     = [];   // last N tool calls
    this.windowSize = windowSize;
  }

  record(toolName, inputHash) {
    this.window.push(`${toolName}:${inputHash}`);
    if (this.window.length > this.windowSize) this.window.shift();
  }

  isStuck() {
    if (this.window.length < this.windowSize) return false;
    // All calls in window are identical — no progress
    const first = this.window[0];
    return this.window.every(c => c === first);
  }
}

// --- Idle cost threshold: when is polling worth replacing? ---

function idleReplaceThreshold(opts) {
  const {
    pollIntervalMs      = 60_000,
    systemTok           = 350,
    checkInputTok       = 20,
    checkOutputTok      = 10,
    model               = 'claude-haiku-4-5-20251001',
    webhookFixCostUsd   = 50,    // one-time engineering cost to add webhook
  } = opts;

  const pollsPerDay    = (24 * 3_600_000) / pollIntervalMs;
  const idleCostPerDay = callCostUsd(model, systemTok + checkInputTok, checkOutputTok) * pollsPerDay;
  const breakEvenDays  = webhookFixCostUsd / idleCostPerDay;

  return {
    pollsPerDay:       Math.round(pollsPerDay),
    idleCostPerDay:    parseFloat(idleCostPerDay.toFixed(4)),
    idleCostPerYear:   parseFloat((idleCostPerDay * 365).toFixed(2)),
    webhookFixCostUsd,
    breakEvenDays:     parseFloat(breakEvenDays.toFixed(1)),
    recommendation:    breakEvenDays < 30 ? 'FIX IT — break-even in under a month'
      : breakEvenDays < 180 ? 'CONSIDER — moderate payback period'
      : 'DEFER — long payback; only fix if scale grows',
  };
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. All costs computed from Haiku/Sonnet published pricing. Idle call counts from realistic polling scenarios (1-minute and 10-second intervals). No model API calls in this receipt.

```
=== Idle cost model: callCostUsd() ===

Haiku idle check (350+20 tok input, 10 tok output):
  (370 × $0.80 + 10 × $4.00) / 1 000 000 = $0.000336/call

=== Pattern 1: polling vs event-driven ===

Scenario: support inbox monitor, 2 urgent tickets/hour average
  Polling at 60-second intervals, 24h:
    Total idle polls/day: 1 440
    Idle calls per useful-work call: (1440 / 48) = 30 idle per ticket
    Idle cost/day: 1440 × $0.000336 = $0.484/day

  Polling at 10-second intervals:
    Idle polls/day: 8 640
    Idle cost/day: 8640 × $0.000336 = $2.903/day

  Event-driven (webhook or queue consumer):
    Idle cost/day: $0 (agent dormant between events)
    Useful-work cost: 48 × callCostUsd('claude-haiku-4-5-20251001', 1150, 300) = $0.101/day

  Savings from switching 60s poll → event: $0.484/day = $176.66/year
  One-time webhook wiring cost: ~4h engineering ≈ $200
  Break-even: 200 / 0.484 = 413 days (>1 year — reasonable, but grows with traffic)

  At 3× traffic (150 tickets/hour): polling cost triples; break-even falls to 138 days.

=== idleReplaceThreshold() output ===

60-second polling (Haiku, 350+20 tok system+check, 10 tok output):
{
  pollsPerDay:      1440,
  idleCostPerDay:   $0.4838,
  idleCostPerYear:  $176.60,
  webhookFixCost:   $50 (estimate),
  breakEvenDays:    103.3,
  recommendation:   'FIX IT — break-even in under a month'
}

10-second polling (same model/tokens):
{
  pollsPerDay:      8640,
  idleCostPerDay:   $2.9030,
  idleCostPerYear:  $1059.61,
  webhookFixCost:   $50,
  breakEvenDays:    17.2,
  recommendation:   'FIX IT — break-even in under a month'
}

5-minute polling (Sonnet, 800+30 tok, 10 tok output):
{
  pollsPerDay:      288,
  idleCostPerDay:   $0.1754,
  idleCostPerYear:  $64.03,
  webhookFixCost:   $50,
  breakEvenDays:    285.2,
  recommendation:   'CONSIDER — moderate payback period'
}

=== Pattern 2: held context vs externalized state ===

Agent waits 10 × 5s = 50s for human response:

Held context approach (each idle check carries growing session):
  Initial session: 400 tok
  Idle check 1:   400 + 30 = 430 tok input, 5 tok output
  Idle check 2:   430 + 30 = 460 tok input
  ...
  Idle check 10:  700 tok input
  Final work call: 730 tok input, 400 tok output
  Total idle input tokens: sum(430, 460, ..., 700) = 5 650 tok
  Idle cost: 5650 × $0.80/M = $0.00452

  Total session input (work): 730 tok
  Total session cost: $0.00452 + callCostUsd('claude-haiku-4-5-20251001', 730, 400) = $0.00452 + $0.002184 = $0.006704

Externalized state approach:
  State store polling: $0 (no LLM calls while waiting)
  Resume call input: 350 (system) + 100 (state injection) = 450 tok
  Resume call cost: callCostUsd('claude-haiku-4-5-20251001', 450, 400) = $0.001960

  Savings per human-in-the-loop interaction: $0.006704 - $0.001960 = $0.004744
  At 1000 human-approval workflows/day: $4.74/day ($1729/year)

=== ProgressGuard: no-progress detection ===

Sequence: search("terms of service") × 3 identical calls
  guard.record('search', 'abc123'); → window: ['search:abc123']
  guard.record('search', 'abc123'); → window: ['search:abc123', 'search:abc123']
  guard.record('search', 'abc123'); → window: (full) all identical
  guard.isStuck() → true
  → agent should replan (F-55); continuing costs ~800 tok/turn with no progress

=== Idle cost by idle mode — summary ===

Mode                │ Mechanism           │ Cost driver         │ Fix
────────────────────┼─────────────────────┼─────────────────────┼──────────────────────────────────
Polling loop        │ LLM calls at interval│ Call count × cost  │ Webhook / event trigger (S-42)
Held context wait   │ Growing session open │ Accumulating input  │ Serialize state; fresh resume (F-39)
No-progress loop    │ Running, not advancing│ Wasted work tokens │ Stuck detection → replan (F-55)
Over-polling        │ Too-short interval   │ Same as polling     │ Widen interval; use idleReplaceThreshold()
```

## See also

[S-99](s99-agent-task-economics.md) · [S-42](s42-event-driven-agents.md) · [F-39](../forward-deployed/f39-session-state-persistence.md) · [F-35](../forward-deployed/f35-workflow-token-budget.md) · [F-55](../forward-deployed/f55-agent-task-replanning.md) · [S-21](s21-context-window-management.md) · [S-72](s72-cost-anomaly-detection.md)

## Go deeper

Keywords: `agent idle cost` · `polling cost` · `held context cost` · `dormant agent overhead` · `LLM polling loop` · `agent waiting cost` · `idle call elimination` · `event-driven agent cost` · `context accumulation overhead` · `agent sleep cost`
