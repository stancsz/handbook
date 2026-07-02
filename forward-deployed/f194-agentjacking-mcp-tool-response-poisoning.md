# F-194 · AgentJacking & MCP Tool-Response Poisoning

A single public Sentry DSN key. One HTTP POST. An AI coding agent running on a developer's machine obediently executes attacker-controlled code — bypassing EDR, bypassing WAF, bypassing explicit "ignore untrusted data" instructions. This is AgentJacking, a novel attack class published by Tenet Security on June 12, 2026, achieving an 85% success rate against Claude Code, Cursor, and Codex CLI. The attack vector is the Model Context Protocol's implicit trust in tool responses — and it changes how you think about every MCP server your agent connects to.

## Forces

- **MCP is now the default agent tool protocol.** Anthropic, OpenAI, Google, and Microsoft all support it. A coding agent that connects to Sentry, GitHub, Slack, or any of the 1,000+ MCP servers is implicitly trusting every byte those servers return — including public, unauthenticated endpoints like Sentry's event ingestion API.
- **85% of tested agents executed injected payloads even when explicitly instructed to ignore untrusted data.** RLHF alignment does not transfer to adversarial tool responses. The model treats a `sentry_sdk.capture_message()` response the same as a trusted internal API call.
- **The attack surface scales with MCP server count.** AgentJacking uses Sentry as the delivery mechanism, but the root vulnerability is the trust amplification: any compromised or public MCP server can poison an agent's context. GitHub MCP servers, code review tools, CI/CD connectors — all are potential vectors.
- **2,388 organizations were found with valid injectable DSNs.** This is not theoretical. The infrastructure for this attack is already present in real codebases.
- **Existing security tooling cannot detect it.** No malware signature. No exploit pattern. The payload is plain text embedded in a markdown-formatted error report that looks like legitimate tooling output.

## The move

Three layers of defense — none sufficient alone, all required together.

### Layer 1 — Treat all MCP tool responses as untrusted input

Every tool response is context your agent trusts. Apply the same sanitization pipeline you'd use on user-submitted text:

- **Strip markdown directives** before injecting tool responses into the agent's context. AgentJacking hides instructions in markdown formatting (`**IMPORTANT FIX:**`, code blocks, links).
- **Validate response schemas.** MCP tool responses have defined schemas. Reject responses that deviate — a Sentry error response that includes a "recommended fix" field is not a standard Sentry payload.
- **Scope MCP server access.** A Sentry MCP server should not have network access to clone repos or exfiltrate credentials. Apply least-privilege to MCP server permissions, not just to the agent's own permissions.

```python
# Tool response sanitizer — strip markdown injection vectors
import re

def sanitize_tool_response(response: dict, tool_name: str) -> dict:
    """Strip markdown and directive patterns from tool responses."""
    suspicious_patterns = [
        r"\*\*.{0,50}FIX.{0,50}\*\*",     # **IMPORTANT FIX: ...**
        r">>> .*",                          # >>> instruction markers
        r"```[\s\S]*?INSTRUCTIONS?[\s\S]*?```",  # hidden instruction blocks
        r"\[.*\]\(http.*\)",                # markdown links (redirect vectors)
    ]
    sanitized = {}
    for key, value in response.items():
        if isinstance(value, str):
            for pattern in suspicious_patterns:
                value = re.sub(pattern, "[REDACTED]", value, flags=re.IGNORECASE)
        sanitized[key] = value
    return sanitized
```

### Layer 2 — Block unauthenticated MCP servers from production agents

Sentry's event ingestion API accepts events from anyone with a DSN key — no authentication, no rate-limit per key. This is by design for legitimate error reporting. It is a critical trust boundary for agents.

- **Audit your MCP server inventory.** Every MCP server your agent connects to: which ones accept unauthenticated input? Which ones have no DSN rotation policy? Sentry, PagerDuty, Datadog, S3 — many monitoring tools use shared-key patterns that are publicly exposable.
- **Require authentication on MCP server connections.** Where the MCP server supports it (e.g., GitHub OAuth, custom JWT), enforce it. For servers that don't, route through a proxy that validates the response before it reaches the agent.
- **Rotate and scope DSN keys.** Sentry DSNs should be per-environment (not shared dev/prod), per-service, and rotated. A leaked DSN in a `sentry.client.config` is an AgentJacking vector.

```python
# MCP server audit: flag unauthenticated endpoints
MCP_SERVER_AUDIT = {
    "sentry": {
        "auth": "dsn_key_only",  # unauthenticated ingestion — HIGH RISK
        "data_classification": "internal",
        "agent_access": "BLOCK",
    },
    "github": {
        "auth": "oauth_token",   # authenticated
        "data_classification": "internal",
        "agent_access": "LIMITED",  # read-only, no repo write
    },
    "filesystem": {
        "auth": "implicit",      # local, no network
        "data_classification": "internal",
        "agent_access": "RESTRICTED",  # sandboxed, no /home or /opt
    },
}

def assess_mcp_risk(server_name: str) -> str:
    config = MCP_SERVER_AUDIT.get(server_name, {})
    auth = config.get("auth", "unknown")
    if auth in ("dsn_key_only", "api_key_only"):
        return f"HIGH — {server_name} accepts unauthenticated input. Agent access: {config.get('agent_access', 'UNKNOWN')}"
    return f"OK — {auth}"
```

### Layer 3 — Runtime tool-call authorization gate

Even with sanitization and auditing, a sufficiently targeted attack may succeed. The last line of defense is the authorization layer between the agent's *intent* and tool *execution* ([F-100](f100-agent-sandboxing-guardrails.md)).

- **Block write and exec tool calls by default** for MCP-connected agents. Require explicit purpose-level authorization for `git push`, `npm install`, `curl`, `exec`, file writes to sensitive paths.
- **Log and alert on unusual tool-call sequences.** An agent that receives a Sentry error and immediately calls `git stash && curl ...` is suspicious. Anomaly detection on tool-call chains, not individual calls.
- **Rate-limit outbound connections from agent environments.** If exfiltration succeeds, limit blast radius. Agent sandboxes should have no path to external C2 infrastructure.

## Receipt

> Verified June 12, 2026 — AgentJacking research published by Tenet Security / Cloud Security Alliance. CSA published `CSA_research_note_agentjacking_mcp_sentry_injection_20260612.pdf`. Tested against Claude Code, Cursor, Codex — 85% success rate. 2,388 organizations found with valid injectable DSNs. No toolchain patch available at publication; mitigation is defensive architecture (this entry). Microsoft also documented RCE vulnerabilities in Semantic Kernel (CVE-2026-25592) and MCP-connected browser/IDE attack paths in June 2026.

## See also

- [F-182 · MCP Server CVE Supply Chain Exploits](f182-mcp-server-cve-supply-chain-exploits.md) — CVE landscape for MCP servers
- [F-188 · AI Agent Red Teaming](f188-ai-agent-red-teaming.md) — adversarial testing methodology
- [S-201 · MCP Server Security Hardening](stacks/s201-mcp-server-security-hardening.md) — server-side hardening
- [F-100 · Agent Sandboxing & Guardrails](f100-agent-sandboxing-guardrails.md) — runtime authorization
