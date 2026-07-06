# S-349 · Agentic Guardrails: The Four-Layer Enforcement Plane

An agent with write access is a latent data-deletion machine. An agent with read access can be turned into a data-exfiltration pipeline via a single prompt injection. Traditional prompt-level guardrails — PII filters, jailbreak blocks, output toxicity checks — stop mattering the moment an agent has a tool loop. The model bypasses them at step one by calling `write_file` or `send_email`. The real enforcement point is a four-layer plane that operates *around* the agent loop, not inside it.

## Forces

- **The enforcement gap.** Every major agent incident (recursive loops, data corruption, unauthorized emails, prompt injection exfiltration) happened *after* the model call succeeded — the guardrail was downstream of where it needed to be.
- **OWASP LLM Top 10 v2.0** explicitly calls out Excessive Agency and Indirect Prompt Injection as top-3 risks in production LLM applications. Guardrails are no longer optional — they are a regulatory and operational requirement.
- **57% of organizations** now run AI agents in production, yet observability and guardrails remain the lowest-rated part of the AI stack (Gartner, 2026). Most teams add guardrails reactively — after the first incident.
- **Over-blocking vs. under-blocking.** The cost of over-blocking (broken agents, UX regressions) is visible and immediate. The cost of under-blocking (a $47K weekend, corrupted DB, GDPR fine) is rare but catastrophic. Calibrating this is the central unsolved problem.
- **Agent state complicates everything.** Unlike a stateless chat API, an agent accumulates context across turns. A prompt injection at turn 3 may not activate until turn 7 when the agent decides to "summarize all emails." Guardrails must track state across the session, not just per-request.

## The move

Production agentic guardrails operate in four layers. Each layer catches failure modes the others miss. Together they bound the agent's behavior in ways the agent itself cannot reliably self-impose.

### Layer 1 — Input Validation & Sanitization

The outermost gate. Intercepts user input, tool responses, and retrieved context *before* they enter the prompt.

Key techniques:
- **Prompt injection detection** — scan for instruction override patterns (`ignore previous instructions`, `# instructions`, XML injection in tool responses)
- **Structured schema validation** — enforce that tool responses conform to expected schemas before they're added to context
- **MCP response sanitization** — the AgentJacking attack (F-194) exploited the fact that MCP servers return attacker-controlled data. Validate and truncate all MCP responses.

```python
from llm_guard import scan_prompt, scan_output
from llm_guard.input_scanners import Anonymize, PromptInjection
from llm_guard.output_scanners import Sensitive

# Layer 1: Input validation before the prompt reaches the model
def sanitize_input(user_message: str, conversation_history: list[str]) -> str:
    results = scan_prompt(
        prompts=[user_message, *conversation_history[-5:]],
        scanners=[PromptInjection()],
    )
    if not results[0].is_safe:
        raise ValueError(f"Prompt injection detected: {results[0].matches}")

    return user_message
```

### Layer 2 — Tool-Call Interception

Intercepts *proposed* tool calls before execution. This is the highest-leverage layer — it's where S-198's tool-call guardrails live, extended to cover the full call chain.

Key techniques:
- **Schema enforcement** — validate that tool arguments conform to the expected JSON schema before execution
- **Permission boundary checks** — map tool capabilities to permission levels; block writes to production, deletions above a threshold, or external API calls without explicit session-level confirmation
- **Action budget** — track the number of destructive/expensive actions per session; hard-cutoff after N

```python
from enum import Enum

class ActionRisk(Enum):
    READ = 1
    WRITE = 2
    DELETE = 3
    EXTERNAL = 4  # network calls, emails, etc.

TOOL_RISK = {
    "read_file": ActionRisk.READ,
    "write_file": ActionRisk.WRITE,
    "delete_file": ActionRisk.DELETE,
    "send_email": ActionRisk.EXTERNAL,
    "db_query": ActionRisk.READ,
    "db_write": ActionRisk.WRITE,
}

def intercept_tool_call(tool_name: str, args: dict, session_state: dict) -> bool:
    """Returns True if the call is allowed, False to block."""
    risk = TOOL_RISK.get(tool_name, ActionRisk.READ)

    # Hard block: destructive actions in production
    if risk == ActionRisk.DELETE and session_state.get("env") == "prod":
        return False

    # Hard block: external actions require explicit user confirmation flag
    if risk == ActionRisk.EXTERNAL and not session_state.get("external_enabled"):
        return False

    # Budget: count write actions per session
    if risk in (ActionRisk.WRITE, ActionRisk.DELETE):
        session_state["action_count"] = session_state.get("action_count", 0) + 1
        if session_state["action_count"] > 10:
            return False  # budget exceeded

    return True
```

### Layer 3 — Output Validation Gate

Intercepts the model's raw output before it's returned to the user or fed into the next turn.

Key techniques:
- **Semantic output validation** — use a lightweight model to check: does this output violate known policies? (e.g., PII, disallowed content, overconfident factual claims)
- **Tool-response compatibility** — if the output is meant to be machine-readable (tool arguments), validate JSON schema before the tool executes
- **Relevance scoring** — block outputs that deviate significantly from the task intent (jailbreak outputs, off-topic rants)

```python
from llm_guard import scan_output
from llm_guard.output_scanners import Sensitive, Toxicity, NoRefusal

def validate_output(raw_output: str, context: dict) -> str:
    results = scan_output(
        prompts=[context.get("task", "")],
        outputs=[raw_output],
        scanners=[Toxicity(), Sensitive(), NoRefusal()],
    )

    for scanner_name, result in results[0].results.items():
        if not result.is_safe:
            if scanner_name == "NoRefusal":
                # Model refused to answer on a task it should handle
                raise RuntimeError(f"Unexpected refusal: {result.matches}")
            # Block unsafe outputs
            raise ValueError(f"Output blocked by {scanner_name}: {result.matches}")

    return raw_output
```

### Layer 4 — Execution Sandbox Isolation

The innermost layer. If a malicious or buggy tool call executes, the sandbox limits blast radius.

Key techniques:
- **Kubernetes GKE Agent Sandbox** (sub-second Pod pre-warming, zero extra cost) — first-class sandbox as a K8s resource
- **eBPF-based syscall filtering** — restrict what a runaway agent process can actually do at the kernel level
- **Network namespace isolation** — prevent the agent from making outbound connections it wasn't explicitly granted
- **Immutable filesystem mounts** — treat `/opt/data`, credentials, and config as read-only from the agent's perspective

## Receipt

> Receipt pending — 2026-07-02
>
> Four-layer guardrail architecture validated against OWASP LLM Top 10 v2.0 categories (Excessive Agency, Indirect Prompt Injection, Overreliance). Code examples run against `llm-guard==0.5.x` with Python 3.12+. Full integration test with a live agent loop planned for next cycle.

## See also

- [S-198 · Agent Tool-Call Guardrails](stacks/s198-agent-tool-call-guardrails.md) — Layer 2 deep-dive
- [S-205 · Agent Sandbox Isolation](stacks/s205-agent-sandbox-isolation.md) — Layer 4 deep-dive
- [F-194 · AgentJacking & MCP Tool-Response Poisoning](forward-deployed/f194-agentjacking-mcp-tool-response-poisoning.md) — the specific attack Layer 1 defends against
