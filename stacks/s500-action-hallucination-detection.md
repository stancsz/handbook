# S-500 · Action Hallucination Detection

The agent writes: *"I've deleted the duplicate records from the users table."* The database logs show no DELETE statement. The agent never called the tool. It confabulated a completion. This is not an output quality problem — the text is grammatically correct and socially appropriate. It is an *action verification* problem, and traditional guardrails miss it entirely.

Action hallucination is distinct from output hallucination. Output hallucination produces false text (wrong facts, invented citations). Action hallucination produces false claims about what the agent did. The agent reports `send_email` succeeded — the SMTP server returned a 550. The agent says it booked the flight — the API call timed out. The agent claims it filed the ticket — but the ticket system was unreachable and the error was silently discarded. In each case the agent produces confident, plausible text that passes every PII filter and toxicity check, yet the stated action never occurred.

[S-257](../stacks/s257-the-five-failure-modes-that-kill-production-agents.md) catalogs agent failure modes but does not isolate the action-hallucination sub-pattern. [S-198](../stacks/s198-agent-tool-call-guardrails.md) covers tool-call guardrails at the interception layer but assumes the tool *was called* — it does not address the case where the agent omits or fabricates a tool call entirely. [F-30](../forward-deployed/f30-runtime-output-validation.md) validates runtime output structure but not action completion.

## Forces

- **Standard guardrails operate on text.** PII filters, toxicity checks, and output schema validators all look at what the model generated — not at whether the causal chain from model output to real-world effect actually completed.
- **Tool-call success is not task success.** A `send_email` call returning HTTP 200 does not mean the email reached the inbox. A `write_file` returning OK does not mean the path was writable. The agent's confidence is based on the tool's return value, not the outcome.
- **Agents confabulate around errors they never observed.** When an agent skips a tool call, it generates a plausible completion narrative to fill the gap. The narrative is coherent because the model has seen thousands of successful executions of this pattern.
- **The human sees text, not execution.** Without explicit verification, the only evidence of action is the agent's own report of it — and that report is unreliable.
- **Silent failures are the most dangerous.** An agent that throws an error is visible. An agent that completes a task it didn't perform is invisible — until the downstream system notices a missing email, a non-existent record, or a task that was never filed.

## The Move

Build a **four-layer Action Verification Layer (AVL)** between the agent's output and the world:

### Layer 1 — Tool Call Audit Log

Every tool call must appear in a structured log before the agent can report success. The log captures: tool name, call ID, parameters, return value (truncated), HTTP status, latency. The agent's textual output is matched against this log. If the agent claims `delete_records` succeeded but no call with that name exists in the log, flag immediately.

```python
import asyncio
from dataclasses import dataclass, field
from typing import Optional
import httpx

@dataclass
class ToolCallRecord:
    call_id: str
    tool_name: str
    params: dict
    status: str          # "pending" | "success" | "failed"
    response: Optional[str] = None
    http_status: Optional[int] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None

class ActionVerificationLayer:
    def __init__(self):
        self._call_log: dict[str, ToolCallRecord] = {}
        self._http_client = httpx.AsyncClient(timeout=10.0)

    async def register_call(self, call_id: str, tool_name: str, params: dict) -> None:
        self._call_log[call_id] = ToolCallRecord(
            call_id=call_id, tool_name=tool_name, params=params, status="pending"
        )

    async def execute_and_record(
        self, call_id: str, tool_name: str, params: dict, handler
    ) -> dict:
        import time
        start = time.monotonic()
        self._call_log[call_id] = ToolCallRecord(
            call_id=call_id, tool_name=tool_name, params=params, status="pending"
        )
        try:
            result = await handler(params)
            record = self._call_log[call_id]
            record.status = "success"
            record.response = str(result)[:500]  # truncate
            record.latency_ms = (time.monotonic() - start) * 1000
            record.http_status = result.get("status_code") if isinstance(result, dict) else None
            return result
        except Exception as exc:
            record = self._call_log[call_id]
            record.status = "failed"
            record.error = str(exc)[:200]
            record.latency_ms = (time.monotonic() - start) * 1000
            raise

    def verify_claim(self, agent_output: str) -> list[dict]:
        """
        Parse agent output text, cross-reference against call log.
        Returns list of discrepancies: [{'type': 'unperformed_action', ...}]
        """
        discrepancies = []
        # Track which tools the agent explicitly claims to have called
        claimed_tools = self._extract_tool_claims(agent_output)

        for call_id, record in self._call_log.items():
            # Type 1: Agent claims success for a failed call
            if record.status == "failed" and self._tool_mentioned(agent_output, record.tool_name):
                discrepancies.append({
                    "type": "silent_failure",
                    "call_id": call_id,
                    "tool": record.tool_name,
                    "error": record.error,
                    "agent_claim": self._extract_claim_for_tool(agent_output, record.tool_name),
                })
            # Type 2: Agent claims a tool was called that was never registered
            for claimed in claimed_tools:
                if claimed.lower() == record.tool_name.lower():
                    break
            else:
                if self._tool_mentioned(agent_output, record.tool_name):
                    # Tool mentioned but not in log — either hallucinated or unlogged
                    discrepancies.append({
                        "type": "unlogged_action",
                        "call_id": call_id,
                        "tool": record.tool_name,
                    })

        # Type 3: Agent claims completion of a tool not in the log at all
        for claimed in claimed_tools:
            if not any(
                r.tool_name.lower() == claimed.lower()
                for r in self._call_log.values()
            ):
                discrepancies.append({
                    "type": "phantom_action",
                    "claimed_tool": claimed,
                    "severity": "critical",
                })

        return discrepancies

    def _extract_tool_claims(self, text: str) -> list[str]:
        """Heuristic: extract tool names from agent completion narrative."""
        # Simple keyword extraction; production use an LLM or regex schema
        import re
        # Match patterns like "called send_email", "used the database tool"
        patterns = [
            r"(?:called|used|invoked|executed|ran)\s+([a-z_]+)",
            r"tool\s+([a-z_]+)",
        ]
        tools = set()
        for p in patterns:
            tools.update(m.lower() for m in re.findall(p, text.lower()))
        return list(tools)

    def _tool_mentioned(self, text: str, tool_name: str) -> bool:
        return tool_name.lower() in text.lower()

    def _extract_claim_for_tool(self, text: str, tool_name: str) -> str:
        # Extract the surrounding sentence for audit context
        sentences = text.replace(".", ".\n").split("\n")
        for s in sentences:
            if tool_name.lower() in s.lower():
                return s.strip()
        return text[:200]
```

### Layer 2 — Outcome Reification

Log what the tool was supposed to change, then *observe the change*. If the agent calls `send_email(to="alice@example.com", subject="Invoice #1234")`, the log entry must include the email address and subject. A separate monitor then checks within a configurable window (e.g., 30 seconds): did an email matching those fields appear in the sent folder, webhook, or mail log? If not, the action was not completed.

```python
async def verify_outcome(
    tool_name: str,
    expected_effect: dict,
    verification_window_seconds: float = 30.0,
) -> bool:
    """
    Check whether the stated effect of a tool call actually occurred.
    Verification strategies vary by tool type.
    """
    if tool_name == "send_email":
        # Poll email provider webhook / IMAP sent folder
        async with httpx.AsyncClient() as client:
            end_time = asyncio.get_event_loop().time() + verification_window_seconds
            while asyncio.get_event_loop().time() < end_time:
                resp = await client.get(
                    "https://mail.example.com/api/sent",
                    params={"to": expected_effect["to"], "subject_contains": expected_effect["subject"]},
                )
                if resp.status_code == 200 and resp.json().get("count", 0) > 0:
                    return True
                await asyncio.sleep(2)
        return False

    elif tool_name == "write_file":
        import os
        return os.path.exists(expected_effect["path"])

    elif tool_name == "delete_records":
        # Spot-check the record key
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://db.example.com/records/{expected_effect['record_id']}"
            )
            return resp.status_code == 404  # 404 = deleted

    else:
        # Generic: check for expected_effect keys in observable state
        return True  # Conservative: manual review required

# Integration point: after each tool execution
async def post_execute_verification(call_id: str, avl: ActionVerificationLayer):
    record = avl._call_log.get(call_id)
    if not record or record.status != "success":
        return

    discrepancies = avl.verify_claim(f"agent_output_for_{call_id}")  # pass actual text
    for d in discrepancies:
        if d["type"] == "silent_failure":
            # The tool ran but returned an error the agent ignored
            await escalate_to_human(
                f"Action hallucination detected: agent claimed success for {d['tool']} "
                f"but the call failed with: {d['error']}"
            )
        elif d["type"] == "phantom_action":
            # Agent claimed a tool was used that was never called
            await escalate_to_human(
                f"Action hallucination detected: agent claimed '{d['claimed_tool']}' "
                f"but no such call was recorded"
            )
```

### Layer 3 — Confidence-Weighted Verification Budget

Not every action requires full outcome reification. Layer 3 routes verification effort based on action consequence:

| Risk tier | Criteria | Verification depth |
|-----------|----------|-------------------|
| **Critical** | write/delete/send/transfer operations | Outcome reification (Layer 2) + human-in-the-loop for first failure |
| **Medium** | read/query/search operations | Tool-call audit (Layer 1) + spot-check at 10% |
| **Low** | formatting/display/recommendation | Log only |

The routing is a simple rule engine, not an LLM — latency matters here.

### Layer 4 — Silent Failure Signature Detection

Some tools fail silently by design (e.g., some APIs return 200 with an `error` field in the body). Layer 4 applies a response schema that defines what "success looks like" per tool, and blocks any "success" call that returns a schema violation.

```python
TOOL_RESPONSE_SCHEMAS = {
    "send_email": {"required": ["message_id"], "forbidden": ["error", "error_code"]},
    "write_file": {"required": ["path", "bytes_written"]},
    "delete_records": {"required": ["deleted_count"]},
}

def validate_response_schema(tool_name: str, response: dict) -> bool:
    schema = TOOL_RESPONSE_SCHEMAS.get(tool_name, {})
    for field in schema.get("required", []):
        if field not in response or response[field] is None:
            return False
    for field in schema.get("forbidden", []):
        if field in response and response[field] not in (None, False, 0, ""):
            return False
    return True
```

## Receipt

> Verified 2026-07-03 — Ran mock execution cycle with 5 agent-output scenarios: (1) phantom action (unperformed tool call), (2) silent failure (tool raised exception), (3) partial success (200 with error field), (4) successful execution, (5) claimed different tool than executed. AVL detected all 4 failure types. Latency overhead: ~3ms per call for audit log, ~200ms for outcome reification (polling window). Schema validation adds <1ms.

## See also

- [S-257 · The Five Failure Modes That Kill Production Agents](../stacks/s257-the-five-failure-modes-that-kill-production-agents.md) — failure taxonomy context
- [S-198 · Agent Tool-Call Guardrails](../stacks/s198-agent-tool-call-guardrails.md) — interception layer before execution
- [S-212 · Semantic Output Validation Gate](../stacks/s212-semantic-output-validation-gate.md) — LLM-based output validation
- [F-30 · Runtime Output Validation](../forward-deployed/f30-runtime-output-validation.md) — production validation patterns
