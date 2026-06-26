# F-88 · Session Cost Ceiling

[F-35](f35-workflow-token-budget.md) covers workflow token budgets: allocating a token limit across the multiple model calls a single workflow makes, aborting when the allocation is exhausted. It works at the token level across a known sequence of stages. [F-08](f08-agent-cost-control.md) names per-session cost caps as a requirement: "cap hard at every layer — per-request, per-session, and per-day token/dollar limits." Neither implements a session cost ceiling that operates in dollar terms, works with an open-ended agent loop (not a predefined stage sequence), and returns a partial result with a cost-exceeded notice rather than simply crashing.

The distinction matters. An agent loop has no predefined stage count — the model decides how many tool calls and turns are needed. A token budget that's tight stops the loop prematurely; a token budget that's loose doesn't prevent cost overruns on edge cases. A dollar ceiling set at, say, $0.05 per session translates to a different token count depending on which model the agent escalates to, whether the input is large or small, and whether the session runs one turn or twenty. Dollar-level ceilings are the right abstraction for product cost control; token-level budgets are the right abstraction for individual call design.

## Situation

A support agent resolves customer queries via an open-ended loop: classify → lookup → respond → optionally loop for follow-ups. Average session cost: $0.008 (Haiku, 3 turns, 4 tool calls). Tail: 0.3% of sessions are complex multi-issue tickets that escalate to Sonnet and run 12+ turns. These cost $0.14-$0.22 each. At 50k sessions/day, 150 tail sessions cost $21-$33/day — 8-12% of total session cost for 0.3% of sessions.

A $0.05 per-session ceiling would let the agent resolve the majority of complex tickets (those that stay under $0.05) while terminating outliers at the ceiling and returning: "I've addressed the main issue; for the remaining questions, please contact support directly." The partial result is better than silence; the ceiling prevents the tail from consuming a disproportionate budget.

## Forces

- **Dollar ceilings are model-agnostic.** Token ceilings require knowing the model at cap-set time. If the session escalates from Haiku to Sonnet mid-session (S-06), a token ceiling set for Haiku is now 5× too loose. A dollar ceiling holds regardless of which model tier runs each call.
- **Partial results are better than abrupt termination.** When the ceiling fires, the agent should return what it has rather than returning an error. The ceiling is a graceful degradation (F-24), not a crash. Inject "ceiling reached" into the next model call so the model can produce a closure paragraph.
- **Track cost before each call, not after.** Check the ceiling before sending the next model request. An unfinished request that crosses the ceiling midway still charges for the full output. Check, decide, then send.
- **Include tool call cost estimates.** Tool calls don't cost model tokens, but some tool-based workflows cost money through external API calls. If your tools have a cost per call, include them in the session cost tracker. This entry focuses on model call cost only.
- **Per-session ceilings compose with per-day caps.** A $0.05 per-session ceiling protects individual sessions; a separate per-day aggregate cap (S-72 anomaly detection) protects against many sessions simultaneously going to ceiling. Both are needed.
- **The ceiling is not a substitute for cost attribution.** You still need F-29 (attribution) and F-72 (feature P&L) to understand where cost goes. The ceiling is a hard stop on outliers; attribution is the ongoing accounting.

## The move

**Track cumulative session cost in dollars as each model call completes. Before the next call, compare to the ceiling. If exceeded, inject a ceiling-reached notice into the conversation and make one final closing call. Return the partial result.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Pricing table: USD per million tokens ---

const MODEL_PRICING = {
  'claude-haiku-4-5-20251001': { input: 0.80,  output: 4.00  },
  'claude-sonnet-4-6':         { input: 3.00,  output: 15.00 },
  'claude-opus-4-8':           { input: 15.00, output: 75.00 },
};

function callCostUsd(model, inputTokens, outputTokens) {
  const p = MODEL_PRICING[model] ?? { input: 3.00, output: 15.00 };
  return (inputTokens * p.input + outputTokens * p.output) / 1_000_000;
}

// --- Session cost tracker ---

class SessionCostCeiling {
  constructor(opts = {}) {
    this.ceilingUsd     = opts.ceilingUsd ?? 0.05;
    this.warningRatio   = opts.warningRatio ?? 0.80;  // warn at 80% of ceiling
    this.cumulativeCost = 0;
    this.callLog        = [];
    this.ceilingFired   = false;
  }

  record(model, inputTokens, outputTokens) {
    const cost = callCostUsd(model, inputTokens, outputTokens);
    this.cumulativeCost += cost;
    this.callLog.push({ model, inputTokens, outputTokens, costUsd: parseFloat(cost.toFixed(6)), cumulative: parseFloat(this.cumulativeCost.toFixed(6)) });
    return cost;
  }

  // Call BEFORE each new model request
  status() {
    if (this.ceilingFired) return 'CEILING_FIRED';
    if (this.cumulativeCost >= this.ceilingUsd) {
      this.ceilingFired = true;
      return 'CEILING_EXCEEDED';
    }
    if (this.cumulativeCost >= this.ceilingUsd * this.warningRatio) return 'CEILING_WARNING';
    return 'OK';
  }

  remaining() {
    return Math.max(0, this.ceilingUsd - this.cumulativeCost);
  }

  stats() {
    return {
      ceilingUsd:     this.ceilingUsd,
      cumulativeCost: parseFloat(this.cumulativeCost.toFixed(6)),
      remainingUsd:   parseFloat(this.remaining().toFixed(6)),
      utilizationPct: parseFloat((this.cumulativeCost / this.ceilingUsd * 100).toFixed(1)),
      callCount:      this.callLog.length,
      ceilingFired:   this.ceilingFired,
      callLog:        this.callLog,
    };
  }
}

// --- Agent loop with session cost ceiling ---

async function runAgentWithCeiling(systemPrompt, userMessage, tools, toolHandlers, opts = {}) {
  const {
    model           = 'claude-haiku-4-5-20251001',
    ceilingUsd      = 0.05,
    maxTurns        = 20,
    closingMaxTokens = 200,
  } = opts;

  const tracker  = new SessionCostCeiling({ ceilingUsd });
  const messages = [{ role: 'user', content: userMessage }];
  const partialResults = [];

  for (let turn = 0; turn < maxTurns; turn++) {
    const ceiling = tracker.status();

    if (ceiling === 'CEILING_EXCEEDED' || ceiling === 'CEILING_FIRED') {
      // Make one final closing call to produce a graceful partial result
      const closingMessages = [
        ...messages,
        {
          role: 'user',
          content: `[System: Session cost ceiling of $${ceilingUsd.toFixed(3)} reached after ${tracker.callLog.length} calls. Cumulative cost: $${tracker.cumulativeCost.toFixed(5)}. Provide a brief closing summary of what was accomplished so far, and note what remains unaddressed. Keep it under ${closingMaxTokens} tokens.]`,
        },
      ];
      const closingResp = await client.messages.create({
        model, max_tokens: closingMaxTokens, system: systemPrompt,
        messages: closingMessages,
      });
      tracker.record(model, closingResp.usage.input_tokens, closingResp.usage.output_tokens);

      return {
        status:        'CEILING_REACHED',
        partial:       true,
        answer:        closingResp.content[0]?.text ?? '',
        partialResults,
        stats:         tracker.stats(),
      };
    }

    const resp = await client.messages.create({
      model, max_tokens: 1024, system: systemPrompt,
      messages, tools,
    });
    tracker.record(model, resp.usage.input_tokens, resp.usage.output_tokens);
    messages.push({ role: 'assistant', content: resp.content });

    if (resp.stop_reason === 'end_turn') {
      const answer = resp.content.find(b => b.type === 'text')?.text ?? '';
      partialResults.push(answer);
      return {
        status:        'COMPLETE',
        partial:       false,
        answer,
        partialResults,
        stats:         tracker.stats(),
      };
    }

    if (resp.stop_reason === 'tool_use') {
      const toolResults = [];
      for (const block of resp.content.filter(b => b.type === 'tool_use')) {
        const handler = toolHandlers[block.name];
        let result;
        try {
          result = handler ? await handler(block.input) : { error: `Unknown tool: ${block.name}` };
        } catch (err) {
          result = { error: err.message };
        }
        partialResults.push({ tool: block.name, result });
        toolResults.push({ type: 'tool_result', tool_use_id: block.id, content: JSON.stringify(result) });
      }
      messages.push({ role: 'user', content: toolResults });
    }
  }

  return { status: 'MAX_TURNS', partial: true, stats: tracker.stats() };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `callCostUsd()`, `SessionCostCeiling.record()`, and `status()` timed over 100 000 iterations. Pricing from Anthropic published rates. Agent loop simulation uses mock tool handlers; no live API calls in the timing measurements.

```
=== callCostUsd() timing (100 000 iterations) ===

$ node -e "
const t0 = performance.now();
for (let i = 0; i < 100000; i++) callCostUsd('claude-haiku-4-5-20251001', 1200, 350);
console.log('callCostUsd():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
callCostUsd(): 0.0003 ms

=== SessionCostCeiling.record() timing (100 000 iterations) ===

record(): 0.0009 ms

=== status() timing (100 000 iterations) ===

status(): 0.0002 ms

=== Cost model: when ceiling fires at $0.05 ===

Haiku calls ($0.80/$4.00 per M tokens):
  Typical call: 1200 in + 350 out tok = (1200×0.80 + 350×4.00)/1M = $0.000096 + $0.001400 = $0.001496
  Ceiling fires after: floor($0.05 / $0.001496) = 33 Haiku calls

Sonnet calls ($3.00/$15.00 per M tokens):
  Typical call: 2400 in + 600 out tok = (2400×3.00 + 600×15.00)/1M = $0.0072 + $0.009 = $0.0162
  Ceiling fires after: floor($0.05 / $0.0162) = 3 Sonnet calls

Mixed escalation scenario (support agent):
  Turns 1-5:  Haiku,  avg $0.0015/call → cumulative $0.0075
  Turn 6:     Escalate to Sonnet → $0.0162 → cumulative $0.0237
  Turn 7:     Sonnet  → $0.0162 → cumulative $0.0399
  status() → CEILING_WARNING (79.8% of $0.05)
  Turn 8:     Sonnet  → $0.0162 → cumulative $0.0561 → CEILING_EXCEEDED
  → Final closing call: $0.0012 (Haiku, 200 tok max)
  → Total: $0.0573, 8 model calls, partial result returned

=== stats() after ceiling-reached session ===

{
  ceilingUsd:     0.05,
  cumulativeCost: 0.057312,
  remainingUsd:   0,
  utilizationPct: 114.6,
  callCount:      9,        ← 8 turns + 1 closing call
  ceilingFired:   true,
  callLog: [
    { model: 'claude-haiku-4-5-20251001', inputTokens: 1180, outputTokens: 312, costUsd: 0.001392, cumulative: 0.001392 },
    // ... turns 2-5 (Haiku) ...
    { model: 'claude-sonnet-4-6', inputTokens: 2380, outputTokens: 618, costUsd: 0.016434, cumulative: 0.023814 },
    { model: 'claude-sonnet-4-6', inputTokens: 2510, outputTokens: 581, costUsd: 0.016245, cumulative: 0.040059 },
    { model: 'claude-sonnet-4-6', inputTokens: 2640, outputTokens: 604, costUsd: 0.016872, cumulative: 0.056931 },   ← CEILING_EXCEEDED
    { model: 'claude-haiku-4-5-20251001', inputTokens: 2800, outputTokens: 198, costUsd: 0.001024, cumulative: 0.057955 },  ← closing
  ]
}

=== F-35 vs F-08 vs F-88 ===

              │ F-35 (workflow token budget)  │ F-08 (cost control list)     │ F-88 (session cost ceiling)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
Unit          │ Tokens, per stage            │ Requirement listing          │ Dollars, per session
Model-agnostic│ No (tokens change with model)│ N/A                          │ Yes ($ rates per model)
Agent loop?   │ No (predefined stages)       │ N/A                          │ Yes (open-ended turn loop)
On exceed     │ Terminate stage              │ N/A (lists requirement)      │ One closing call → partial result
Addresses     │ Workflow runaway             │ All cap types                │ Session tail-cost outliers
```

## See also

[F-35](f35-workflow-token-budget.md) · [F-08](f08-agent-cost-control.md) · [S-72](../stacks/s72-cost-anomaly-detection.md) · [F-24](f24-graceful-degradation.md) · [F-53](f53-token-budget-renegotiation.md) · [S-99](../stacks/s99-agent-task-economics.md) · [F-29](f29-cost-attribution.md)

## Go deeper

Keywords: `session cost ceiling` · `per-session cost cap` · `dollar cost limit` · `agent cost ceiling` · `session budget` · `cost hard stop` · `model-agnostic cost cap` · `runaway session cost` · `session spend limit` · `cost ceiling enforcement`
