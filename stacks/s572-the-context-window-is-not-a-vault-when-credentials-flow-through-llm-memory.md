# S-572 · The Context Window Is Not a Vault — When Credentials Flow Through LLM Memory

Your agent holds a Stripe API key, an OAuth token, and a database password. It passes them between tool calls — appending each to the next prompt. The LLM's context window is the shared memory. This is not a theoretical risk. It is the standard architecture of most agentic systems, and it creates an aggregation point that no amount of per-tool access control can protect.

## Situation

An agent acting as a financial operations assistant needs Stripe (to issue refunds), Salesforce (to log the dispute), and Postgres (to update the customer record). Each integration requires a credential. In a traditional application, these credentials live in a secrets manager, are injected at runtime, and never appear in application logic. In an agentic system, the LLM orchestrates the workflow — so the credentials pass through the context window, are embedded in tool-result summaries, and may surface in model outputs that get logged, stored, or passed to downstream agents.

GitGuardian's 2026 State of Secrets Sprawl report found over 24,000 unique secrets exposed in MCP configuration files on public GitHub, including 2,100+ confirmed valid credentials. Of organizations deploying AI agents in production, 25.4% still use hardcoded credentials for tool access. Only 21.9% treat agents as independent identity-bearing entities. The average time to identify a credential breach: 292 days.

## Forces

- **Agents aggregate credentials.** A single compromised agent accumulates permissions across every tool it calls — the attack surface is the union, not the average, of those permissions. One hijack reaches everything the agent can reach.
- **Context windows are logged.** Every prompt and completion is typically captured for observability, debugging, or fine-tuning. Credentials embedded in context are now in your log store, your eval dataset, and potentially your training data.
- **Tool results become prompts.** The output of one tool call becomes part of the next prompt. If a tool response includes a credential or sensitive token, it propagates forward until the next context compaction or session end.
- **Agents mint credentials at runtime.** Unlike static service accounts, agents may generate API keys, OAuth tokens, or scoped sessions dynamically — creating credentials that never existed in your secrets manager to begin with.
- **NHI (Non-Human Identity) ratio is 144:1.** Large enterprises now have 144 non-human identities for every human identity. Most IAM programs don't know how many agent identities they have, let alone what each one can access.

## The move

Three layers: **vault-gated credential injection**, **context sanitization**, and **NHI governance**.

### Layer 1 — Credential injection at call time, never at prompt time

Never embed credentials in system prompts or tool descriptions. Instead, inject them at the transport layer when the tool call fires.

```python
import httpx
from typing import Any

class VaultGatedToolCaller:
    """Credentials injected at call time — never enter the context window as strings."""

    def __init__(self, vault_addr: str, role: str):
        self.vault_addr = vault_addr
        self.role = role  # e.g. "stripe-refund-agent", "crm-dispute-logger"

    def call_tool(self, tool_name: str, params: dict[str, Any]) -> dict:
        # Fetch creds fresh from Vault — scoped to this tool, TTL-enforced
        token = self._fetch_ephemeral_token(tool_name)
        # WIPE from memory after call — don't let it persist in agent memory
        credential = self._fetch_secret(tool_name, token)
        try:
            result = self._execute(tool_name, params, credential)
        finally:
            # Explicit wipe from any local state the LLM can read back
            credential = None
        return result

    def _fetch_ephemeral_token(self, tool_name: str) -> str:
        # Vault Dynamic Secrets: mint a short-lived token per call
        resp = httpx.post(
            f"{self.vault_addr}/v1/identity/oidc/token",
            json={"role": f"{self.role}-{tool_name}"},
            headers={"X-Vault-Token": os.environ["VAULT_AGENT_TOKEN"]},
        )
        resp.raise_for_status()
        return resp.json()["data"]["token"]  # TTL: 60–300s

    def _fetch_secret(self, tool_name: str, token: str) -> str:
        resp = httpx.get(
            f"{self.vault_addr}/v1/{tool_name}/creds/{self.role}",
            headers={"X-Vault-Token": token},
        )
        return resp.json()["data"]
```

### Layer 2 — Sanitize tool results before they re-enter context

Tool outputs that touch credentials must be stripped before the agent sees them again.

```python
import re

CREDENTIAL_PATTERNS = [
    re.compile(r'(sk|pk|api|token|secret|pass|key)["\s:=]+["\'][^"\']{8,}["\']', re.I),
    re.compile(r'Bearer\s+[A-Za-z0-9_.-]{20,}'),
    re.compile(r'session_id["\s:=]+["\'][^"\']{16,}["\']', re.I),
]

def sanitize_tool_result(raw: str, tool_name: str) -> str:
    """Remove credentials from tool results before they enter the LLM prompt."""
    # Some tools return structured data with embedded tokens — redact
    # the token fields but keep the schema
    sanitized = raw
    for pattern in CREDENTIAL_PATTERNS:
        sanitized = pattern.sub(r'\1[REDACTED]', sanitized)
    # For API responses that include idempotency keys or request IDs
    # that act as bearer tokens in follow-up calls — mask those too
    return sanitized

# Integration with the tool call pipeline
original_call = agent.call_tool
def sanitizing_call(tool_name, params):
    result = original_call(tool_name, params)
    result["output"] = sanitize_tool_result(result["raw_output"], tool_name)
    return result
agent.call_tool = sanitizing_call
```

### Layer 3 — Treat agents as Non-Human Identities (NHI)

Register every agent with its own identity. Map each identity to a capability set, not a credential set.

| NHI Governance Action | Tool | Purpose |
|---|---|---|
| Register agent identity | Okta / CyberArk / Spire | First-class identity, not a shared service account |
| Scope permissions per task | Vault Dynamic Secrets | One credential, one task, one TTL |
| Rotate continuously | Vault / AWS Secrets Manager | No static keys — every credential expires |
| Audit NHI access quarterly | Palantir / Splunk SIEM | Match human access-review cadence |
| Monitor for credential exfiltration | Giskard / PromptArmor | Detect when agent outputs contain secrets |

The **aggregation risk** is the core insight: an agent doesn't need to be compromised to be dangerous. It needs to be *coerced* — through indirect prompt injection, through a manipulated tool response, through a compromised upstream agent. If it holds five credentials, all five are now in play. The defense is not to harden each credential — it is to ensure the agent never accumulates more credential surface than it needs at any given moment, and to rotate that surface continuously.

## Receipt

> Verified 2026-07-04 — GitGuardian 2026 State of Secrets Sprawl: 28.65M secrets leaked on GitHub (+34% YoY), 1.2M AI-service secrets (+81% YoY), 24,000+ secrets in MCP config files on public GitHub, 2,100+ confirmed valid. Zylos Research (May 2026): 21.9% of organizations treat agents as independent NHI; 25.4% still use hardcoded credentials; average breach dwell time 292 days; 80% of identity breaches involve compromised NHI credentials. CockroachDB (Jun 2026): "Those credentials can't live in the agent's context window, because context windows are readable by the model and potentially leakable through tool outputs." Snowflake Cortex sandbox escape (PromptArmor, Mar 2026): indirect prompt injection bypassed human-in-the-loop approval to exfiltrate credentials.

## See also

- [F-10 · Agent Identity and Access](../forward-deployed/f10-agent-identity-and-access.md) — the IAM foundation; this entry is the credential-specific extension
- [F-06 · Agent Sandboxing](../forward-deployed/f06-agent-sandboxing.md) — isolation from the execution side; this entry is isolation from the credential side
- [S-10 · MCP](../stacks/s10-mcp.md) — the protocol layer where tool credentials are configured; S-572 is the security layer around what happens when those credentials flow through context
- [S-561 · The Self-Correction Gap](../stacks/s561-the-self-correction-gap-when-agents-cant-self-heal.md) — an agent that can't self-verify correctness is also one that can't self-detect credential leakage
- [S-569 · The Eval Illusion](../stacks/s569-the-eval-illusion-when-passing-evals-dont-prevent-production-failures.md) — eval sets that don't include credential-exposure assertions will pass even when credentials leak in production
