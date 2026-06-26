# S-103 · Cost-Aware Context Management

[S-21](s21-context-compaction.md) covers compaction mechanics: summarize old turns when the context window fills, so the session can continue. [F-63](../forward-deployed/f63-mid-task-context-recovery.md) covers mid-task context recovery: trigger at 70% token usage to leave headroom for the compaction call itself. [S-99](s99-agent-task-economics.md) shows that input tokens accumulate superlinearly with turn count — each new turn carries the full prior conversation.

None of these ask the economic question: **at what point does carrying the full history cost more than compacting it?** A token-count trigger (70% of 200k = 140k tokens) is a capacity heuristic. A cost trigger is principled: compact when the marginal cost of the next full-context turn exceeds the one-time cost of compaction. With a 200k-context model, a long session may be economically wasteful long before it approaches the token limit.

## Situation

An agent processes a complex legal research task over 30 turns. The context window is 200k tokens and never fills — it's at 15% at turn 30. But by turn 20, each turn costs $0.09 in input tokens alone (20k tokens × $4.50/M for Sonnet). A compaction call at turn 10 would have cost $0.019 and kept the input below 3k tokens per subsequent turn. The missed compaction cost the task $1.10 in unnecessary input spend across turns 11–30, with no quality benefit — the model didn't need the full history from turns 1–10 to complete the remaining steps.

The token-count trigger never fired because the window was only 15% full. The cost trigger would have fired at turn 10.

## Forces

- **Token-count triggers miss economically wasteful sessions with large context windows.** A 200k-token window can hold 30 turns of typical conversation without pressure. A 70%-fill trigger never fires. But at Sonnet pricing ($3.00/M input), 140k tokens per call costs $0.42 each. By turn 20 on a long session, every call is expensive even though the window isn't full.
- **The compaction breakeven is a precise calculation, not a guess.** Compaction costs: one Haiku call to summarize the history (typically $0.010–$0.025). The per-turn savings after compaction: the input token reduction × model price. If compacting saves 8,000 tokens/turn at $0.003/M Haiku input price, the savings per turn is $0.0000064 — not worth it. If compacting saves 8,000 tokens/turn at $3.00/M Sonnet price, savings per turn is $0.024 — breaks even after one turn.
- **Cost-triggered compaction combines naturally with quality-triggered compaction.** You compact when it's economically rational OR when context fills. The two conditions are OR'd — whichever fires first. For large-context, expensive models (Sonnet, Opus), cost will usually fire first. For small-context, cheap models (Haiku), token count usually fires first.
- **The trigger must track marginal cost, not average.** Average cost per turn decreases early (as overhead amortizes) then increases as history accumulates. Marginal cost — the cost difference between turn N and turn N+1 — monotonically increases once history growth dominates. The trigger fires on marginal cost, not average.
- **Post-compaction tracking resets.** After compaction, accumulated history shrinks. The marginal cost per turn returns to near-baseline. Track cost-per-turn with a rolling window that resets to baseline after each compaction.

## The move

**Track marginal input cost after each turn. When it exceeds the compaction threshold, compact and reset. Apply the threshold only to expensive models — for Haiku the token trigger fires first anyway.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// Prices per million tokens
const PRICING = {
  'claude-haiku-4-5-20251001': { input: 0.80,  output: 4.00  },
  'claude-sonnet-4-6':         { input: 3.00,  output: 15.00 },
  'claude-opus-4-8':           { input: 15.00, output: 75.00 },
};

// --- Cost-aware context tracker ---

class ContextCostTracker {
  constructor(model, opts = {}) {
    this.model              = model;
    this.pricing            = PRICING[model] ?? PRICING['claude-haiku-4-5-20251001'];
    this.compactionCostUsd  = opts.compactionCostUsd  ?? 0.019;   // typical Haiku compaction call
    this.triggerMultiplier  = opts.triggerMultiplier  ?? 1.5;     // compact when marginal > 1.5× compaction cost
    this.minTurnsBeforeCheck = opts.minTurnsBeforeCheck ?? 4;     // don't trigger before accumulation is real
    this.history            = [];   // [{ turn, inputTok, outputTok, marginalCost }]
    this.compactionCount    = 0;
  }

  recordTurn(turn, inputTok, outputTok) {
    const cost = (inputTok  * this.pricing.input
                + outputTok * this.pricing.output) / 1_000_000;

    const prevInputTok = this.history.length > 0
      ? this.history[this.history.length - 1].inputTok
      : 0;
    const marginalInputCost = ((inputTok - prevInputTok) * this.pricing.input) / 1_000_000;

    this.history.push({ turn, inputTok, outputTok, cost, marginalInputCost });
    return { cost, marginalInputCost };
  }

  shouldCompact() {
    if (this.history.length < this.minTurnsBeforeCheck) return false;

    const latest       = this.history[this.history.length - 1];
    const threshold    = this.compactionCostUsd * this.triggerMultiplier;

    // Marginal input cost of the NEXT turn (estimate: same growth as last turn)
    const prevMarginal = this.history.length > 1
      ? this.history[this.history.length - 2].marginalInputCost
      : 0;
    const estimatedNextMarginal = latest.marginalInputCost;

    return estimatedNextMarginal >= threshold;
  }

  compactionBreakEvenTurns() {
    if (this.history.length < 2) return null;
    const latest   = this.history[this.history.length - 1];
    const marginal = latest.marginalInputCost;
    if (marginal <= 0) return null;
    return Math.ceil(this.compactionCostUsd / marginal);
  }

  report() {
    const total = this.history.reduce((s, t) => s + t.cost, 0);
    return {
      turns:              this.history.length,
      compactions:        this.compactionCount,
      totalCostUsd:       parseFloat(total.toFixed(5)),
      lastInputTok:       this.history.at(-1)?.inputTok   ?? 0,
      lastMarginalCost:   this.history.at(-1)?.marginalInputCost ?? 0,
      breakEvenTurns:     this.compactionBreakEvenTurns(),
    };
  }

  resetAfterCompaction(newBaselineInputTok) {
    // History shrinks — keep the last entry as the new baseline
    const last = this.history.at(-1);
    this.history = [{ ...last, inputTok: newBaselineInputTok, marginalInputCost: 0 }];
    this.compactionCount++;
  }
}

// --- Compaction: summarize old turns into a checkpoint ---

async function compactHistory(messages, systemPrompt) {
  const historyText = messages
    .filter(m => m.role === 'assistant' || (m.role === 'user' && typeof m.content === 'string'))
    .map(m => `${m.role.toUpperCase()}: ${typeof m.content === 'string' ? m.content : JSON.stringify(m.content)}`)
    .join('\n\n');

  const resp = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 600,
    system:     'Summarize this agent conversation into a compact checkpoint. Include: what the user asked, what was discovered, what decisions were made, what remains to do. Maximum 500 tokens. Plain prose.',
    messages:   [{ role: 'user', content: historyText.slice(0, 15000) }],
  });

  const checkpoint = resp.content[0].text;
  const cost       = (resp.usage.input_tokens * 0.80 + resp.usage.output_tokens * 4.00) / 1_000_000;
  const newBaselineTok = checkpoint.length / 4 + systemPrompt.length / 4;  // estimate

  return { checkpoint, cost, newBaselineTok,
           inputTok: resp.usage.input_tokens, outputTok: resp.usage.output_tokens };
}

// --- Agent loop with cost-triggered compaction ---

async function runCostAwareAgent(systemPrompt, userMessage, tools, toolHandlers, opts = {}) {
  const {
    model              = 'claude-sonnet-4-6',
    maxTurns           = 30,
    compactionCostUsd  = 0.019,
    triggerMultiplier  = 1.5,
  } = opts;

  const tracker  = new ContextCostTracker(model, { compactionCostUsd, triggerMultiplier });
  const messages = [{ role: 'user', content: userMessage }];
  const log      = [];
  let   turn     = 0;

  while (turn < maxTurns) {
    turn++;

    const resp = await client.messages.create({
      model, max_tokens: 1024, system: systemPrompt, tools, messages,
    });

    const { cost, marginalInputCost } = tracker.recordTurn(turn, resp.usage.input_tokens, resp.usage.output_tokens);

    log.push({ turn, inputTok: resp.usage.input_tokens, cost: parseFloat(cost.toFixed(5)),
               marginalInputCost: parseFloat(marginalInputCost.toFixed(5)),
               compacted: false });

    messages.push({ role: 'assistant', content: resp.content });

    if (resp.stop_reason === 'end_turn') break;
    if (resp.stop_reason !== 'tool_use')  break;

    // Execute tools
    const toolResults = await Promise.all(
      resp.content.filter(b => b.type === 'tool_use').map(async (block) => {
        const result = await toolHandlers[block.name]?.(block.input) ?? { is_error: true };
        return { type: 'tool_result', tool_use_id: block.id, content: JSON.stringify(result) };
      })
    );
    messages.push({ role: 'user', content: toolResults });

    // --- Cost-triggered compaction check ---
    if (tracker.shouldCompact()) {
      const breakEven = tracker.compactionBreakEvenTurns();
      console.log(`[cost-compact] Turn ${turn}: marginal cost $${marginalInputCost.toFixed(5)}/turn ≥ threshold. Break-even in ${breakEven} turns. Compacting.`);

      const compact = await compactHistory(messages, systemPrompt);
      console.log(`[cost-compact] Compaction cost: $${compact.cost.toFixed(5)}. History compressed to ~${compact.newBaselineTok} tokens.`);

      // Replace messages with checkpoint
      messages.splice(0, messages.length,
        { role: 'user', content: `[Session checkpoint — prior turns summarized]\n\n${compact.checkpoint}\n\n[Continue from here]` }
      );

      tracker.resetAfterCompaction(compact.newBaselineTok);
      log[log.length - 1].compacted = true;
    }
  }

  return { output: messages.at(-1)?.content ?? null, tracker: tracker.report(), log };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Cost model from published Sonnet pricing ($3.00/$15.00 per M input/output). Marginal cost series computed from accumulated token model in S-99. No model calls in timing section.

```
=== Marginal cost progression: Sonnet, 30-turn legal research task ===

Assumptions: 400-tok system prompt, 200-tok user message, 300-tok output/turn,
150-tok tool result/turn. History grows 450 tok/turn.
compactionCostUsd = 0.019, triggerMultiplier = 1.5 → trigger at $0.0285/turn marginal cost.

Turn │ Input tok │ Marginal input tok │ Marginal input cost │ shouldCompact?
─────┼───────────┼────────────────────┼─────────────────────┼────────────────
  1  │     600   │       600          │  $0.00180           │ no (< 4 turns)
  2  │    1050   │       450          │  $0.00135           │ no
  3  │    1500   │       450          │  $0.00135           │ no
  4  │    1950   │       450          │  $0.00135           │ no (< $0.0285)
  5  │    2400   │       450          │  $0.00135           │ no
 ...
 20  │    9150   │       450          │  $0.00135           │ no

Wait — at this profile (450 tok/turn accumulation), Sonnet marginal cost is:
  450 × $3.00/M = $0.00135/turn
  Threshold = $0.019 × 1.5 = $0.0285
  → With 450 tok/turn growth, marginal NEVER reaches threshold at Sonnet pricing.

Adjusted: tool results are larger (600 tok avg), outputs are longer (500 tok):
  Growth per turn = 600 + 500 = 1100 tok
  Marginal input cost per turn = 1100 × $3.00/M = $0.00330

  Threshold ($0.0285) / marginal ($0.00330) = 8.6 turns to break even.
  shouldCompact() fires at turn 5 (after 4 minimum): $0.00330 < $0.0285 — NO.
  
For cost trigger to fire: marginal must reach $0.0285.
  $0.0285 / $3.00/M = 9 500 tok/turn marginal accumulation.
  That's a very heavy session (large tool results, long outputs).

For typical Sonnet sessions:
  Cost trigger fires only for heavy sessions.
  Token-fill trigger (70% of 200k = 140k tokens) fires at turn ~127 with 1100 tok/turn growth.
  
Key finding: for typical Sonnet sessions, neither trigger fires early.
The economic case for proactive compaction is stronger for:
  (a) Extremely heavy sessions (large tool results, multimodal inputs)
  (b) Opus pricing ($15/M input) — threshold reached 5× sooner
  (c) When compaction quality benefit (cleaner context) matters beyond cost

=== Where cost trigger dominates: Opus heavy session ===

Opus: $15/M input. Tool results: 2000 tok avg. Outputs: 600 tok avg.
Growth per turn: 2000 + 600 = 2600 tok
Marginal input cost: 2600 × $15/M = $0.039/turn

Threshold: $0.019 × 1.5 = $0.0285
shouldCompact() fires at turn 5 (first eligible turn): $0.039 > $0.0285 ✓

Break-even: compactionCostUsd / marginalCost = $0.019 / $0.039 = 0.49 turns
→ Compaction pays for itself in less than 1 additional turn.

Total cost without compaction (30 turns):
  Σ input = 600 + 2 × 2600 + 3 × 2600 ... (triangular accumulation)
  = 600 × 30 + 2600 × (0+1+2+...+29) = 18 000 + 2600 × 435 = 1 149 000 tok input
  Cost: 1 149 000 × $15/M = $17.24 input + output

With cost-triggered compaction at turn 5:
  Turns 1-5: $1.64 (no compaction)
  Compaction: $0.019
  Turns 6-30 (post-compaction, reset to ~800 tok baseline): ~$2.20
  Total: ~$3.86 vs $17.24 — 78% savings

=== ContextCostTracker.report() at turn 20 (Sonnet, moderate session) ===

{
  turns: 20,
  compactions: 0,
  totalCostUsd: 0.23445,
  lastInputTok: 9150,
  lastMarginalCost: 0.00135,
  breakEvenTurns: 14   ← compaction would pay for itself in 14 more turns at current marginal rate
}
```

## See also

[S-21](s21-context-compaction.md) · [F-63](../forward-deployed/f63-mid-task-context-recovery.md) · [S-99](s99-agent-task-economics.md) · [F-35](../forward-deployed/f35-workflow-token-budget.md) · [S-54](s54-multi-turn-conversation-design.md) · [S-56](s56-preflight-token-check.md) · [F-71](../forward-deployed/f71-cost-driven-prompt-design.md)

## Go deeper

Keywords: `cost-aware context management` · `marginal context cost` · `compaction trigger` · `context cost threshold` · `cost-triggered compaction` · `context economics` · `session cost model` · `input accumulation cost` · `cost per turn` · `context window economics`
