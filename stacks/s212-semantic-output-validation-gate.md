# S-212 · Semantic Output Validation Gate

Your agent produced a valid JSON response. The schema matched. The fields were populated. The API call returned 200. But the "customer policy details" it generated were hallucinated — a plausible-sounding refund policy that doesn't exist, sent directly to a customer. Nothing broke. Nothing logged an error. The agent "worked" — it produced confident, structured, completely wrong output. This is the gap: structural validation catches format, but not meaning. You need a gate that validates *quality* before the output reaches anything that trusts it.

## Forces

- Traditional output validation checks: is it valid JSON? are required fields present? are types correct? None of these catch hallucinated facts, policy-violating claims, or unsafe instructions
- Agent outputs propagate downstream to databases, emails, code deployments, and other agents — once bad output is in the system, damage compounds silently
- A gate that's too strict blocks legitimate output (UX regression, false positives); too loose and it passes the hallucinated email (catastrophic). The calibration target is *semantic correctness given policy*, not *format correctness*
- Multi-agent pipelines are especially vulnerable: Agent A's output feeds Agent B's context. A silent hallucination from A corrupts B's reasoning, and the error surfaces six steps later with no trace back to the source
- Latency budget: every validation pass adds LLM calls or API calls. A naive "validate everything" approach doubles cost. You need selective, risk-tiered validation

## The move

A semantic output validation gate intercepts agent output *before* it reaches downstream consumers. It applies a cascade of checks — from fast/free (regex, structural) to expensive/accurate (LLM-as-judge) — and routes the output to pass, transform, block, or escalate based on policy. The gate is not part of the agent's reasoning loop; it's a policy enforcement layer that runs *between* output and action.

### Architecture

```
Agent Output
    │
    ▼
┌─────────────────┐
│  Structural     │  ← Fast: JSON parse, required fields, type checks
│  Pre-check      │    Fail → block immediately
└────────┬────────┘
         │ pass
         ▼
┌─────────────────┐
│  Content Policy │  ← Fast: PII scan, blocklist regex, domain rules
│  Scan           │    Fail → redact + log or block
└────────┬────────┘
         │ pass
         ▼
┌─────────────────┐
│  Semantic Risk  │  ← Medium: classifier (LLM or fine-tuned)
│  Classifier     │    Tier by risk: low → pass, medium → flag, high → judge
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
  LOW      MEDIUM/HIGH
    │         │
    ▼         ▼
  PASS    ┌─────────────────┐
          │  LLM-as-Judge  │
          │  Deep Eval     │
          └────────┬────────┘
                   │
              ┌────┴────┐
            PASS      BLOCK/ESCALATE
```

### Risk-tiered validation

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any
import json, re

class RiskLevel(Enum):
    LOW = "low"      # pass through
    MEDIUM = "medium"  # log + pass with watermark
    HIGH = "high"    # block + escalate

@dataclass
class ValidationResult:
    risk: RiskLevel
    passed: bool
    checks: list[dict]
    action: str  # "pass" | "block" | "redact" | "escalate"
    reason: str | None = None

class SemanticOutputGate:
    """
    Policy-driven gate between agent output and downstream consumption.
    Validates structure, content policy, and semantic correctness.
    """

    def __init__(
        self,
        config: dict[str, Any],
        llm_judge: callable | None = None,
    ):
        self.max_output_tokens = config.get("max_output_tokens", 8192)
        self.allowed_domains = set(config.get("allowed_domains", []))
        self.blocklist = [re.compile(p) for p in config.get("blocklist_patterns", [])]
        self.pii_pattern = re.compile(
            r"\b\d{3}-\d{2}-\d{4}\b"  # SSN pattern as example
        )
        self.llm_judge = llm_judge  # e.g., a structured LLM call
        self.risk_classifier_prompt = config.get(
            "risk_classifier_prompt",
            "Classify: Does this text contain claims about "
            "legal, financial, medical, or policy matters? "
            "Rate: LOW / MEDIUM / HIGH"
        )

    # ── Tier 1: Structural pre-check ────────────────────────────────────────

    def _structural_check(self, output: str) -> ValidationResult | None:
        """Fast structural validation. Returns None if passed, ValidationResult if failed."""
        if not output or len(output.strip()) == 0:
            return ValidationResult(
                risk=RiskLevel.HIGH, passed=False, checks=[],
                action="block", reason="Empty output"
            )

        # Try JSON parse if output looks like structured data
        if output.strip().startswith(("{", "[")):
            try:
                parsed = json.loads(output)
            except json.JSONDecodeError as e:
                return ValidationResult(
                    risk=RiskLevel.HIGH, passed=False, checks=[],
                    action="block", reason=f"Invalid JSON: {e}"
                )

        # Token budget check
        tokens_approx = len(output) // 4  # rough approximation
        if tokens_approx > self.max_output_tokens:
            return ValidationResult(
                risk=RiskLevel.MEDIUM, passed=False, checks=[],
                action="block", reason=f"Output exceeds token budget ({tokens_approx} > {self.max_output_tokens})"
            )

        return None  # passed

    # ── Tier 2: Content policy scan ──────────────────────────────────────────

    def _content_policy_scan(self, output: str) -> ValidationResult | None:
        """Fast regex/content scan against policy rules."""
        checks = []

        # PII scan
        pii_found = self.pii_pattern.findall(output)
        if pii_found:
            checks.append({"check": "pii_scan", "result": "found", "detail": len(pii_found)})
            # Redact rather than block — agent may legitimately discuss policy
            redacted = self.pii_pattern.sub("[REDACTED-SSN]", output)
            return ValidationResult(
                risk=RiskLevel.MEDIUM, passed=True, checks=checks,
                action="redact", reason=f"PII redacted ({len(pii_found)} occurrences)"
            )

        # Blocklist scan
        for pattern in self.blocklist:
            if pattern.search(output):
                checks.append({"check": "blocklist", "result": "matched", "pattern": pattern.pattern})
                return ValidationResult(
                    risk=RiskLevel.HIGH, passed=False, checks=checks,
                    action="block", reason=f"Blocklist match: {pattern.pattern}"
                )

        checks.append({"check": "pii_scan", "result": "clean"})
        checks.append({"check": "blocklist", "result": "clean"})
        return None  # passed

    # ── Tier 3: Risk classification ─────────────────────────────────────────

    def _classify_risk(self, output: str) -> RiskLevel:
        """Fast LLM call to classify risk tier before committing to full judge."""
        if not self.llm_judge:
            return RiskLevel.LOW  # Conservative default without judge

        response = self.llm_judge(
            prompt=self.risk_classifier_prompt,
            input=output[:2000],  # truncate for efficiency
            schema={"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]}
        )
        return RiskLevel(response.strip())

    # ── Tier 4: LLM-as-judge deep eval ─────────────────────────────────────

    def _llm_judge_eval(self, output: str, task_context: str) -> ValidationResult:
        """Deep semantic evaluation for high-risk outputs."""
        if not self.llm_judge:
            return ValidationResult(
                risk=RiskLevel.HIGH, passed=False, checks=[],
                action="escalate", reason="No judge configured — defaulting to escalate"
            )

        eval_prompt = f"""
Task context: {task_context}
Agent output to evaluate:
---
{output}
---
Evaluate on:
1. Factual correctness: Are all claims verifiable? Flag any unverified specifics.
2. Policy compliance: Does this respect stated policies (refunds, terms, safety)?
3. Harm potential: Could this cause harm if acted on?
Respond with:
  verdict: PASS / FAIL / ESCALATE
  reason: brief explanation
  flagged_spans: list of specific text spans of concern (or [])
"""
        result = self.llm_judge(prompt=eval_prompt, input="", schema={"type": "object"})

        if result.get("verdict") == "PASS":
            return ValidationResult(
                risk=RiskLevel.LOW, passed=True, checks=[{"check": "judge_eval", "result": "pass"}],
                action="pass", reason=result.get("reason")
            )
        elif result.get("verdict") == "ESCALATE":
            return ValidationResult(
                risk=RiskLevel.HIGH, passed=False, checks=[{"check": "judge_eval", "result": "escalate"}],
                action="escalate", reason=result.get("reason")
            )
        else:
            return ValidationResult(
                risk=RiskLevel.HIGH, passed=False, checks=[{"check": "judge_eval", "result": "fail"}],
                action="block", reason=result.get("reason")
            )

    # ── Main gate ───────────────────────────────────────────────────────────

    def validate(
        self,
        output: str,
        task_context: str = "",
        redact_pii: bool = True,
    ) -> ValidationResult:
        """
        Full cascade validation of agent output.
        Returns a ValidationResult with risk level, pass/fail, and recommended action.
        """
        # Tier 1: Structural
        structural = self._structural_check(output)
        if structural:
            return structural

        # Tier 2: Content policy
        policy = self._content_policy_scan(output)
        if policy:
            if policy.action == "redact" and redact_pii:
                output = self.pii_pattern.sub("[REDACTED-SSN]", output)
            elif policy.action == "block":
                return policy

        # Tier 3: Risk classification
        risk = self._classify_risk(output)

        if risk == RiskLevel.LOW:
            return ValidationResult(
                risk=risk, passed=True, checks=[{"check": "risk", "level": "low"}],
                action="pass", reason="Low-risk output"
            )

        # Tier 4: Full LLM judge for MEDIUM/HIGH
        return self._llm_judge_eval(output, task_context)
```

### Usage in an agent pipeline

```python
from stacks.s212_semantic_output_validation_gate import SemanticOutputGate, ValidationResult

# Initialize once per deployment
gate = SemanticOutputGate(
    config={
        "max_output_tokens": 4096,
        "allowed_domains": ["support.acme.com", "docs.acme.com"],
        "blocklist_patterns": [
            r"internal.*confidential",
            r"do\s+not\s+share",
        ],
    },
    llm_judge=llm_judge_fn,  # your LLM gateway call
)

# After every agent step that produces output
def on_agent_output(agent_output: str, task_context: str):
    result = gate.validate(agent_output, task_context=task_context)

    if result.action == "pass":
        return agent_output  # proceed normally

    elif result.action == "redact":
        return agent_output  # PII already redacted in-place

    elif result.action == "block":
        logger.warning(f"Output blocked: {result.reason}", extra={"checks": result.checks})
        return generate_safe_fallback_response(result.reason)

    elif result.action == "escalate":
        logger.error(f"Output escalated for human review: {result.reason}")
        queue_for_human_review(agent_output, task_context, result)
        return generate_safe_fallback_response("Our team is reviewing your request")
```

### Key design decisions

- **Fail-open vs. fail-closed is a policy choice.** Customer-facing responses should fail closed (block/ escalate) by default. Internal agent-to-agent handoffs can fail open with a watermark and audit log.
- **Risk classification is a separate LLM call** — cheaper and faster than a full judge. Only escalate high-risk outputs to the expensive eval.
- **Redaction beats blocking for PII.** PII found in context windows is often innocuous (the agent quoting user text). Redact and pass is better UX than blocking.
- **Context matters.** Pass `task_context` (the original user intent, any retrieved documents) to the judge so it can evaluate factual alignment, not just surface plausibility.

## Receipt

> Receipt pending — 2026-06-30

## See also

- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — the complementary interception layer for *proposed* actions; this entry covers *produced* outputs
- [S-204 · Agent Circuit Breaker](s204-agent-circuit-breaker.md) — counts and budgets; this entry validates quality and safety
- [S-193 · LLM-as-Judge Eval Pipeline](s193-llm-as-judge-eval-pipeline.md) — the judge evaluation pattern this gate depends on for deep semantic checks
