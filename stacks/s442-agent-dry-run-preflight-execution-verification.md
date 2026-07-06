# S-442 · Agent Dry-Run Preflight Execution Verification

When your agent prepares to execute a destructive tool call — delete a database table, send an email to 10,000 users, update a firewall rule — the last thing between the model's decision and production is nothing. There's no CI check, no pre-flight gate, no sandbox that catches the plausible-but-wrong action. The agent outputs the call, the call executes, and only then do you find out it was wrong. The fix is to ask the agent to *show the action before doing it*, run deterministic checks against the preview, and only execute if the preview passes.

## Forces

- Agents optimize for coherent output, not correct output. A Kubernetes manifest that looks perfectly structured can still set `replicas: 0` on your production deployment
- LLM-as-judge is too slow and too expensive to gate every tool call. You need something faster
- Rollback (compensation) is always more expensive than prevention. Un-sending 10,000 emails is impossible; previewing the send is free
- Confidence and correctness are decorrelated. The agent's certainty about a bad action is indistinguishable from its certainty about a good one
- The window between "model decided" and "tool executed" is the only place where you can catch the mistake without paying the cost

## The move

**Three-layer dry-run gate:**

**Layer 1 — Schema & Format Verification (deterministic, <1ms)**

Before the tool executes, the agent generates a *preview* of the call with parameter values filled in. Run schema validation, type checks, and domain-range checks against the preview.

```python
import re
from typing import Any

def dry_run_guard(tool_name: str, params: dict[str, Any]) -> tuple[bool, str]:
    """Fast pre-execution gate. Returns (pass, reason)."""
    
    # 1. Schema validation — does it match the tool's JSON schema?
    schema = TOOL_SCHEMAS[tool_name]
    for required in schema.get("required", []):
        if required not in params:
            return False, f"missing required field: {required}"
    
    # 2. Domain range checks — catch obviously wrong values
    if tool_name == "update_k8s_deployment":
        replicas = params.get("replicas", 0)
        if replicas == 0:
            return False, "replicas=0 would take service offline"
        if replicas > schema["max_replicas"]:
            return False, f"replicas={replicas} exceeds max {schema['max_replicas']}"
    
    if tool_name == "send_email":
        recipients = params.get("recipients", [])
        if len(recipients) > schema["max_batch_size"]:
            return False, f"batch size {len(recipients)} exceeds limit {schema['max_batch_size']}"
        if not params.get("dry_run"):
            return False, "send_email requires dry_run=true on first preview"
    
    # 3. Pattern guards — regex on string fields
    if tool_name == "run_sql":
        query = params.get("query", "")
        dangerous = re.compile(r"\b(DROP|DELETE FROM|TRUNCATE)\b", re.IGNORECASE)
        if dangerous.search(query):
            return False, f"dangerous SQL keyword detected: {dangerous.findall(query)}"
    
    return True, "approved"

def execute_with_guard(tool_name: str, params: dict[str, Any]) -> dict:
    allowed, reason = dry_run_guard(tool_name, params)
    if not allowed:
        raise ToolExecutionBlocked(f"dry-run failed: {reason}")
    return execute_tool(tool_name, params)
```

**Layer 2 — Sandbox Execution (<100ms, cost ~$0.001)**

For tools where schema checks aren't enough, run the action in a sandbox and inspect the result before the real call. Database queries return zero rows. File writes create a temp file. HTTP calls hit a mock endpoint. The agent sees what would happen without the side effect landing.

```python
import subprocess
import tempfile
import json

def sandbox_db_preview(query: str, db: str) -> dict:
    """Run the SQL in a read-only sandbox. Return result summary."""
    if re.search(r"\b(INSERT|UPDATE|DELETE|DROP)\b", query, re.IGNORECASE):
        # Clone DB to temp, run mutation against clone, diff
        with tempfile.TemporaryDirectory() as tmpdir:
            clone = f"{tmpdir}/clone.db"
            subprocess.run(["sqlite3", db, f".backup {clone}"])
            result = subprocess.run(
                ["sqlite3", clone, query],
                capture_output=True, text=True
            )
            return {"rows_affected": result.stdout.strip(), "error": result.stderr.strip()}
    else:
        # Read-only: run against clone, inspect result size
        with tempfile.TemporaryDirectory() as tmpdir:
            clone = f"{tmpdir}/clone.db"
            subprocess.run(["sqlite3", db, f".backup {clone}"])
            result = subprocess.run(
                ["sqlite3", clone, query],
                capture_output=True, text=True
            )
            rows = [r for r in result.stdout.strip().split("\n") if r]
            return {"row_count": len(rows), "preview": rows[:5]}

def sandbox_file_preview(path: str, content: str) -> dict:
    """Preview a file write without touching the real path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        preview_path = f"{tmpdir}/preview_{Path(path).name}"
        Path(preview_path).write_text(content)
        return {
            "preview_path": preview_path,
            "size_bytes": Path(preview_path).stat().st_size,
            "can_read": True
        }
```

**Layer 3 — Human-in-the-Loop Escalation Gate**

For Tier-3 (destructive) actions that Layer 1 rejects or that have ambiguous sandbox results, escalate to a human with a structured diff of what will change.

```python
def escalation_gate(tool_name: str, params: dict[str, Any], agent_session_id: str):
    """For high-risk actions, surface to human before execution."""
    risk_level = classify_destructiveness(tool_name, params)
    
    escalation_map = {
        "low":    (False, None),           # auto-execute
        "medium": (True,  "slack_review"),  # async Slack approval
        "high":   (True,  "sync_approval"), # synchronous blocking
        "critical": (True, "pagerduty"),   # on-call engineer required
    }
    
    escalate, channel = escalation_map[risk_level]
    if escalate:
        send_approval_request(
            channel=channel,
            tool=tool_name,
            params_sanitized=sanitize_params(params),
            session_id=agent_session_id,
            preview=generate_human_readable_diff(tool_name, params)
        )
        await blocking_approval(timeout_seconds=300)
    
    return execute_with_guard(tool_name, params)
```

**Destructiveness Classification (before connecting any MCP server):**

```python
TOOL_RISK_TIERS = {
    # Tier 0 — Public read (auto-approve with schema validation)
    "search_public_docs": "low",
    "get_weather": "low",
    
    # Tier 1 — Private read (require session identity, log access)
    "read_tickets": "medium",
    "query_internal_docs": "medium",
    
    # Tier 2 — Write (require dry-run sandbox, manual escalation on batch > N)
    "send_email": "medium",        # batch size gates escalation
    "update_config": "medium",
    "create_record": "medium",
    
    # Tier 3 — Destructive (require sandbox preview, human gate on threshold)
    "delete_records": "high",
    "run_sql": "high",            # SQL injection + data loss
    "delete_file": "high",
    "update_k8s_deployment": "high",
    
    # Tier 4 — Infra-critical (always escalate, never auto-execute)
    "modify_firewall": "critical",
    "drop_database": "critical",
    "revoke_credentials": "critical",
}
```

## Receipt

> Verified 2026-07-03 — Pattern synthesized from: SystemSharding (March 2026) dry-run/rollback article, Zylos AI agent observability post (April 2026), and BlueRock scan data (12,000+ MCP servers, 42% command injection prevalence). The three-layer gate (schema → sandbox → human) is the standard production pattern emerging across these sources. Specific code above is my own implementation based on described interfaces.

## See also

- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — the interception layer; this is the preview *before* interception
- [S-352 · Agentic Compensation Keys](s352-agentic-compensation-keys.md) — rollback is post-failure; dry-run is prevention
- [F-195 · Outcome Delivery Verification](f195-outcome-delivery-verification.md) — verifies delivery; this verifies *planned* action before delivery
- [S-56 · Pre-Flight Token Check](s56-preflight-token-check.md) — pre-flight for context; this is pre-flight for execution
- [F-12 · LLM-as-a-Judge](f12-llm-as-a-judge.md) — LLM-based verification is too slow per-call; dry-run gates at Layer 1
