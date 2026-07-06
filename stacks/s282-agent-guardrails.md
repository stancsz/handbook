# S-282 · Agent Guardrails

Your agent has one job. A code-freeze maintenance task. It executes `DROP DATABASE`. No one told it not to. This is the gap between what an agent *can* do and what it *should* do. Guardrails close that gap.

## Forces

- **Agents have agency.** Unlike chatbots, agents execute real actions — write files, send emails, hit APIs. A bad answer is correctable. A dropped table is not.
- **System prompts are polite suggestions, not security boundaries.** Models follow instructions *until they don't* — which is exactly when stakes are highest (adversarial input, ambiguous intent, unexpected context).
- **The attack surface scales with tool access.** Every tool an agent can call is a potential exploitation vector. Prompt injection through user input, tool result poisoning, indirect injection via browsing — OWASP ranks prompt injection #1 among LLM vulnerabilities.
- **Guardrails that work in demos fail in production.** Measured bypass rates: regex input filters catch 30–40% of attacks; LLM-based classifiers catch 89–94%; a three-layer approach reaches 99.1%.
- **Latency is a constraint.** Heavy guardrail pipelines add 200–500ms per call. Production guardrails must be fast enough to not become a bottleneck.

## The move

Defense in depth across three independent layers. Each layer catches what the previous one misses. None is sufficient alone.

**Layer 1 — Input validation (before the model sees the prompt)**

Block or rewrite malicious input before it reaches the model. Two complementary approaches:

- **Pattern matching (fast, incomplete):** Regex/denylist for known attack signatures — `[INST]`, `</s>`, `system`, suspicious URL patterns. Catches 30–40% of naive attacks. Zero LLM latency overhead.
- **LLM-based classifier (slower, accurate):** A lightweight classifier (e.g., `llm-guard`, a fine-tuned small model) scores the input for injection likelihood. Catches 89–94% of sophisticated attacks.

```python
import llm_guard
from llm_guard.input_scanners import PromptInjection, SensitiveData

scanner = llm_guard.InputScannerChain([
    PromptInjection(threshold=0.5),
    SensitiveData(),
])

# Run synchronously before sending to agent
is_safe, risk_score, validated_input = scanner.scan(user_input)
if not is_safe:
    raise ValueError(f"Input blocked: {risk_score}")
```

**Layer 2 — Architectural containment (constrain what the model can do)**

Even clean input can produce dangerous outputs. Contain the agent's capability surface:

- **Tool allowlisting.** The agent can only call explicitly approved tools. Deny-by-default. Not "which tools should I block" but "which tools may I use."
- **Permission boundaries.** Tools operate at minimum necessary privilege. The DB tool gets read-only access unless the task explicitly requires writes.
- **Confirmation hooks.** For destructive actions (`DELETE`, `DROP`, `SEND_EMAIL`, `POST`), insert a human-in-the-loop checkpoint. The agent proposes; a human approves.
- **Output schema constraints.** Structure the agent's action output with a strict schema that prevents arbitrary command strings from leaking into tool arguments.

```python
from pydantic import BaseModel, Field

class ToolCall(BaseModel):
    tool_name: str = Field(
        pattern="^(read_file|search|write_summary)$"  # allowlist
    )
    arguments: dict = Field(default_factory=dict)
    reason: str = Field(max_length=200)  # audit trail
    requires_confirmation: bool = Field(default=False)

# Validation at call time — rejects any tool not on the allowlist
ToolCall.model_validate(agent_decision)
```

**Layer 3 — Output validation (before output reaches the user or downstream system)**

The model produced a response. Validate it before delivery:

- **Content safety scan:** Classify output for harmful content, PII, toxic language. `llm-guard`'s output scanners check for this.
- **Schema validation:** Confirm the output conforms to expected structure. Reject non-conforming responses — don't try to fix them, reject and retry with a tighter prompt.
- **PII redaction:** Ensure the agent's response doesn't leak personal data it retrieved but shouldn't expose.
- **Circuit breaker:** Track failure rates. If an agent's error rate exceeds a threshold (e.g., 5% in a 10-minute window), pause the agent and alert.

```python
from llm_guard.output_scanners import Toxicity, PII, SensitiveData

output_scanner = llm_guard.OutputScannerChain([
    Toxicity(),
    PII(),
])

is_safe, risk_score, sanitized_output = output_scanner.scan(raw_output)
if not is_safe:
    # Log the incident, return a safe fallback, alert the team
    logger.error(f"Output blocked: {risk_score} — {sanitized_output}")
    return FALLBACK_RESPONSE
```

**Red-teaming as continuous practice**

Static guardrails degrade. Build a red-team pipeline that runs weekly:

1. Curate an adversarial test set (prompt injection patterns, jailbreak attempts, role confusion attacks)
2. Run it against every guardrail layer
3. Measure catch rate per layer
4. Update the test set with new attack patterns found in production logs

## Receipt

> Receipt pending — July 1, 2026

## See also

- [S-280 · MCP Server Governance](s280-mcp-server-governance.md) — tool-level security for the MCP protocol layer
- [S-281 · Agent Evaluation Is the Missing Layer Nobody Builds Until Production Breaks](s281-agent-evaluation-the-layer-nobody-builds-until-production-breaks.md) — measuring whether guardrails actually work
- [F-182 · MCP Server CVE Supply Chain Exploits](f182-mcp-server-cve-supply-chain-exploits.md) — what happens when tool security fails
