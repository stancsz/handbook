# S-157 · Context Carry Cost Tracker

[S-103](s103-cost-aware-context-management.md) computes the break-even point for compaction: compact when the marginal cost of the next full-context call exceeds the one-time cost of compacting. It answers *when* to compact. [F-95](../forward-deployed/f95-tool-invocation-cost-attribution.md) tracks cost per tool call. [F-108](../forward-deployed/f108-streaming-output-token-metering.md) meters output tokens during streaming.

None of these answer the question: *which specific messages* in the current conversation history cost the most to carry? Knowing that a session has become expensive is different from knowing why. A 10-turn session at $0.047 total input cost might have $0.0135 of that concentrated in a single tool result added at turn 1 — a 450-token result that rides in the context on all 10 subsequent turns. That one message costs more in carry expense than the system prompt itself.

The carry cost of a message is: `tokens × appearances × price_per_token`. A message added at turn 1 in a 10-turn session appears 10 times. A message added at turn 8 appears 3 times. The earliest, largest messages carry the highest cost. Identifying them by name and position tells you exactly which messages to compact first to get the most token savings per compaction effort.

## Situation

A legal research agent runs 10 turns. Turn 1 adds: a 350-token system prompt, a 60-token user message, an 80-token assistant response, and a 450-token tool result (a contract excerpt). Turns 2–10 add 140 tokens each (60-token user message + 80-token assistant response per turn). Total input cost: $0.047.

`carryReport()` shows:

```
Msg idx 3 (tool result, 450 tok × 10 turns): $0.0135 carry cost  ← most expensive
Msg idx 0 (system prompt, 350 tok × 10 turns): $0.0105 carry cost
Msg idx 2 (assistant-1, 80 tok × 10 turns): $0.0024 carry cost
...
```

The tool result at index 3 is more expensive than the system prompt. If the agent compacted that tool result to a 50-token summary at turn 5, the savings would be: 400 tokens × 5 remaining turns × $3.00/M = $0.006 saved on a $0.047 session — a 12.8% reduction. The system prompt cannot be compacted (it is the instruction set); the tool result can.

Without the carry report, the decision of what to compact would be based on message order (compact old things) rather than cost contribution (compact expensive things). In long sessions with one large early tool result and many small subsequent turns, these can differ significantly.

## Forces

- **Carry cost is not proportional to message position.** The first message in the array is always the system prompt — often 300–600 tokens. A tool result injected at turn 2 might be 800 tokens. The tool result costs more per turn than the system prompt, even though the system prompt was added first. `carryReport()` sorts by total carry cost so the highest-cost messages appear first, regardless of position.
- **`appearances` is the multiplier that matters.** A 1 000-token tool result added at turn 9 of a 10-turn session has appearances=2 and carry cost $0.006. The same result added at turn 1 has appearances=10 and carry cost $0.030. Early messages accumulate carry cost superlinearly with session length. The right moment to compact a large tool result is right after the model has processed its content — not at the end of the session.
- **`growth()` shows the marginal cost of each new turn.** At 140 tokens/turn (60 user + 80 assistant), each turn adds $0.00042. At turn 10, the per-call cost is $0.0066. By turn 25 with the same 140-token growth, the per-call cost would be $0.012. `growth()` makes the accumulation curve visible without requiring S-103's break-even calculation — it is the input to that calculation.
- **Combine with S-103 for compaction decisions.** S-103 answers: should I compact now? This tracker answers: if I compact now, which messages give the most savings? Run `carryReport()` at the S-103 trigger point; use it to decide which messages to summarize.
- **Not in the call path.** `record()` is fast (0.0016ms for 5 messages), but `carryReport()` at 0.0335ms for 10 turns × 13 messages should be called on compaction trigger events, not after every turn. Call `record()` on every turn; call `carryReport()` when the S-103 cost trigger fires.
- **Message index assumes append-only.** This model is correct for standard single-session agents: messages are only appended, never reordered or removed. If you remove messages mid-session (e.g., drop some tool results), the index assignments shift. In that case, track messages by a stable ID rather than array index.

## The move

**Record messages before each API call. On a compaction trigger, call `carryReport()` to identify the highest carry-cost messages. Compact those first.**

```js
// --- Context carry cost tracker ---
// Tracks per-message token carry cost across a multi-turn session.
// Carry cost: tokens × appearances × price_per_token.
// carryReport(): shows which messages most inflate cumulative input cost.
// Combine with S-103 (compaction trigger) to decide what to compact.

class ContextCarryCostTracker {
  constructor(opts = {}) {
    this._inputCostPerMToken = opts.inputCostPerMToken ?? 3.00;  // Sonnet
    this._charsPerToken      = opts.charsPerToken ?? 4;
    this._turns              = [];  // [{turn, breakdown: [{idx, role, tokens}], totalTokens}]
  }

  _tokensForMessage(msg) {
    let text = '';
    if (typeof msg.content === 'string') text = msg.content;
    else if (Array.isArray(msg.content)) {
      text = msg.content.map(b => (typeof b === 'string' ? b : (b.text ?? ''))).join('');
    }
    return Math.ceil(text.length / this._charsPerToken);
  }

  // Call before each API call. Returns { turn, totalTokens, costUsd } for this call.
  record(turn, messages) {
    const breakdown  = messages.map((msg, idx) => ({
      idx, role: msg.role, tokens: this._tokensForMessage(msg),
    }));
    const totalTokens = breakdown.reduce((s, m) => s + m.tokens, 0);
    this._turns.push({ turn, breakdown, totalTokens });
    return {
      turn,
      totalTokens,
      costUsd: parseFloat((totalTokens * this._inputCostPerMToken / 1e6).toFixed(6)),
    };
  }

  // Per-turn token growth: marginal tokens added each turn vs the previous.
  growth() {
    return this._turns.map((t, i) => {
      const prev = this._turns[i - 1];
      return {
        turn:           t.turn,
        totalTokens:    t.totalTokens,
        marginalTokens: prev ? t.totalTokens - prev.totalTokens : t.totalTokens,
        callCostUsd:    parseFloat((t.totalTokens * this._inputCostPerMToken / 1e6).toFixed(6)),
      };
    });
  }

  // Carry cost per message: tokens × appearances × price_per_token.
  // Sorted by carryCostUsd desc — highest-cost messages to compact appear first.
  carryReport() {
    const msgAccum = new Map();  // idx → { role, tokens, appearances }
    for (const t of this._turns) {
      for (const m of t.breakdown) {
        if (!msgAccum.has(m.idx)) {
          msgAccum.set(m.idx, { role: m.role, tokens: m.tokens, appearances: 0 });
        }
        msgAccum.get(m.idx).appearances++;
      }
    }
    const entries = [];
    for (const [idx, v] of msgAccum) {
      const carryCostUsd = v.tokens * v.appearances * this._inputCostPerMToken / 1e6;
      entries.push({
        messageIdx:   idx,
        role:         v.role,
        tokens:       v.tokens,
        appearances:  v.appearances,
        carryCostUsd: parseFloat(carryCostUsd.toFixed(6)),
      });
    }
    return entries.sort((a, b) => b.carryCostUsd - a.carryCostUsd);
  }

  totalInputCostUsd() {
    const total = this._turns.reduce((s, t) => s + t.totalTokens, 0)
                  * this._inputCostPerMToken / 1e6;
    return parseFloat(total.toFixed(4));
  }
}

// --- Integration: record before each API call; carryReport() on S-103 trigger ---

const CARRY_TRACKER = new ContextCarryCostTracker({ inputCostPerMToken: 3.00 });

async function callModel(turn, messages, model) {
  // Record before the API call
  const { totalTokens, costUsd } = CARRY_TRACKER.record(turn, messages);

  // S-103 compaction trigger (example threshold)
  if (totalTokens > COMPACTION_THRESHOLD) {
    const report = CARRY_TRACKER.carryReport();
    // report[0] = most expensive message to carry
    // Compact the top N messages via S-21
    const toCompact = report.slice(0, 3).map(m => m.messageIdx);
    messages = await compactMessages(messages, toCompact);
  }

  return callApi(model, messages);
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()` timed over 100 000 iterations with 5 messages. `carryReport()` timed over 100 000 iterations on a 10-turn session (~13 total messages). Sonnet pricing ($3.00/M input).

```
=== ContextCarryCostTracker timing (100 000 iterations) ===

record() — 5 messages:                    0.0016 ms
carryReport() — 10 turns × ~13 messages:  0.0335 ms

=== 10-turn session: per-turn token growth ===

Session structure:
  Turn 1: [system(350) + user1(60) + assistant1(80) + tool_result(450)] = 940 tok
  Turn 2-10: each adds user(60) + assistant(80) = +140 tok/turn

Turn  1 | totalTok:  940 | marginal: +940 | callCost: $0.002820
Turn  2 | totalTok: 1080 | marginal: +140 | callCost: $0.003240
Turn  3 | totalTok: 1220 | marginal: +140 | callCost: $0.003660
Turn  4 | totalTok: 1360 | marginal: +140 | callCost: $0.004080
Turn  5 | totalTok: 1500 | marginal: +140 | callCost: $0.004500
Turn  6 | totalTok: 1640 | marginal: +140 | callCost: $0.004920
Turn  7 | totalTok: 1780 | marginal: +140 | callCost: $0.005340
Turn  8 | totalTok: 1920 | marginal: +140 | callCost: $0.005760
Turn  9 | totalTok: 2060 | marginal: +140 | callCost: $0.006180
Turn 10 | totalTok: 2200 | marginal: +140 | callCost: $0.006600

Total input cost: $0.0471

=== carryReport(): most expensive messages to carry ===

Msg idx 3  (tool_result,   450 tok × 10 turns) = $0.0135  ← compact first
Msg idx 0  (system_prompt, 350 tok × 10 turns) = $0.0105  ← cannot compact
Msg idx 2  (assistant-1,    80 tok × 10 turns) = $0.0024
Msg idx 5  (assistant-2,    80 tok ×  9 turns) = $0.00216
Msg idx 7  (assistant-3,    80 tok ×  8 turns) = $0.00192
...

Insight: the tool_result (idx 3) is more expensive than the system prompt (idx 0),
despite being 100 tokens smaller, because it is still 450 tokens — not 350 — across the same 10 turns.
Both carry across all 10 turns; the larger message wins on carry cost.

If compacting tool_result at turn 5 (replacing 450 tok with a 50-tok summary):
  Token savings: 400 tok × 5 remaining turns = 2 000 tokens saved
  Cost savings: 2 000 × $3.00/M = $0.006 (12.8% of total session cost)
  Compaction cost: ~1 500-token prompt to the model: $0.0045
  Net benefit: positive if session continues ≥ 4 turns after compaction.

=== S-103 vs F-95 vs F-108 vs S-157 ===

              │ S-103 (compaction trigger)      │ F-95 (tool cost attribution)  │ F-108 (streaming meter)     │ S-157 (carry cost)
──────────────┼─────────────────────────────────┼───────────────────────────────┼─────────────────────────────┼──────────────────────────────
Question      │ Should I compact now?           │ Which tools cost most?        │ How many output tokens?     │ Which messages cost most?
Scope         │ Cumulative input cost threshold │ Per tool, per session         │ Per call, output side       │ Per message, across turns
Output        │ Boolean trigger                 │ Cost breakdown by tool name   │ Running token count         │ Carry cost by message index
Compose       │ S-157 record() → S-103 trigger  │ Independent, orthogonal       │ Independent, output side    │ carryReport() at S-103 trigger
```

## See also

[S-103](s103-cost-aware-context-management.md) · [S-21](s21-context-compaction.md) · [F-95](../forward-deployed/f95-tool-invocation-cost-attribution.md) · [S-99](s99-agent-task-economics.md) · [F-123](../forward-deployed/f123-session-cost-forecaster.md) · [F-111](../forward-deployed/f111-context-compression-before-expensive-stage.md)

## Go deeper

Keywords: `context carry cost` · `message token carry cost` · `conversation history cost breakdown` · `LLM input cost per message` · `session input cost accumulation` · `which messages to compact` · `context compaction priority` · `per-message carry cost` · `token cost by conversation turn` · `context accumulation cost tracker`
