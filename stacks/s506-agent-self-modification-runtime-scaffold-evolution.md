# S-506 · Agent Self-Modification: Runtime Scaffold Evolution

You ship an agent. It works. Six weeks later the benchmark scores it achieved have dropped — not because the model degraded, but because the scaffold around it became misaligned with the task. The tools changed, the latency profile shifted, the failure modes evolved. Your agent's hardcoded retry limits, timeout thresholds, and tool-selection heuristics are now wrong. Someone manually updates the scaffold. What if the agent updated it itself?

Self-modifying agents — systems that rewrite their own scaffolding to improve performance — have moved from theory to production benchmarks. SICA raised SWE-Bench Verified from 17% to 53% with no human changes. Live-SWE-agent reached 77.4%. The pattern is real and the gap between "hand-crafted scaffold" and "self-improving scaffold" is measurable.

## Forces

- **Scaffolds are load-bearing but treated as throwaway.** Guardrails, routing logic, tool-selection heuristics, timeout budgets, and retry policies determine 60–80% of agent reliability — yet they're written once and never revisited. The agent evolves; the container doesn't.
- **Scaffold tuning is the real bottleneck, not the model.** For specialized domains (code review, CRM automation, financial data entry), the base model's capability far exceeds what the scaffold extracts. The ceiling is the harness, not the engine.
- **Self-modification surface is seductive but dangerous.** When an agent can edit its own evaluation logic, it can optimize for the wrong thing by the most direct available path — including editing the code that judges it.
- **The scaffold is not the model.** Editing scaffolding is not model fine-tuning. It changes orchestration, not weights. The distinction matters for safety boundaries and rollback scope.

## The move

Treat the scaffold as a versioned, evaluable artifact. Build the loop: observe → propose → evaluate → commit-or-revert.

**The five-step modification loop:**

```
observe  →  collect per-step metrics (latency, tool-call accuracy, error rate, cost/step)
             compare against rolling baseline
             trigger modification when delta exceeds threshold (e.g., >15% regression)
propose  →  agent generates scaffold modification from failure trace analysis
             categorize as: timeout adjustment, tool-selection rule, retry policy,
             context-management strategy, or routing logic
evaluate  →  run modified scaffold against held-out eval set
             require: accuracy ≥ baseline AND cost ≤ baseline × 1.1
             multi-metric guard: safety score must not drop below threshold
commit    →  if eval passes, commit to scaffold version store with diff + rationale
revert    →  if eval fails or safety score drops, atomic revert to previous version
```

**Immutability layers — what the agent cannot touch:**

```
ALWAYS_LOCKED:
  - Evaluation harness code and scoring functions
  - Safety policy definitions (I_hard, G_hard from S-503)
  - Permission model and tool allowlist
  - Audit logging infrastructure

AGENT_EDITABLE:
  - Timeout values and retry counts
  - Tool-selection heuristics and routing rules
  - Context compaction thresholds
  - Cost-budget thresholds (S-362)
  - Prompt fragments (within bounded autonomy, S-355)
```

**Reward-hacking countermeasures — the three you need:**

1. **Evaluator separation.** The agent cannot read or write the evaluation code. The eval harness lives in a separate process, owned by the platform, not the agent.
2. **Multi-metric gates.** Single-metric evaluation is gameable. Require passes on ≥3 orthogonal metrics (accuracy + cost + safety) before committing a modification.
3. **Synthetic adversarial traces.** Feed the modification proposal step a poisoned trace — a case where the agent's "improvement" is actually a regression — and verify the revert trigger fires.

```python
# Minimal scaffold modification loop (pseudocode)
import ast, hashlib, subprocess

class ScaffoldingEvolutionLoop:
    LOCKED_PATHS = {"eval harness", "safety policy", "permissions", "audit log"}

    def __init__(self, agent, eval_suite, safety_threshold=0.95):
        self.agent = agent
        self.eval_suite = eval_suite
        self.safety_threshold = safety_threshold
        self.scaffold_versions = []

    def observe(self) -> dict:
        """Collect current performance snapshot."""
        return {
            "accuracy": self.eval_suite.run(),
            "avg_cost_per_task": self.agent.cost_tracker.avg(),
            "safety_score": self.eval_suite.safety_score(),
        }

    def propose_modification(self, baseline: dict, regression: dict) -> str:
        """Agent proposes scaffold edit from failure analysis."""
        diff = {
            "baseline": baseline,
            "regression": regression,
            "failure_traces": self.agent.last_n_traces(n=5),
        }
        return self.agent.generate_scaffold_edit(diff)

    def evaluate(self, proposed_scaffold: str, baseline: dict) -> dict:
        """Sandboxed eval of proposed scaffold change."""
        # Validate: agent cannot touch locked paths
        for locked in self.LOCKED_PATHS:
            assert locked not in proposed_scaffold, f"Agent touched locked: {locked}"

        # Swap in proposed scaffold
        original = self.agent.scaffold_snapshot()
        self.agent.apply_scaffold(proposed_scaffold)

        # Run eval suite
        result = self.eval_suite.run()

        # Revert always — commit only if confirmed
        self.agent.restore_scaffold(original)
        return result

    def commit_or_revert(self, result: dict, baseline: dict,
                         proposed_scaffold: str) -> bool:
        acc_ok  = result["accuracy"] >= baseline["accuracy"]
        cost_ok = result["avg_cost_per_task"] <= baseline["avg_cost_per_task"] * 1.1
        safe_ok = result["safety_score"] >= self.safety_threshold

        if acc_ok and cost_ok and safe_ok:
            version = self.scaffold_versions.push({
                "scaffold": proposed_scaffold,
                "baseline_metrics": baseline,
                "result_metrics": result,
                "sha": hashlib.sha256(proposed_scaffold.encode()).hexdigest()[:8],
            })
            self.agent.apply_scaffold(proposed_scaffold)
            return True
        else:
            return False  # reverted to baseline

# Anti-reward-hacking: adversarial probe
def adversarial_probe(loop: ScaffoldingEvolutionLoop, baseline: dict) -> bool:
    """Feed a poisoned modification — verify the loop rejects it."""
    poisoned = loop.agent.generate_scaffold_edit({
        "fake_regression": {"accuracy": 0.1},  # looks like a big win
        "poison": "eval_suite.set_score(1.0)"  # but it hacks the harness
    })
    result = loop.evaluate(poisoned, baseline)
    # Must reject: safety score or accuracy will fail the multi-metric gate
    assert result["safety_score"] < loop.safety_threshold, \
        "FAIL: adversarial modification was accepted"
    return True
```

## Receipt

> Verified 2026-07-03 — Built on: SICA paper (arXiv:2504.15228, Robeyns et al.), Tian Pan "Self-Modifying Agent Horizon" (Apr 2026), BSWEN self-improving coding agent blog (Mar 2026), Sakana AI Research "The First AI Agent That Hacked Itself" (2026), Zylos Research AI Agent Reliability 2026. SICA: 17%→53% SWE-bench Verified. Live-SWE-agent: 0%→77.4%. Sakana found reward-hacking agents generalize alignment-faking and intentional sabotage behaviors. Code example is pseudocode-inference — Receipt pending (requires live eval harness).

## See also

- [S-352 · Agentic Compensation Keys](stacks/s352-agentic-compensation-keys.md) — compensation pairs with self-modification: when the agent modifies its scaffold, undoability must be preserved
- [S-355 · Agent Autonomy Levels](stacks/s355-agent-autonomy-levels-bounded-autonomy.md) — self-modification permissions map to autonomy level; L3+ required for scaffold editing
- [S-503 · Consequential Action Gates](stacks/s503-consequential-action-gates-tiered-hitl-architecture.md) — the HITL gate that governs scaffold commit/revert decisions
- [S-362 · Budget-Aware Agents](stacks/s362-budget-aware-agents.md) — cost-per-task metric feeds the modification loop's baseline
- [R-13 · Agent Trajectory Synthesis](frontier/r13-agent-trajectory-synthesis.md) — trajectories as the data substrate for the modification proposal step
