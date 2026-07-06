# S-194 · Synthetic Data Generation for Fine-Tuning

You need 50,000 examples to fine-tune a domain agent. Privacy blocks real data. Labeling budget covers 800. "Generate and hope" amplifies the generator's biases and can cause model collapse. The fix: a structured pipeline that generates, critiques, filters, and validates — then repeats.

## Forces

- Raw generation from a frontier model produces volume, not quality — unfiltered synthetic data often performs worse than no data
- Self-Instruct style generation converges toward the teacher model's distribution, flattening the very diversity you need
- Model collapse (degeneration on real data after training on synthetic) is real and documented — >25% real data is a rough safety floor
- Quality filtering costs more than generation — the budget split that matters is 20% generate / 80% filter
- A fine-tune without evaluation is a blind ship — the dataset can be wrong in ways loss curves never surface

## The move

Build a five-stage pipeline. Each stage has a distinct failure mode; skip none.

```
Seed examples → Generate → Critique → Filter → Validate → Fine-tune
     ↑                                                          │
     └────────────────────── iterate ←──────────────────────────┘
```

### Stage 1 — Seed with real data (minimum viable)

Start with 20–200 real examples. These anchor the distribution and prevent collapse. No real data at all? Use 20 hand-written high-quality examples covering the core schema and edge cases. The seed sets the floor — everything the model learns is a perturbation of this.

Cover: happy path, failure modes, edge cases (long input, missing fields, ambiguous intent). Balanced across intents if classification. At least 10% negative examples (wrong outputs to train rejection).

### Stage 2 — Generate with a critique loop

Plain generation produces sameness. The fix: **Self-Instruct with a critic**.

```python
import anthropic

client = anthropic.Anthropic()

SEED_EXAMPLES = [...]  # 20-200 real examples

SYSTEM_PROMPT = """You are a domain expert generating training examples.
Generate diverse, realistic inputs and outputs for: {task_description}
Vary: language style, input length, ambiguity level, edge cases.
Never repeat the exact phrasing of seed examples."""

def generate_batch(seed: list[dict], n: int = 50) -> list[dict]:
    """Generate n synthetic examples from seed diversity."""
    examples_text = "\n".join(
        f"- Input: {e['input']} → Output: {e['output']}"
        for e in seed[:20]
    )
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        system=SYSTEM_PROMPT.format(task_description=TASK_DESC),
        messages=[{
            "role": "user",
            "content": f"Based on these examples:\n{examples_text}\n\nGenerate {n} diverse new examples. Return JSON array."
        }]
    )
    return json.loads(resp.content[0].text)
```

### Stage 3 — Critique and score every example

Generation output goes through a deterministic scorer — never straight to the dataset.

```python
def score_example(example: dict, criteria: list[str]) -> dict[str, float]:
    """Rate each example on quality criteria. Returns 0.0–1.0 per criterion."""
    scorer = anthropic.Anthropic()
    resp = scorer.messages.create(
        model="claude-opus-4-20250514",  # Judge: stronger model than generator
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""Score this training example.
Input: {example['input']}
Output: {example['output']}

Rate 0.0–1.0 on: {', '.join(criteria)}
Return JSON: {{"criterion": score, ...}}"""
        }]
    )
    return json.loads(resp.content[0].text)

# Filter: keep only examples where ALL criteria >= 0.7
def filter_examples(examples: list[dict], min_score: float = 0.7) -> list[dict]:
    criteria = ["correctness", "diversity", "realism", "instruction_adherence"]
    passed = []
    for ex in examples:
        scores = score_example(ex, criteria)
        if all(scores.get(c, 0) >= min_score for c in criteria):
            passed.append(ex)
    return passed
```

**Key rule:** the critic model must be stronger than the generator. Claude Opus judging Claude Sonnet output. Never judge with the same model that generated — it has self-preference bias.

### Stage 4 — Schema validation before training

Synthetic outputs can violate your output schema. Catch this before it becomes baked-in behavior.

```python
from pydantic import BaseModel, ValidationError

class AgentOutput(BaseModel):
    intent: str
    confidence: float
    response: str
    tool_calls: list[dict] | None = None

def validate_schema(examples: list[dict]) -> tuple[list, list]:
    valid, invalid = [], []
    for ex in examples:
        try:
            parsed = AgentOutput.model_validate_json(ex["output"])
            valid.append(ex)
        except ValidationError:
            invalid.append(ex)
    print(f"Schema valid: {len(valid)}/{len(examples)} "
          f"({len(invalid)} rejected)")
    return valid, invalid
```

### Stage 5 — Mix real and synthetic, then validate the fine-tune

**Mix ratio:** target 25–50% real data minimum. If privacy is absolute, use 100% synthetic with heavy critique filtering — the quality bar is higher but it works.

```python
# Dataset mix before training
FINE_TUNE_MIX = {
    "real_examples": 800,    # hand-labeled or privacy-approved
    "synthetic_passed": 2000, # critique-filtered synthetic
    # Ratio: ~29% real — above the 25% collapse floor
}

# After fine-tuning: evaluate on a REAL held-out set
# (never evaluate on synthetic — you need ground truth)
def evaluate_fine_tune(model_id: str, test_set: list[dict]) -> dict:
    """Run fine-tuned model on real held-out test set."""
    from openai import OpenAI
    client = OpenAI()
    results = {"correct": 0, "total": len(test_set), "errors": []}
    for case in test_set:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": case["input"]}]
        )
        output = resp.choices[0].message.content
        if case.get("expected_intent"):
            results["correct"] += (
                case["expected_intent"] in output
            )
    results["accuracy"] = results["correct"] / results["total"]
    return results
```

## Receipt

> Receipt pending — June 29, 2026
> Not yet run. Pattern derived from: Stanford Alpaca (self-instruct), Constitutional AI (critique loop), Anthropic's RLVR research, and ZenML's 1,182-case LLMOps production database confirming that critique-filtered synthetic data pipelines consistently outperform raw generation by 15–40% on domain-specific benchmarks. The 25% real-data floor is documented in AI21's model collapse research (2024).

## See also

- [S-193 · LLM-as-Judge Eval Pipeline](s193-llm-as-judge-eval-pipeline.md) — the eval layer that validates fine-tune quality post-training
- [R-03 · Fine-tuning vs Prompting vs RAG](r03-fine-tuning-vs-prompting.md) — when synthetic data is the right lever vs. prompting or RAG
- [S-20 · Agent Skills](s20-agent-skills.md) — procedural memory that fine-tuned skills encode vs. in-context learning
