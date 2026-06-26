# S-25 · Reflection

The first output is a draft, not a verdict. Reflection runs a **generate → critique → refine** loop until the output clears a bar — or you hit a stop rule. (Madaan et al., 2023, *Self-Refine*; Shinn et al., 2023, *Reflexion*.)

## Forces
- A single decode lands on *a* plausible answer, not the best one — and a model often can't see its own bug from the inside
- A pointed critique ("list defects against rubric Y") catches real errors; a vague "is this good?" just rubber-stamps
- A loop with no stop rule burns budget forever; cost grows roughly linearly with iterations (3 passes ≈ 3× the calls)
- Reflection is **sequential** (each pass sees the last). [S-24](s24-self-consistency.md) is **parallel** (k samples, vote). Same goal — higher reliability — different mechanism
- It reduces variance and surface defects; it does **not** add capability a model lacks

## The move
- **Pick a flavor by budget:**
  - **Single-model** (cheapest): same weights, two prompt roles — a generator, then a critic, then a reviser.
  - **Dual-role** (stronger): a separate, often larger critic ([S-06](s06-model-routing.md)). Its bias must differ from the generator's or it just agrees with itself.
  - **Reflexion** (memory): append each critique to a running failure log the next attempt reads first. Pays off when a failure mode recurs.
- **Name the stop rule up front — never "iterate until satisfied":**
  1. Fixed cap (2–3 iterations; most gains land by iteration 2).
  2. Quality threshold (critic scores ≥ T, T set in advance).
  3. Convergence (stop when successive outputs barely change).
  4. **External check** (tests pass, schema validates, verifier returns OK) — the best, because it's the only rule that doesn't trust the model to grade its own homework.
- **Critique on a rubric, not vibes.** Name the constraints and failure modes to check; that turns "looks fine" into actionable defects.
- **Reflection is worth it only when the first try is actually flawed *and* you can check it.** On easy, well-specified tasks it adds cost for nothing.

## Receipt
> Verified 2026-06-25 — `romanToInt` against llama3.2 via Ollama (localhost:11435), graded by a real 8-case JS test harness (subtractive notation: IV, IX, XL, XCIX, MCMXCIV, CDXLIV…).

```
PART 1 — natural first attempt:
  tests passed: 8/8  -> first try already correct; reflection would add cost for nothing

PART 2 — seeded buggy first draft (sums values, ignores subtraction; a realistic first-draft bug):
  start:            2/8   (6 failing: IV=6, IX=11, XL=60, ...)
  after 1 refine:   8/8   PASS
  (critique = the real test failures fed back; refine = the real model's fix)
```

Two honest lessons. (1) **Reflection isn't free or universal:** the model solved this common task correctly on the first try, so a critique loop would have spent extra calls for zero gain — I saw the same first-pass success across five varied tasks. (2) **When the draft is genuinely broken, a test-driven loop repairs it:** a romanToInt that ignored subtractive notation went 2/8 → 8/8 in one refine, driven by the actual failing cases. The lever is the *objective check* — without the test harness, the model would have had nothing concrete to fix. (Only the buggy first draft in Part 2 was seeded; the critique and the fix are genuine model output.)

## See also
[S-24](s24-self-consistency.md) · [S-19](s19-agent-loop.md) · [S-06](s06-model-routing.md) · [F-07](../forward-deployed/f07-evaluation-driven-development.md) · [F-12](../forward-deployed/f12-llm-as-a-judge.md)

## Go deeper
Keywords: `self-refine` · `reflexion` · `generate-critique-refine` · `iterative refinement` · `CRITIC` · `Madaan 2023 arXiv 2303.17651` · `Shinn 2023 arXiv 2303.11366` · `LATS` · `convergence stopping` · `test-time compute`
