# S-215 · Model Merging for Agent Specialization

You fine-tuned a model for your code-review agent. A colleague fine-tuned the same base for your customer-support agent. A third team fine-tuned it for internal search. Now you want one model that does all three — but retraining from scratch costs GPU weeks. Model merging combines the weights of multiple fine-tuned models into a single artifact in minutes, with no training data and no GPU hours. The merged model routinely outperforms every source model on benchmarks none of them were explicitly trained on.

## Forces

- Fine-tuning creates specialists; you need generalists — merging creates multi-task models from specialists without retraining
- Ensembling (running N models and voting) costs N× inference — merging is 1× after the merge step
- Naive weight averaging cancels out conflicting deltas, producing a model worse than any source
- Architecture identity is a hard constraint: same base model, same layer count, same attention heads — no exceptions
- The merge step is free but evaluation is not: a merge without a benchmark suite is a blind bet
- Model soups, DARE, and TIES solve the delta-conflict problem in different ways with different tradeoffs

## The move

**The core insight:** Fine-tuning from the same base produces weights that differ primarily by a task-specific *delta* (θ_ft = θ_base + δ). Merging is about combining those deltas intelligently, not naively averaging the full weights.

**The five methods, simplest to most sophisticated:**

| Method | What it does | Best for |
|---|---|---|
| **Model Soup** | Linear interpolation between checkpoint averages | Same-task, same-hyperparam variants |
| **Naive Average** | `(θ₁ + θ₂ + …) / N` | Never use alone — destroys performance |
| **SLERP** | Spherical linear interpolation | Preserving capability diversity |
| **TIES** | Trim → Elect sign → Merge | Disagreement resolution across tasks |
| **DARE** | Drop and rescale deltas | Sparse merges, retaining rare capabilities |

**Step 1 — Verify architecture match.** All models must share the same base architecture, quantisation level, and vocabulary. Merging a bf16 model with a int4 model produces garbage.

**Step 2 — Choose the merge method.** DARE and TIES handle task conflict best. SLERP preserves rare capabilities. Model Soup is the simplest valid approach.

**Step 3 — Use mergekit.** The industry-standard tool handles YAML config, weight alignment, and output sharding.

```yaml
# mergekit.yml — DARE/TIES merge of three specialist adapters
# All must share the same base model architecture
merge_method: dare_ties
base_model: mistralai/Mistral-7B-v0.1

models:
  - model: ./specialist-code
    parameters:
      density: 0.5
      weight: 0.4
  - model: ./specialist-reasoning
    parameters:
      density: 0.5
      weight: 0.35
  - model: ./specialist-chat
    parameters:
      density: 0.5
      weight: 0.25

parameters:
  int8_mask: true
dtype: bfloat16
```

```bash
# Run the merge (CPU-only, no GPU needed)
mergekit-yaml mergekit.yml ./merged-model \
  --copy-tokenizer \
  --out-shard-size 1B \
  --lazy-unpickle

# Verify the merged model
lm_eval --model hf \
  --model_args pretrained=./merged-model \
  --tasks mmlu,truthfulqa,humaneval
```

**Step 4 — Evaluate before using.** Run the same benchmark suite on all source models and the merge. The merged model should match or exceed the best source on at least 80% of tasks. If it underperforms on a critical task, adjust weights or drop that model from the merge.

**Step 5 — For MoE conversion, use mergekit-moe.** Transform a dense model into a mixture-of-experts model by injecting expert parameters from specialized models while keeping shared MLP layers from the base.

**Key pitfalls:**
- Merging models fine-tuned from *different* base models (e.g., Llama 2 + Mistral) produces incoherent outputs
- High density (1.0) in DARE merges too many parameters and reintroduces delta conflict
- Model soups require the same fine-tuning recipe — inconsistent hyperparameters reduce quality
- Always keep the source models — merges are not invertible

## Receipt

> Receipt pending — 2026-06-30

## See also

- [S-06 · Model Routing](stacks/s06-model-routing.md) — selecting which model to use at query time (complementary: merging happens offline, routing happens online)
- [S-194 · Synthetic Data Generation for Fine-Tuning](stacks/s194-synthetic-data-fine-tuning-pipeline.md) — generating the training data that precedes a merge
- [R-03 · Fine-tuning vs Prompting](frontier/r03-fine-tuning-vs-prompting.md) — when to fine-tune vs. when to stay at inference time
