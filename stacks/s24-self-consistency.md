# S-24 · Self-Consistency

One chain-of-thought answer is a single sample from a distribution — and that sample can be the wrong one. Instead, sample *k* reasoning chains at temperature > 0 and take the **majority vote** of their final answers. (Wang et al., 2022.)

## Forces
- A greedy decode gives you whichever chain topped the model *this once* — not necessarily the most reliable answer
- Hard problems have many valid reasoning paths and several plausible-but-wrong ones; any single draw can land on a wrong one
- One wrong answer on a high-stakes call (math, classification, code intent) costs more than *k* extra cheap samples
- A single chain gives no confidence signal; *k* chains give you the vote margin for free
- This is the mirror image of [F-11](../forward-deployed/f11-agent-reliability.md): variance hurts reliability, but you can *spend* variance to buy accuracy

## The move
- **Sample, then vote.** Run the same prompt *k* times at temperature > 0 (T=0 yields *k* identical samples and defeats the point), extract each final answer, return the mode.
- **The answer must be extractable and comparable** — a number, label, letter, or normalized string. You cannot majority-vote free-form prose.
- **Read the margin as confidence.** `top_count / k` is a cheap confidence estimate; escalate or ask a human on a thin margin.
- **More samples help with diminishing returns.** The original paper pushed *k* high (tens of samples); in practice pick *k* against your cost budget — pair with [S-06](s06-model-routing.md) so you only spend it on the hard queries that need it.
- **It can't fix a *systematically* wrong model.** If the dominant reasoning path is flawed, the vote amplifies the error — self-consistency reduces variance, not bias.

## Receipt
> Verified 2026-06-25 — the "bat and ball" cognitive-reflection trap (intuitive wrong answer $0.10; correct $0.05) against llama3.2 via Ollama (localhost:11435), **k=9 samples at temperature 1.0**, majority vote on the extracted `ANSWER:` number.

```
correct answer: 0.05
9 sampled answers: [0.05, 10, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05]
vote tally: { "0.05": 8, "10": 1 }
---
single-sample accuracy: 8/9 (89%)   <- 1 in 9 draws was a wrong outlier
majority vote:          0.05  -> CORRECT, margin 8/9
```

A modest but honest demonstration of the mechanism: a single sample had a real (~11%) chance of returning the wrong outlier; voting over 9 suppressed it and returned the correct answer with a strong 8/9 confidence margin. The gains are largest where single-sample accuracy is *lower* — Wang et al. report substantial improvements over greedy chain-of-thought on math benchmarks like GSM8K (exact figures are model- and setup-dependent; check the paper). Here the model was already mostly right, so the win is outlier suppression plus a free confidence signal — not a dramatic rescue.

## See also
[S-25](s25-reflection.md) · [S-16](s16-prompting.md) · [S-06](s06-model-routing.md) · [F-11](../forward-deployed/f11-agent-reliability.md) · [R-02](../frontier/r02-reasoning-models.md)

## Go deeper
Keywords: `self-consistency` · `majority vote` · `chain-of-thought` · `sampling temperature` · `Wang 2022` · `arXiv 2203.11171` · `vote margin` · `GSM8K` · `test-time compute`
