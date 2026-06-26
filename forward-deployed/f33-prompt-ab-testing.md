# F-33 · Prompt A/B Testing

[F-07](f07-evaluation-driven-development.md) covers the ongoing discipline of eval-driven development — evals in CI, regression gating, quality as a merge requirement. That assumes you already have a working prompt and you're protecting it. This entry covers the earlier step: you have two candidate prompts and you need to know which one is better before you commit either one to CI.

## Situation

You wrote a support agent prompt that's working but not great — responses are too long, tone is off. You draft an alternative with explicit length constraints and a tone directive. Both prompts are reasonable. You can't tell by reading them which performs better on the real distribution of user queries. You need a decision rule: run 100 comparisons with a judge, declare the winner, ship it, and move on. The whole test costs $0.05.

## Forces

- **Reading prompts is not testing them.** Prompt quality is an emergent property of the interaction between the prompt, the model, and the input distribution. You can't reason your way to which prompt wins — you have to measure.
- **Pairwise comparison is more reliable than absolute scoring for close calls.** Asking a judge "which is better, A or B?" is easier than asking "rate A on a 1–5 scale" and then "rate B on a 1–5 scale" and comparing the means. Pairwise avoids scale drift (the same judge may score a 3 in round one and a 4 in round two for the same quality level); absolute scoring requires more examples to reach the same confidence.
- **Sample size determines what you can detect.** At N=100, a pairwise test detects a ~14% win-rate shift (one prompt winning 57% vs 43%) at ~80% power. At N=50, you need a ~20% shift. Running 50 examples and calling the one that wins 55% the winner is noise — at that margin, you can't tell signal from noise.
- **Mid-test peeking inflates false positive rate.** If you check results at N=30, N=50, N=80, and N=100, you're running four statistical tests. The chance that at least one crosses your threshold by noise is much higher than 5%. Decide your sample size upfront and look once.
- **Use your real input distribution.** Random examples from your eval set are not equivalent to production traffic. A/B test on examples that represent what the deployed prompt will actually face — same topic distribution, same query length distribution, same user intent mix.
- **The test is cheap enough to run on every significant prompt change.** A 100-example pairwise test costs approximately $0.05 total. There's no economic argument for skipping it.

## The move

**Pick N upfront based on the effect size you care about. Use pairwise judge. Look once. Ship the winner into CI ([F-07](f07-evaluation-driven-development.md)) where it becomes the regression baseline.**

**Pairwise judge call:**

```js
async function pairwiseJudge(userInput, outputA, outputB, judgeClient) {
  const prompt = `
You are evaluating two AI assistant responses to the same user input.

<user_input>${userInput}</user_input>
<response_A>${outputA}</response_A>
<response_B>${outputB}</response_B>

Which response is better? Consider: accuracy, helpfulness, conciseness, and appropriate tone.
Respond with exactly one character: A or B`.trim();

  const result = await judgeClient.messages.create({
    model:      'claude-haiku-4-5-20251001',  // fast + cheap; binary classification
    max_tokens: 1,
    messages:   [{ role: 'user', content: prompt }],
  });

  return result.content[0].text.trim();  // 'A' or 'B'
}
```

**A/B test runner:**

```js
async function runAbTest(promptA, promptB, examples, { primaryModel, judgeClient }) {
  let winsA = 0, winsB = 0;

  // Run all comparisons before inspecting results — no peeking mid-test
  const results = await Promise.all(examples.map(async (input) => {
    const [outA, outB] = await Promise.all([
      primaryModel.generate(promptA, input),
      primaryModel.generate(promptB, input),
    ]);

    // Swap order for half the examples to control position bias (F-12)
    const swapped = Math.random() < 0.5;
    const winner  = await pairwiseJudge(
      input,
      swapped ? outB : outA,
      swapped ? outA : outB,
      judgeClient
    );

    return swapped ? (winner === 'A' ? 'B' : 'A') : winner;
  }));

  results.forEach(w => { if (w === 'A') winsA++; else winsB++; });

  const winRateA   = winsA / examples.length;
  const winRateB   = winsB / examples.length;
  const n          = examples.length;
  // Two-proportion z-test: z = (p - 0.5) / sqrt(0.25 / n)
  const z          = (winRateA - 0.5) / Math.sqrt(0.25 / n);
  const significant = Math.abs(z) > 1.96;  // p < 0.05

  return { winsA, winsB, winRateA, winRateB, z, significant,
           winner: significant ? (winsA > winsB ? 'A' : 'B') : 'no_significant_winner' };
}
```

**Sample size selection:**

| N | Min detectable win-rate shift | When to use |
|---|---|---|
| 50 | ~20% (60% vs 40%) | Large, obvious differences only |
| 100 | ~14% (57% vs 43%) | **Default** — most prompt comparisons |
| 200 | ~10% (55% vs 45%) | Fine-grained tuning |
| 500 | ~6% (53% vs 47%) | Near-identical prompts, high-stakes decision |

**Decision rules:**

```
Winner is clear (>60% at N=100):     ship the winner; add to CI baseline
No significant winner:               keep existing prompt (don't ship without signal)
Effect is real but tiny (52% at N=500): not worth the complexity; keep simpler prompt
Both prompts fail on a subset:       investigate the subset — it's a distribution gap
```

**What to include in test examples:**

```
✓ Real queries from production logs (most important)
✓ Edge cases that broke the current prompt
✓ Queries where quality complaints were filed
✗ Synthetic queries you wrote to test your hypotheses
✗ Queries from a different domain than production traffic
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Judge prompt: pairwise comparison with two ~50-token responses and ~20-token user query. Haiku pricing approximate — verify at your provider before budgeting.

```
=== Prompt A/B test: token and cost breakdown ===

Prompts:
  Prompt A: 17 tokens (baseline)
  Prompt B: 26 tokens (with length + tone constraints)

Judge prompt per comparison: 143 tokens
Judge output per comparison: 1 token (A or B)
Cost per comparison (Haiku): ~$0.000118

Sample sizes and detection power:
N     Cost     Min detectable shift (≈80% power, p<0.05)
50    $0.0059  20% win-rate shift (60% vs 40%)
100   $0.0118  14% win-rate shift (57% vs 43%)
200   $0.0237  10% win-rate shift (55% vs 45%)
500   $0.0592  6%  win-rate shift (53% vs 47%)

100-example full A/B test (primary calls + judge):
  Primary model calls (A × 100 + B × 100):  ~$0.041
  Judge calls (100 pairwise comparisons):    $0.012
  Total:                                     ~$0.053

Readable as: $0.05 and 15 minutes of wall-clock time for a decision
that would otherwise be a coin flip or a week of argument.
```

The 14% detection threshold at N=100 is the practical floor for most A/B decisions. If prompt B only wins 52% of the time, the difference isn't meaningful enough to override engineering simplicity — keep the shorter, simpler prompt. Ship the winner into CI ([F-07](f07-evaluation-driven-development.md)) and add the test set as a regression suite so future changes are measured against the same bar.

## See also

[F-07](f07-evaluation-driven-development.md) · [F-12](f12-llm-as-a-judge.md) · [F-22](f22-cicd-for-ai-pipelines.md) · [F-17](f17-synthetic-eval-generation.md) · [F-26](f26-behavioral-drift-detection.md) · [S-59](../stacks/s59-instruction-density.md)

## Go deeper

Keywords: `prompt A/B testing` · `pairwise comparison` · `prompt evaluation` · `sample size` · `minimum detectable effect` · `LLM judge pairwise` · `position bias control` · `two-proportion z-test` · `prompt variant` · `eval-driven development`
