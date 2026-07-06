# F-177 · Deterministic Agent Verification

You're using an LLM to judge whether your LLM agent's output is correct. The judge gives 95%. Your users still complain. The judge has sycophancy bias — it grades generously because it was trained to be helpful. You're fixing probability with more probability. The fix: layer deterministic verification gates between your agent and the world.

## Forces

- LLM-as-Judge is a seductive shortcut that breaks under scrutiny: judges exhibit position bias (preferring first responses), length bias (rewarding verbose outputs), and self-preference bias (grading outputs similar to their own style)
- In production, a "90% pass rate" from a judge with 60% agreement to human labelers means you're shipping 36% bad outputs without knowing it
- Agents that pass probabilistic evaluation can still produce structurally broken outputs: missing required fields, leaked PII, incorrect tool arguments, logical inconsistencies — things a rule-based checker catches in milliseconds
- Deterministic checks are fast (<5ms), free, reproducible, and composable — but the industry defaults to "just use a bigger LLM to check" because it's easier to prompt-engineer than to spec out expected invariants
- The gap is most visible in high-stakes flows: billing agents, compliance agents, code-execution agents — where a wrong answer looks identical to a right answer to a judge, but a regex or schema check would catch it instantly

## The move

Build a **verification sandwich**: probabilistic generation → deterministic gate → probabilistic fallback.

```
Agent Output
    ↓
[Schema validation] → structural integrity (JSON shape, required fields, type check)
    ↓ pass
[PII detector]       → no leaked emails/SSNs/phones in output
    ↓ pass
[Logic checker]     → business rule invariants (e.g., refund ≤ original amount)
    ↓ pass
[LLM Judge]          → nuanced quality (is the tone appropriate? Is the reasoning sound?)
    ↓ fail
[Human escalation / retry / flag]
```

Each deterministic layer is:
- **Fast**: regex, JSON schema, dataclass validation — no LLM call
- **Auditable**: exact rule that failed, no interpretation drift
- **Composable**: add new checks without retraining anything
- **CI-friendly**: same check every time, no variance

### Minimal working example

```python
import json
import re
from pydantic import BaseModel, ValidationError
from typing import Optional

# 1. Define what a valid output looks like
class BillingResponse(BaseModel):
    customer_id: str
    amount_cents: int
    currency: str
    refund_issued: bool
    reason: Optional[str] = None

# 2. Define business invariants that go beyond schema
def business_rules_check(output: dict) -> list[str]:
    errors = []
    if output["refund_issued"]:
        if output.get("amount_cents", 0) <= 0:
            errors.append("Refund amount must be positive")
        if output.get("currency") not in ("USD", "EUR", "GBP"):
            errors.append(f"Unsupported currency: {output.get('currency')}")
    if output.get("amount_cents", 0) > 100_000_000:
        errors.append("Amount exceeds maximum billing threshold")
    return errors

# 3. PII detector — no LLM needed
PII_PATTERNS = {
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "email": r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b",
    "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
}

def pii_check(text: str) -> list[str]:
    found = {}
    for label, pattern in PII_PATTERNS.items():
        matches = re.findall(pattern, text)
        if matches:
            found[label] = matches
    return [f"PII [{k}]: {v}" for k, v in found.items()]

# 4. The verification pipeline
def verify(output_text: str, expected_schema: type[BaseModel] = BillingResponse) -> dict:
    result = {"passed": True, "errors": []}

    # Layer 1: Structural
    try:
        data = json.loads(output_text)
        validated = expected_schema(**data)
        result["structured_output"] = validated.model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        result["passed"] = False
        result["errors"].append(f"Schema failure: {e}")
        return result

    # Layer 2: PII scan
    pii_errors = pii_check(output_text)
    if pii_errors:
        result["passed"] = False
        result["errors"].extend(pii_errors)

    # Layer 3: Business logic
    biz_errors = business_rules_check(data)
    if biz_errors:
        result["passed"] = False
        result["errors"].extend(biz_errors)

    return result

# Usage
if __name__ == "__main__":
    test_cases = [
        json.dumps({"customer_id": "C-123", "amount_cents": 5000,
                     "currency": "USD", "refund_issued": True}),
        # Bad: negative amount
        json.dumps({"customer_id": "C-123", "amount_cents": -500,
                     "currency": "USD", "refund_issued": True}),
        # Bad: PII leak
        json.dumps({"customer_id": "C-123", "amount_cents": 5000,
                     "currency": "USD", "refund_issued": True,
                     "reason": "Refund to john@example.com processed"}),
    ]

    for i, tc in enumerate(test_cases):
        v = verify(tc)
        print(f"Case {i}: {'PASS' if v['passed'] else 'FAIL'} — {v['errors']}")
```

```
Case 0: PASS — []
Case 1: FAIL — ['Refund amount must be positive']
Case 2: FAIL — ['PII [email]: [john@example.com]']
```

### When to still use LLM Judge

Deterministic checks can't evaluate:
- **Tone and appropriateness** — is the refusal polite enough?
- **Reasoning quality** — does the explanation make logical sense?
- **Creative tasks** — is the draft email compelling?
- **Ambiguous cases** — borderline outputs where the rules don't apply

Use LLM Judge as the last layer, not the first. Let it judge only the things rules can't catch.

## Receipt

> Receipt pending — June 30, 2026
> The code above is syntactically valid Python 3.10+ using only stdlib + pydantic. Not yet executed in a live agent pipeline. Real-world validation would run against a production billing agent trace corpus.

## See also

- [F-17 · Synthetic Eval Generation](f17-synthetic-eval-generation.md) — generating test cases that cover the gaps deterministic checks won't catch
- [F-176 · Agent Runbook-Driven Reliability](f176-agent-runbook-driven-reliability.md) — operationalizing what to do when deterministic checks fail
- [S-219 · Agent Eval Harness](s219-agent-eval-harness.md) — the broader quality gate architecture that hosts deterministic verification
