# S-335 · Preference Data Pipeline Engineering

You need to train an agent that prefers correct tool sequences over wrong ones, efficient plans over wasteful ones, helpful responses over harmful ones. The model has the weights — you have the data. The problem: a preference data pipeline that actually produces training-ready signal is orders of magnitude more complex than "ask humans to pick A or B." Collection UI, inter-rater noise, distribution skew, annotation quality, adversarial pair construction, and batch-to-training integration form a system that most teams underestimate until their DPO run produces a worse model than they started with.

## Forces

- **Preference data quality dwarfs quantity.** LIMA showed 1,000 curated samples matched 52,000 from Alpaca. InstructGPT found 13,000 SFT pairs + 33,000 preference annotations outperformed raw scale. The signal-to-noise ratio in your pairs is the primary determinant of training outcome — not how many you collected.
- **Human raters are inconsistent, biased, and expensive.** A 2025 Toloka study found inter-annotator agreement on agent quality judgments drops below 60% for complex multi-step tasks. Ambiguous pairs — where both responses seem acceptable — generate noise that DPO amplifies rather than filters.
- **The DPO loss function is sensitive to preference margin.** DPO's gradient is proportional to the quality difference between chosen and rejected responses. Pairs where both seem equally good produce near-zero gradient. Pairs where the rejected response is only slightly worse than the chosen one produce the strongest learning signal. This means the annotation interface must surface *adversarial* pairs — responses that look plausible but contain subtle errors.
- **Preference distribution shapes model behavior.** Over-representing certain task types in your pairs causes the model to over-align in those areas and under-align elsewhere. A dataset that's 70% coding tasks will produce an agent that's surprisingly mediocre at math, even if you trained it to prefer good responses everywhere.
- **Online/incremental preference collection is hard.** Static dataset DPO converges to a ceiling — production edge cases that emerge post-deployment can't be addressed without expanding the dataset and retraining. Iterative DPO variants (IPO, CPO) exist but introduce training instability risks.
- **Synthetic preference generation is promising but dangerous.** Using an LLM to label or generate preference pairs at scale is cheap, but it inherits the teacher's biases and can collapse to the generator's distribution. It works as a *filter* on human data, not a replacement.

## The move

### 1. Design the annotation interface around decision difficulty

Don't present annotators with a binary choice on a single response. Present a **side-by-side comparison** with a structured rubric:

```
Task: [prompt]
Response A: [full text + tool calls + trajectory]
Response B: [full text + tool calls + trajectory]

For each axis, rate A vs B:
- Correctness:  A >> B  /  A > B  /  A ≈ B  /  B > A  /  B >> A
- Efficiency:   A >> B  /  A > B  /  A ≈ B  /  B > A  /  B >> A
- Safety:       A >> B  /  A > B  /  A ≈ B  /  B > A  /  B >> A

Which would you prefer to deploy?  [A / B / Neither]
```

Multi-axis ratings let you construct pairs by filtering on specific quality dimensions. The "Neither" option prevents forced choices on genuinely bad pairs.

### 2. Sample pairs adversarially, not uniformly

Random pair sampling produces mostly easy decisions — one response is obviously better. These contribute near-zero gradient. Instead:

```python
# Step 1: Score all responses with an LLM judge
judge_scores = judge_model.batch_score(responses, rubric=["correctness", "efficiency"])
# Step 2: Select pairs where scores are close (adversarial pairs)
# score_gap < threshold = hard pair = strong learning signal
pairs = []
for task_id, responses in dataset.items():
    scored = sorted(zip(judge_scores[task_id], responses), key=lambda x: -x[0])
    for i in range(len(scored)):
        for j in range(i+1, min(i+4, len(scored))):
            gap = scored[i][0] - scored[j][0]
            if 0 < gap < ADVERSARIAL_THRESHOLD:  # hard but real preference
                pairs.append((task_id, scored[i][1], scored[j][1], gap))
```

### 3. Filter with automated checks before human review

Automated rejection catches the obvious noise:

```python
def filter_pairs(pairs: list[dict]) -> list[dict]:
    filtered = []
    for p in pairs:
        # Reject if responses are identical or near-identical
        if p["chosen"] == p["rejected"] or levenshtein_ratio(p["chosen"], p["rejected"]) > 0.95:
            continue
        # Reject if length ratio > 5x (one is clearly truncated/corrupted)
        if len(p["chosen"]) / max(len(p["rejected"]), 1) > 5:
            continue
        # Reject if both contain safety-triggering content
        if any(safety_flag(r) for r in [p["chosen"], p["rejected"]]):
            continue
        # Reject if semantic similarity is too high (judge would flip a coin)
        if embed_similarity(p["chosen"], p["rejected"]) > 0.92:
            continue
        filtered.append(p)
    return filtered
```

### 4. Track inter-annotator agreement and prune noisy raters

```python
# Compute Fleiss' Kappa across raters for each task type
kappa_by_category = compute_fleiss_kappa(annotations, categories)
# Flag task types where annotators can't agree
unreliable_categories = [c for c, k in kappa_by_category.items() if k < 0.4]
# Re-annotate those with expert raters, or exclude from training
```

### 5. Balance the preference distribution

```python
from collections import Counter
from sklearn.preprocessing import reweight

category_counts = Counter(p["task_category"] for p in preference_data)
# Target uniform distribution across categories
weights = {cat: 1.0 / count for cat, count in category_counts.items()}
balanced_data = [
    {**p, "weight": weights[p["task_category"]]}
    for p in preference_data
]
```

### 6. Integrate with training — iterative DPO loop

```python
from trl import DPOTrainer
from transformers import AutoModelForCausalLM, AutoTokenizer

def iterative_dpo_loop(model, train_prompts, initial_data, n_iterations=3):
    for iteration in range(n_iterations):
        # Train DPO on current preference data
        trainer = DPOTrainer(
            model=model,
            ref_model=copy.deepcopy(model),  # or use cached reference
            beta=0.1,  # KL penalty strength
            label_smoothing=0.1,  # helps with noisy pairs
        )
        trainer.train()

        # Generate new candidate responses
        candidates = model.generate(train_prompts, num_return_sequences=4)

        # Re-score with LLM judge and expand preference data
        new_pairs = build_adversarial_pairs(train_prompts, candidates)
        preference_data = merge_and_dedup(preference_data, new_pairs)
        preference_data = filter_pairs(preference_data)
        preference_data = balance_distribution(preference_data)

        # Evaluate on held-out test set
        if eval_on_test_set(model) < threshold:
            break
```

## Receipt

> Receipt pending — July 2, 2026
> Code example demonstrates pipeline architecture; individual components (judge scoring, adversarial pair selection, Fleiss' Kappa) require environment instantiation. The `trl` DPOTrainer integration pattern reflects v0.12+ API. The adversarial pair selection threshold (gap < 0.2) is task-dependent and should be tuned per domain.

## See also

- [S-194 · Synthetic Data Generation for Fine-Tuning](s194-synthetic-data-fine-tuning-pipeline.md) — synthetic data as complement to human preference data; filter-before-label strategy
- [S-300 · Reward Hacking in RL-Trained Agents](s300-reward-hacking-in-rl-trained-agents.md) — what goes wrong when the preference signal is noisy or gamed
- [R-12 · Agent-RLVR Training Loop](frontier/r12-agent-rlvr-training-loop.md) — verifiable rewards for agent tasks where preference data alone isn't enough
- [R-13 · Agent Trajectory Synthesis](frontier/r13-agent-trajectory-synthesis.md) — collecting the trajectory data that preference pairs are built from
- [S-219 · Agent Eval Harness](s219-agent-eval-harness.md) — the eval harness that closes the loop on whether your preference data actually improved the agent
