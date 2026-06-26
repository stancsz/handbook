# F-11 · Agent Reliability

Capability is "can it ever do this?" Reliability is "does it do this *every* time?" Production runs on the second question, and most benchmarks only answer the first.

## Forces
- A model that succeeds *sometimes* looks done in a demo and fails in production — the demo is `pass@1`, production is `pass^k`
- Per-step success compounds *down*: a 95%-per-step agent over 10 steps finishes ~60% of the time; over 20 steps, ~36%
- Longer-horizon tasks fail more even when the model is just as capable on each step — it can't hold the thread across the whole chain ([S-21](../stacks/s21-context-compaction.md))
- The intuitive fix (bolt on memory) can make long-horizon reliability *worse*, not better

## The move
- **Quote `pass^k`, not just `pass@1`.** `pass@1` = succeeds in one try; `pass^k` = succeeds in *all* k independent tries. The gap is the variance you'll ship. An agent at 90% `pass@1` is ~35% `pass^10` — it will fail roughly two of every three ten-step runs.
- **Measure across task *durations*, not just task types.** Reliability is two-dimensional: it drops with horizon length. Report success at short / medium / long horizons separately or you're blind to the cliff.
- **Test scaffolds empirically — don't assume memory helps.** Naive episodic-memory augmentation often fails to beat a plain ReAct loop ([S-19](../stacks/s19-agent-loop.md)) on long horizons. Measure before adopting.
- **Scope narrow-and-repeatable over heroic.** A 4-step task done 10,000×/day at four nines beats a 47-step demo that works once. Cut the horizon, add retries/checkpoints, and the compound-failure math stops fighting you.
- **Know the trajectory.** METR's time-horizon metric — the task length a frontier model completes at 50% reliability — has doubled roughly every 7 months. Reliable horizons are growing, but "50% reliability" is the bar being measured; production needs far higher.

This is [Law 3](../laws.md) (receipts over claims) turned on the agent itself: a success rate is a claim until you've run it k times.

## Receipt
> Verified 2026-06-25 — `pass@1` vs `pass^k` measured directly: the *same* instruction-following task run 8× independently against llama3.2 via Ollama (localhost:11435). Task: "write one sentence about the ocean that is **exactly 7 words** long."

```
run 1: PASS (7w) -> The ocean whispers ancient secrets to shores.
run 2: PASS (7w) -> The ocean's waves crash against ancient rocks.
run 3: PASS (7w) -> The ocean's waves crash against rocky shores.
run 4: PASS (7w) -> The ocean waves crash on sandy shores.
run 5: PASS (7w) -> Waves crash endlessly against the ancient shore.
run 6: FAIL (6w) -> The ocean whispers ancient, unending mysteries.
run 7: FAIL (8w) -> Waves crash against the ancient, weathered stone cliffs.
run 8: FAIL (6w) -> The ocean holds mysteries beyond imagination.
---
pass@1 (per-run success): 63%   pass^8 (all 8 succeed): 0%
at 63%/step, a 10-step chain finishes ~1% of the time
```

The model is clearly *capable* — it wrote a valid 7-word sentence five times. It is not *reliable* — `pass^8` is 0%, and the same 63% per-step rate in a 10-step agent loop would complete ~1% of runs. Capability passed; reliability failed. The 63%/0% numbers are this run; the 95%→60% compounding is arithmetic; the METR "time-horizon doubling ~every 7 months" and `pass^k` framing are from 2026 long-horizon-reliability research — verify the current paper before quoting a specific figure, as the metric is actively moving.

## See also
[F-14](f14-reading-agent-benchmarks.md) · [S-24](../stacks/s24-self-consistency.md) · [F-02](f02-evaluation-at-scale.md) · [F-03](f03-failure-modes.md) · [F-05](f05-agent-failure-taxonomy.md) · [F-07](f07-evaluation-driven-development.md)

## Go deeper
Keywords: `pass^k` · `pass@k` · `METR time horizon` · `compound failure` · `long-horizon agents` · `reliability engineering` · `MTBF` · `variance-aware evaluation`
