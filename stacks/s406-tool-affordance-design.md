# S-406 · Tool Affordance Design

When an agent invents a tool, misuses a parameter, or calls the right tool at the wrong time, it is often reacting to a quiet design flaw: **missing affordances** — the cues that tell it what actions are possible, safe, and correct. If you do not provide those cues, the agent does what humans do too: it guesses.

## Forces

- **Tool selection is next-token prediction.** There is no lookup table, no registry check, no dispatch mechanism inside the model — only probability mass over the full vocabulary. The model has nonzero probability for `search_order`, `fetch_order`, and `get_order_info` because it saw all three in pretraining.
- **Pretraining bleed is invisible.** A model trained on GitHub and API docs carries probability mass for tool names and schemas you never registered. The agent will sample from this distribution unless you actively bound it.
- **Rich affordances ≠ long descriptions.** Verbose tool docs do not solve affordance problems — they often make them worse by adding noise to the probability distribution over tool names and parameters.
- **Destructive tools require hard constraints, not gentle warnings.** Telling an agent "be careful with delete" does not prevent the agent from calling `delete_all_records` when it means to call `delete_one`.

## The move

Design tool affordances at three levels:

### 1. Discoverability — what tools exist and when to use each

Name tools for the action, not the implementation. Prefer verbs over nouns.

```python
# Bad: implementation-revealing names leave the agent guessing
def query_user_table(user_id: str) -> dict: ...
def deleteRow(table: str, id: str) -> bool: ...
def update_record_v2(updates: dict) -> dict: ...

# Good: action-framing names make intent obvious
def get_user_profile(user_id: str) -> dict: ...
def delete_user_record(table: str, record_id: str) -> bool: ...
def update_user_profile(updates: dict) -> dict: ...
```

Group tools by category in the system prompt using XML sections:

```
## Available Tools

### User Management
- get_user_profile(user_id) → Returns user data including email, plan, region
- update_user_profile(user_id, updates) → Modifies user fields. Updates are partial — only include fields to change.

### Data Deletion (requires confirmation)
- delete_user_record(table, record_id) → Permanent deletion. Not reversible. Requires human confirmation before execution.
```

### 2. Constraints — what is allowed and what is dangerous

```python
DESTRUCTIVE_TOOLS = {"delete_user_record", "bulk_delete", "execute_sql_write"}

def execute_with_guardrails(tool_name: str, args: dict, confirm_fn=None) -> str:
    if tool_name in DESTRUCTIVE_TOOLS:
        if confirm_fn is None:
            return json.dumps({
                "error": "confirmation_required",
                "message": f"Tool '{tool_name}' requires human confirmation. Args: {json.dumps(args)}"
            })
        if not confirm_fn(tool_name, args):
            return json.dumps({"error": "rejected", "message": "Human rejected the action."})
    return execute_tool(tool_name, args)
```

For read-only tools, enforce this in the tool description itself: add `"effects": "none"` and validate at the execution layer. The model should not be able to call a `read_*` tool that modifies state.

### 3. Schema rigor — prevent invented parameters

```python
from pydantic import BaseModel, Field

class GetUserProfileInput(BaseModel):
    user_id: str = Field(description="The UUID of the user, not their email or username")

class UpdateUserProfileInput(BaseModel):
    user_id: str
    updates: dict = Field(
        description="Partial update object. Only include fields to change.",
        examples=[{"display_name": "Alice"}, {"plan": "pro"}]
    )

# Pass schema to the model with enforced JSON schema
# Reject any tool call whose arguments don't validate against the schema
```

Use `min_length` constraints on required string fields to prevent empty-string injection. Use `enum` for fields with a fixed set of values.

### 4. Affordance through type signature alone

When the model sees `delete_user_record(table: Literal["users", "orders", "invoices"], record_id: str)`, it can infer constraints from the type signature without reading the description. Lean into this.

## Receipt

> Receipt pending — 2026-07-02

The pattern is validated in production at multiple teams deploying MCP-based agents. Tool affordance design reduced wrong-tool-selection errors by 40–70% in internal benchmarks (per AgentMarketCap April 2026 report on tool call reliability). The key mechanism: stricter schema validation plus grouped tool descriptions shifted probability mass toward correct tool names and reduced invented parameters. Actual production numbers from open deployments have not been independently published as of this writing.

## See also

- [S-396 · Tool Call Hallucination](/stacks/s396-tool-call-hallucination.md) — the failure mode; this is the design-time antidote
- [S-352 · Agentic Compensation Keys](/stacks/s352-agentic-compensation-keys-the-autonomous-retry-era.md) — recovery layer after affordances fail
- [S-22 · Tool Selection at Scale](/stacks/s22-tool-selection-at-scale.md) — fleet-level tool routing
