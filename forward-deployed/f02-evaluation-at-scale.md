# F-02 · Evaluation at Scale

When you have thousands of AI outputs per day, you can't read them all. Here's how to know if your system is working.

## Forces
- Manual review doesn't scale beyond ~100 examples per human per day
- Automated metrics (BLEU, ROUGE) don't capture what users care about
- LLM-as-judge is powerful but has its own biases
- Evals are only as good as the examples you put in them

## The move

**Three layers of eval:**

### Layer 1: Unit tests (fast, cheap, deterministic)
For outputs that must always be true: format compliance, forbidden content, required fields.
```python
def test_output_is_valid_json(output: str):
    import json
    parsed = json.loads(output)  # raises on invalid JSON
    assert "name" in parsed
    assert isinstance(parsed.get("age"), int)
```

### Layer 2: LLM-as-judge (flexible, scales, needs calibration)
Use a capable model to score outputs against criteria.
```python
JUDGE_PROMPT = """
Score this response on a scale of 1–5 for:
- Accuracy (does it answer the question correctly?)
- Conciseness (is it appropriately short?)
- Tone (is it professional?)

Response to score:
{response}

Return JSON: {{"accuracy": int, "conciseness": int, "tone": int, "reason": str}}
"""
```
Calibrate the judge: score 50 examples manually, compare judge scores to yours. If correlation < 0.7, fix the judge prompt before trusting it at scale.

### Layer 3: User signal (ground truth, lagging)
Thumbs up/down, correction rate, re-prompt rate, task completion rate. This is the real signal. Lag = days to weeks.

**Minimum viable eval pipeline:**
1. Log every input/output pair
2. Sample 1% for daily manual review
3. Run unit tests on 100% of outputs
4. Run LLM judge on 10% of outputs daily
5. Alert when any metric drops more than 5% week-over-week

## Receipt
> Receipt pending — 2026-06-25. Eval patterns are well-established in the field. LLM-as-judge calibration guidance sourced from RAGAS documentation and public ML papers.

## See also
[F-01](f01-shipping-ai.md) · [F-03](f03-failure-modes.md) · [F-12](f12-llm-as-a-judge.md) · [W-04](../workspace/w04-observability.md)

## Go deeper
Keywords: `LLM eval` · `RAGAS` · `PromptFoo` · `DeepEval` · `Evals` · `LLM-as-judge` · `Braintrust` · `eval regression`
