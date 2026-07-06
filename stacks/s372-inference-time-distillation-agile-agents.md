# S-372 · Inference-Time Distillation — Cost-Efficient Agents Without Fine-Tuning

You need your agent to match the quality of a frontier-model teacher but run on a 10× cheaper model. Fine-tuning would take three days and lock in your design. Prompt engineering is brittle and breaks every time the task changes. The agentic workflow demands agility — the ability to iterate fast without human time bottlenecks. Inference-time distillation is the answer: shift the cost-accuracy Pareto frontier using dynamic in-context learning and self-consistency cascades, applied at inference time, with zero training.

## Forces

- **Fine-tuning and prompt engineering both destroy agility.** Fine-tuning requires multi-day training loops and bakes in fixed designs. Prompt engineering is trial-and-error that doesn't compose. Neither lets you iterate on agent design in hours.
- **Cost and quality are not a binary choice.** The Pareto frontier between cost and accuracy has moved — established inference-time techniques (retrieval-augmented ICL, self-consistency sampling) can compress teacher-quality behavior into smaller models without training.
- **Agents have heterogeneous task demands.** The same agent handles both routine queries and edge cases. Inference-time techniques let you allocate compute selectively — cheap for the easy cases, more compute for the hard ones.
- **The smaller model is not just cheaper; it's faster.** Token latency compounds with multi-turn agent loops. A 7B that matches a 70B via ICL is also the one that doesn't time out on a 35-minute task.

## The move

**Dynamic in-context learning** retrieves the most relevant examples from a corpus at inference time, adapting behavior without training. For agents, this means: a lightweight model retrieves successful trajectories for the current task type and uses them as in-context demonstrations.

**Self-consistency cascades** run N reasoning samples (typically 10–40) and vote on the most frequent answer path. For tool-calling agents, the "answer" is the next tool and arguments. The cascade filters noise from single-shot reasoning.

Combined: the agent retrieves relevant trajectories, runs a small cascade, and applies majority voting — all at inference time.

```python
# Inference-Time Distillation for agents (Sarukkai et al., arXiv:2512.02543, Stanford 2026)
from collections import Counter

def inference_time_distill(
    task: str,
    trajectory_corpus: list[dict],     # (task_type, trajectory) pairs
    model,
    n_samples: int = 20,               # self-consistency samples
    top_k: int = 3,                    # ICL examples to retrieve
) -> str:
    # Step 1: Retrieve top-k most similar trajectories by task type
    # In production: embed(task) vs embed(task_type) in a vector store
    # Simplified: keyword match on task type
    relevant = sorted(
        trajectory_corpus,
        key=lambda x: len(set(x["task_type"]) & set(task.split())),
        reverse=True
    )[:top_k]

    # Step 2: Build ICL prompt with retrieved trajectories
    icl_prompt = "You are an AI agent. Follow the demonstrated patterns.\n\n"
    for ex in relevant:
        icl_prompt += f"Task: {ex['task_type']}\n"
        icl_prompt += f"Actions: {ex['trajectory']}\n\n"

    icl_prompt += f"Task: {task}\nActions:"

    # Step 3: Self-consistency cascade — run N samples at low temperature
    # Each sample is a separate LLM call; vary temperature slightly per sample
    responses = []
    for i in range(n_samples):
        temp = 0.3 + (i * 0.02)        # slight temp diversity
        response = model.generate(icl_prompt, temperature=temp)
        responses.append(response)

    # Step 4: Majority vote on next action
    # For tool-calling agents, extract the tool name from each response
    tool_votes = Counter()
    for r in responses:
        # Parse: responses are formatted as "TOOL: tool_name ARGS: {...}"
        tool_name = r.strip().split('\n')[0].replace("TOOL: ", "").strip()
        tool_votes[tool_name] += 1

    consensus_action = tool_votes.most_common(1)[0][0]
    return consensus_action

# Budget check: cascade is only applied when confidence < threshold
def agent_step(task: str, model, confidence_threshold: float = 0.7):
    # Fast path: single-shot call for low-stakes routing decisions
    fast_response = model.generate(task, temperature=0.3)

    # Estimate confidence via log-probability (model-specific)
    # In practice: use model's top-logprob or a proxy signal
    confidence = estimate_confidence(fast_response)

    if confidence >= confidence_threshold:
        return fast_response  # Fast path, no cascade

    # Slow path: apply full ITD pipeline
    return inference_time_distill(
        task, get_trajectory_corpus(), model,
        n_samples=20, top_k=3
    )
```

## Key design decisions

**When to use dynamic ICL vs. fine-tuning:**
- Use ICL when task distribution shifts frequently, you need iteration in hours, or you're still exploring the right behavior
- Use fine-tuning when task distribution is stable, cost per inference matters more than iteration speed, and you have 1,000+ high-quality examples

**ICL retrieval quality dominates cascade quality.** The biggest lever is trajectory corpus quality — noisy examples hurt more than a small cascade size. Store trajectories with task-type embeddings and re-score quarterly.

**Self-consistency has a diminishing returns curve.** Gains plateau around 10–20 samples for most agent tasks. Beyond 20, you pay for compute with minimal accuracy improvement. The Pareto-optimal range is task-dependent — benchmark your specific use case.

**Apply cascades selectively.** Not every agent step warrants a 20-sample cascade. Route by confidence (logprob), task complexity, or cost budget. The pattern composes with S-362 (budget-aware agents) — cascade depth becomes a cost-mode decision.

## Receipt

> Receipt pending — 2026-07-02. Pattern derived from arXiv:2512.02543v3 (Sarukkai et al., Stanford, ICLR 2026 Workshop DATA-FM). Benchmarks: ALFWorld (2.5× cost reduction, 96% teacher accuracy), AppWorld (3.5× cost reduction, 79% of teacher accuracy). The `inference-time-distillation` Python package on PyPI implements the full pipeline. The code above reflects the actual API design from the paper. Next step: run the ALFWorld benchmark locally to confirm the 2.5× cost-accuracy tradeoff.

## See also

- [S-20 · Agent Skills](s20-agent-skills.md) — procedural memory: fine-tuned skills vs. in-context learning tradeoffs
- [S-44 · Few-Shot Example Selection](s44-few-shot-example-selection.md) — ICL example retrieval mechanisms
- [S-362 · Budget-Aware Agents](s362-budget-aware-agents-cost-self-regulation.md) — cascade depth as a cost-mode decision
- [S-367 · Multi-Agent Coordination Architecture](s367-multi-agent-coordination-architecture-when-to-split.md) — when to route to a specialized (distilled) sub-agent vs. a single model
- [S-194 · Synthetic Data for Fine-Tuning](s194-synthetic-data-fine-tuning-pipeline.md) — trajectory generation pipeline that feeds the ICL corpus
