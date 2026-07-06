# [S-553] · Behavioral Output Contracting

You deploy confidently. Your CI pipeline passed, your traces look clean, your error rate sits at 0.2%. Three days later a customer emails to say the agent started returning malformed invoices — and your dashboard never flinched. The HTTP response was 200. The output was valid JSON. It just wasn't what you meant.

This is the semantic regression problem: agents that drift from intended behavior while their technical metrics stay green. Behavioral output contracting catches it.

## Forces

- Traditional monitoring validates syntax (is it valid JSON?) not semantics (is it the right JSON?)
- LLMs are non-deterministic — the same prompt produces acceptable and broken outputs probabilistically, without error signals
- Production inputs are wider than any pre-deploy test set can cover; regressions surface only under real traffic
- Alerting on raw quality is noisy without a grounded definition of "correct enough"
- Post-deployment evaluation that runs disconnected from the deployment gate creates a feedback lag that lets bad behavior compound

## The move

Define the surface-level invariants of your agent's outputs — the things that must be true regardless of input — and validate every production output against them automatically. Run the check as a deployment gate, continuously in production, and as a regression trigger in CI.

### 1. Identify the output boundary

Your agent's output crosses a **trust boundary**: from your system's control into external systems, user-facing content, or downstream API calls. Contract the boundary, not the internals.

Ask: *what must this output always contain / never contain / never exceed?* These are your invariants, not your preferences.

```python
from pydantic import BaseModel, field_validator
import json

# Define the contract — not the full schema, just the non-negotiable surface
class InvoiceOutputContract(BaseModel):
    amount_cents: int
    currency: str  # Must be ISO 4217
    recipient_id: str
    line_items: list[dict]

    @field_validator("amount_cents")
    @classmethod
    def amount_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount_cents must be positive")
        return v

    @field_validator("currency")
    @classmethod
    def currency_must_be_iso(cls, v: str) -> str:
        ISO_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CAD"}
        if v.upper() not in ISO_CURRENCIES:
            raise ValueError(f"currency must be ISO 4217, got {v}")
        return v.upper()

    @field_validator("line_items")
    @classmethod
    def line_items_must_not_be_empty(cls, v: list) -> list:
        if len(v) == 0:
            raise ValueError("invoice must have at least one line item")
        return v


def validate_agent_output(raw_output: str) -> InvoiceOutputContract:
    """
    Parse and contract-validate agent output.
    Raises on contract violation — does NOT return a fallback silently.
    """
    parsed = json.loads(raw_output)
    return InvoiceOutputContract.model_validate(parsed)
```

### 2. Three tiers of behavioral assertions

Not everything is a deal-breaker. Partition violations:

| Tier | Trigger | Response |
|------|---------|----------|
| **Hard contract** | `amount_cents <= 0`, `recipient_id` missing | Reject + escalate — never surface to user |
| **Soft contract** | `currency` unknown but parseable, `line_items` very long | Flag, log, surface with a warning |
| **Quality signal** | Response structurally valid but semantically thin (no actionable data) | Route to async eval queue for human review |

Hard contract violations never flow downstream. Soft violations flow with metadata. Quality signals flow with a `needs_review: true` flag and are sampled.

### 3. Run it in three places

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import logging

class ViolationSeverity(Enum):
    HARD = "hard"       # Reject output
    SOFT = "soft"       # Log + warn
    QUALITY = "quality" # Queue for review

@dataclass
class ValidationResult:
    passed: bool
    severity: ViolationSeverity
    message: str
    patched_output: Optional[dict] = None  # For soft violations with auto-fixes


def validate_in_pipeline(raw_output: str, env: str) -> ValidationResult:
    """
    Validate agent output against the behavioral contract.
    In staging/CI: all violations fail the run.
    In production: hard violations are rejected; soft violations are flagged.
    """
    try:
        validated = validate_agent_output(raw_output)
        return ValidationResult(passed=True, severity=None, message="Contract satisfied")
    except ValueError as e:
        msg = str(e)
        if "must be positive" in msg or "must have at least one line item" in msg:
            return ValidationResult(
                passed=False,
                severity=ViolationSeverity.HARD,
                message=f"Hard contract violation: {msg}"
            )
        elif "must be ISO" in msg:
            return ValidationResult(
                passed=False,
                severity=ViolationSeverity.SOFT,
                message=f"Soft contract violation: {msg}",
                patched_output={"currency": "UNKNOWN", "needs_review": True}
            )
        else:
            return ValidationResult(
                passed=False,
                severity=ViolationSeverity.QUALITY,
                message=f"Quality signal: {msg}"
            )
    except json.JSONDecodeError:
        return ValidationResult(
            passed=False,
            severity=ViolationSeverity.HARD,
            message="Output is not valid JSON — cannot parse"
        )
```

**CI gate:** Pipeline fails if any `HARD` or `SOFT` violation fires. A single violation in CI is enough to block a deploy.

**Production guard:** Every output is validated. `HARD` violations trigger the compensation path (fallback model, cached response, or explicit error to user — never the raw bad output). `SOFT` violations are logged with structured metadata and counted toward an SLO budget. `QUALITY` signals go to an async review queue.

**Continuous sampling:** Route 1–5% of passing outputs to the quality queue for human review. Accumulate confirmed regressions into the eval harness test set within 24 hours.

### 4. Compile failures into test cases

```python
def promote_to_eval_case(result: ValidationResult, input_prompt: str, raw_output: str):
    """
    After human confirms a QUALITY violation is a real regression:
    promote it to the pinned eval set for regression prevention.
    """
    eval_case = {
        "input": input_prompt,
        "expected_output": None,  # Agent cannot self-label this
        "contract_check": result.severity.value,
        "note": result.message,
        "added": "2026-07-04",
    }
    # Append to your pinned eval set (e.g., JSONL file, or push to your eval platform)
    with open("evals/pinned_regression_cases.jsonl", "a") as f:
        f.write(json.dumps(eval_case) + "\n")
```

The eval set grows from real failures, not imagined edge cases. This is the feedback loop that closes the gap between staging and production.

## Receipt

> Verified 2026-07-04 — Behavioral output contracting described as a three-tier validation pattern with Pydantic-based contract definitions, staged enforcement (CI / production guard / continuous sampling), and an explicit failure-to-test-case promotion path. Code example is a runnable Python/Pydantic pattern. Eval case promotion to JSONL-backed pinned set is illustrative of the workflow; actual implementation depends on the team's eval platform (deepeval, LangSmith, etc.).

## See also

- [S-538 · Agent Evaluation Harness](stacks/s538-agent-evaluation-harness.md) — the infrastructure that runs the test set generated by this pattern
- [S-552 · Agent Evaluation: The Undersized Layer](stacks/s552-agent-evaluation-the-undersized-layer.md) — explains why agent evaluation is chronically underinvested
- [S-525 · Trace vs. Eval: The Production Observability Gap](stacks/s525-trace-vs-eval-the-production-observability-gap.md) — the gap this pattern closes
- [S-107 · Pipeline Stage Output Budget](stacks/s107-pipeline-stage-output-budget.md) — output shaping as a cost/quality lever
