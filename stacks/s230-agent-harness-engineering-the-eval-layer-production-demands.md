# S-230 · Agent Harness Engineering — The Eval Layer Production Demands

The model ships. The agent demos beautifully. Then it hits production and fails in ways benchmarks never predicted — wrong URLs, tool-call deadlocks, CVEs hallucinated as hallucinations. The fix is never a better model. It's a better harness.

## Forces

- **Standard benchmarks are gameable.** UC Berkeley audited eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found all could be gamed to near-perfect scores without solving the actual task — one team solved 890 tasks with a single character change
- **Production failures are harness failures, not model failures.** The Cleanlab 2025 survey found that of 1,837 teams claiming production agents, only 95 actually had them live — and most failures cited system-level problems (broken URLs in tool calls, environment mismatches, eval methodology bugs), not model quality
- **You cannot unit-test a non-deterministic system the traditional way.** No exception is thrown when the model returns a wrong answer. Quality is a distribution, not a binary. Without a harness, regressions are silent
- **A single harness improvement outperforms model upgrades.** One team improved 15 LLMs at coding in a single afternoon — by changing only the file-editing harness (content-addressable hashlines), not the model. The model is the moat; the harness is the bridge
- **Eval is the most undervalued engineering role in AI right now.** Prompt engineering gets the glory. Harness engineering — writing the grader, building the environment, designing the pass/fail criteria — is what ships reliable agents

## The move

A harness is the **evaluation infrastructure around an agent**: the environment the agent acts in, the grader that judges outcomes, the transcript that records the full trajectory, and the budget controls that prevent runaway cost. It has five layers:

### Layer 1 — Task Definition (the contract)

Define what "success" means before you run the agent. Write an **assertion suite**, not a prompt:

```python
class FlightBookingSpec:
    """Each check is a predicate over the final environment state."""
    def check_booking_confirmed(self, transcript, env) -> bool:
        return env.get("confirmation_email_sent") is True

    def check_no_double_charge(self, transcript, env) -> bool:
        charges = env.get("payment_events", [])
        return len(charges) == 1 and charges[0]["amount"] > 0

    def check_receipt_sent(self, transcript, env) -> bool:
        return "receipt" in env.get("email_type_sent", "").lower()
```

**Key principle:** assertions operate on *environment state*, not on LLM output text. Extract the environment state at end of trial and judge that.

### Layer 2 — Environment Simulation (the sandbox)

Agents fail on broken URLs, localhost calls in cloud environments, and real-world rate limits. Build a **sandboxed environment** with injectable failures:

```python
from unittest.mock import Mock

class AgentHarness:
    def __init__(self, agent, spec: FlightBookingSpec):
        self.agent = agent
        self.spec = spec
        self.env = {}          # mutable environment state
        self.transcript = []   # full agent ↔ tool interaction log

    def run(self, task: str, injections: dict = None):
        """injections lets you inject failures: {'url_broken': True, ...}"""
        injections = injections or {}
        self.env = {"injections": injections, "payment_events": []}
        self.transcript = []
        # Wrap tool calls to intercept and record
        for step in self.agent.run(task):
            self.transcript.append(step)
            self._apply_step_to_env(step)
        return self

    def _apply_step_to_env(self, step):
        # Simplification: in real code, parse tool calls and mutate env
        pass

    def grade(self) -> dict:
        """Return per-check results and overall pass/fail."""
        results = {}
        for name in dir(self.spec):
            if name.startswith("check_"):
                check = getattr(self.spec, name)
                try:
                    results[name] = check(self.transcript, self.env)
                except Exception as e:
                    results[name] = False  # eval errors → fail, don't crash
        return results

    def cost(self) -> float:
        """Sum token costs from transcript entries."""
        return sum(s.get("token_cost", 0) for s in self.transcript)
```

### Layer 3 — Multi-Dimensional Grading (not just pass/fail)

Beyond binary success, grade on four axes:

| Dimension | What it measures | Why it matters |
|---|---|---|
| **Correctness** | Did the agent achieve the goal? | Core requirement |
| **Efficiency** | Token cost, latency, iteration count | Budget control |
| **Safety** | No hallucinated CVEs, no PII leaks | Production risk |
| **Robustness** | Passes with injected failures, not just happy path | Generalization |

```python
def evaluate(self, trials: list[dict]) -> dict:
    """
    trials: [{'task': str, 'injections': dict, 'expected': dict}]
    Returns a scorecard across all four dimensions.
    """
    rows = []
    for trial in trials:
        harness = AgentHarness(self.agent, self.spec).run(**trial)
        graded = harness.grade()
        rows.append({
            "task": trial["task"],
            "correctness": all(graded.values()),
            "efficiency": harness.cost() < self.budget,
            "safety": graded.get("check_no_hallucinated_cves", False),
            "robustness": graded.get("check_graceful_degradation", False),
            "total_cost": harness.cost(),
            "transcript": harness.transcript,
        })
    return self._aggregate_scores(rows)
```

### Layer 4 — Budget Gates (prevent silent waste)

Layer iteration budgets (see [S-229](s229-iteration-budgets-the-loop-control-pattern-max_iterations-gets-wrong.md)) with harness-level cost tracking:

```python
AGENT_BUDGET = 0.50  # USD per task

def run_with_budget_guard(self, task):
    harness = AgentHarness(self.agent, self.spec)
    start_budget = AGENT_BUDGET
    for step in harness.agent.run(task):
        harness.transcript.append(step)
        if harness.cost() > start_budget:
            harness.env["terminated"] = "budget_exceeded"
            break
    return harness
```

### Layer 5 — Regression Suite (the silent guardian)

The most valuable harness feature: catch regressions *before* deployment, automatically. Run the full suite on every agent config change:

```bash
# CI integration: run harness suite on PR
pytest tests/harness/ \
  --agent-config=./config/production.yaml \
  --budget=0.50 \
  --report=junit.xml

# Gate: fail PR if correctness < 95% or safety < 100%
```

**Proven pattern from OpenAI Codex / Anthropic internal docs:** Planner/Generator/Evaluator separation removes self-grading bias. The same agent should not generate and judge — use a separate eval model or rule-based grader.

**Another proven pattern:** Git-as-checkpoint. Store agent traces as git blobs — durable, diffable, replayable. When an agent fails, `git bisect` the trace history to find which change broke it.

## Receipt

> Receipt pending — 2026-06-30
> Not yet executed. Code above is architectural — representative of real harness patterns from Anthropic Cookbook, OpenAI eval guides, and the `awesome-harness-engineering` community list. Actual run with production agent would require environment setup (sandboxed tool backend, mock flight API, etc.). Mark this receipt when first real trial is executed against a live agent.

## See also

- [S-229 · Iteration Budgets](s229-iteration-budgets-the-loop-control-pattern-max_iterations-gets-wrong.md) — loop control patterns that prevent harness waste
- [S-116 · Output Determinism Testing](s116-output-determinism-testing.md) — harness-adjacent testing for agent stability
- [w10 · 技能三角](workspace/w10-skill-triangle.md) — LLM evaluation is the third leg of the production agent skill triangle
