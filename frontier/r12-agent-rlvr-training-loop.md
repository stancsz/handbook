# R-12 · Agent-RLVR — Training Specialized Agents with Verifiable Rewards

[R-07](r07-post-training-rlvr.md) covers how RLVR trains math and code models. But agents that *use tools, navigate environments, and execute multi-step tasks* break the standard recipe. A SWE agent that edits files, runs tests, and files PRs has no single "answer" to check — only outcomes. Agent-RLVR (Scale AI, arXiv:2506.11425) bridges this gap by adding *guidance* to the RLVR loop: instead of hoping an agent stumbles onto the right trajectory, you teach it.

## Forces
- **Standard RLVR fails in sparse-reward environments.** Math has a single correct answer. Agent tasks have long sequences of decisions where any wrong turn produces zero reward. An agent starting from scratch has near-zero probability of stumbling onto a passing trajectory.
- **Environment infrastructure is non-trivial.** Running a SWE agent means spinning up a git repo, sandboxing code execution, checking test suites — this is real engineering, not a prompt change.
- **Guidance is the unlock.** A teacher model provides intermediate hints ("try running the test suite first") that collapse the search space. Without guidance, training on SWE-bench goes from 9.4% → 15.2% Pass@1. With guidance: 9.4% → 22.4%.
- **Verifiers are the bottleneck.** The RLVR data flywheel only turns if someone can programmatically determine success. For SWE: unit tests. For CLI: exit code + output assertions. For other domains: you need to build or source a verifier, and bad verifiers produce bad agents.
- **Guidance itself can be trained.** The Agent-RLVR paper shows that training the guidance model improves outcomes further — guidance is not just a static prompt, it's a learned component.

## The move

**Agent-RLVR is a four-phase loop:**

```
Generate → Verify → Guide → Reattempt → Update
```

**Phase 1 — Generate.** The agent attempts a task. For SWE: read a GitHub issue, write a fix, run the tests. For CLI: interpret a natural-language command, execute bash, return the result. The trajectory (all tool calls, all outputs, all reasoning steps) is captured.

**Phase 2 — Verify.** The outcome is checked programmatically:
- SWE: did the PR's tests pass?
- CLI: does the exit code == 0 and output match the spec?
- Classification: does the output label match ground truth?
- Constraint satisfaction: did the agent respect all hard limits?

If verified: positive reward signal. If not: zero reward, but *record the failed trajectory*.

**Phase 3 — Guide.** A guidance model (often the same or a related frontier model) reviews the failed trajectory and produces an *hint trace* — not the answer, but directional advice: "The test is failing because X. Consider looking at Y first." This is the critical addition that standard RLVR lacks.

**Phase 4 — Reattempt.** The agent retries the task with the guidance appended to its context. Trajectories with guidance succeed at higher rates.

**Phase 5 — Update.** The agent policy is updated via GRPO (Group Relative Policy Optimization — no value network needed) using the rewards from guided trajectories. The guidance model can also be fine-tuned separately on (task, successful_trajectory) pairs to improve future hints.

```python
import subprocess
import json
from dataclasses import dataclass
from typing import Optional

@dataclass
class AgentTrajectory:
    task_id: str
    prompt: str
    steps: list[dict]  # [{"tool": "...", "input": "...", "output": "..."}]
    final_output: str
    reward: float = 0.0
    guidance: Optional[str] = None

def verify_swe_task(repo_path: str, patch: str) -> float:
    """Binary verifier for SWE agent output.
    Returns 1.0 if the patch fixes all failing tests, 0.0 otherwise.
    """
    try:
        # Apply the patch
        result = subprocess.run(
            ["git", "apply"],
            input=patch,
            cwd=repo_path,
            capture_output=True,
            timeout=30
        )
        if result.returncode != 0:
            return 0.0

        # Run the test suite
        test_result = subprocess.run(
            ["pytest", "--tb=no", "-q"],
            cwd=repo_path,
            capture_output=True,
            timeout=120
        )
        # Pass: all tests green
        return 1.0 if test_result.returncode == 0 else 0.0
    except subprocess.TimeoutExpired:
        return 0.0
    except Exception:
        return 0.0

def verify_cli_task(command_spec: str, agent_output: str, exit_code: int) -> float:
    """Verifier for CLI agent tasks.
    Success if exit code 0 AND output contains expected substrings.
    """
    if exit_code != 0:
        return 0.0
    # Lightweight semantic check: did key phrases appear?
    expected_phrases = extract_expectations(command_spec)
    hits = sum(1 for p in expected_phrases if p.lower() in agent_output.lower())
    return hits / len(expected_phrases) if expected_phrases else float(exit_code == 0)

# Minimal Agent-RLVR training step (pseudocode)
def agent_rlvr_step(base_agent, task, guidance_model, verifier):
    # Phase 1: Generate (no guidance)
    trajectory = base_agent.run(task)
    reward = verifier(task, trajectory)

    if reward < 1.0:
        # Phase 3: Generate guidance
        guidance = guidance_model.generate(
            f"Task: {task}\n"
            f"Agent attempted: {trajectory.final_output}\n"
            f"Failed. Provide a hint to guide the next attempt."
        )
        # Phase 4: Reattempt with guidance
        guided_trajectory = base_agent.run(task, context=[{"role": "assistant", "content": guidance}])
        guided_reward = verifier(task, guided_trajectory)

        if guided_reward > 0:
            # Phase 5: Update policy with (task, guided_trajectory, guided_reward)
            base_agent.update(trajectory=guided_trajectory, reward=guided_reward)
```

## Key design decisions

**Verifier quality is everything.** If your verifier has false positives (passes bad outputs) or false negatives (rejects good ones), your agent learns the wrong thing. For SWE: unit tests are ground truth. For other domains: invest in the verifier first, train the agent second. This is backwards from how most teams operate.

**Guidance ≠ the answer.** The hint should point at strategy, not solution. "The failing test is in test_api.py, check the exception type" beats "change ValueError to TypeError." Overly specific guidance defeats the RLVR purpose — you're back to behavioral cloning.

**Guidance model scales down.** A 70B guidance model outperforms a 7B one, but you don't need to match the agent model. A smaller guidance model fine-tuned on (task, failed_trajectory, hint) pairs often beats a general frontier model.

**Sample efficiency is the killer metric.** Agent-RLVR achieves 22.4% Pass@1 on SWE-bench Verified with only 817 training environments — roughly 4,000 trajectories total (one attempt + one guided attempt per task). Compare to the 50,000+ examples naive synthetic data pipelines burn through.

## When not to use this

- **No reliable verifier exists** — if you can't programmatically check success, you can't RLVR. Use SFT or RLHF instead.
- **Tasks require subjective judgment** — style, tone, "helpfulness" have no ground truth. RLVR doesn't apply.
- **Environment is too slow** — each RLVR step requires running the full agent loop. If one attempt takes 10 minutes, your training run takes weeks.
- **You're in early exploration** — RLVR converges toward a distribution. If you don't know what good looks like yet, premature RLVR locks in the wrong behavior.

## See also
- [R-07 · Post-Training and RLVR](r07-post-training-rlvr.md) — the foundational RLVR recipe this extends
- [R-02 · Reasoning Models](r02-reasoning-models.md) — reasoning traces are both input to and output of the RLVR pipeline
- [F-177 · Deterministic Agent Verification](f177-deterministic-agent-verification.md) — building the verification layer that RLVR depends on
