# S-396 · Tool Call Hallucination

You registered `get_order_status`. The agent calls `search_order`. You never registered `web_search` — the agent called it anyway, with full confidence. The tool ran in production for three days before anyone noticed it was querying a mock service that always returned "found."

This is not a prompt problem. The model is working exactly as designed: it generates tool calls the same way it generates text — by sampling from a probability distribution trained on internet-scale code, API docs, and tool-use examples. The pretraining probability mass for `search_order` exists. Your tool is named `get_order_status`. No router inside the model reconciles the gap.

## Forces

- **Tool selection is token prediction.** There is no lookup table, no registry check, no dispatch mechanism inside the model — only next-token probability over the full vocabulary
- **Pretraining bleed is invisible.** Models carry probability mass for tool names and parameter patterns from training data that don't match your actual registry
- **Schema mismatch compounds silently.** Even when the tool name is correct, parameter names (`user_id` vs `customer_id`) are generated, not looked up — wrong names pass schema validation if the type is right
- **Registered vs. unregistered tools are equally probable.** The model cannot distinguish a tool you defined from one it invented from training data
- **Mitigation costs are asymmetric.** Preventing hallucinations is cheaper than auditing their blast radius post-hoc

## The move

Three-layer defense: **schema anchoring**, **reliability calibration**, and **output gating**.

### Layer 1 — Schema Anchoring

Force tool names and parameter names into the model's probability distribution via in-context injection, not just tool definitions.

```python
# Bad: tool definition alone — model generates names from pretraining distribution
tools = [
    {"name": "get_order_status", "description": "Check order status."}
]

# Good: schema anchoring with enforced name + explicit disambiguation
tools = [
    {
        "name": "get_order_status",   # exact name — anchor it
        "description": "Check order status. "
                        "IMPORTANT: always use get_order_status. "
                        "Do NOT use search_order, find_order, or lookup_order — "
                        "these do not exist in this environment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID. Format: ORD-XXXXX. "
                                    "Use order_id, NOT orderId, NOT order_number."
                }
            },
            "required": ["order_id"]
        }
    }
]
```

The disambiguation sentence in the description shifts the probability mass toward the correct name. Xu et al. (arXiv:2412.04141) show this is part of **reliability alignment** — training the model to treat its tool registry as a hard constraint, not a suggestion.

### Layer 2 — Reliability Calibration

Use a held-out tool list to detect when the model invents tools. Run a probe before deployment:

```python
def detect_hallucinated_tools(agent, probe_tools: list[str]) -> dict[str, bool]:
    """Probe whether the agent will call tools that don't exist.
    
    probe_tools: list of tool names that DEFINITELY don't exist.
    If the agent calls any of these, it is hallucinating tool names.
    """
    hallucinations = {}
    for tool_name in probe_tools:
        response = agent.run(f"Check if the tool '{tool_name}' exists.")
        hallucinations[tool_name] = tool_name in response.tool_calls
    
    return hallucinations

# Example: model calls web_search even though it's not registered
# Result: {"web_search": True} → hallucinations detected
```

RelyToolBench (Xu et al., 2024) provides a structured benchmark for this: it measures **R_NTA** (Rate of Non-Tool-Appropriate calls) and **step localization accuracy** — how precisely you can identify which step in the trajectory was the hallucination.

### Layer 3 — Output Gating

Validate every tool call before execution against the registered registry:

```python
import functools

REGISTERED_TOOLS = {"get_order_status", "cancel_order", "issue_refund"}

def validated_tool_call(tool_name: str, arguments: dict) -> dict:
    """Gate every tool call against the registered registry."""
    if tool_name not in REGISTERED_TOOLS:
        return {
            "error": "unknown_tool",
            "tool_name": tool_name,
            "message": f"Tool '{tool_name}' is not registered. "
                       f"Registered tools: {sorted(REGISTERED_TOOLS)}"
        }
    
    # Proceed with actual tool execution
    return dispatch(tool_name, arguments)
```

This is the only layer that catches **all three hallucination types** — wrong name, wrong parameter, and unregistered tool — regardless of whether the error originated in the model's token generation or your tool wrapper.

## Taxonomy (from RelyToolBench)

| Type | Example | Detection |
|------|---------|-----------|
| **Tool Selection** | Calls `search_order` instead of `get_order_status` | Schema anchoring + output gating |
| **Tool Usage** | Passes `user_id` instead of `order_id` | Schema anchoring (param names in description) |
| **Unregistered Tool** | Calls `web_search` which doesn't exist | Output gating (registry check) |
| **Solvability** | Calls a tool when the task could be answered from context | Trajectory eval (I-014: process dimension) |

## See also

- [S-03 · Tool Use](s03-tool-use.md) — foundational tool definition
- [S-393 · Tool Output Semantic Verification](s393-tool-output-semantic-verification.md) — the sibling problem: tool output can also be wrong
- [S-385 · Agent Trajectory Evaluation: Process vs. Outcome](s385-agent-trajectory-evaluation-process-vs-outcome-scoring.md) — tool-selection is a key process-evaluation dimension
- [S-365 · MCP Supply Chain](s10-mcp.md) — MCP tool registries are the new attack surface for tool-call hallucination

## Receipt

> Receipt pending — 2026-07-02
> Tool call hallucination taxonomy from Xu et al., arXiv:2412.04141 (Reliability Alignment / RelyToolBench). Schema anchoring pattern drawn from the paper's description alignment technique. Output gating pattern is a standard registry validation approach. Probe-based detection (Layer 2) is a practical implementation of the R_NTA metric described in the paper. Real-world example (bank agent, wrong parameter names) drawn from Kumar, Medium (Feb 2026). Real deployment case (refund agent, non-existent tool) from Salman Qazi blog (June 2026).
