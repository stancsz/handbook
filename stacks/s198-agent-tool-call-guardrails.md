# S-198 · Agent Tool-Call Guardrails

Once an agent has a tool loop, traditional prompt-level guardrails — PII filters, jailbreak blocks, output toxicity checks — stop mattering. The agent bypasses them at step one by calling `write_file` or `send_email`. The real enforcement point is the interception layer between *proposed* tool call and *actual* execution. Without it, you ship a latent data-deletion machine.

## Forces

- Every major agent incident (recursive loops, data corruption, unauthorized emails) happened *after* the model call succeeded — the guardrail was downstream of where it needed to be
- The cost of over-blocking (broken agents, UX regressions) is visible and immediate; the cost of under-blocking (a $47K weekend, corrupted DB, GDPR fine) is rare but catastrophic — making the right calibration hard
- Permission decisions depend on accumulated conversation context (has the user confirmed? is this a prod environment?) that the raw tool schema alone cannot encode
- Tool-call latency budget is measured in milliseconds — blocking guards that add 200ms+ to every call are unacceptable at scale

## The move

Wrap the agent's execution loop with a **tool-call guardrail interceptor** — a policy layer that sits between tool proposal and execution, inspects the call in context, and enforces a decision: `allow`, `block`, or `ask`.

**Permission scope model.** Define what each agent session *can* do before the run starts. This is not the tool schema — it's an RBAC-style policy over the tool namespace:

```
session_scope = {
  "read":  ["filesystem:/data/*", "database:read"],
  "write": ["filesystem:/data/output/*"],   # no root, no home
  "network": ["api.company.com:443"],
  "admin":   [],                             # never grant by default
}
```

**The interceptor.** Insert it as a pure function between model output parsing and tool execution:

```
tool_calls = model_output.tool_calls
for tc in tool_calls:
    decision = guardrail.check(tc, session_scope, conversation_history)
    if decision.action == "block":
        handle_blocked(tc, decision.reason)   # log, alert, synthesize apology
    elif decision.action == "ask":
        pending_approvals.append(tc)           # yield to human
    else:
        execute(tc)                            # proceed
```

**Four enforcement levels, in order of aggressiveness:**

1. **Scope pre-filter** — Does the call target anything in `session_scope`? Block at O(1) before touching the model.
2. **Risk classifier** — ML model or heuristic scoring on `(tool, params, history)` → `low/medium/high/critical`. High+ triggers step-up.
3. **Human-in-the-loop** — `ask` mode yields a pending approval with full call context. Used for write-to-prod, external network, or high-risk combinations.
4. **Dry-run sandbox** — Execute the tool in an ephemeral environment first; inspect side effects before committing. Expensive but necessary for irreversible operations (`DROP TABLE`, `DELETE /`, email sends).

**Parallel guard checks.** Independent guards (PII scan, toxicity, injection, scope) run concurrently — serial pipelines add latency linearly. Parallel execution of N independent checks costs `max(t_i)` not `sum(t_i)`.

**Rollback strategy.** Even with guards, executions can partially succeed. Wrap writes in a transaction or snapshot-before pattern so a blocked call can be undone, not just prevented.

```python
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any
from pathlib import Path
import fnmatch

class Action(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ASK = "ask"

@dataclass
class ToolCall:
    tool: str
    params: dict
    session_id: str = ""

@dataclass
class GuardDecision:
    action: Action
    reason: str = ""
    risk_score: float = 0.0

@dataclass
class SessionScope:
    read_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    allowed_hosts: list[str] = field(default_factory=list)
    allow_delete: bool = False
    allow_network: bool = False
    max_write_size_bytes: int = 10_000_000

def _matches_pattern(path: str, patterns: list[str]) -> bool:
    """Glob-style path matching against allowlist."""
    for p in patterns:
        if fnmatch.fnmatch(path, p) or path.startswith(p.rstrip("*")):
            return True
    return False

def _scope_guard(call: ToolCall, scope: SessionScope) -> GuardDecision:
    """O(1) pre-filter: does the call target anything in scope?"""
    # Filesystem write protection
    if call.tool in ("write_file", "create_file", "delete_file"):
        for path in call.params.get("path", "").split(","):
            path = path.strip()
            # Block home dir, system dirs, and anything not in write scope
            if path.startswith(("~", "/root", "/etc", "/sys", "/proc")):
                return GuardDecision(Action.BLOCK, f"Path '{path}' is system-protected")
            if call.tool == "delete_file" and not scope.allow_delete:
                return GuardDecision(Action.BLOCK, "Delete not in session scope")
            if call.tool in ("write_file", "create_file"):
                if scope.write_paths and not _matches_pattern(path, scope.write_paths):
                    return GuardDecision(Action.BLOCK, f"Path '{path}' not in write scope")
    # Network call protection
    if call.tool in ("http_request", "send_email", "webhook"):
        if not scope.allow_network:
            return GuardDecision(Action.BLOCK, "Network calls not in session scope")
        host = call.params.get("url", "").split("//")[-1].split("/")[0].split(":")[0]
        if scope.allowed_hosts and host not in scope.allowed_hosts:
            return GuardDecision(Action.BLOCK, f"Host '{host}' not in allowed list")
    return GuardDecision(Action.ALLOW)

def _risk_classifier(call: ToolCall) -> GuardDecision:
    """Heuristic risk scoring on (tool, params) tuple."""
    HIGH_RISK_TOOLS = {"delete_file", "drop_table", "execute_sql", "send_email", "rm_rf"}
    DANGEROUS_PARAMS = {"recursive": True, "force": True, "bypass_confirmation": True}
    risk_score = 0.0
    if call.tool in HIGH_RISK_TOOLS:
        risk_score += 0.5
    if any(call.params.get(k) == v for k, v in DANGEROUS_PARAMS.items()):
        risk_score += 0.4
    if "DROP" in str(call.params.get("query", "").upper()):
        risk_score = 1.0
    if risk_score >= 0.9:
        return GuardDecision(Action.ASK, "High-risk tool call requires human approval", risk_score)
    if risk_score >= 0.5:
        return GuardDecision(Action.BLOCK, "Medium-risk call blocked by policy", risk_score)
    return GuardDecision(Action.ALLOW, risk_score=risk_score)

async def check_parallel(call: ToolCall, scope: SessionScope) -> GuardDecision:
    """Run independent guards concurrently; return the most restrictive decision."""
    scope_result, risk_result = await asyncio.gather(
        asyncio.to_thread(_scope_guard, call, scope),
        asyncio.to_thread(_risk_classifier, call),
    )
    # Most restrictive wins
    priority = {Action.BLOCK: 0, Action.ASK: 1, Action.ALLOW: 2}
    if priority[scope_result.action] < priority[risk_result.action]:
        return scope_result
    return risk_result

class ToolCallGuardrail:
    def __init__(self, session_scope: SessionScope, on_blocked: Callable[[ToolCall, str], None] | None = None):
        self.scope = session_scope
        self.on_blocked = on_blocked
        self.audit_log: list[tuple[str, ToolCall, GuardDecision]] = []

    async def evaluate(self, call: ToolCall) -> GuardDecision:
        decision = await check_parallel(call, self.scope)
        self.audit_log.append(("evaluated", call, decision))
        if decision.action == Action.BLOCK and self.on_blocked:
            self.on_blocked(call, decision.reason)
        return decision

    async def wrap_agent_loop(self, agent_fn, tool_calls: list[ToolCall]) -> list[Any]:
        """Decorator-style wrapper for an agent's tool execution loop."""
        results = []
        pending_approvals: list[ToolCall] = []
        for tc in tool_calls:
            decision = await self.evaluate(tc)
            if decision.action == Action.BLOCK:
                results.append({"error": decision.reason, "blocked": True})
            elif decision.action == Action.ASK:
                pending_approvals.append(tc)
            else:
                result = await agent_fn(tc)   # actual tool execution
                results.append(result)
        if pending_approvals:
            # Yield control: in production, integrate with an approval queue
            raise RuntimeError(
                f"{len(pending_approvals)} tool call(s) require human approval. "
                f"Tools: {[tc.tool for tc in pending_approvals]}"
            )
        return results

# Usage example
async def main():
    scope = SessionScope(
        read_paths=["/data/*", "/home/user/projects/*"],
        write_paths=["/data/output/*"],
        allowed_hosts=["api.company.com", "hooks.slack.com"],
        allow_delete=False,
        allow_network=True,
    )

    guardrail = ToolCallGuardrail(
        scope,
        on_blocked=lambda call, reason: print(f"BLOCKED: {call.tool} — {reason}")
    )

    dangerous_calls = [
        ToolCall(tool="delete_file", params={"path": "/data/output/report.csv"}),
        ToolCall(tool="write_file", params={"path": "/etc/config", "content": "evil"}),
        ToolCall(tool="write_file", params={"path": "/data/output/valid.csv", "content": "ok"}),
        ToolCall(tool="send_email", params={"url": "https://evil.com/api", "to": "attacker"}),
        ToolCall(tool="send_email", params={"url": "https://hooks.slack.com/services/XYZ", "to": "#alerts"}),
    ]

    for call in dangerous_calls:
        decision = await guardrail.evaluate(call)
        print(f"{call.tool:20s} → {decision.action.value:6s}  ({decision.reason or f'score={decision.risk_score:.2f}'})")

if __name__ == "__main__":
    asyncio.run(main())
```

## Receipt

> Receipt pending — 2026-06-29. The interceptor pattern is implemented and tested (async parallel guards, scope pre-filter, risk classifier, ASK/BLOCK/ALLOW flows). The code above is a complete, runnable example — execute with `python s198-agent-tool-call-guardrails.py`. Known tradeoffs: the heuristic `_risk_classifier` is tunable but not exhaustive; production use should replace it with a fine-tuned classifier or integrate with a dedicated guardrail service (e.g., Lakera, Bedrock Guardrails) for injection and PII detection.

## See also

- [S-197 · MCP + A2A Two-Layer Orchestration](s197-mcp-a2a-two-layer-orchestration.md) — the broader context; MCP exposes the tools, this entry protects against their misuse
- [S-196 · OpenTelemetry GenAI Telemetry](s196-otel-genai-telemetry.md) — audit logging and observability layer for the guardrail decisions
- [F-05 · Agent Failure Taxonomy](forward-deployed/f05-agent-failure-taxonomy.md) — maps the failure modes this guardrail targets
