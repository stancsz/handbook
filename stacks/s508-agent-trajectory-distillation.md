# [S-508] · Agent Trajectory Distillation

Your $50K/month frontier API bill is a symptom, not a diagnosis. The fix is not a better cache key — it is a smaller model that learned to replicate your best agent's behavior.

## Situation

You have a production agent built on GPT-4o or Claude Sonnet. It works well. It costs a fortune. You have six months of logs showing which tool-call sequences succeeded, which failed, and why. Now you want to compress that behavioral intelligence into a small model that handles 80% of the same tasks at 10% of the cost and 5x the latency. This is agent trajectory distillation — and it is nothing like distilling a text model.

## Forces

- **Frontier cost is unsustainable at scale.** GPT-4o-class inference at volume is $3-15/Mtokens. An agent that runs 50 steps to complete one task can cost $2-10 per task. For high-volume narrow workflows (document classification, support ticket routing, data extraction), this is economics, not engineering.
- **Agents produce trajectories, not tokens.** Standard distillation copies outputs. Agent distillation must copy decision sequences — when to call which tool, how to handle errors, when to stop. Trajectories have branching structure that flat text does not.
- **Teacher success is not uniformly distributed.** Your frontier agent succeeds 73% of the time on Task X. Distilling from all trajectories (including failures) teaches the student to replicate failure modes. You need trajectory filtering, not just collection.
- **The student inherits the teacher's context illusions.** If the teacher was built on a rich RAG context, the student has no access to that context at inference time. Distilled behavior must be self-contained, not context-dependent.

## The Move

**Step 1 — Define the distillation scope before collecting data.**

Narrow the target to one behavior, not "be as good as the teacher." Good distillation targets: "route support tickets to the right queue 90% of the time," "extract structured fields from invoices," "decide whether to escalate a conversation to a human." Bad targets: "handle any customer support scenario." Scope is the single most important variable.

**Step 2 — Collect and filter trajectories.**

```
TRAJECTORY_COLLECT_PROMPT = """
Run this task using the full agent stack.
Log: [user_input, tool_name, tool_input, tool_output, stop_reason, final_output]
Only log successful trajectories (task completed without hallucination or crash).
Flag partial successes separately — do not mix with full successes.
"""

# Trajectory quality filter
def filter_trajectories(trajectories):
    return [
        t for t in trajectories
        if t.success
        and t.error_recovery_attempts <= 2
        and t.stop_reason == "task_complete"
        and t.context_length < 32_000  # avoid context-dependent behavior
    ]
```

Filter aggressively. NVIDIA's Data Flywheel Blueprint showed that filtering to high-confidence trajectories (teacher agreement score > 0.85) improved student tool-call accuracy from 61% to 94%. Raw collection without filtering teaches the student to imitate the teacher's worst habits.

**Step 3 — Choose the distillation signal.**

| Signal | When to use | Tradeoff |
|--------|-------------|----------|
| **Final output matching** | Simple classification, extraction | Ignores reasoning process; student learns shortcuts |
| **Trajectory cloning** | Tool-calling, multi-step tasks | Preserves decision structure; requires clean trajectory format |
| **Process reward modeling (PRM)** | Tasks with many valid paths | Best for complex reasoning; most expensive to collect |
| **Verified outputs only** | High-stakes domains (medical, legal) | Minimum quality bar; slow to collect |

For most agent distillation, trajectory cloning with verified outputs is the sweet spot: collect the full [state → action → result] sequence, label the final outcome, train the student to predict the next action given the state.

**Step 4 — Format as a training dataset.**

```json
// Convert trajectory to training example
{
  "messages": [
    {"role": "system", "content": "You are a ticket routing agent."},
    {"role": "user", "content": "Customer says: 'I was charged twice for my subscription'"},
    {"role": "assistant", "content": "", "tool_calls": [
      {"name": "classify_ticket", "arguments": {"category": "billing", "urgency": "high"}}
    ]},
    {"role": "tool", "content": "{"routed_to": "billing_queue", "agent": "billing-bot"}"},
    {"role": "assistant", "content": "Escalation: billing → billing-bot (high urgency)"}
  ],
  "outcome": "correct"
}
```

Format as multi-turn chat completions fine-tuning (OpenAI, Anthropic, or Ollama). Include the tool call as a structured turn, not as a text action description. The student must learn to produce `tool_calls`, not just text.

**Step 5 — Train with DPO or SFT.**

```
# Supervised fine-tuning baseline
sft_config = {
    "model": "Qwen3-3B",
    "lr": 1e-5,
    "batch_size": 8,
    "epochs": 3,
    "gradient_checkpointing": true,
    "train_on_trajectories_only": true,
    "filter_threshold": 0.85  # teacher agreement
}

# DPO for preference alignment on borderline cases
dpo_config = {
    "teacher_model": "gpt-4o",
    "student_model": "Qwen3-3B",
    "preferred_trajectories": high_quality,
    "rejected_trajectories": medium_quality,
    "beta": 0.1  # KL penalty strength
}
```

**Step 6 — Shadow deploy before full cutover.**

Run the student model in parallel with the teacher on live traffic. Gate deployment on: tool-call accuracy ≥ 95% of teacher, error recovery rate ≥ teacher, no new failure categories. Use the 30-40% disagreement threshold from Perea's production pipeline: if student and teacher disagree on > 40% of cases in shadow mode, the distillation is not ready.

**Step 7 — Build a distillation flywheel.**

```
                    ┌──────────────────────┐
  Production logs ──│ Trajectory Collector │── Filtered trajectories
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Trajectory Selector  │── (teacher agreement ≥ 0.85)
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  SFT / DPO Trainer   │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Shadow Evaluator    │── (disagreement < 40%)
                    └──────────┬───────────┘
                               │
                    Production student model (10-100x cheaper)
```

The flywheel means the student improves over time as production data accumulates. Each new high-quality teacher trajectory refines the student.

## Receipt

> Verified 2026-07-03 — NVIDIA Data Flywheel Blueprint reports a fine-tuned Llama-3.2-1B achieving **98% of 70B tool-calling accuracy** via trajectory distillation. Perea's production pipeline (2026-05) reports 30-40% cost reduction with shadow-mode-sourced student models. Microsoft Ignite BRK188 (2025) showed 80-90% cost reduction on specific agent tasks via Agentic RFT. The pattern is confirmed across multiple independent sources.

## See also

- [S-006 · Model Routing](stacks/s06-model-routing.md) — when to route to the right model tier
- [S-005 · Multi-Agent Patterns](stacks/s05-multi-agent-patterns.md) — teacher-worker topology
- [S-103 · Cost-Aware Context Management](stacks/s103-cost-aware-context-management.md) — cost as a first-class design constraint
- [S-457 · Stratified Agent Stack Economics](stacks/s457-stratified-agent-stack-economics.md) — tiered model selection
