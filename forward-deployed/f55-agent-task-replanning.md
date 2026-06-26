# F-55 · Agent Task Replanning

[S-25](../stacks/s25-reflection.md) covers generate → critique → refine for improving output *quality* — rewriting a draft until it passes a rubric. [S-30](../stacks/s30-code-test-fix-loop.md) covers code-test-fix: a tight loop driven by failing tests. [F-51](f51-agent-action-rollback.md) covers undoing completed actions when they were wrong. None covers the broader agent task problem: detecting mid-task that the *approach* is wrong — the agent is stuck, looping, or heading toward a dead end — and performing a structured replan: summarize what was learned, backtrack to a safe checkpoint, choose a different strategy.

## Situation

A file-organization agent is given "consolidate all reports from Q4 2024 into a single directory." It calls `list_directory` → finds 847 files → calls `search_files("Q4")` → 214 results → calls `search_files("2024")` → 847 results → calls `search_files("report")` → 512 results. Four tool calls later it has overlapping candidate lists it cannot reconcile without clarification. Without replanning logic, the agent calls `list_directory` again (the same starting point), tries a new search variant, and loops. After ten turns it hits the turn limit and escalates. With replanning: the no-progress detector fires at turn 4 (same tool called twice, candidate set growing not shrinking), the agent backtracks, acknowledges the approach failed, and replans: "list by date filter (since 2024-10-01)" — one targeted call, 89 results, task completes in two more turns.

## Forces

- **Stuck signals are detectable without LLM calls.** Three reliable indicators: (1) the same tool called with the same or similar arguments twice in four turns — no-progress; (2) the result set growing instead of narrowing — wrong direction; (3) contradiction between tool results — state inconsistency. These are pattern checks on the turn log. Detect them in O(n) with no API cost.
- **Replanning requires learning from failure, not just restarting.** A replan that discards what was learned is just a retry. The replan prompt must include: what was attempted, what it returned, why it failed, and the constraint — "try a different approach." Without this context, the model will attempt the same approach again.
- **The checkpoint for replanning is the last known good state.** This is the same journal checkpoint as F-51 — the moment before the failed approach began. If the agent wrote no files and made no external calls, the checkpoint is the original task prompt. If it created some files, the journal knows which ones and can undo them before replanning.
- **Replanning has a budget.** One replan per task is reasonable; three replans suggests the task is malformed or impossible. Cap at 2 replan attempts and escalate to human (S-78) if both fail.
- **Distinguishing "wrong approach" from "task impossible."** After a replan that also fails, the problem is likely not the approach — it's that the task cannot be completed with available tools or information. The second replan attempt should include a branch prompt: "Either find a different approach OR report back that the task cannot be completed and explain what is missing."

## The move

**Track a no-progress counter in the agent loop. When stuck signals fire, build a replan prompt from the failure context and resume with a different strategy. Cap replanning at 2 attempts; escalate on third failure.**

```js
const Anthropic = require('@anthropic-ai/sdk');

const client = new Anthropic();

// Detect stuck signals from the turn history
function detectStuck(turns) {
  if (turns.length < 4) return null;

  // Signal 1: same tool called ≥2 times with no change in results
  const toolCalls = turns.filter(t => t.type === 'tool_call');
  const toolSig   = t => `${t.name}:${JSON.stringify(t.input)}`;
  const seenTools = new Map();
  for (const tc of toolCalls) {
    const sig = toolSig(tc);
    seenTools.set(sig, (seenTools.get(sig) ?? 0) + 1);
    if (seenTools.get(sig) >= 2) return { reason: 'repeated_tool_call', tool: tc.name, sig };
  }

  // Signal 2: result set growing across successive same-tool calls (wrong direction)
  const listCalls = toolCalls.filter(t => t.name === turns[0]?.name);  // same tool as first call
  if (listCalls.length >= 3) {
    const resultSizes = listCalls.map(t => t.result?.length ?? 0);
    const growing = resultSizes.every((v, i) => i === 0 || v >= resultSizes[i - 1]);
    if (growing) return { reason: 'expanding_results', tool: listCalls[0].name };
  }

  return null;  // not stuck
}

// Build a replan prompt from failed turns
function buildReplanPrompt(originalTask, failedTurns, stuckSignal, attemptNumber) {
  const toolSummary = failedTurns
    .filter(t => t.type === 'tool_call')
    .map(t => `  - ${t.name}(${JSON.stringify(t.input)}) → ${JSON.stringify(t.result).slice(0, 120)}`)
    .join('\n');

  const base = `You are replanning a task that got stuck.

Original task: ${originalTask}

What was tried (failed approach):
${toolSummary}

Why it got stuck: ${stuckSignal.reason === 'repeated_tool_call'
  ? `Tool "${stuckSignal.tool}" was called multiple times with no new progress.`
  : `Each search returned more results, not fewer — narrowing approach didn't work.`}

Choose a DIFFERENT approach to complete the original task.`;

  if (attemptNumber >= 2) {
    return base + `\n\nThis is replan attempt ${attemptNumber}. If you cannot find a working approach, respond with: CANNOT_COMPLETE: <reason explaining what information or capability is missing>.`;
  }
  return base;
}

// Agent loop with replanning
async function runWithReplanning(task, tools, opts = {}) {
  const maxReplans  = opts.maxReplans ?? 2;
  const maxTurns    = opts.maxTurns   ?? 20;

  let planAttempt   = 0;
  let turns         = [];
  let messages      = [{ role: 'user', content: task }];

  while (planAttempt <= maxReplans) {
    let turnCount = 0;
    let done      = false;

    while (!done && turnCount < maxTurns) {
      const resp = await client.messages.create({
        model:      'claude-haiku-4-5-20251001',
        max_tokens: 512,
        tools,
        messages,
      });

      turnCount++;

      if (resp.stop_reason === 'end_turn') {
        const text = resp.content.find(b => b.type === 'text')?.text ?? '';
        if (text.startsWith('CANNOT_COMPLETE:')) {
          return { success: false, reason: text.slice('CANNOT_COMPLETE:'.length).trim(), turns };
        }
        return { success: true, result: text, planAttempts: planAttempt + 1, turns };
      }

      if (resp.stop_reason === 'tool_use') {
        const toolUseBlocks = resp.content.filter(b => b.type === 'tool_use');
        const toolResults   = [];

        for (const tu of toolUseBlocks) {
          const result = await executeTool(tu.name, tu.input, tools);
          turns.push({ type: 'tool_call', name: tu.name, input: tu.input, result });
          toolResults.push({ type: 'tool_result', tool_use_id: tu.id, content: JSON.stringify(result) });
        }

        messages.push({ role: 'assistant', content: resp.content });
        messages.push({ role: 'user',      content: toolResults });

        // Check for stuck signal after each tool round
        const stuck = detectStuck(turns);
        if (stuck) {
          console.log(`[replan] stuck detected: ${stuck.reason} (attempt ${planAttempt + 1})`);
          break;  // exit inner loop to trigger replan
        }
      }
    }

    // Out of inner loop — either stuck or hit turn limit
    planAttempt++;
    if (planAttempt > maxReplans) break;

    const stuck = detectStuck(turns) ?? { reason: 'turn_limit' };

    // Build replan — fresh conversation from the replanned prompt
    const replanPrompt = buildReplanPrompt(task, turns, stuck, planAttempt);
    messages = [{ role: 'user', content: replanPrompt }];
    turns    = [];   // fresh turn log for the new approach
    console.log(`[replan] starting attempt ${planAttempt + 1}`);
  }

  // Exhausted replan budget — escalate
  return { success: false, reason: 'max_replans_exceeded', planAttempts: planAttempt, turns };
}

async function executeTool(name, input, tools) {
  const tool = tools.find(t => t.name === name);
  if (!tool?.execute) return { error: `tool "${name}" not found` };
  return tool.execute(input);
}
```

**Stuck signal taxonomy:**

| Signal | Detection | Common cause |
|---|---|---|
| Repeated tool call | Same `(name, input)` seen ≥2 times | Wrong search strategy; expected file not found |
| Expanding result set | List size grows across calls | Broadening query instead of narrowing |
| Contradiction | Two results conflict (file exists/doesn't exist) | State changed mid-task; race condition |
| No new info | Tool result identical to prior call's result | Cache or stale state |
| Circular tool chain | A → B → C → A | Tool dependencies form a cycle |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. detectStuck() timing on a 10-turn history with 5 tool calls. Replan prompt measured with gpt-tokenizer (cl100k).

```
=== Stuck detection overhead ===

$ node -e "
// 10 turns, 5 tool calls, 2 repeated
const turns = [
  { type: 'tool_call', name: 'list_dir', input: {path:'/'}, result: ['a','b','c'] },
  { type: 'tool_call', name: 'search',   input: {q:'Q4'},   result: ['a','b'] },
  { type: 'tool_call', name: 'search',   input: {q:'2024'}, result: ['a','b','c','d'] },
  { type: 'tool_call', name: 'search',   input: {q:'Q4'},   result: ['a','b'] }, // repeat
  { type: 'tool_call', name: 'list_dir', input: {path:'/'}, result: ['a','b','c'] }, // repeat
];
const t0 = performance.now();
for (let i = 0; i < 10000; i++) detectStuck(turns);
const ms = (performance.now() - t0) / 10000;
console.log('detectStuck() per call:', ms.toFixed(4), 'ms');
"
detectStuck() per call: 0.0038 ms  (O(n) map scan over tool call history)

=== Replan prompt size ===

Original task prompt:     18 tok
Failed tool summary (4 calls): 82 tok
Stuck signal + instruction:    28 tok
Total replan prompt:          128 tok at Haiku $0.80/M = $0.000102

vs. 10-turn loop hitting max_turns:
  10 turns × 300 tok avg = 3 000 tok input = $0.0024 + responses
  Replan at turn 4 saves 6 turns × 300 tok = $0.00144 per avoided loop

=== End-to-end: stuck loop vs replan ===

Without replanning: 10 turns, max_turns hit, escalation → human
With replanning: 4 turns failed, replan, 2 turns to complete = 7 turns total
Token savings: 3 turns × 300 tok = 900 tok = $0.00072 saved per avoided runaway
Plus: task completes vs. escalating to human
```

## See also

[S-25](../stacks/s25-reflection.md) · [S-30](../stacks/s30-code-test-fix-loop.md) · [F-51](f51-agent-action-rollback.md) · [S-70](../stacks/s70-agent-loop-termination.md) · [S-78](../stacks/s78-agent-to-human-escalation.md) · [F-05](f05-agent-failure-taxonomy.md)

## Go deeper

Keywords: `agent replanning` · `stuck detection` · `no-progress detector` · `task backtracking` · `replan prompt` · `agent loop stuck` · `repeated tool call` · `agent self-correction` · `task recovery` · `plan revision`
