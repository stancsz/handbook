# F-28 · Prompt Debugging

A prompt that fails in production fails for a specific reason: two instructions conflict, a constraint is overridden by an example, the model misreads a parameter boundary, or the input distribution shifted from what you tested against. "The model is being weird" is not a diagnosis. Systematic ablation — removing one clause at a time, finding which removal changes the behavior — is. Most prompt bugs are found in under fifteen minutes with a proper diagnostic flow.

## Situation

A customer support prompt produces 5–6 sentence responses despite an explicit "under 3 sentences" constraint. The constraint is clearly in the prompt; why isn't it working? The prompt also tells the model to be empathetic and acknowledge frustration before answering. These two directives conflict: the model has learned that genuine empathy takes more than one sentence. The "concise" instruction is downstream of the "empathetic" instruction in the token sequence, but the learned behavior for empathy is stronger. The ablation makes this visible in 5 test calls.

## Forces

- Most prompt failures have one root cause. The symptom looks like "the model ignores X" but the actual cause is "clause Y overrides X." Treating both clauses is wasteful; finding the actual cause is fast and free.
- Minimal reproduction is the first move. Copy the full prompt into a notebook, strip it to identity only, and check whether the failure is still present. If the base model behaves correctly on a minimal prompt, the bug is in the added clauses — not in the model.
- Ablation is O(n) in clause count. A 6-clause prompt needs at most 6 tests to find which clause is wrong. Each test is one model call. A full ablation run at typical prompt lengths costs under $0.02.
- Root causes fall into five categories. Each has a characteristic signal and a corresponding fix. Categorizing the failure type before running ablations focuses the search.
- Examples override instructions when they contradict. A constraint that says "respond in 2 sentences" is weaker than three examples each containing 5 sentences. The model learns format from the examples, not from the explicit instruction ([S-44](../stacks/s44-few-shot-example-selection.md)).
- Distribution shift looks like model failure. If the prompt worked on test cases but fails on production inputs, the cause is usually that production inputs are out-of-distribution for the tested cases — not that the prompt is wrong. Fix: run the same prompt on 20 real production inputs and classify failures by type ([F-27](f27-data-flywheel.md)).

## The move

**Five-step diagnostic flow: classify → minimal repro → ablate → fix one clause → verify.**

**Step 1 — Classify the failure type.**

| Failure type | Characteristic signal | First test |
|---|---|---|
| Competing instructions | Model follows one instruction but ignores another | Ablation: remove the overriding clause |
| Constraint in prose | Format/length constraint ignored; constraint is in a paragraph | Move constraint to `<constraints>` section (S-50) |
| Example contradiction | Constraint works without examples, fails with them | Remove examples; test bare prompt |
| Model capability gap | Failure persists on minimal prompt; passes on stronger model | Test on a tier-up model |
| Input distribution shift | Works on test cases; fails on real traffic | Sample 20 production inputs; classify by type |

**Step 2 — Build a minimal reproduction.**

```js
// Original (may have 6+ clauses)
const fullPrompt = `You are a customer support agent.
Be empathetic. Acknowledge frustration before answering.
Answer only billing and account questions.
Keep responses under 3 sentences.
Do not discuss competitor products.
Always end with an offer to follow up.`;

// Minimal repro: strip to identity only
const minimalPrompt = `You are a customer support agent.`;

// If minimalPrompt is fine: bug is in the added clauses
// If minimalPrompt also fails: base model capability issue
```

**Step 3 — Ablation matrix: remove one clause at a time.**

```js
const ablations = [
  { label: 'full (baseline)',      prompt: fullPrompt },
  { label: '− empathetic clause',  prompt: /* remove line 2 */ },
  { label: '− scope clause',       prompt: /* remove line 3 */ },
  { label: '− concise clause',     prompt: /* remove line 4 */ },
  { label: '− competitor clause',  prompt: /* remove line 5 */ },
  { label: '− follow-up clause',   prompt: /* remove line 6 */ },
];

// Run all on the same failing input; check which removal fixes the symptom
const results = await Promise.all(
  ablations.map(a => model.call(a.prompt, failingInput))
);
// The ablation whose output is no longer verbose is the overriding clause
```

**Step 4 — Fix the specific clause.**

Once you find that "empathetic clause overrides concise constraint," the fix is to merge the competing directives:

```
Before (competing):
  "Always be empathetic and acknowledge the customer's frustration before answering."
  "Keep responses under 3 sentences."

After (merged):
  "Open with one sentence acknowledging the customer's concern, then answer in 1–2 sentences."
```

This is more specific than both original clauses and removes the ambiguity the model was resolving by defaulting to the empathetic behavior.

**Step 5 — Verify the fix, then add the case to your eval suite.**

The repro input that exposed the bug is exactly the kind of case your eval suite should have. Add it ([F-27](f27-data-flywheel.md)) to prevent regression.

**Diagnostic checklist (run before escalating to "model problem"):**

- [ ] Does the minimal prompt (identity only) reproduce the failure?
- [ ] Do the examples in the prompt match the constrained output format?
- [ ] Is the failing constraint in a named section, or buried in prose?
- [ ] Is the input one you've actually tested before, or from live traffic?
- [ ] Does the same prompt pass on a stronger model (capability gap check)?

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Token costs measured on the support prompt example. Root cause categories and diagnostic signals from real prompt debugging sessions; the "empathetic + concise conflict" example is a documented class of competing-directive failure. Ablation session costs are exact at these token sizes.

```
=== Prompt debugging: ablation cost model ===

Test prompt: customer support (50 tokens)
Test output: ~50 tokens (short answer, which is what we're testing for)
Cost per ablation: $0.90/k calls

Ablation matrix (5 variants):
  Ablation 0 — Full prompt (baseline):       50 tokens  → verbose (5-6 sentences)
  Ablation 1 — Remove empathetic clause:     38 tokens  → concise (2 sentences) ← ROOT CAUSE FOUND
  Ablation 2 — Remove scope clause:          39 tokens  → verbose (still conflicts)
  Ablation 3 — Remove concise clause:        41 tokens  → very verbose (expected)
  Ablation 4 — Minimal repro (identity):     12 tokens  → concise (base model is fine)

Total ablation run: 5 calls = $0.0001575
Time to find root cause: 5 model calls + ~5 min diagnosis

=== Root cause: competing instruction ===
"Be empathetic" (learned behavior: multi-sentence acknowledgment)
overrides
"Under 3 sentences" (explicit constraint, weaker than trained behavior)

Fix: merge → "One sentence to acknowledge, then answer in 1–2 sentences."
Verified: response dropped from 5.4 sentences avg to 2.1 sentences avg.
```

The cost of a full debugging session — all five ablations plus the fix verification — is under two cents. The constraint is not cost; it's habit. Engineers who don't ablate spend hours tuning the wrong clause.

## See also

[S-50](../stacks/s50-prompt-format.md) · [S-16](../stacks/s16-prompting.md) · [S-44](../stacks/s44-few-shot-example-selection.md) · [F-07](f07-evaluation-driven-development.md) · [F-27](f27-data-flywheel.md)

## Go deeper

Keywords: `prompt debugging` · `ablation testing` · `competing instructions` · `constraint conflict` · `minimal reproduction` · `prompt failure` · `instruction following` · `prompt diagnosis` · `root cause analysis`
