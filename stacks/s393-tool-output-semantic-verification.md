# S-393 · Tool Output Semantic Verification

Your agent called `process_refund(order_id: "ORD-9912")`. The tool returned `{"status": "success", "refund_id": "REF-7731"}`. The agent reports to the user: "Refund processed." But the money never moved — the external payment API returned a transient error encoded as a non-HTTP 200 response, and the tool wrapper logged it without surfacing it to the agent. The agent trusted the `status: "success"` field. No crash. No trace error. Just a silent wrong state propagated into user-visible output.

This is the semantic gap: syntactically valid tool output can still be semantically wrong, and the agent has no mechanism to know the difference.

## Forces

- **Agents trust tool outputs implicitly.** Unlike code that can throw exceptions, tool results arrive as structured data that the agent accepts at face value
- **Silent failures outnumber loud ones.** HTTP errors, timeouts, and schema violations are visible. Business-rule violations (partial success, rate-limit surface-as-success, downstream idempotency drift) are not
- **Schema validation catches structure, not correctness.** A response can pass JSON Schema and still describe a failed operation
- **Retrying unverified tool results compounds the error.** If the agent retries a semantically-failed operation believing it succeeded, it may double-charge, double-ship, or double-refund
- **The compensation layer (S-352) is expensive.** Compensation keys undo damage after it propagates. Semantic verification prevents the damage from happening

## The move

**1. Wrap every tool result in an error envelope.**

```python
class ToolResult[T]:
    ok: bool                          # machine-readable success flag
    data: T | None                    # typed payload on success
    error: ToolError | None           # structured error on failure
    metadata: ResultMetadata          # latency, upstream_status, attempt

class ToolError:
    code: str                         # e.g. "UPSTREAM_TIMEOUT", "PARTIAL_SUCCESS"
    retryable: bool
    detail: str                       # human-readable for human review
    upstream_response: Any | None     # raw upstream for forensics
```

Never return raw tool output directly. The envelope forces every caller — human or agent — to handle the `ok` branch explicitly.

**2. Implement post-call semantic verification.**

Not every tool result that passes the envelope check is semantically correct. Verify business invariants:

```python
def verify_refund_result(result: ToolResult[RefundData], original: RefundRequest) -> VerifiedRefund:
    if not result.ok:
        raise VerificationError(f"Tool call failed: {result.error.code}")

    data = result.data

    # Semantic checks — not schema checks
    assert data.refund_id is not None, "refund_id must not be null on success"
    assert data.amount == original.amount, f"amount mismatch: {data.amount} != {original.amount}"
    assert data.currency == original.currency, f"currency mismatch"

    # Downstream state verification (optional, highest confidence)
    state = payment_api.get_refund_state(data.refund_id)
    assert state == "settled", f"refund not settled: {state}"

    return VerifiedRefund(verified=True, data=data)
```

**3. Gate agent reasoning on verification status.**

```python
def execute_tool_with_verification(tool: Tool, args: dict, max_retries: int = 2) -> ToolResult:
    for attempt in range(max_retries + 1):
        raw_result = tool.execute(args)

        try:
            verified = post_call_verifier.verify(tool.name, raw_result, context=current_request)
            if verified.ok:
                return verified  # agent receives verified result
        except VerificationError as e:
            if attempt < max_retries and e.retryable:
                continue
            return ToolResult(ok=False, error=ToolError(code="VERIFICATION_FAILED", ...))

    return ToolResult(ok=False, error=ToolError(code="VERIFICATION_EXHAUSTED", retryable=False, ...))
```

**4. Escalate unverified states to a human gate.**

For high-stakes operations (payments, data deletion, external writes), unverified results go to a human review queue. The agent proceeds with a `pending_verification` flag. The pattern: agent does the reasoning, the verification gate does the trust.

```python
HIGH_STAKES_OPERATIONS = {"payment", "refund", "delete", "write", "transfer"}

def execute_with_governance_gate(tool: Tool, args: dict) -> ToolResult:
    result = execute_tool_with_verification(tool, args)

    if tool.name in HIGH_STAKES_OPERATIONS and not result.verified:
        governance.notify_human(result, context=current_request)
        return ToolResult(ok=False, error=ToolError(
            code="ESCALATED", retryable=False,
            detail="Result unverified — human review required"
        ))

    return result
```

## Receipt

> Verified 2026-07-02 — The ToolResult envelope pattern (step 1) maps directly to the "error envelope" pattern described in Zylos Research (2026-04-11): `ok: bool` + `data/error` union type. The semantic verification loop (step 2) is implemented as `post_call_verifier.verify()` in how2.sh's output verification pipeline (Feb 2026). AgentMarketCap (April 2026) reports that structured error envelopes cut silent failure rates by 40-60% in production agent pipelines. The compounding reliability math (15 steps × 85% = 12% success) directly motivates verification at every step — not just at the compensation layer (S-352).

## See also
- [S-352 · Agentic Compensation Keys](s352-agentic-compensation-keys-the-autonomous-retry-era.md) — undo layer; this entry is the prevent layer
- [S-87 · External API Response Validation](s87-external-api-response-validation.md) — schema validation for upstream API drift
- [S-93 · Tool Side-Effect Idempotency](s93-tool-side-effect-idempotency.md) — prevents duplicate execution harm
- [S-384 · Agent Circuit Breakers](s384-agent-circuit-breakers.md) — halts loops on downstream failures
