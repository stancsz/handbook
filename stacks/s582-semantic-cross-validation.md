# S-582 · Semantic Cross-Validation Gate

You asked the agent to fetch the customer's current plan tier. It returned "Enterprise". The schema validated. The API returned 200. The output gate passed. The downstream agent scheduled an Enterprise-feature rollout. The customer was on a Starter plan. The rollout failed, the customer was confused, and you spent two hours untangling what happened.

The gate validated format. It didn't validate truth.

## Forces

- **Single-source validation is a hallucination enabler** — validating output against what the agent produced it with (the prompt, the tool schema, the retrieval context) catches style and structure failures, not factual ones. The agent's own reasoning is in the causal chain; checking outputs against it confirms itself
- **Different models, different error surfaces** — a frontier model's hallucination patterns differ from a smaller model's. If both reach the same conclusion independently, the signal is orders of magnitude stronger than either alone
- **Cross-verification costs tokens, but wrong-output costs everything** — the trade-off is real but asymmetric. An extra $0.002 verification call against a $4,000 incident is not a trade-off
- **Structural validation is necessary but insufficient** — JSON parse, schema match, required fields present. These catch the failures that are easy to detect. The hard failures — wrong entity, wrong date, hallucinated policy — require a different question, not a stricter check of the same question

## The move

After a high-stakes agent step completes, run the output through a **semantically independent verification pass** — a separate call, different model, or different information source — that answers: *"Is this actually true?"* rather than *"Does this match the schema?"*

Two primary patterns:

### 1. Model-vs-Model Cross-Validation

Use two models with different architectures/providers. The primary agent produces output. A verifier model — ideally from a different provider with a different training corpus — independently re-derives the answer from the same tool results or document context, then compares.

```python
def cross_validate_plan_tier(primary_output: str, tool_results: list[dict]) -> bool:
    """Verifier model independently re-extracts plan tier from raw tool results."""
    verifier_prompt = f"""
    Based ONLY on these tool results, what is the customer's plan tier?
    Tool results: {tool_results}
    Answer with a single word: Starter | Professional | Enterprise | Unknown
    """
    verifier_response = llm.call(
        model="different-provider-model",  # e.g., Claude vs Gemini vs Llama
        prompt=verifier_prompt,
        temperature=0
    )
    verified_tier = parse_plan_tier(verifier_response)
    primary_tier = parse_plan_tier(primary_output)

    if primary_tier != verified_tier:
        logger.warning(f"Cross-validation mismatch: primary={primary_tier}, verified={verified_tier}")
        return False  # gate closes — output does not propagate
    return True
```

The critical constraint: **the verifier gets the raw tool results, not the primary agent's output**. Feeding the primary output to the verifier defeats the purpose — you need independent derivation, not echo confirmation.

### 2. Source-vs-Output Cross-Validation

Query an independent authoritative source to confirm the agent's extracted facts. The agent extracted `"order #42, amount: $1,240"`. Before the finance agent processes it, confirm against the order database directly — not through the same retrieval path the agent used.

```python
def cross_validate_order(order_id: str, extracted_amount: float) -> bool:
    """Independent DB query confirms extracted facts."""
    db_record = db.query("SELECT amount FROM orders WHERE id = %s", order_id)
    if db_record is None:
        return False  # order doesn't exist — hallucination

    if abs(float(db_record["amount"]) - extracted_amount) > 0.01:
        logger.warning(f"Amount mismatch for {order_id}: extracted={extracted_amount}, db={db_record['amount']}")
        return False  # wrong value

    return True  # confirmed
```

The key distinction: this is not the same tool the agent called. The agent used a CRM tool. You confirm via the billing database. Different system, different failure modes, different error surface.

### 3. Inverted-Query Cross-Validation

Ask a second agent to find evidence that *contradicts* the output, rather than evidence that confirms it. Humans are prone to confirmation bias; adversarial verification catches what confirmatory checking misses.

```python
def adversarial_validate(summary: str, source_docs: list[str]) -> ValidationResult:
    """Second agent actively tries to falsify the summary."""
    adversarial_prompt = f"""
    The following summary was generated about a set of documents.
    Your job is to find factual errors, unsupported claims, or contradictions.
    Be critical. Find what's wrong with it.

    Summary: {summary}

    Sources:
    {format_sources(source_docs)}

    Return JSON:
    {{
      "has_errors": true/false,
      "errors": ["list of specific factual errors found"],
      "confidence": "high/medium/low"
    }}
    """
    result = llm.call(model=VERIFY_MODEL, prompt=adversarial_prompt, temperature=0.1)
    return parse_json(result)
```

### Gating Logic

```python
async def step_with_cross_validation(
    agent: Agent,
    task: str,
    cross_validate: bool = True,
    high_stakes: bool = False,
) -> StepResult:
    primary = await agent.execute(task)

    if not cross_validate:
        return primary

    # Choose verification depth based on stakes
    if high_stakes:
        verified = await model_vs_model_validate(primary, source_data=agent.last_tool_results)
        if not verified.confirmed:
            return primary._replace(status="blocked", block_reason=f"Cross-validation failed: {verified.reason}")

    # Standard cross-validation for medium-stakes steps
    if primary.confidence < 0.7:
        verified = await source_vs_output_validate(primary)
        if not verified:
            return primary._replace(status="flagged", flag_reason="Cross-validation disagreement — review required")

    return primary
```

### When to Cross-Validate

Apply selectively — this pattern is not free. Cross-validate when:

| Condition | Action |
|-----------|--------|
| Output will propagate to another agent or system | Always cross-validate |
| High monetary or compliance stakes | Cross-validate with adversarial pass |
| Agent used retrieval to derive the output | Cross-validate against a different retrieval path |
| Agent's confidence signal is low | Cross-validate when confidence < threshold |
| Tool call was structurally valid but could be semantically wrong | Cross-validate via independent DB query |

Do **not** cross-validate every step — the compound cost of doubled inference on every step is rarely worth it. Calibrate by risk tier:

- **High stakes** (financial, compliance, safety): cross-validate every step
- **Medium stakes** (data processing, reports): cross-validate on low-confidence outputs only
- **Low stakes** (formatting, routing, exploratory): skip cross-validation

## Receipt

> Verified — This pattern is in active production use. Google Cloud's Agent Assurance and multiple enterprise agent frameworks (LangGraph, Microsoft Copilot Studio) incorporate multi-model verification for high-stakes agent actions. The inverted-query approach (adversarial verification) is documented in AI safety literature under "constitutional AI" and "debate" frameworks. The core mechanism — independent verification against a different error surface — is structurally identical to RAID storage parity and human cross-checking processes, applied to LLM outputs.

## See also

- [S-200 · Agent Reliability Compounding](s200-agent-reliability-compounding.md) — the math that makes single-step failure survivable but multi-step failure catastrophic; cross-validation is a primary mitigation
- [S-212 · Semantic Output Validation Gate](s212-semantic-output-validation-gate.md) — validates single-step output quality against expectations; cross-validation complements it by validating against *independent* sources
- [S-204 · Agent Circuit Breaker](s204-agent-circuit-breaker.md) — counts and kills runaway loops; cross-validation catches the wrong-answer-fast failure mode that circuit breakers miss
- [S-162 · Tool Result Field Projector](s162-tool-result-field-projector.md) — reduces noise in tool results before the agent reasons over them; cross-validation checks the output *after* reasoning
