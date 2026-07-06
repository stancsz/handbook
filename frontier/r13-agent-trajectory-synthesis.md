# R-13 · Agent Trajectory Synthesis

You need to train an agent that uses tools, navigates interfaces, and completes multi-step tasks. The model you have is strong at text generation but weak at sequential decision-making — exactly the gap that trajectory data fills. The problem: high-quality agent trajectories (goal + observations + reasoning + grounded actions) don't exist at internet scale. Human annotation is too expensive. LLM rollouts look plausible but fail in the real environment. This is the trajectory synthesis problem — and it is the bottleneck every agent lab is racing to solve.

## Forces

- **Trajectory data doesn't exist at scale on the internet.** Unlike text or images, agent trajectories require an agent interacting with a specific environment — a sequence of observations, decisions, and actions that can't be scraped. This makes training GUI agents, coding agents, and tool-using agents fundamentally harder than training language models.
- **Current LLMs aren't trained for sequential action.** Foundation models are trained on next-token prediction for informative responses. Sequential decision-making — where the right action depends on prior observations — is a different skill. Bridging this gap requires actual agent behavior data, not more text.
- **Human annotation is expensive and narrow.** Getting 1,000 annotated trajectories from expert annotators costs $50K–$200K. After three months the product shifted and 20% of your cases are stale. Scale this to millions of training examples and human annotation becomes a hard ceiling.
- **LLM rollouts are high-volume but low-quality.** You can generate 10,000 synthetic trajectories from a frontier model in hours. Most are syntactically plausible but fail when replayed in the actual environment. Volume without verification produces a model that confidently fails.
- **Trajectory diversity is non-negotiable for robustness.** An agent trained only on successful trajectories learns to repeat patterns, not to recover from errors. A useful eval set includes both on-distribution successes and adversarial edge cases.
- **Verification is the hardest part.** Generating a trajectory is easy. Verifying it achieved its goal in the environment — without human review — is the unsolved piece. Every synthesis pipeline converges on the same question: how do you know the trajectory actually worked?

## The move

**Three synthesis strategies, in order of increasing scalability:**

1. **LLM rollouts + environment verification** — generate trajectories with a teacher model, replay them in the target environment, keep only the ones that succeed. The challenge: frontier models are expensive at million-scale generation. Use this for high-value, narrow-scope trajectories (e.g., SWE-bench style coding tasks).

2. **Tutorial-guided synthesis (AgentTrek pattern)** — harvest structured tutorials from the web (e.g., "how to file a PR on GitHub", "how to set up a database"). Parse them into goal + step-by-step instructions. Use a VLM agent to execute the tutorial in a simulated environment. Score with an evaluator model. This is the highest-quality scalable approach: tutorials provide ground-truth action sequences; the agent provides execution verification. (AgentTrek, Xu et al., ICLR 2025 — arXiv:2412.09605)

3. **Critique-filter cascade** — generate N trajectories with a base model, score them with a judge model on coherence and plausibility, keep the top K%, replay in environment, keep the ones that succeed. This is the production pipeline: it amortizes frontier-model cost by using a smaller model for generation and a larger model for filtering.

**The four components of a trajectory, in order of importance:**

| Component | Description | Why it matters |
|---|---|---|
| Goal | High-level objective | Defines task scope, anchors evaluation |
| Observations | Environment state at each step | Without these, the model can't learn context-dependent action |
| Reasoning | Why the agent chose this action given prior observations | Teaches decision logic, not just action mimicry |
| Actions | Grounded tool calls / keystrokes / API calls | The skill being trained |

**The critical pattern — Guide-Then-Synthesize:**

Do NOT generate trajectories with the model you're trying to train. Use a stronger teacher model to generate high-quality trajectories, then fine-tune the student model on them. If you generate with the student and train the student, you're amplifying the student's errors.

```python
import json
import subprocess
from dataclasses import dataclass

@dataclass
class TrajectoryStep:
    goal: str
    observation: str
    reasoning: str
    action: str
    success: bool = False

def synthesize_and_verify(goal: str, model: str = "claude-sonnet-4-20250514") -> TrajectoryStep:
    """
    Guide-Then-Synthesize pattern: generate with a strong teacher,
    verify by executing in the target environment.
    """
    # Step 1: Generate trajectory with teacher model
    prompt = f"""Given the goal: {goal}
Generate a trajectory with: goal, observation, reasoning, action for each step.
Stop when the goal is achieved. Output JSON."""
    
    trajectory_raw = generate_with_model(model, prompt)
    steps = json.loads(trajectory_raw)

    # Step 2: Replay each action in the actual environment
    verified_steps = []
    for step in steps:
        action = step["action"]
        # Execute the action in sandbox — returns (success, observation)
        obs, ok = execute_in_environment(action)
        step["observation"] = obs
        step["success"] = ok
        verified_steps.append(step)

        if not ok:
            # Trajectory failed — truncate and mark
            break

    # Step 3: Keep only verified trajectories
    all_success = all(s["success"] for s in verified_steps)
    return verified_steps, all_success

# Production pattern: batch synthesis with critique-filter
def batch_synthesize(goals: list[str], n_generate: int = 10, top_k: float = 0.3):
    """
    1. Generate N trajectories per goal with base model
    2. Score with judge model
    3. Keep top K% by score
    4. Verify in environment
    5. Return only verified trajectories
    """
    candidates = []
    for goal in goals:
        for _ in range(n_generate):
            traj = synthesize_and_verify(goal)
            score = judge_score(traj)  # LLM-as-judge on coherence
            candidates.append((traj, score))
    
    # Filter by score
    threshold = sorted(s for _, s in candidates)[int(len(candidates) * (1 - top_k))]
    scored = [(t, s) for t, s in candidates if s >= threshold]
    
    # Final verification
    verified = [t for t, _ in scored if all(step["success"] for step in t)]
    return verified  # Ready for RLVR or fine-tuning

# Real-world scale: the pipeline outputs trajectories in the format
# expected by Agent-RLVR (R-12) or behavioral cloning loss
```

## Receipt

> Receipt pending — July 1, 2026. The Guide-Then-Synthesize + critique-filter pattern is established in the AgentTrek (ICLR 2025) and Scale AI Agent-RLVR (arXiv:2506.11425) papers. The code above reflects the architecture — execution in a real environment requires a sandboxed git repo for coding tasks or a headless browser for GUI tasks.

## See also

- [R-11 · Agent Simulation Environments](r11-agent-simulation-environments.md) — the environments where trajectories are executed and verified
- [R-12 · Agent-RLVR Training Loop](r12-agent-rlvr-training-loop.md) — how verified trajectories feed into RL training for agents
- [F-17 · Synthetic Eval Generation](f17-synthetic-eval-generation.md) — generating test cases vs. generating training trajectories; the eval framing
- [S-222 · Agent Trajectory Replay](s222-agent-trajectory-replay.md) — using trajectory data for debugging production failures
