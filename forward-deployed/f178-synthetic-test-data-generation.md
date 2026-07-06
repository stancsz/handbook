# F-178 · Synthetic Test Data Generation

Your agent scores 94% on MMLU and 89% on HumanEval. It still fails on 30% of real customer tickets. The benchmarks lied — they leaked into pre-training. You need your own eval, but you have 200 real examples and need 5,000. You generate 5,000 more with an LLM and they all look suspiciously like the 200 you fed in. The model learned to echo your seed data, not generalize beyond it.

Synthetic test data generation is the discipline of building evaluation corpora that don't exist yet — with enough diversity, difficulty, and ground truth to actually stress-test your agent.

## Forces

- **Benchmark contamination is systemic.** MMLU, GSM8K, HumanEval, HellaSwag — all found in pre-training scrapes. Reported scores reflect memorization, not reasoning. A model that scores 95% on a contaminated benchmark may be 60% on a clean one.
- **Model release cadence outpaces hand-labeling.** Frontier models ship every 6–12 weeks. Hand-crafted evals take months. By the time your eval is ready, the model has moved on.
- **Agent complexity defeats static evals.** Multi-turn personas, branching tool calls, looping behavior, and adversarial user inputs create failure modes that a static question-answer dataset cannot simulate.
- **Real production data is scarce, slow, or legally blocked.** Privacy regulations, competitive sensitivity, and low incident rates mean most teams cannot label their way to coverage.
- **Naive LLM generation collapses into mode collapse.** Ask GPT-4 to generate 1,000 customer complaint examples and you get 1,000 variations of the same five templates. You need structured diversity, not volume.

## The move

The synthetic data pipeline has four stages. Skip one and the corpus degrades.

### Stage 1 — Seed with real data or structured constraints

Start from actual production traces, hand-labeled examples, or domain schemas. If you have zero real data, use a well-scoped domain specification as a constraint envelope. Without seeds or constraints, the LLM generates from its own training distribution — which is exactly the contaminated benchmark distribution you are trying to escape.

```python
# Seed with real traces, not prompts alone
SEED_EXAMPLES = [
    {
        "user_input": "Show me all invoices over $10k from Acme Corp",
        "expected_tools": ["db.query", "filter.amount_gt", "format.table"],
        "constraints": ["never_expose_raw_sql", "amounts_in_usd"],
    },
    # ... 20-50 real examples minimum for diversity signal
]
```

Minimum viable seed: 20–50 examples with real variety. Quality of seed determines ceiling of synthetic output.

### Stage 2 — Evolve for diversity and difficulty

Use multi-agent persona evolution or instruction-backtranslation to generate hard variants. The key techniques:

**Persona evolution** — assign different user archetypes (impatient executive, technically-savvy researcher, non-native speaker) and generate contextually different inputs for the same core intent.

**Constraint injection** — take a passing example and add a constraint violation, edge case, or adversarial twist. "All invoices" → "All invoices from Q3 excluding voided ones."

**Backtranslation** — generate a correct answer first, then derive the question that would produce it. This gives you clean ground truth paired with realistic prompts that weren't reverse-engineered.

```python
import anthropic

client = anthropic.Anthropic()

def evolve_example(seed: dict, constraint: str) -> dict:
    """Inject a constraint twist into a passing example."""
    prompt = f"""
Given this example:
- Input: {seed['user_input']}
- Expected tools: {seed['expected_tools']}
- Constraints: {seed['constraints']}

Generate a HARDER variant that additionally requires: {constraint}

Return JSON with fields: user_input, expected_tools, new_constraints.
"""
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        message=prompt,
    )
    import json
    return json.loads(response.content[0].text)
```

### Stage 3 — Filter for quality and contamination

Generate 3–5x your target count, then filter. Filters catch:

- **Semantic duplicates** — use embedding similarity (cosine > 0.92) to deduplicate
- **Low-quality outputs** — score each synthetic example with a judge LLM against a rubric (coverage, specificity, plausibility)
- **Ground truth violations** — run the expected tool sequence against a sandbox and confirm the output matches the claimed ground truth
- **Contamination flags** — check against a known-benchmark corpus with fuzzy matching (n-gram Jaccard > 0.3 against any benchmark entry)

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def dedup_synthetic(corpus: list[str], threshold: float = 0.92) -> list[str]:
    """Remove semantically duplicate synthetic examples."""
    vec = TfidfVectorizer().fit_transform(corpus)
    sim = cosine_similarity(vec)
    keep = []
    seen = set()
    for i in range(len(corpus)):
        if all(sim[i][j] < threshold for j in seen):
            keep.append(corpus[i])
            seen.add(i)
    return keep
```

### Stage 4 — Calibrate with human spot-checks

Even a perfect pipeline needs human calibration. Spot-check 5% of the synthetic corpus across difficulty tiers (easy/medium/hard). Track agreement between your ground truth labels and what the agent actually produces. Feed disagreement back into Stage 2 as constraint hints.

Target ratio: **1 human label per 20 synthetic examples** for calibration, not full annotation.

### The full pipeline in CI

```yaml
# .github/workflows/eval-data.yml
- name: Generate synthetic eval corpus
  run: |
    python scripts/synth_gen.py \
      --seed-dir data/seeds/ \
      --output data/eval_corpus.jsonl \
      --target-count 5000 \
      --diversity-threshold 0.92 \
      --filter-contamination

- name: Calibrate with human sample
  run: python scripts/calibrate.py --sample-rate 0.05 --corpus data/eval_corpus.jsonl

- name: Run agent against synthetic corpus
  run: python -m pytest tests/test_agent_on_synthetic.py --eval-corpus=data/eval_corpus.jsonl
```

## Receipt

> Receipt pending — June 30, 2026
> Verified: pipeline stages mapped against real production patterns. Code examples tested for structure. Full end-to-end run with real seed data and API calls not yet executed in this session.

## See also

- [F-12 · LLM-as-a-Judge](f12-llm-as-a-judge.md) — synthetic data amplifies judge quality; the judge quality constrains synthetic data quality
- [F-07 · Evaluation-Driven Development](f07-evaluation-driven-development.md) — synthetic data is the input; EDD is the gate that consumes it
- [F-177 · Deterministic Agent Verification](f177-deterministic-agent-verification.md) — combine synthetic trajectories with deterministic output gates for rigorous agent verification
