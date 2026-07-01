# S-295 · Synthetic Trajectory Fine-Tuning Pipeline

Your agent scores 92% on your internal benchmark. Production tells a different story — it fails on your internal APIs, produces payloads in the wrong schema, and calls tools in the wrong order. The model was trained on the internet. Your business runs on your own systems. Synthetic trajectory fine-tuning closes that gap by collecting agent runs, grading them automatically, and using successful trajectories as training data for the next generation.

## Forces

- **Successful trajectories are rare and expensive.** A production agent might succeed 30–60% of the time. Waiting for organic successes means months of collection. You need to generate and grade at scale.
- **Grading is harder than it looks.** Task completion (passed/failed) only works for verifiable outcomes. Most agent work — drafting, reasoning, multi-step coordination — has no clean answer key. You need a multi-signal grading strategy.
- **Naive synthetic fine-tuning causes model collapse.** Training purely on synthetic trajectories degrades the model's ability to handle cases outside the generator's distribution. A minimum of 20–30% real-world data is a documented safety floor.
- **Feedback-to-model lag kills the loop.** Collecting trajectories takes days. Grading takes hours. Fine-tuning takes hours. Deploying takes days. If any step breaks, the loop stalls and the model drifts from production reality.
- **Tool-specific patterns are fragile under distribution shift.** If your MCP server changes an API schema, every tool-call trajectory generated against the old schema is now misleading training data.

## The move

The pipeline has five stages. Each feeds the next.

### 1. Collect trajectories at the inference layer

Instrument your agent runtime to emit structured trajectory logs. Each trajectory records: task input, reasoning trace, tool calls (name + parameters + raw result), and final output.

```python
import json, uuid, time
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class Trajectory:
    trajectory_id: str
    task_input: str
    reasoning_steps: list[str]
    tool_calls: list[dict]   # {tool, params, result, duration_ms}
    final_output: str
    completion_status: str    # success | failure | partial
    reward_score: Optional[float] = None
    graded_at: Optional[str] = None

# Hook into your agent runtime's tool-calling layer
def trajectory_middleware(agent_fn):
    def wrapper(task: str) -> Trajectory:
        traj = Trajectory(
            trajectory_id=str(uuid.uuid4()),
            task_input=task,
            reasoning_steps=[],
            tool_calls=[],
            final_output="",
            completion_status="failure",
        )
        start = time.monotonic()

        # Wrap each tool call to record inputs/outputs
        original_call = agent_fn.__globals__.get("_tool_call")
        def logged_call(tool, params):
            t0 = time.monotonic()
            result = original_call(tool, params) if original_call else None
            traj.tool_calls.append({
                "tool": tool,
                "params": params,
                "result": str(result)[:500],  # truncate for storage
                "duration_ms": int((time.monotonic() - t0) * 1000),
            })
            return result

        traj.final_output = agent_fn(task)  # run the agent
        traj.completion_status = "success"  # stub — grading sets this properly
        return traj

    return wrapper
```

### 2. Grade with multi-signal feedback

Build a grading function that combines available signals. Use the strongest signal available for each task type:

```python
from anthropic import Anthropic
client = Anthropic()

def grade_trajectory(traj: Trajectory) -> tuple[str, float]:
    """
    Multi-signal grading. Returns (status, reward_score 0-1).
    """
    # Signal 1: Verifiable outcome (strongest)
    if traj.tool_calls:
        last_result = traj.tool_calls[-1].get("result", "")
        if "200" in last_result or "success" in last_result.lower():
            return "success", 1.0

    # Signal 2: Task completion via LLM judge
    judge_prompt = f"""Rate this agent trajectory on a scale of 0-1.
Task: {traj.task_input[:500]}
Final output: {traj.final_output[:500]}
Tool calls made: {[c['tool'] for c in traj.tool_calls]}

Consider: Did the agent complete the task? Was tool usage appropriate?
Score only. Return a single float."""
    
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": judge_prompt}]
    )
    try:
        score = float(response.content[0].text.strip())
        score = max(0.0, min(1.0, score))
        status = "success" if score > 0.7 else "partial" if score > 0.4 else "failure"
        return status, score
    except ValueError:
        return "partial", 0.5

def grade_batch(trajectories: list[Trajectory], threshold: float = 0.7) -> list[Trajectory]:
    """Grade a batch, filter to quality bar, return high-quality positives."""
    graded = []
    for traj in trajectories:
        status, score = grade_trajectory(traj)
        traj.completion_status = status
        traj.reward_score = score
        traj.graded_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        if score >= threshold:
            graded.append(traj)
    return graded
```

### 3. Mix synthetic and real data

Combine graded synthetic trajectories with real agent runs. Target a 70/30 synthetic-to-real ratio. Real data provides diversity that prevents the model from collapsing to the generator's distribution.

```python
from datasets import Dataset

def build_training_mix(
    synthetic_trajectories: list[Trajectory],
    real_trajectories: list[Trajectory],
    synthetic_ratio: float = 0.70,
) -> Dataset:
    """
    Mix synthetic and real trajectories into an SFT dataset.
    Enforces synthetic_ratio by downsampling the larger source.
    """
    max_synthetic = int(len(real_trajectories) * synthetic_ratio / (1 - synthetic_ratio))
    sampled_synthetic = synthetic_trajectories[:max_synthetic]

    def format_trajectory(traj: Trajectory) -> dict:
        tool_log = "\n".join(
            f"<tool>{c['tool']}</tool><input>{c['params']}</input><output>{c['result']}</output>"
            for c in traj.tool_calls
        )
        return {
            "messages": [
                {"role": "user", "content": traj.task_input},
                {"role": "assistant", "content": f"{' '.join(traj.reasoning_steps)}\n{tool_log}\n{final_output}"},
            ],
            "completion_status": traj.completion_status,
            "reward": traj.reward_score,
        }

    all_examples = (
        [format_trajectory(t) for t in sampled_synthetic] +
        [format_trajectory(t) for t in real_trajectories]
    )
    return Dataset.from_list(all_examples)
```

### 4. Fine-tune with rollback guard

```python
from unsloth import FastLanguageModel
import torch

def fine_tune_from_trajectories(
    base_model: str = "meta-llama/LLlama-3.1-8B-Instruct",
    training_dataset: Dataset,
    output_dir: str = "./lora_adapter",
    epochs: int = 3,
    learning_rate: float = 2e-4,
    rollback_threshold: float = 0.90,
) -> str:
    """
    Fine-tune a LoRA adapter from graded trajectories.
    Includes a rollback guard: if eval loss spikes, abort and keep previous adapter.
    Returns path to new adapter.
    """
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=4096,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        lora_dropout=0.05,
    )

    # Split: 90% train / 10% eval
    split = training_dataset.train_test_split(test_size=0.1, seed=42)
    
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=split["train"],
        eval_dataset=split["test"],
        dataset_text_field="messages",
        max_seq_length=4096,
        dataset_num_proc=4,
        packing=True,
        args=TrainerArgs(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_steps=10,
            num_train_epochs=epochs,
            learning_rate=learning_rate,
            fp16=not torch.cuda.is_bavailable(),
            bf16=torch.cuda.is_bf16_available(),
            eval_strategy="steps",
            eval_steps=50,
            save_strategy="steps",
            save_steps=50,
            save_total_limit=1,        # keep only best
            load_best_model_at_end=True,  # auto-rollback on eval degradation
            metric_for_best_model="eval_loss",
            greater_is_better=False,
        ),
    )
    trainer.train()
    model.save_pretrained(output_dir)
    return output_dir
```

### 5. Deploy with canary + quality gate

Never swap the production model without a quality gate. Run a canary: 5% of traffic on the new adapter for 1 hour, compare task-success rate and latency. Roll back if success rate drops below `rollback_threshold` of baseline.

## Receipt

> Receipt pending — 2026-07-01. The code above composes real primitives: Unsloth FastLanguageModel (open source), Anthropic LLM judge, standard trajectory logging middleware, and HuggingFace SFTTrainer. The 70/30 mixing ratio and rollback guard pattern come from documented production deployments (NVIDIA NeMo, Microsoft Foundry RFT, Tonic.ai synthetic pipelines). End-to-end run on a production agent stack was not executed in this session — validate against your own agent runtime before deploying.

## See also

- [S-194 · Synthetic Data Generation for Fine-Tuning](s194-synthetic-data-fine-tuning-pipeline.md) — upstream data generation (this entry is about agent trajectories, not static datasets)
- [S-281 · Agent Evaluation Is the Missing Layer](s281-agent-evaluation-the-layer-nobody-builds-until-production-breaks.md) — the grading signals used here feed the eval layer
- [R-12 · Agent-RLVR Training Loop](frontier/r12-agent-rlvr-training-loop.md) — the reinforcement-learning foundation that RFT builds on
