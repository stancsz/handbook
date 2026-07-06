# S-653 · LLM-as-Judge Failure Modes

[You're using an LLM to grade another LLM's outputs — and it has four systematic biases that silently corrupt your evaluation signal. You won't notice until your "best" model turns out to be merely the longest one.]

## Forces

- **LLM-as-judge is 50–1000x cheaper than human review**, so every team uses it. Almost none audit it. The cost saving creates a hidden reliability debt.
- **The judge is a model.** It inherits the same biases — position, verbosity, self-preference, self-enhancement — that make LLM outputs unreliable in the first place.
- **Bias compounds invisibly.** If your judge favors A over B because A appears first, you route more traffic to A, generate more A-style outputs for training, and entrench the bias in your data flywheel.
- **Naive calibration is insufficient.** Calibrating judge scores against human labels once and forgetting is not calibration — judge behavior drifts with model version, rubric changes, and distributional shift in evaluated outputs.
- **Most teams discover the problem backwards.** They notice their agent's quality scores went up, shipping more features, only to find real user satisfaction dropped. By then, the evaluation signal is already poisoned.

## The Move

LLM-as-judge failure modes fall into four categories. Each is detectable and mitigable — but only if you instrument for it.

### 1. Position Bias

The judge systematically prefers responses in a particular ordinal position. Cause: recency bias (models weight recent tokens more heavily) and primacy bias (first items anchor judgment). Particularly pronounced in pairwise comparison where the judge sees two options side-by-side.

**Detection:** Run the same pairwise comparison twice with order alternated (A vs B and B vs A). Compute *swap consistency rate* — what fraction of the time does the judge flip its verdict? Below 80% swap consistency signals position bias.

**Mitigation:** Always run both orderings. Average the two scores. Flag (not discard) cases where scores disagree by more than 1 point — these are high-variance candidates for human review.

```python
def judge_pairwise_with_order_control(judge_llm, option_a, option_b, rubric, num_orderings=2):
    """
    Pairwise comparison with order alternation.
    Swap consistency rate below 80% signals position bias.
    """
    verdicts = []
    for ordering in range(num_orderings):
        if ordering % 2 == 0:
            first, second = option_a, option_b
        else:
            first, second = option_b, option_a

        prompt = f"""Evaluate these two responses against the rubric.
Score each independently, then state your preference.

Rubric: {rubric}

Response A: {first}
Response B: {second}

Output: {{"a_score": <0-10>, "b_score": <0-10>, "winner": "<A or B>", "confidence": "<high/medium/low>"}}
"""
        verdict = judge_llm.generate(prompt)
        if ordering % 2 == 1:
            verdict = swap_winner_label(verdict)  # Flip A↔B to align ordering
        verdicts.append(verdict)

    # Average scores and check disagreement
    avg_a = mean(v["a_score"] for v in verdicts)
    avg_b = mean(v["b_score"] for v in verdicts)
    disagreement = abs(verdicts[0]["winner_score"] - verdicts[1]["winner_score"])

    return {
        "option_a_score": avg_a,
        "option_b_score": avg_b,
        "high_variance": disagreement > 1.0,
        "verdicts": verdicts,
    }
```

### 2. Verbosity Bias

The judge prefers longer responses, conflating length with quality. Particularly insidious: it means your agent gets rewarded for padding rather than precision.

**Detection:** Score a deliberately concise response against a bloated-but-equivalent one. A judge with verbosity bias scores the verbose version higher. Run this probe monthly or after any judge model update.

**Mitigation:** Include an explicit length-penalty clause in the rubric: *"Penalize verbosity. A shorter, clearer answer scores higher than a longer one covering the same ground."* Normalize scores by token count: `length_normalized_score = raw_score / log(token_count + 1)`. Track length-controlled win rate over time.

```python
def length_normalize(verdict: dict, response_tokens: int) -> float:
    """
    Length-normalized score: penalizes verbosity bias.
    Using log(token_count) so longer responses still contribute,
    but diminishing returns create a ceiling.
    """
    return verdict["raw_score"] / math.log(response_tokens + 1)

# Production probe: detect verbosity bias
def probe_verbosity_bias(judge_llm, concise_response, bloated_response, rubric):
    concise_norm = length_normalize(
        judge_llm.score(concise_response, rubric), len(concise_response.split())
    )
    bloated_norm = length_normalize(
        judge_llm.score(bloated_response, rubric), len(bloated_response.split())
    )
    # If bloated scores higher even after normalization, verbosity bias is severe
    return {"bloated_wins": bloated_norm > concise_norm,
            "gap": bloated_norm - concise_norm}
```

### 3. Self-Preference Bias

The judge favors outputs from its own model family. A GPT-class judge prefers GPT-class outputs. This is the most dangerous bias because it makes every self-evaluation look great.

**Detection:** Use a judge from a *different* provider family than the model under test. If you must use the same family (e.g., evaluating a Claude-tuned model with Claude as judge), add a mandatory disclosure in the prompt: *"You are evaluating outputs from a model in your own family. Be especially critical of self-similarity bias."*

**Mitigation:** Cross-family judging is the production standard. Pair GPT-4o-mini as judge with Claude-evaluated outputs, or vice versa. Track win rates by judge-model pair — if a given judge consistently favors its own family, retire that pairing.

### 4. Self-Enhancement Bias

When the judge evaluates its *own* outputs, it scores them higher — not through deception but through unconscious confirmation of its own reasoning. Distinct from self-preference: self-preference is about model family; self-enhancement is about the specific output the judge just generated.

**Detection:** This is the hardest bias to catch programmatically. Production signal: if a model is consistently scoring its own outputs higher than a cross-family judge scores them, self-enhancement is in play.

**Mitigation:** Prohibit self-judging in your eval pipeline. Every production eval must use a judge that did not generate the output under evaluation. Enforce this structurally in your eval harness:

```python
def eval_pipeline(outputs: list[AgentOutput], judge_llm):
    for output in outputs:
        # Never judge yourself
        if judge_llm.identifies_as(output.source_model):
            raise ValueError(
                f"Self-judging detected: {judge_llm.model_id} cannot judge "
                f"outputs from {output.source_model}"
            )
        score = judge_llm.evaluate(output, rubric=output.rubric)
        output.record_eval(score)
```

### Calibration Workflow

Run calibration on a golden dataset quarterly or after any judge model change:

1. **Collect golden dataset**: 50–200 human-scored examples covering your key dimensions (accuracy, helpfulness, safety, coherence).
2. **Compute Cohen's κ** between judge and human labels. Target: κ > 0.6 (acceptable), κ > 0.8 (strong).
3. **Diagnose failure modes**: If κ is low, run the four-bias probes above to identify which bias dominates.
4. **Adjust rubric**: Rewrite ambiguous criteria. Add explicit prohibitions ("do NOT penalize brevity", "length is not a quality signal").
5. **Re-score golden dataset**: Repeat until κ meets threshold.
6. **Set automated monitoring**: Alert when swap consistency drops below 75% or when verbosity bias probe exceeds threshold.

### Production Deployment Pattern

```
CI/CD pipeline:
  └─ 100% of unit-test evals run through judge
  └─ Human review on flagged failures (high-variance verdicts)

Live production:
  └─ Sample 1–10% of sessions through judge
  └─ Rollup quality metrics per agent version
  └─ Alert on >2σ deviation from baseline
```

This tiered approach keeps eval cost manageable while catching drift early. The CI layer provides deterministic regression coverage; the sampling layer catches emergent behavioral issues invisible to unit tests.

## Receipt

> Receipt pending — 2026-07-05. Core mitigation patterns (order control, length normalization, cross-family judging, self-judging prohibition) are structurally sound. Calibration workflow derived from FutureAGI and Zylos Research production patterns. Bias detection code is illustrative — swap consistency probe and verbosity bias probe should be run against your specific judge-rubric pair before treating thresholds as production-ready. Cohen's κ calibration requires a golden dataset sized to your eval dimensions (minimum 50 examples, 200 recommended).

## See also

[S-644 · The Three-Layer Agent Eval Model](s644-the-three-layer-agent-eval-model.md) — organizes agent eval into final-answer, trajectory, and per-turn layers; judge quality is foundational to all three.
[S-385 · Agent Trajectory Evaluation: Process vs. Outcome Scoring](s385-agent-trajectory-evaluation.md) — trajectory-level eval is especially susceptible to judge bias since the judge must reason over long sequences.
[S-212 · Semantic Output Validation Gate](s212-semantic-output-validation-gate.md) — complementary: judge bias is about grading quality; output validation is about enforcing structural correctness.
[S-221 · Agentic RAG Production Loop](s221-agentic-rag-production-loop.md) — retrieval quality feeds eval quality; a biased judge evaluating a biased retrieval system creates a double-blind spot.
