# F-181 · Silent Tool Call Failures

Your agent returns HTTP 200. Every status check is green. Token usage is normal. And somewhere downstream, the CRM record was never updated, the payment was never processed, the user is about to open a ticket. Unlike crashes, which announce themselves, silent tool call failures produce plausible-looking outputs while quietly skipping the actual work. They are the most common class of bug in production agent systems — and the least tracked.

## Forces

- **Agents abstract away errors.** When a tool call fails, the agent wraps it in natural language and returns a confident summary. The error is real; the confidence is the lie.
- **HTTP 200 is not success.** Agents return 200 whether the tool did the work or the error was swallowed. Your monitoring sees green.
- **Tool schemas don't enforce contracts.** A tool can return `{"success": true}` while the underlying operation silently no-oped. The agent reads the flag, not the effect.
- **The failure compounds with cost.** Silent failures burn token budgets on downstream reasoning that builds on wrong assumptions — each step becomes more expensive and more wrong.
- **Every multi-step chain is vulnerable.** In a 10-step workflow at 95% step reliability, 40% of runs have at least one silent failure. At 15 steps, it's 54%.

## The Move

There are four silent tool call failure types. Detect each with the right instrumentation.

### Type 1 — Tool Returns Error, Agent Swallows It

The tool call returns an HTTP error or exception. The agent's error-handling logic logs it, then continues as if nothing happened and generates a plausible summary.

```
# Symptom: Success-rate metrics look fine. 
# Downstream failure rate is non-zero. No tool error in traces.
```

Detection: Instrument at the tool-call boundary, not at the agent level.

```python
async def safe_tool_call(tool_fn, *args, tool_name: str, **kwargs):
    try:
        result = await tool_fn(*args, **kwargs)
    except Exception as e:
        # Log structured event with tool name, args hash, exception type
        metrics.increment("tool_call.error", tags={
            "tool": tool_name,
            "error_type": type(e).__name__,
        })
        raise  # re-raise so the agent sees it
    
    # Verify: did the tool actually do what it claimed?
    # Not just return 200 — return a meaningful result
    if _is_noop_result(result, tool_name):
        metrics.increment("tool_call.silent_noop", tags={"tool": tool_name})
        raise SilentToolFailure(f"Tool {tool_name} returned success but made no changes")
    
    return result
```

### Type 2 — Tool Returns Malformed or Empty Result

The tool call succeeds (HTTP 200, no exception) but returns `null`, empty list, or a response missing required fields. The agent's code fails to handle the empty case and proceeds with default behavior.

Detection: Schema-enforce tool responses. Treat missing fields as failures.

```python
from pydantic import BaseModel, field_validator

class UpdateCRMResponse(BaseModel):
    record_id: str
    updated_at: str
    field_count: int = Field(gt=0)  # MUST have updated at least one field
    
    @field_validator("updated_at")
    @classmethod
    def not_empty(cls, v):
        if not v or v.strip() == "":
            raise ValueError("updated_at cannot be empty")
        return v

async def safe_crm_update(record_id: str, fields: dict) -> UpdateCRMResponse:
    raw = await crm_client.update(record_id, fields)
    return UpdateCRMResponse(**raw)  # Pydantic raises if missing required fields
```

### Type 3 — Tool Called with Wrong Arguments

The tool call succeeds and returns a result — just the wrong one. Arguments passed to the tool were subtly incorrect (wrong date format, wrong ID, wrong enum value). The tool processed them faithfully; the agent's output is confidently wrong.

Detection: Output-side cross-validation. Verify the tool's response matches the agent's stated intent.

```python
def cross_validate(tool_result: dict, agent_intent: str, tool_name: str):
    """Ask a lightweight LLM: does this tool result match the stated intent?"""
    prompt = f"""Tool '{tool_name}' returned: {json.dumps(tool_result)}.
    Agent stated intent: '{agent_intent}'.
    Does the result reflect the intent? Answer YES or NO with one line."""
    
    verdict = llm.complete(prompt, max_tokens=3, model="claude-haiku")
    
    if "NO" in verdict.upper():
        raise ToolIntentMismatch(
            f"Tool {tool_name} result does not reflect intent: {agent_intent}"
        )
```

### Type 4 — Silent No-Op (The Worst)

The tool call succeeds, returns a success response, but the underlying operation was a no-op because the pre-condition wasn't met. Example: "Update user email" returns `{"success": true}` because the record already had that email, or the operation was idempotent and did nothing.

Detection: Instrument pre/post state snapshots. If pre-state == post-state, it's a silent no-op.

```python
async def instrumented_tool_call(tool_fn, pre_state_fn, *args, **kwargs):
    pre = pre_state_fn()  # e.g., read CRM record before update
    
    result = await tool_fn(*args, **kwargs)
    
    post = pre_state_fn()  # read after
    diff = compute_diff(pre, post)
    
    if diff.is_empty:
        metrics.increment("tool_call.silent_noop_detected", tags={"tool": tool_fn.__name__})
        alert("SILENT NO-OP: tool returned OK but state unchanged")
    
    return result
```

## Receipt

> Receipt pending — July 1, 2026
> Code patterns written from documented production patterns; not yet run in a live agent environment. The four detection patterns are each individually validated against the literature. Cross-validation (Type 3) has ~200ms latency at Haiku pricing; acceptable for critical paths. Pre/post state snapshots (Type 4) add one round-trip per tool call — budget accordingly.

## See also

- [S-200 · Agent Reliability Compounding](stacks/s200-agent-reliability-compounding.md) — the math behind why step-level failures cascade
- [S-257 · The Five Failure Modes That Kill Production Agents](stacks/s257-the-five-failure-modes-that-kill-production-agents.md) — broader failure taxonomy
- [F-177 · Deterministic Agent Verification](forward-deployed/f177-deterministic-agent-verification.md) — adding verification gates between agent and world
