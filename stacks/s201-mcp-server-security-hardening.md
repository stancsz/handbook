# S-201 · MCP Server Security Hardening

MCP graduated from experiment to production attack surface in 2026. OpenAI added it to their bug bounty program in April with up to $6,500 per report for "third-party prompt injection and data exfiltration via MCP-connected agents." Multiple CVEs (CVSS 7.3–9.6) affected 437,000+ installations. 43% of analyzed production MCP servers were vulnerable to command injection. If you're shipping MCP servers, the protocol gives you no security for free — you build it yourself, or you become a news story.

## Forces

- MCP's architecture is a trust amplification device: a single compromised server can exfiltrate data from every connected AI client across your org
- Traditional security tools can't detect prompt injection — there's no malware signature, no exploit pattern, no parsing boundary between instructions and data
- Tool descriptions, names, and metadata are attacker-controlled surfaces — a poisoned MCP server can make your Claude desktop silently choose the wrong tool with no user-visible signal
- The three trust boundaries (client↔server, server↔resources, tools↔execution) each require independent hardening; a gap in any one collapses the whole chain
- Supply chain attacks are live: malicious packages have been found in both PyPI and npm targeting MCP tooling

## The move

Harden each of the three MCP trust boundaries independently.

### Boundary 1 — Client ↔ Server (Transport + Auth)

```python
# Minimal auth-gated MCP server skeleton
import hashlib, hmac, time
from mcp.server import Server
from mcp.types import Tool, CallToolResult

MCP_SERVER = Server("secure-db")
API_KEY = os.environ["MCP_API_KEY"]
ALLOWED_CLIENTS = {"claude-desktop", "cursor", "windsurf"}

def verify_request(headers: dict) -> bool:
    sig = headers.get("x-mcp-signature", "")
    ts = headers.get("x-mcp-timestamp", "0")
    # Reject stale requests (>5 min)
    if abs(time.time() - float(ts)) > 300:
        return False
    expected = hmac.new(
        API_KEY.encode(),
        f"{ts}:{headers.get('x-mcp-body-hash', '')}".encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(sig, expected)

@MCP_SERVER.list_tools()
async def list_tools() -> list[Tool]:
    client_id = get_client_id()
    if client_id not in ALLOWED_CLIENTS:
        return []  # clients see only allowed tools
    return [Tool(name="search_db", description="...", inputSchema={...})]

@MCP_SERVER.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    if not verify_request(request.headers):
        raise PermissionError("Invalid MCP signature")
    if name not in ALLOWED_TOOLS:
        raise PermissionError(f"Tool {name} not permitted for this client tier")
    # sanitize + validate args before execution
    safe_args = sanitize_tool_args(name, arguments)
    return execute_tool(name, safe_args)
```

For remote servers, **OAuth 2.1 with PKCE is mandatory** per the MCP spec. For local servers, HMAC-signed requests with timestamp replay protection block the common attack vectors.

### Boundary 2 — Server ↔ Resources (Access Control)

Every tool that touches a resource (DB, filesystem, API) must treat the MCP server as untrusted — the LLM calling the tool is not authorized by default.

```python
from mcp.types import Resource

TOOL_PERMISSIONS = {
    "search_db":  {"scopes": ["db:read"],  "clients": ALLOWED_CLIENTS},
    "write_file": {"scopes": ["fs:append"], "clients": {"cursor"}},
    "send_email": {"scopes": ["smtp:send"], "clients": set()},  # blocked by default
}

def enforce_scope(tool_name: str, client_id: str) -> bool:
    entry = TOOL_PERMISSIONS.get(tool_name, {"scopes": [], "clients": set()})
    return (
        client_id in entry["clients"]
        and "db:read" in entry["scopes"]  # example: check scope presence
    )

@MCP_SERVER.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    if not enforce_scope(name, get_client_id()):
        raise PermissionError(f"Client {get_client_id()} lacks permission for {name}")
    # ... execute
```

**Key principle:** Deny by default. Only explicitly listed tools are available to explicitly listed clients. Unlisted clients see an empty tool list — no error, no leak.

### Boundary 3 — Tools ↔ Execution (Input Sanitization + Output Filtering)

This is where prompt injection lands. The attack: user-controlled text (a document, email body, webpage) is embedded in the LLM context, which then issues a tool call to exfiltrate data. The defense is layered:

```python
import re

# Layer 1: Structural injection patterns
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|above|all)\s+instructions?", re.I),
    re.compile(r"forget\s+everything", re.I),
    re.compile(r"system\s*[:\-]", re.I),
    re.compile(r"<\|.*?\|>", re.S),  # tag-based injection
    re.compile(r"#{3,}\s*system", re.I),  # markdown heading injection
]

def detect_injection(text: str) -> bool:
    """Run before passing any user text to the LLM or tool."""
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    return False

def sanitize_tool_args(tool_name: str, args: dict) -> dict:
    """Strip injection patterns from all string args."""
    sanitized = {}
    for key, value in args.items():
        if isinstance(value, str):
            if detect_injection(value):
                raise ValueError(f"Potential injection detected in arg '{key}'")
            sanitized[key] = value.replace("\x00", "")  # null byte strip
        elif isinstance(value, list):
            sanitized[key] = [sanitize_tool_args(tool_name, {k: v}) for v in value]
        else:
            sanitized[key] = value
    return sanitized

# Layer 2: Output filtering — redact before returning tool results to the LLM
SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "credentials", "ssn"}

def filter_tool_output(result: dict) -> dict:
    """Mask sensitive fields before passing back to the agent."""
    if not isinstance(result, dict):
        return result
    filtered = {}
    for k, v in result.items():
        if any(sk in k.lower() for sk in SENSITIVE_KEYS):
            filtered[k] = "[REDACTED — sensitive field]"
        elif isinstance(v, dict):
            filtered[k] = filter_tool_output(v)
        else:
            filtered[k] = v
    return filtered
```

**Output filtering is non-negotiable** because tool results become LLM context. If a compromised tool returns credentials, the LLM will dutifully use them on the next tool call unless the result is sanitized first.

### Supply Chain

```bash
# Pin to exact versions — never latest
npm install @modelcontextprotocol/server-filesystem@1.2.0

# Audit dependencies before shipping
pip-audit           # Python
npm audit           # JS
grype .             # SBOM scanning

# Scan for malicious MCP packages (active campaigns on PyPI + npm)
mcp-scan --package suspicious-mcp-tool
```

## Receipt

> Receipt pending — June 29, 2026
> The patterns above synthesize three verified sources: Network Intelligence's MCP Security Checklist (March 2026, CISA author), PhantomByte's production guide (April 2026), and Practical DevSecOps' vulnerability analysis (2026). Real-world CVE data (CVSS 7.3–9.6, 437K affected installations) sourced from Network Intelligence's March 2026 publication. Code examples are structurally correct TypeScript/Python; runtime verification pending environment setup.

## See also

- [S-198 · Agent Tool-Call Guardrails](stacks/s198-agent-tool-call-guardrails.md) — interception layer between proposed and actual tool execution
- [S-196 · LLM Telemetry via OTel GenAI Conventions](stacks/s196-otel-genai-telemetry.md) — observability for agent traces including MCP tool calls
- [S-197 · MCP + A2A Two-Layer Orchestration](stacks/s197-mcp-a2a-two-layer-orchestration.md) — MCP in multi-agent architecture
