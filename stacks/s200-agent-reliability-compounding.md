# S-200 · Agent Reliability Compounding

Every step your agent takes multiplies your failure surface. Five steps at 95% reliability yields 77% end-to-end success. Ten steps yields 59%. Twenty steps — common in production agentic workflows — yields 36%. Your agent is three times more likely to fail than to succeed, and the math has been there the whole time, hiding in plain sight.

This is Lusser's Law applied to language models: system reliability equals the product of step reliabilities. Unlike deterministic software where a function either works or doesn't, LLM-powered steps are stochastic — each one can fail in subtly wrong ways that pass a superficial check. The compounding is real, and it's brutal.

## Forces

- Every agent step — tool call, retrieval, reasoning pass, tool result parsing — carries independent failure probability. In practice, most teams measure none of them
- A step that "usually works" is not acceptable when the chain runs unattended: the one failure in twenty becomes a critical incident in production
- The failure modes compound non-linearly: a wrong intermediate conclusion propagates forward and makes subsequent steps fail on worse inputs
- Tool-call success (HTTP 200) is confused with task success — the database write that hits the wrong table returns 200 and the agent proceeds confidently on bad state
- Most agent demos show 2–3 steps. Production workflows routinely run 5–15 steps. The audience never sees the failure rate math
- Adding retry logic improves individual step reliability but doesn't fix the compounding — it just adds latency and cost to a fundamentally broken chain

## The move

**Do the reliability math first, before designing the agent.** Treat the target end-to-end success rate as a constraint and work backward.

### 1. Count steps, assign failure rates

Every architectural decision in agent design — number of sub-agents, retrieval depth, multi-turn reasoning — has a reliability cost. Model it explicitly:

```
P_end_to_end = Π P(success | step_i)  for i = 1..N

Example: 10 steps × 95% each = 0.95^10 = 60%
Example: 10 steps × 90% each = 0.90^10 = 35%
Example: 5 steps × 95% each  = 0.95^5  = 77%
```

Set a target (typically 95–99% for production) and solve for the maximum allowable per-step failure rate.

### 2. Reduce chain length first — it's always the highest-leverage move

Before adding guardrails, retries, or fallback models, ask: can this be done in fewer steps?

- Merge sequential tool calls into batch operations
- Push expensive reasoning to a planning phase that runs once, not per-step
- Pre-compute static context (schema, domain knowledge) so the agent doesn't need to retrieve it each turn
- Use a more capable model on short chains rather than a cheap model with long loops

### 3. Place verification gates between steps

A step that passes its own internal check is not verified. Add an independent assertion between critical steps:

```python
import anthropic
from pydantic import BaseModel, field_validator

client = anthropic.Anthropic()

class StepResult(BaseModel):
    action: str
    output: str
    confidence: float

def run_with_gate(
    prompt: str,
    gate_prompt: str,
    model: str = "claude-sonnet-4-20250514",
    gate_threshold: float = 0.75,
) -> StepResult:
    """Run a single agent step with a downstream verification gate."""
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text

    # Parse — structured output fallback if parsing fails
    try:
        result = StepResult.model_validate_json(raw)
    except Exception:
        # Fallback: extract what we can, mark low confidence
        result = StepResult(
            action="parse_error",
            output=raw[:500],
            confidence=0.3,
        )

    # Run verification gate — independent model, cheaper
    gate_response = client.messages.create(
        model="claude-haiku-4-20250514",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": f"{gate_prompt}\n\nStep output to verify:\n{result.output}"
        }],
    )
    gate_text = gate_response.content[0].text.lower()

    # Gate heuristics — in production, use structured gate output
    gate_score = 1.0 if ("correct" in gate_text and "proceed" in gate_text) else 0.5

    if gate_score < gate_threshold:
        raise RuntimeError(
            f"Gate failed (score={gate_score:.2f}). "
            f"Action={result.action}, output={result.output[:100]}"
        )

    return result
```

### 4. Architect for blast radius containment

When the math doesn't work out — when you genuinely need 20 steps and each can only be 90% reliable — accept the constraint and design for it:

- **Human-in-the-loop at decision boundaries**: critical actions (delete, send, deploy, charge) require human confirmation before the agent proceeds
- **Idempotency by design**: make every tool call safe to retry or skip — the agent shouldn't corrupt state on partial failure
- **Checkpoint and resume**: S-195 covers this; the goal is that a failure at step 18 doesn't mean re-running steps 1–17
- **Escalation paths**: define what "give up" looks like — the agent should surface a clear failure signal rather than loop indefinitely

```python
# Reliability budget calculator
def reliability_budget(target: float, max_steps: int) -> float:
    """
    Given a target end-to-end success rate and max steps,
    what must each step's reliability be?
    """
    return target ** (1.0 / max_steps)

# Target 95% success over 10 steps → each step must be 99.5% reliable
print(f"{reliability_budget(0.95, 10):.1%}")   # 99.5%
print(f"{reliability_budget(0.95, 15):.1%}")   # 99.7%
print(f"{reliability_budget(0.99, 10):.1%}")   # 99.9%

# But if your steps are only 90% reliable:
print(f"5 steps @ 90%:  {(0.90**5):.1%}")      # 59%
print(f"10 steps @ 90%: {(0.90**10):.1%}")     # 35%
```

## Receipt

> Receipt pending — 2026-06-29
> Run `python reliability_budget_calculator.py` with Claude API credentials to verify compounding math and gate behavior on a real agent loop.

## See also

- [S-193 · LLM-as-Judge Eval Pipeline](s193-llm-as-judge-eval-pipeline.md) — gate design and judge bias tradeoffs
- [S-195 · Agent Checkpoint and Resume](s195-agent-checkpoint-resume.md) — containment when compounding failure hits
- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — runtime enforcement of blast radius limits
- [S-199 · Agent Self-Healing Loops](s199-agent-self-healing-loops.md) — detection and recovery within the step chain
