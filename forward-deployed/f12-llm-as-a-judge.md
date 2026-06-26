# F-12 · LLM-as-a-Judge

Using one model to score another's outputs — the eval method that makes [F-02](f02-evaluation-at-scale.md) and [F-07](f07-evaluation-driven-development.md) scale. It works, but the judge is an instrument with its own biases, and an uncalibrated instrument lies confidently.

## Forces
- Human review stops at hundreds of examples a day; a judge scores at API speed — that's the whole appeal
- The judge has measurable biases: **position** (favors the answer shown first), **verbosity** (favors longer answers regardless of quality), **self-preference** (rates its own family's outputs higher)
- On close calls the judge is noisy — it can disagree with *itself* on the identical prompt
- Provider silent model updates drift verdicts over weeks with no alert

## The move
- **Treat the judge as a measurement instrument, not an oracle.** It needs validation, calibration, and version control like any sensor.
- **Test position bias by swapping A/B order.** Run each pair both ways; if the verdict follows the *slot* instead of the better answer, position bias dominates — break ties with an explicit criterion.
- **Control verbosity in the rubric.** Add a `conciseness` criterion ("penalize padding that doesn't add information") so length isn't silently rewarded.
- **Keep a human-labeled calibration set (200–500 examples)** and require the judge's scores to correlate with it (≈0.7+) before you trust it at scale. Re-check on a schedule.
- **Lock the judge model version** — pin provider + model id + snapshot. Re-validate on every upgrade.
- **Don't let a model judge itself.** Use a different model as judge than the one under test; same-family judging inflates self-preference.
- **Prefer pairwise ("which is better?") over absolute 1–5 scores** — absolute rubrics drift faster between runs.

This is [Law 3](../laws.md) (receipts over claims) turned on the eval harness: the judge is where your receipts come from, so the instrument itself needs a receipt.

## Receipt
> Verified 2026-06-25 — order-swap test against llama3.2 as judge via Ollama (localhost:11435), picking the more compelling of two taglines (A/B), each pair run in both orders.

```
Close call (two evenly-matched taglines), 8 runs per order:
  order1 (P first): A B B A A B A B   -> P chosen 4/8
  order2 (P second):A A A B B A B A   -> P chosen 3/8
  => judge DISAGREES WITH ITSELF on the identical prompt (slot-A ~56%, near chance)

Clear quality gap (specific tagline vs generic), 12 runs per order:
  order1 (strong first): A A A A A A A A A A A A
  order2 (strong second):B B B B B B B B B B B B
  => strong answer chosen 24/24 across both orders — stable, position did not matter
```

**Honest read:** this judge was reliable when the quality gap was obvious (24/24, no position effect) and a near-coin-flip when the call was close (4/8 vs 3/8 on the *same* input). I did **not** observe strong position bias on llama3.2 here — slot-A sat near 50% — so the order-swap above demonstrates the *test method* and a real **repetition-instability** failure, not a position-bias result. For bias magnitudes that do show up at scale, see the literature: judges favoring their own outputs (reported ~10–25% higher self-win-rate for some frontier models) and frontier judges exceeding 50% error on advanced bias stress tests. The method is the point: swap, repeat, and calibrate before you trust a verdict.

## See also
[F-02](f02-evaluation-at-scale.md) · [F-07](f07-evaluation-driven-development.md) · [F-11](f11-agent-reliability.md) · [S-16](../stacks/s16-prompting.md) · [F-03](f03-failure-modes.md) · [F-30](f30-runtime-output-validation.md)

## Go deeper
Keywords: `LLM-as-a-judge` · `position bias` · `verbosity bias` · `self-preference bias` · `order-swap test` · `judge calibration` · `pairwise evaluation` · `Krippendorff alpha` · `JudgeBiasBench`
