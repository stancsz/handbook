# S-331 · LLM-as-a-Judge Evaluation

When you can't programmatically verify an agent's output — which is most of the time — you ask another LLM to judge it. LLM-as-a-judge is the dominant approach to evaluating open-ended, multi-step, or subjective agent behaviors. It is also the most fragile. The same model that generates outputs generates verdicts, and bias compounds.

## Forces
- **Most agent outputs aren't checkable by code.** "Did the agent give a helpful response?" "Did it follow the escalation policy?" "Was the explanation accurate?" — these have no ground-truth answer. An LLM judge is the only scalable scorer.
- **The judge and the agent share the same model.** A model's failure modes (confabulation, leniency, recency bias) corrupt both generation and evaluation simultaneously. A bad judge gives false confidence.
- **Judge prompts are load-bearing and rarely tested.** A judge prompt designed for one task type often silently fails on another. Teams copy-paste prompts without calibration and ship false signal.
- **Unstructured verdicts are unprocessable.** "The response was good" is useless for trending, alerting, or regression detection. Structured output with scores and reasons is required for engineering use.
- **Reference-free judges are weaker than reference-guided ones.** Without a ground-truth answer to compare against, the judge defaults to preference, not correctness.

## The move

Three-layer evaluation architecture: deterministic checks first, then reference-guided scoring, then reference-free holistic judgment. The judge model should differ from the agent model.

### Layer 1 — Deterministic checks (always run first)

```python
def layer1_deterministic(result: AgentResult) -> Optional[EvalVerdict]:
    checks = [
        (result.tool_calls, "escalate_tool" in [t["name"] for t in result.tool_calls],
         "Must call escalate_tool on high-priority ticket"),
        (result.output, all(
            ref["id"] in result.citations
            for ref in result.required_citations
        ), "All required sources must be cited"),
        (result.latency_ms, result.latency_ms < 5000, "Response under 5s"),
        (result.tool_errors, result.tool_errors == 0, "Zero tool errors"),
    ]
    verdicts = []
    for val, passed, msg in checks:
        verdicts.append(Verdict(
            check=msg, passed=passed, score=1.0 if passed else 0.0,
            reason="automated check" if passed else f"FAIL: {msg}"
        ))
    if not all(v.passed for v in verdicts):
        return EvalVerdict(verdicts=verdicts, final_score=0.0, judge_type="deterministic")
    return None  # proceed to layer 2
```

### Layer 2 — Reference-guided scoring (when golden answers exist)

```python
REF_JUDGE_PROMPT = """You are evaluating an agent's response against a reference answer.

TASK: {task_description}
REFERENCE ANSWER: {reference}
AGENT RESPONSE: {response}

Score on a scale of 0.0 to 1.0:
- 1.0: Response covers all key points in the reference, no hallucination
- 0.5: Covers most key points, minor omission or slight inaccuracy
- 0.0: Major omission, factual error, or contradicts reference

Provide your score and a one-sentence reason.
Return ONLY valid JSON: {{"score": float, "reason": string}}"""

def layer2_reference_guided(
    agent_response: str,
    reference: str,
    task: str,
    judge_model: str = "claude-sonnet-4-20250514",
) -> EvalVerdict:
    verdict = structured_output(
        model=judge_model,
        prompt=REF_JUDGE_PROMPT.format(
            task_description=task,
            reference=reference,
            response=agent_response,
        ),
        schema=VerdictSchema,
        provider="anthropic",
    )
    return EvalVerdict(verdicts=[verdict], final_score=verdict.score, judge_type="reference-guided")
```

### Layer 3 — Reference-free holistic judgment (judge-of-judge calibrated)

```python
JUDGE_OF_JUDGE_PROMPT = """You are a quality auditor on a team of LLM judges.
A subordinate judge (model: {agent_model}) scored this response {agent_score}/1.0.
Your job: decide if that score is fair.

AGENT OUTPUT: {response}
CONTEXT: {task_context}

Rate the subordinate judge:
- {agent_score}: Is this score too high, too low, or about right?
- What did the subordinate judge miss?
- Your corrected score: ___

Return ONLY valid JSON: {{"audit_score": float, "audit_reason": string, "judge_accurate": bool}}"""

def layer3_reference_free(agent_response: str, task: str, agent_model: str, agent_score: float) -> EvalVerdict:
    # Use a larger/different model as the auditor
    audit = structured_output(
        model="claude-opus-4-20250514",  # larger model as auditor
        prompt=JUDGE_OF_JUDGE_PROMPT.format(
            agent_model=agent_model,
            agent_score=agent_score,
            response=agent_response,
            task_context=task,
        ),
        schema=AuditSchema,
        provider="anthropic",
    )
    return EvalVerdict(
        verdicts=[Verdict(check="audit", passed=audit.judge_accurate,
                          score=audit.audit_score, reason=audit.audit_reason)],
        final_score=audit.audit_score,
        judge_type="reference-free-audited",
    )
```

### Key calibration rules

1. **Judge model ≠ agent model.** Using the same model as judge and agent amplifies shared biases. Use a larger or different model family for judging.
2. **Structured output mandatory.** Unstructured judge responses can't be aggregated, alerted on, or compared across runs. Always use `response_format` with a schema.
3. **Position bias.** Judges prefer responses in the first or last position when comparing two outputs. Counter this by randomizing order and running each comparison twice with reversed positions.
4. **Leniency inflation.** LLMs tend to give high scores. Calibrate against a known set of 20 samples with human-agreed scores before trusting the judge.
5. **Track judge accuracy over time.** Run periodic judge-of-judge audits. When the auditor's corrections exceed ±0.15 on 20% of samples, re-calibrate or retrain the judge prompt.
6. **N-way over binary.** Score on 0.0–1.0 continuous scale rather than pass/fail. Binary scoring hides regression: an agent that degrades from 0.95 → 0.80 looks like a pass on both runs.

## Receipt

> Receipt pending — July 1, 2026
> The code above reflects the production architecture used by teams at Confident AI, Langfuse, and OpenAI's internal evals pipeline (referenced in public case studies and Langfuse's Pydantic AI evaluation cookbook, 2025–2026). Key patterns verified: structured output as mandatory for judge pipelines, multi-layer eval stack, judge-of-judge calibration loop. Not yet run end-to-end in this exact form.

## See also

- [F-191 · AI Agent Evaluation Harness](f191-ai-agent-evaluation-harness.md) — the broader harness context this sits inside
- [F-189 · Private Eval Dataset Construction](f189-private-eval-dataset-construction.md) — the ground-truth data layer that powers Layer 2 reference-guided scoring
- [R-13 · Agent Trajectory Synthesis](r13-agent-trajectory-synthesis.md) — where the agent behaviors being judged actually come from
