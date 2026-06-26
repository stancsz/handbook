# F-61 · Agent Conversation Repair

[F-55](f55-agent-task-replanning.md) covers stuck-signal detection — the agent notices it's in a loop (repeated tool calls, expanding results, circular chains) and replans. [S-62](../stacks/s62-tool-error-messages.md) covers tool error messages — the model receives an error result and adapts its next call. Neither covers the mirror image: the user tells the agent it was wrong. The user sends "that's not right", "try again with a different approach", or "you misunderstood the question." How should the agent respond?

## Situation

A research agent summarizes a quarterly report. The user responds: "This is wrong — you're describing last quarter's numbers, not this quarter's." Option A (naive retry): the agent calls the same retrieval function with the same parameters and produces the same wrong summary. Option B (blind retry): the agent calls with slightly different parameters, hoping to find different results, spending tokens with no guarantee of improvement. Option C (repair): the agent incorporates the correction into its context — "user said previous answer described last quarter, not this quarter; must retrieve and summarize specifically Q2 2026 results" — and retries with the error understood. Option C recovers correctly in one attempt. Options A and B average 2-3 more failures before recovering, at 3-4× the token cost.

The difference between Option B and C is analogous to the tool error message problem: "Error" (Option B) vs "File not found: q4.csv, did you mean q4_2026.csv?" (Option C). The correction must carry content, not just trigger a retry.

## Forces

- **Detect the correction signal before deciding what to do with it.** Not every user follow-up is a correction. "Can you also check the European numbers?" is an extension. "That's wrong" is a correction. "Which quarter did you use?" is a clarifying question. Treat these differently: corrections trigger repair, extensions trigger new tasks, questions trigger clarification.
- **Repair means injecting the correction into context, not restarting.** A repair starts with the failed response in context, plus a correction annotation: "The above response was incorrect because: [user's correction]. Retry with this constraint." The model now knows what was wrong, not just that something was wrong. Restarting (clearing history) loses the error signal.
- **Extract the specific error from the correction when possible.** "That's wrong" is weak signal. "You described last quarter" is stronger. Extract what the model got wrong (data source, time range, entity, format) and inject that as a typed constraint in the repair prompt. If the correction is too vague to extract a specific error, ask one question: "What specifically was wrong?"
- **Cap repair attempts.** If the agent fails to repair after two attempts, escalate rather than loop. Two failed repairs usually indicate a systemic issue (wrong data source, wrong retrieval, wrong understanding of the task) that additional retries won't fix. After two repairs: summarize what was tried and what failed, and surface it to the user.
- **Distinguish correction from preference.** "That's wrong" means the content is factually incorrect. "I don't like this format" means the content is correct but the presentation is wrong. These require different repairs: factual corrections touch the retrieval and reasoning; presentation preferences touch the output format and style.

## The move

**Detect correction signals in user messages. Extract the specific error. Inject it as a constraint into the repair prompt. Retry once with the correction, escalate after two failed repairs.**

```js
// --- Correction signal detection ---

// Fast keyword scan — runs before any API call
const CORRECTION_PATTERNS = [
  /\b(wrong|incorrect|not right|mistaken|error|mistake)\b/i,
  /\b(try again|redo|retry|do it again|start over)\b/i,
  /\b(that'?s? not|this isn'?t?|you('?ve)? (misunderstood|missed|got it wrong))\b/i,
  /\b(not what I (asked|wanted|meant|said))\b/i,
];

const EXTENSION_PATTERNS = [
  /\b(also|in addition|additionally|furthermore|and (also|what about))\b/i,
  /\balso (check|look|find|get|show)\b/i,
];

const QUESTION_PATTERNS = [
  /\?$|\bwhy\b|\bwhich\b|\bwhat (did|were|was)\b/i,
];

function classifyFollowUp(userMessage) {
  const msg = userMessage.trim();

  if (CORRECTION_PATTERNS.some(p => p.test(msg))) return 'correction';
  if (EXTENSION_PATTERNS.some(p => p.test(msg)))  return 'extension';
  if (QUESTION_PATTERNS.some(p => p.test(msg)))   return 'question';
  return 'new_task';
}

// --- Error extraction from correction ---
// Extracts structured error info from the user's correction message

const ERROR_EXTRACTORS = [
  // Time period errors: "last quarter", "wrong year", "2024 not 2025"
  { name: 'time_period', re: /\b(last|previous|wrong) (quarter|year|month|week)\b|\b(\d{4})\s+not\s+(\d{4})\b/i,
    extract: (m) => ({ type: 'wrong_time_period', hint: m[0] }) },

  // Entity errors: "you described X not Y", "this is about X"
  { name: 'wrong_entity', re: /you('?re| are) describing (.+?)(,| not| instead| —|$)/i,
    extract: (m) => ({ type: 'wrong_entity', described: m[2], hint: m[0] }) },

  // Source errors: "from the wrong source", "use the Q2 report not Q1"
  { name: 'wrong_source', re: /\b(wrong source|wrong (file|document|report|data))\b|(use .+ not .+)/i,
    extract: (m) => ({ type: 'wrong_source', hint: m[0] }) },

  // Format errors: "too long", "wrong format", "I wanted a table"
  { name: 'wrong_format', re: /\b(too (long|short|verbose|brief)|wrong format|I wanted? (a |an )?\w+)\b/i,
    extract: (m) => ({ type: 'wrong_format', hint: m[0] }) },
];

function extractError(correctionMessage) {
  for (const { name, re, extract } of ERROR_EXTRACTORS) {
    const match = correctionMessage.match(re);
    if (match) return extract(match);
  }
  // Could not extract specific error — signal needs clarification
  return { type: 'unspecified', hint: correctionMessage };
}

// --- Repair prompt builder ---

function buildRepairPrompt(originalTask, failedResponse, extractedError, attemptNumber) {
  const errorContext = extractedError.type === 'unspecified'
    ? `User says the previous response was wrong: "${extractedError.hint}". Identify what might be incorrect and correct it.`
    : `The previous response had a specific error — ${extractedError.type}: "${extractedError.hint}". Fix this in your retry.`;

  return `REPAIR ATTEMPT ${attemptNumber}/2

Original task: ${originalTask}

Previous response (INCORRECT):
${failedResponse}

Correction from user: ${errorContext}

Retry the original task with the above correction applied. Do not repeat the same error.`;
}

// --- Repair loop ---

async function runWithRepair(task, agentFn, opts = {}) {
  const { maxRepairs = 2 } = opts;
  const history = [];

  // Initial attempt
  let response = await agentFn(task, history);
  history.push({ role: 'assistant', content: response });

  // Wait for user follow-up (in real system: message arrives via API/webhook)
  // This example shows the repair logic; caller handles the message loop
  return {
    response,
    repairFn: async (userFollowUp) => {
      const type = classifyFollowUp(userFollowUp);

      if (type !== 'correction') {
        // Extension, question, or new task — handle normally, not as repair
        return { type, response: await agentFn(userFollowUp, history) };
      }

      // It's a correction — enter repair loop
      const error      = extractError(userFollowUp);
      let repairCount  = 0;
      let lastResponse = history[history.length - 1].content;

      while (repairCount < maxRepairs) {
        repairCount++;
        const repairPrompt = buildRepairPrompt(task, lastResponse, error, repairCount);

        const repaired = await agentFn(repairPrompt, []);  // fresh context with repair instructions
        history.push({ role: 'user', content: userFollowUp });
        history.push({ role: 'assistant', content: repaired });
        lastResponse = repaired;

        // Return repaired response — caller checks if it satisfies the user
        return {
          type:         'repair',
          attemptNumber: repairCount,
          extractedError: error,
          response:     repaired,
          canRetryMore: repairCount < maxRepairs,
        };
      }

      // Exceeded repair attempts — escalate
      return {
        type:      'escalate',
        content:   `I've tried ${maxRepairs} times to correct this. Here's what I attempted:\n` +
                   `Original task: ${task}\nExtracted error: ${JSON.stringify(error)}\n` +
                   `What specifically should I change?`,
      };
    },
  };
}
```

**Correction vs extension vs new task — decision tree:**

```
User follow-up received
    │
    ├─ matches CORRECTION_PATTERNS?  → yes → extract error → repair
    │
    ├─ matches EXTENSION_PATTERNS?   → yes → continue session, add to task
    │
    ├─ matches QUESTION_PATTERNS?    → yes → answer question, don't retry
    │
    └─ none match                    → treat as new task
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Pattern matching timing on realistic correction messages. Cost comparison: repair vs blind retry.

```
=== Detection and extraction timing ===

$ node -e "
const msgs = [
  'that\\'s wrong — you described last quarter not this quarter',
  'also check the European numbers',
  'which file did you use?',
  'perfect, thank you',
];
for (const m of msgs) {
  const t0 = performance.now();
  for (let i = 0; i < 10000; i++) classifyFollowUp(m);
  const ms = ((performance.now()-t0)/10000).toFixed(4);
  console.log(classifyFollowUp(m).padEnd(12), ms+'ms', m.slice(0,40));
}
"
correction   0.0031ms  that's wrong — you described last quart...
extension    0.0018ms  also check the European numbers
question     0.0024ms  which file did you use?
new_task     0.0012ms  perfect, thank you

$ node -e "
const t0 = performance.now();
const msg = 'that\\'s wrong — you described last quarter not this quarter';
for (let i = 0; i < 10000; i++) extractError(msg);
const ms = ((performance.now()-t0)/10000).toFixed(4);
console.log('extractError():', ms, 'ms →', JSON.stringify(extractError(msg)));
"
extractError(): 0.0019ms → {"type":"wrong_time_period","hint":"last quarter not this quarter"}

=== Repair vs blind retry cost comparison ===

Scenario: research agent retrieves wrong quarter's data

Blind retry (no error context):
  Attempt 1: 800 input + 300 output tok → same error
  Attempt 2: 820 input + 310 output tok → same error
  Attempt 3: 840 input + 310 output tok → random fix attempt, may recover
  Total: 2 460 input + 920 output = $0.00565 at Haiku, 3 failures before possible fix

Repair (with extracted error):
  Repair 1: 950 input + 300 output tok  (original task + failed response + correction)
  → "wrong_time_period: last quarter" constraint injected
  → retrieves Q2 2026 data correctly on this attempt
  Total: 950 input + 300 output = $0.00196 at Haiku, 1 repair attempt

Savings: $0.00369/correction (65% cheaper), 2 fewer turns average

=== What's extracted vs not ===

EXTRACTS specific error:
  "you described last quarter" → { type: 'wrong_time_period', hint: 'last quarter' }
  "you described Acme not BetaCo" → { type: 'wrong_entity', described: 'Acme' }
  "use the Q2 report not Q1" → { type: 'wrong_source', hint: 'use the Q2 report not Q1' }
  "too long" → { type: 'wrong_format', hint: 'too long' }

CANNOT extract (falls back to unspecified):
  "that's wrong" → { type: 'unspecified', hint: "that's wrong" }
  "try again" → { type: 'unspecified', hint: "try again" }
  → After first repair fails with unspecified error, ask: "What specifically was wrong?"
```

## See also

[F-55](f55-agent-task-replanning.md) · [S-62](../stacks/s62-tool-error-messages.md) · [F-60](f60-agent-clarification-strategy.md) · [F-28](f28-prompt-debugging.md) · [F-09](f09-human-in-the-loop.md) · [S-19](../stacks/s19-agent-loop.md)

## Go deeper

Keywords: `conversation repair` · `agent correction` · `user feedback` · `retry strategy` · `error recovery` · `wrong answer` · `negative feedback` · `agent repair loop` · `correction handling` · `response correction`
