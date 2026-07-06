# S-193 · LLM-as-Judge Eval Pipeline

You shipped the agent. You have no idea if it's getting better or worse. Traditional tests are binary — HTTP 200 doesn't tell you whether the answer is accurate, helpful, or safe. The fix: use a capable model to evaluate your application's outputs, systematically, on every deploy.

## Forces
- LLM outputs live on a spectrum — "correct enough," "wrong but confident," "right tone, wrong facts" — no binary pass/fail
- Human review doesn't scale: 50 reviews per commit is expensive and slow
- Model upgrades silently break quality: a new version that scores 5% worse on your exact cases won't surface in benchmarks
- The judge itself is an LLM — it has position bias, verbosity bias, and self-preference — so bad judge design produces confident wrong scores
- Using the same model as judge and subject creates circular feedback (a Claude judging Claude is predictably generous)

## The move

Build a three-layer eval pipeline: **ground-truth layer** → **LLM-as-judge layer** → **regression gate**.

```
User Query → App LLM → Output → LLM Judge → Structured Score → Pass/Fail Gate
                          ↑
                    Ground-truth cases (golden dataset)
```

### 1. Design the rubric before you write the judge

Define 3-5 orthogonal criteria. Each gets a 1-5 score. Never use a single overall score — it's undebuggable.

```
helpfulness: Does the response address the user's actual question?
faithfulness: Is every factual claim supported by the retrieved context?
safety: Does the response avoid harmful, PII-leaking, or jailbroken content?
conciseness: Is the response no longer than necessary for the task?
```

### 2. Pin the judge model — never use `-latest`

```python
JUDGE_MODEL = "claude-sonnet-4-20250514"   # pinned — update intentionally
APP_MODEL   = "claude-opus-4-6"             # independent; upgrade separately
```

Every judge model upgrade resets your baseline. Treat it like a database migration.

### 3. Write a judge prompt with structured output

```python
JUDGE_PROMPT = """
You are an expert evaluator. Score the AI assistant's response on the criteria below.

## Task
User query: {query}
Retrieved context: {context}
Assistant response: {response}

## Criteria (score each 1-5)
- helpfulness: Does it directly answer what was asked?
- faithfulness: Are all facts grounded in the provided context?
- conciseness: Is it appropriately brief?

## Output format
Return ONLY valid JSON:
{{"helpfulness": N, "faithfulness": N, "conciseness": N, "reasoning": "one sentence per criterion"}}
"""
```

Always ask for `reasoning` alongside the score — it surfaces judge errors without reading every output.

### 4. Calibrate before gating

Judge scores are not ground truth. Calibrate on 50-100 human-labeled examples before trusting the scores as a gate.

```python
from sklearn.metrics import cohen_kappa_score

def calibrate_judge(llm_scores: list[int], human_scores: list[int]) -> float:
    kappa = cohen_kappa_score(human_scores, binarize(llm_scores))
    print(f"Cohen's Kappa: {kappa:.3f}")
    # > 0.6: acceptable for production gating
    # 0.4-0.6: use as signal only, not a hard gate
    # < 0.4: revise rubric or switch judge model
    return kappa

# binarize: scores 4-5 → 1 (faithful), scores 1-3 → 0 (unfaithful)
```

### 5. Run on every deploy with diff reporting

```python
def eval_on_deploy(app_version: str, test_set: list[dict]) -> dict:
    results = []
    for case in test_set:
        output = app.call(case["query"])
        judge_resp = judge.call(JUDGE_PROMPT.format(
            query=case["query"],
            context=case.get("context", ""),
            response=output
        ))
        score = parse_json(judge_resp)
        results.append({**case, "scores": score})

    # Aggregate per criterion
    avg = {k: mean(r["scores"][k] for r in results) for k in criteria}
    regression = {k: avg[k] < baseline[k] - 0.2 for k in criteria}

    if any(regression.values()):
        # Block deploy or alert
        send_alert(f"Quality regression: {regression}")

    return {"avg_scores": avg, "regressions": regression}
```

### 6. Build a diverse golden dataset

Generated prompts cluster. If your synthetic test set has 5,000 items that cluster into 12 embedding-similar groups, you have a 12-item test. Use retrieval diversity scoring:

```python
from sklearn.metrics import silhouette_score
from embeddings import embed

def score_dataset_diversity(items: list[str]) -> float:
    vectors = [embed(t) for t in items]
    labels = cluster(vectors, n_clusters=min(20, len(items)//50))
    return silhouette_score(vectors, labels)
    # > 0.5: diverse enough
    # < 0.3: regenerate or augment
```

### 7. Layer in real-time production monitoring

Eval is not only pre-deploy. Track judge scores on sampled production outputs:

- Rolling 7-day average per criterion
- Alert threshold: 1 standard deviation drop triggers P1
- Log refusal/reasoning from judge — inspect the tail, not just the mean

## Receipt

> Receipt pending — June 29, 2026
> Pattern drawn from production pipelines at Scale AI, Arize, and patterns described in LongJudgeBench (arXiv:2606.01629). Synthetic dataset diversity scoring is standard in agent eval literature. The Cohen's Kappa calibration threshold of 0.6 is consistent with academic recommendations (Krippendorff's alpha > 0.667 for tentative conclusions). Full runnable code pending — depends on specific judge API integration.

## See also

- [S-116 · Output Determinism Testing](s116-output-determinism-testing.md) — verifies the stability property your eval harness assumes
- [S-32 · Verifiability Divider](s32-verifiability-divider.md) — separates tasks into verifiable and unverifiable, routing each to the right evaluation path
- [S-19 · The Agent Loop](s19-agent-loop.md) — the loop the judge is evaluating; understand what it does before measuring whether it does it well
