# S-32 · The Verifiability Divider

The clearest predictor of whether an agent ships is not the model — it's whether the agent's output can be checked cheaply. CLI agents, code agents, and data-transform agents are in production because their outputs are deterministic and checkable: a test passes or fails, a file matches or doesn't, an exit code is 0 or not. Browser and UI agents stall on the same frontier model because "did the flow succeed?" has no oracle in the artifact. Same intelligence, opposite outcomes — the divider is verifiability, not capability.

## Situation

You're choosing what to automate, or debugging why an agent that demos well never makes it to production. Two agents using the identical model behave completely differently: one converges and ships, the other plateaus at "looks right most of the time." The difference is almost never the prompt. It's that one task has a cheap oracle and the other doesn't.

## Forces

- An agent loop needs a stopping signal. With a checkable oracle, the signal is the artifact itself; without one, the signal collapses to "the model feels done" — which is wrong exactly when it matters (see [S-30](s30-code-test-fix-loop.md)).
- Verifiable surfaces compound: every run produces a labeled example, so evals, regression tests, and reward signals come for free. Unverifiable surfaces require a human or an LLM judge to manufacture each label — a recurring cost, not a one-time one.
- The cheap automated checks available on unverifiable surfaces are *proxies* (keyword present, length bounded, page loaded), and a proxy passes wrong outputs as readily as right ones. Form is not truth.
- "Make it verifiable" is often a design lever, not a fixed property. You can frequently move a task across the divider by changing the output contract — demand a structured value instead of prose, a diff instead of a description, an assertion instead of a confirmation message.
- Law 3 (receipts over claims) is this divider applied to the handbook itself: an entry without a checkable receipt is the unverifiable surface.

## The move

**Sort tasks by oracle cost before you sort by model.** The first question is not "which model?" — it's "what's the cheapest way to know this output is correct?" If the answer is "a human reads it," you're on the hard side of the divider; budget accordingly.

**Pull tasks across the divider by changing the output contract.** Don't ask an agent to "update the config and confirm" — ask it to emit the new config, then validate it against a schema ([S-04](s04-structured-output.md)) or re-read the file and diff. Don't ask a browser agent "did checkout work?" — have it assert on a post-state fact (an order ID in the database) it didn't author. Replace self-reported success with externally-derived state.

**Never accept a proxy as an oracle.** A check that a contradictory output would also pass is verifying form, not correctness. Length limits, keyword presence, and "no error thrown" are smoke tests, not oracles. If your only check is a proxy, treat the task as unverified.

**On the hard side, manufacture an oracle deliberately.** When no native oracle exists, build the most deterministic one you can afford: schema validation ([F-16](../forward-deployed/f16-tool-call-validation.md)) > output diff > type/lint > LLM-as-judge ([F-12](../forward-deployed/f12-llm-as-a-judge.md)). A judge is the *last* resort because the judge itself then needs a receipt.

**Prefer the verifiable surface when you get to choose the problem.** The market isn't rewarding code agents because code is glamorous — it's rewarding them because correctness is cheap to establish. When two framings of a task exist, the checkable one will ship first and break less.

## Receipt

> Verified 2026-06-26 — Node v24.16.0. No model in the loop by design: the divider is a property of the *verifier*, not the generator, so the receipt measures the verifier. (Local Ollama was unavailable this session; not needed here.)

Same task class, two surfaces. The question: does the artifact carry its own oracle?

```
Surface A — VERIFIABLE (code). Output is a value; ground truth exists.
  third_largest([10,10,10]) seeded bug exposed:
  A FAIL: thirdLargest([10,10,10]) -> undefined, expected null
  A oracle result: 2/3 pass  (deterministic, exact diff)

Surface B — UNVERIFIABLE (prose/UI). No ground-truth oracle in the artifact.
  Task: one-sentence summary of "The release shipped Tuesday after the rollback."
  out1 = "The release shipped on Tuesday."            proxy_check=true
  out2 = "The release was rolled back and did not ship."  proxy_check=true
  -> two CONTRADICTORY outputs both pass the only cheap check
```

**What the receipt shows:**

- On Surface A the oracle is exact and free: it pinned the failure to one input with the precise wrong value (`undefined` vs `null`). That diff is a repair signal and a permanent regression test in one.
- On Surface B the only cheap automated check is a proxy (`contains "release"`, `≤ 30 words`). Both `out1` and `out2` pass it — and they mean *opposite things*. A proxy that accepts contradictory outputs verifies form, not truth. An agent gated on it cannot tell when it's done, which is exactly why these agents plateau.
- The fix is structural, not a better model: give Surface B an external oracle (assert the deploy's real post-state) and it crosses to the easy side of the divider.

## See also

[S-30](s30-code-test-fix-loop.md) · [F-16](../forward-deployed/f16-tool-call-validation.md) · [S-15](s15-browser-computer-use-agents.md) · [S-04](s04-structured-output.md) · [F-07](../forward-deployed/f07-evaluation-driven-development.md)

## Go deeper

Keywords: `verifiability` · `oracle` · `checkable output` · `proxy metric` · `RLVR` · `verifiable rewards` · `code agents` · `browser agents` · `stopping condition` · `output contract`
