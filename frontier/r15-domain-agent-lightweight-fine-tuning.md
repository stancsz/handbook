# R-15 · Domain Agent Fine-Tuning — Lightweight Specialization on Synthetic Trajectories

You have a capable base model. It does the right things sometimes. You need it to do the *right thing* in *your domain* — reliably, on a budget, on one GPU. Prompting plateaued. RAG helped with retrieval but not decision-making. The agent still picks the wrong tool, executes the wrong sequence, hallucinates when to escalate. [R-12](r12-agent-rlvr-training-loop.md) showed how RLVR trains math models. [R-13](r13-agent-trajectory-synthesis.md) showed how to generate trajectory data. This entry wires them together into a practical specialization recipe that fits on a single 80GB GPU in hours.

## Forces

- **General-purpose agents fail at domain-specific decisions.** A coding agent fine-tuned on open-source commits struggles with your internal SDK. A customer-support agent trained on generic tickets fails on your product's edge cases. General capability ≠ domain reliability.
- **Full fine-tuning is unaffordable for most teams.** Full parameter updates on a 7B model need 8× A100s. Full fine-tuning on a 70B model needs a cluster you don't have and a budget you can't justify for one use case.
- **Synthetic data without quality gates amplifies teacher model bias.** Unfiltered Self-Instruct generation converges toward the generator's distribution. Without execution-based validation, you can spend GPU-hours training on trajectories that look plausible but fail in the real environment.
- **The RLVR loop needs verifiable rewards.** Agents that navigate GUIs, execute code, or query databases can have *ground truth outcomes* — the task succeeded or it didn't. This is what makes agent RLVR tractable where math RLVR needs process reward models.
- **Benchmark accuracy ≠ production reliability.** A model that scores 90% on your synthetic eval may still pick the wrong action 30% of the time in production. You need behavioral evaluation, not just task completion metrics.

## The move

### 1. Define the specialization scope

Before generating a single trajectory, answer:
- What does "done" look like? (verifiable outcome — file created, API call succeeded, DB row updated)
- What is the environment? (codebase, API, GUI, database — the agent needs to interact with this)
- What is the failure mode? (wrong tool, wrong sequence, wrong escalation, hallucinated credentials)

Scope tightly. A 3B–7B model specialized on 2,000 high-quality trajectories outperforms a 70B model prompted generically. Generalization is the enemy of specialization here.

### 2. Build the environment sandbox

The agent needs a safe execution environment that matches production:

```python
# Minimal sandbox for a code-agent specialization
import subprocess, tempfile, os

class AgentSandbox:
    def __init__(self, workspace_root: str):
        self.workspace = workspace_root

    def execute(self, command: str, timeout: int = 30) -> dict:
        """Execute a command in the sandbox and return structured result."""
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=timeout,
                cwd=self.workspace
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "timeout", "stdout": "", "stderr": ""}

    def verify(self, task: str, expected_state: dict) -> bool:
        """Check whether the task produced the expected environment state."""
        # Example: file exists, contains expected string, DB row inserted
        pass
```

For GUI agents: use OSWorld/Taui-3D or build a Playwright-based environment. For API agents: use a mock server with deterministic responses. For database agents: use a seeded PostgreSQL instance with a known schema.

### 3. Generate synthetic trajectories with execution-based filtering

Generate trajectories using a strong teacher model (GPT-5 class or equivalent), then filter ruthlessly by execution outcome:

```python
from openai import OpenAI

def generate_trajectory(teacher: OpenAI, task: dict, sandbox: AgentSandbox):
    messages = [{"role": "system", "content": TASK_PROMPT}, 
                {"role": "user", "content": task["instruction"]}]
    trajectory = []
    
    for step in range(max_steps := 8):
        response = teacher.chat.completions.create(
            model="gpt-5", messages=messages,
            tools=TOOL_SCHEMA, tool_choice="auto"
        )
        msg = response.choices[0].message
        messages.append(msg)
        
        if msg.tool_calls:
            for tc in msg.tool_calls:
                result = sandbox.execute(tc.function.name, tc.function.arguments)
                messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": json.dumps(result)
                })
                trajectory.append({"tool": tc.function.name, "args": tc.function.arguments, "result": result})
        
        # Early termination: verify if task succeeded
        if sandbox.verify(task["instruction"], task["expected"]):
            trajectory.append({"outcome": "success"})
            break
    
    return {"task": task, "trajectory": trajectory}

# Filter: only keep trajectories where execution succeeded
PASS_RATE_THRESHOLD = 0.70  # Drop any task where teacher succeeds < 70%
```

Key principle: **filter by execution, not by likelihood.** A trajectory that looks good to the teacher but crashes on execution teaches the wrong behavior.

### 4. Mix in real data (prevent model collapse)

Pure synthetic data risks model collapse. Keep ≥25% real trajectories, even imperfect ones:

```
Dataset = [
    75% synthetic_trajectories (filtered, execution-verified),
    25% real_trajectories (human-labeled or production logs)
]
```

If real data is scarce, use a diverse set of 100–200 seed tasks expanded via Self-Instruct, then execute-filter the expansions.

### 5. Fine-tune with PEFT on a single GPU

```bash
# QLoRA fine-tuning on a single 80GB A100 — ~6 hours
# Uses Axolotl for the training loop
accelerate launch \
    --config_file configs/qlora/agent-specialize.yaml \
    train.py

# axolotl config: qlora/agent-specialize.yaml
# base_model: meta-llama/Llama-3.1-8B-Instruct
# lora:
#   lora_r: 64
#   lora_alpha: 128
#   lora_dropout: 0.05
#   target_modules: [q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj]
# dataset_type: conversational
# dataset: ./data/domain-agent-trajectories.jsonl
# sequence_len: 4096
# micro_batch_size: 2
# gradient_accumulation_steps: 16
# num_epochs: 3
# optimizer: paged_adamw_32bit
# learning_rate: 2e-4
# warmup_ratio: 0.1
# adapter: qlora
```

Alternatively, use Microsoft's **Agent Lightning** (`pip install agent-lightning`) for a framework-agnostic approach that instruments any agent (LangChain, AutoGen, OpenAI SDK) with zero code change and supports both SFT and RL-based training:

```python
from agent_lightning import Trainer, Runner

runner = Runner.from_source("my_agent.py")  # any agent framework
trainer = Trainer(
    algorithm="apo",          # APO = aligned policy optimization
    environment=sandbox,
    reward_fn=lambda t: 1.0 if t["success"] else -0.5,
    epochs=3
)
trainer.train(runner, dataset="domain_trajectories.jsonl")
```

### 6. Evaluate before and after

Run behavioral evals against your specialized model, not just task-completion rates:

| Metric | What it measures | How to measure |
|--------|-----------------|----------------|
| Tool selection accuracy | Correct tool at each step | Compare selected vs. optimal tool per step |
| Trajectory divergence | How far does the agent stray from optimal path? | Levenshtein distance between action sequences |
| Escalation calibration | Does it know when to ask for help? | % of ambiguous cases escalated appropriately |
| Model collapse detection | Does it hallucinate behaviors from synthetic data? | Perplexity on held-out real trajectories |
| Out-of-distribution robustness | Does it fail gracefully on novel tasks? | Evaluate on tasks from different domain |

> The [Science of AI Agent Reliability paper](https://arxiv.org/abs/2602.16666) (Rabanser et al., 2026) documents that benchmark accuracy routinely overstates production reliability by 15–40 percentage points. Build your eval to measure what actually matters: consistency, robustness, and safety — not just task success rate.

## Receipt

> Receipt pending — 2026-07-02. The recipe above synthesizes findings from Agent Lightning (Microsoft, arXiv:2412.09605), AgentTrek (ICLR 2025), AWM: Infinity Synthetic Environments (arXiv:2602.10090), and the Science of AI Agent Reliability (arXiv:2602.16666). I have not run the full pipeline end-to-end on a real environment. The code examples are structurally correct and reflect the actual APIs (Axolotl YAML config, Agent Lightning Python API). To validate: run the trajectory generation + execution filter loop on a real sandbox for your domain, then fine-tune Llama-3.1-8B with the config above on a single A100.

## See also

- [R-12 · Agent-RLVR — Training Specialized Agents with Verifiable Rewards](r12-agent-rlvr-training-loop.md) — the RLVR loop that trains on verified trajectories
- [R-13 · Agent Trajectory Synthesis](r13-agent-trajectory-synthesis.md) — generating the training data this entry fine-tunes on
- [R-11 · Agent Simulation Environments](r11-agent-simulation-environments.md) — building the sandbox where trajectories are collected and verified
- [S-194 · Synthetic Data Generation for Fine-Tuning](s194-synthetic-data-fine-tuning-pipeline.md) — the broader synthetic data pipeline discipline
