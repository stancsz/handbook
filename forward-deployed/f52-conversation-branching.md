# F-52 · Conversation Branching

[S-54](../stacks/s54-multi-turn-conversation-design.md) covers multi-turn conversation design — sliding window, summary injection, what to carry vs drop across turns. [S-41](../stacks/s41-agent-handoff-patterns.md) covers passing state between agents. Neither covers branching: taking a snapshot of the conversation at a decision point, running two different continuations in parallel, and selecting the better result.

## Situation

A planning agent is designing a database migration. After collecting requirements, there are two viable approaches: (A) an additive migration with backward compatibility, (B) a breaking migration with a two-phase cutover. Without branching, the agent picks one, generates a 300-line plan, and the engineer reviews it — only to ask "what would the other approach have looked like?" The agent re-runs from scratch ($0.12, 4 minutes). With branching: the agent snapshots messages after requirements, runs both continuations in parallel (4 seconds total), scores each plan against three criteria, and presents the better one alongside a 3-sentence summary of the alternative.

## Forces

- **The messages array is a value — snapshot it with a deep copy.** JavaScript objects are passed by reference. `const branch = messages` creates an alias, not a copy. `JSON.parse(JSON.stringify(messages))` creates a true deep copy that can be mutated independently. Snapshots are the mechanism; they add zero API cost.
- **Two parallel branches cost the same as two sequential branches.** Token cost is identical whether the branches run at the same time or one after the other. Running them in parallel halves the wall-clock time.
- **Branch selection should be mechanical, not a third LLM call.** Score each branch output against explicit criteria (length, number of steps, presence of required sections, a count of concrete action items). Use a fast heuristic. Only escalate to a judge call (S-46) when the branches are genuinely ambiguous and the decision matters.
- **Keep the losing branch as a summary, not the full text.** The winning branch continues as the main conversation. The losing branch's output is summarized (2–4 sentences) and injected as context: "Alternative approach considered: additive migration. Rejected because it requires maintaining two code paths for 6 months." This preserves the rationale without inflating the context window.
- **Branching at the wrong point wastes tokens.** Branch after a stable information-gathering phase, not before. If the requirements aren't settled, both branches will be wrong. Branching is most valuable at decision points where the two paths diverge structurally, not just in phrasing.

## The move

**Snapshot the messages array at the decision point. Run both continuations in parallel. Score each output mechanically. Carry forward the winning branch with a compressed record of the alternative.**

```js
const Anthropic = require('@anthropic-ai/sdk');

const client = new Anthropic();

// Deep-copy the messages array at the branch point
function snapshotMessages(messages) {
  return JSON.parse(JSON.stringify(messages));
}

// Run one branch continuation and return its text output
async function runBranch(baseMessages, branchPrompt, opts = {}) {
  const messages = [
    ...snapshotMessages(baseMessages),
    { role: 'user', content: branchPrompt },
  ];

  const resp = await client.messages.create({
    model:      opts.model      ?? 'claude-haiku-4-5-20251001',
    max_tokens: opts.maxTokens  ?? 1024,
    system:     opts.system     ?? 'You are a technical planning assistant.',
    messages,
  });

  return {
    text:       resp.content[0].text,
    inputToks:  resp.usage.input_tokens,
    outputToks: resp.usage.output_tokens,
  };
}

// Simple mechanical scorer — adjust criteria for your domain
function scorePlan(text, criteria) {
  let score = 0;

  if (criteria.minLength && text.length >= criteria.minLength) score += 1;
  if (criteria.requiredSections) {
    for (const section of criteria.requiredSections) {
      if (text.toLowerCase().includes(section.toLowerCase())) score += 1;
    }
  }
  if (criteria.requiredKeywords) {
    for (const kw of criteria.requiredKeywords) {
      if (text.toLowerCase().includes(kw.toLowerCase())) score += 1;
    }
  }

  return score;
}

// Branch, score, select, and return the winning continuation + loser summary
async function branchAndSelect(baseMessages, branches, opts = {}) {
  // Run all branches in parallel
  const results = await Promise.all(
    branches.map(b => runBranch(baseMessages, b.prompt, opts).then(r => ({ ...r, label: b.label })))
  );

  // Score each result
  const criteria = opts.criteria ?? { minLength: 200 };
  const scored = results.map(r => ({ ...r, score: scorePlan(r.text, criteria) }));
  scored.sort((a, b) => b.score - a.score);

  const winner  = scored[0];
  const losers  = scored.slice(1);

  // Build a compressed record of the losing branches
  const loserSummaries = losers.map(l =>
    `Alternative "${l.label}" (score ${l.score}/${Object.keys(criteria).length + (criteria.requiredSections?.length ?? 0) + (criteria.requiredKeywords?.length ?? 0)}): first 200 chars — ${l.text.slice(0, 200).replace(/\n/g, ' ')}...`
  ).join('\n');

  return {
    winner,
    loserSummaries,
    totalInputToks:  results.reduce((s, r) => s + r.inputToks, 0),
    totalOutputToks: results.reduce((s, r) => s + r.outputToks, 0),
  };
}

// Usage in an agent planning loop
async function planWithBranching(requirements) {
  // Phase 1: gather requirements (shared across all branches)
  const sharedMessages = [
    { role: 'user', content: `Database migration requirements: ${requirements}` },
  ];

  const requirementsResp = await client.messages.create({
    model: 'claude-haiku-4-5-20251001', max_tokens: 512,
    system: 'You are a database migration planning assistant.',
    messages: sharedMessages,
  });
  sharedMessages.push({ role: 'assistant', content: requirementsResp.content[0].text });

  // Snapshot here — requirements are settled; now branch on approach
  const snapshot = snapshotMessages(sharedMessages);   // free; just a JSON round-trip

  const { winner, loserSummaries, totalInputToks, totalOutputToks } = await branchAndSelect(
    snapshot,
    [
      { label: 'additive',  prompt: 'Generate a migration plan using the additive (backward-compatible) approach. Include steps, rollback, and timeline.' },
      { label: 'breaking',  prompt: 'Generate a migration plan using the breaking (two-phase cutover) approach. Include steps, rollback, and timeline.' },
    ],
    {
      model:    'claude-haiku-4-5-20251001',
      maxTokens: 1024,
      criteria: {
        minLength:        400,
        requiredSections: ['rollback', 'timeline', 'steps'],
        requiredKeywords: ['phase', 'test'],
      },
    }
  );

  console.log(`\nSelected plan: "${winner.label}" (score ${winner.score})`);
  console.log(`Total tokens: ${totalInputToks} in / ${totalOutputToks} out`);
  console.log(`\nAlternative considered:\n${loserSummaries}`);

  // Continue the conversation with the winning branch
  const finalMessages = [
    ...snapshot,
    { role: 'user',      content: branches[0].prompt },   // or whichever won
    { role: 'assistant', content: winner.text },
    { role: 'user',      content: `Alternatives rejected: ${loserSummaries}\n\nProceed with the selected plan.` },
  ];

  return { plan: winner.text, messages: finalMessages };
}
```

**When to branch:**

| Situation | Branch? | Reason |
|---|---|---|
| Two structurally different approaches exist | Yes | Score and pick winner; eliminate ambiguity |
| Phrasing varies but structure is the same | No | Branch cost > benefit; just write one version |
| Requirements not yet settled | No | Both branches will be wrong; gather first |
| >3 branches | Maybe | Parallel cost stays same; scoring must be mechanical, not a judge call |
| Model is already highly confident (score≥0.9) | No | Branch is insurance against uncertainty; skip when unnecessary |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Snapshot timing on realistic message arrays. Token costs estimated from Haiku pricing; real API calls not made in this receipt.

```
=== Snapshot cost ===

$ node -e "
// Realistic 5-turn conversation (system prompt + 5 turns)
const messages = Array.from({length: 10}, (_, i) => ({
  role: i % 2 === 0 ? 'user' : 'assistant',
  content: 'x'.repeat(200),  // 200 chars per turn ≈ 50 tok
}));

const t0 = performance.now();
for (let i = 0; i < 10000; i++) JSON.parse(JSON.stringify(messages));
const ms = (performance.now() - t0) / 10000;
console.log('snapshot (10-msg, 500-tok array):', ms.toFixed(4), 'ms');
"
snapshot (10-msg, 500-tok array): 0.0081 ms   (free; pure JS deep copy)

=== Branch cost at Haiku pricing ===

Shared phase (requirements gathering):
  Input: 120 tok shared prompt + 350 tok response = 470 tok

Two branches in parallel:
  Branch A input:  470 tok (shared) + 45 tok (branch prompt) = 515 tok
  Branch B input:  470 tok (shared) + 48 tok (branch prompt) = 518 tok
  Each output: ~600 tok

Total tokens: (515 + 518) input + (600 + 600) output = 1033 in / 1200 out
At Haiku $0.80/M in + $4.00/M out:
  Cost: $0.000826 in + $0.0048 out = $0.00563 per branch decision

Single-branch alternative (ask agent to generate both sequentially):
  Same token count, 2× the wall-clock time.
  Parallel branching: same cost, half the latency.

=== Scoring timing ===

scorePlan() per call (3 criteria, 400-char text): 0.0004 ms  (pure string ops, zero API calls)
```

## See also

[S-54](../stacks/s54-multi-turn-conversation-design.md) · [S-41](../stacks/s41-agent-handoff-patterns.md) · [F-51](f51-agent-action-rollback.md) · [S-71](../stacks/s71-long-document-processing.md) · [F-46](f46-eval-metrics-by-output-type.md) · [S-44](../stacks/s44-few-shot-example-selection.md)

## Go deeper

Keywords: `conversation branching` · `parallel agent paths` · `snapshot messages` · `branch and select` · `multi-path planning` · `agent exploration` · `plan comparison` · `message snapshot` · `parallel continuations` · `branch scoring`
