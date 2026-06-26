# S-30 · Code-Test-Fix Loop

When a code agent has no test oracle, it stops when it *thinks* it's done. That is the wrong stopping condition. The write-test-fix loop is the core pattern for any agent that produces code: tests define correct, test execution proves it, and the exact failure message is the repair signal.

## Forces

- Code agents need a feedback signal to know when their output is correct — without one, the convergence criterion is "model feels confident," which is wrong
- LLM self-review of code is probabilistic: the model catches bugs in well-known patterns it has seen in training, but misses novel bugs, subtle logic errors, and business-logic edge cases silently
- Test execution is deterministic: a failing assertion gives an exact value, line, and expectation — no ambiguity, no guessing
- Every iteration that starts with exact failure output converges faster than one that starts with "try again"
- Test-writing is overhead that pays back on every repair cycle — without it, each debug session starts from scratch

## The move

**Tests before code.** The oracle must exist before the agent starts writing. If you don't have tests, the agent is flying blind regardless of how good the model is.

**Feed the exact failure, not a summary.** Give the model the raw assertion error, traceback, and failing values. `FAIL: is_balanced(")(") returned True, expected False` is a repair signal. "Something is wrong" is not.

**Cap iterations.** Set a hard limit — 3 to 5 fix cycles is normal; beyond that, hand off to a human. The agent should not cycle until the context window fills. Document which test is still failing at handoff.

**Weaker oracles if tests are impossible.** JSON schema validation, output diffs, type checker output, and linter errors all beat LLM self-review as oracle signals. Use the most deterministic signal available.

**Don't use self-review as the sole gate.** It works on textbook patterns the model has memorized. It fails on the bugs you actually care about.

## Receipt

> Verified 2026-06-26 — parentheses balancer with a seeded bug, against llama3.2 via Ollama (localhost:11435).

**Bug:** `is_balanced(s)` only checks the final count (returns `count == 0`), so `")("` ends at count 0 and returns `True` — wrong.

```
Test run on buggy code: 4/5 pass
  FAIL: is_balanced(")(") returned True, expected False

LLM self-review ("Is this function correct?"):
  Model: "No. The function returns True for any string with an equal
  number of ( and ), including strings where closing parentheses appear
  before their matching opening ones..."
  -> Correctly flagged the bug.
  But: this is a textbook algorithm the model has seen in training
  thousands of times. It caught it *here*; it won't catch a novel
  business-logic edge case in your codebase.

Feed exact failure to model:
  Prompt: "FAIL: is_balanced(")(") returned True, expected False. Fix it."
  Model fix: added `if count < 0: return False` inside the loop.

Test run on fixed code: 5/5 pass
```

**The lesson:** self-review worked this time — on a pattern the model had memorized. Test execution works every time, on every bug, including the ones the model doesn't recognize. "Sometimes" is not a shipping standard. An agent loop that relies on self-review as its oracle will terminate early on the bugs that matter most.

## See also

[S-25](s25-reflection.md) · [F-07](../forward-deployed/f07-evaluation-driven-development.md) · [F-11](../forward-deployed/f11-agent-reliability.md) · [S-19](s19-agent-loop.md) · [S-32](s32-verifiability-divider.md)

## Go deeper

Keywords: `SWE-bench` · `code agent` · `test oracle` · `write-test-fix` · `self-repair` · `agentic coding` · `test-driven development` · `scaffolding` · `pass@k` · `execution feedback`
