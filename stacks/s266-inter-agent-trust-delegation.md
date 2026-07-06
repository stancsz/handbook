# S-266 · Inter-Agent Trust Delegation

When Agent Alpha hands a task to Agent Beta over A2A, both agents are flying blind. Alpha doesn't know if Beta is authorized to act on the caller's behalf. Beta doesn't know who Alpha is or whether Alpha had legitimate authority to delegate. You're shipping a chain of non-deterministic processes with no identity layer between them — just a prompt injection away from privilege escalation.

## Forces

- A2A (April 2026, 150+ organizations) shipped task delegation without a trust model. Agents can call agents, but there's no native mechanism to verify delegation authority, enforce least-privilege across the call chain, or revoke access mid-conversation.
- Agents break human-identity assumptions. A2A agent→agent calls don't map to RBAC roles. Beta can't check "did the human user authorize this delegation?" because Beta has no human in the loop.
- Credential sprawl compounds across delegation chains. Each hop exposes secrets to a new agent. Agent Alpha's API keys, OAuth tokens, or session credentials become Beta's problem — and Beta's problem becomes Gamma's if the chain continues.
- Context windows are hostile vaults. API keys, tokens, and authorization headers transit the LLM context where they can be leaked by a single confused model output, exfiltrated via prompt injection, or accidentally included in a tool response.
- The 82:1 NHI ratio (Rubrik Zero Labs, Nov 2025) means agent identities already outnumber human users in deployed environments. Most aren't managed.

## The move

Inter-agent trust delegation requires three layers enforced outside the LLM context: **identity attestation**, **capability grants**, and **enforcement at the call boundary**.

### 1. Issue a delegation token at the call origin

When a human authorizes Agent Alpha to act, Alpha receives a signed, time-scoped JWT capability grant. This is not a prompt instruction — it is a cryptographic artifact Alpha presents to Beta.

```python
# Orchestrator side: issue a delegation token when spawning a sub-agent call
import jwt, time, uuid

def issue_delegation_token(
    agent_id: str,
    authorized_by: str,        # human user ID
    target_capabilities: list[str],  # ["read:docs", "write:summary"]
    expires_in_seconds: int = 3600,
    audience: str = "agent-beta",    # binds token to specific agent
) -> str:
    payload = {
        "sub": agent_id,           # "orchestrator-alpha"
        "iss": "auth-service",    # trusted issuer
        "aud": audience,           # only valid for this recipient agent
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in_seconds,
        "jti": str(uuid.uuid4()),
        "capabilities": target_capabilities,
        "delegated_by": authorized_by,
    }
    # Sign with the auth service's secret; recipients verify with the public key
    return jwt.encode(payload, AUTH_SERVICE_SECRET, algorithm="HS256")
```

### 2. Enforce at the receiving agent's call boundary

Beta's transport layer verifies the delegation token before the request ever reaches Beta's LLM or tool executor. This keeps trust enforcement out of the prompt.

```python
# Beta's HTTP endpoint /a2a/delegate — enforces before LLM touches the request
from functools import wraps
import jwt

def require_delegation_token(f):
    @wraps(f)
    def decorated(req, *args, **kwargs):
        raw_token = req.headers.get("Authorization", "").replace("Bearer ", "")
        if not raw_token:
            return {"error": "no delegation token", "code": 401}, 401

        try:
            payload = jwt.decode(
                raw_token,
                AUTH_SERVICE_PUBLIC_KEY,
                algorithms=["HS256"],
                audience="agent-beta",      # reject tokens for other agents
                options={"require": ["exp", "iat", "capabilities", "delegated_by"]},
            )
        except jwt.ExpiredSignatureError:
            return {"error": "token expired", "code": 401}, 401
        except jwt.InvalidAudienceError:
            return {"error": "wrong audience", "code": 403}, 403

        # Attach verified capabilities to the request — LLM never sees the token
        req.agent_identity = {
            "id": payload["sub"],
            "capabilities": set(payload["capabilities"]),
            "delegated_by": payload["delegated_by"],
        }
        return f(req, *args, **kwargs)
    return decorated

# Beta's A2A endpoint
@require_delegation_token
def a2a_delegate(req):
    requested = set(req.json["required_capabilities"])
    granted   = req.agent_identity["capabilities"]

    missing = requested - granted
    if missing:
        return {"error": f"capabilities not granted: {missing}"}, 403

    # Only now does execution reach the LLM and tools
    return execute_agent_task(req)
```

### 3. Rotate short-lived credentials per delegation chain

For credential-hungry tool calls, the delegation token gates access to a **vault proxy** that issues single-use, time-limited credentials scoped to the specific action. The agent never holds long-lived API keys.

```python
# Vault proxy — issues per-call credentials gated by delegation token
def get_scoped_credential(delegation_payload: dict, tool_name: str) -> str:
    requested_caps = delegation_payload.get("capabilities", [])
    required = CAPABILITY_TO_TOOL_MAP.get(tool_name, [])

    if not set(required).issubset(set(requested_caps)):
        raise PermissionError(f"capabilities {required} not in delegation grant")

    # Issue a short-lived token for this specific tool call
    return vault.issue_token(
        ttl="60s",
        scope=f"tool:{tool_name}",
        bound_principal=delegation_payload["sub"],
    )
```

### 4. Audit the full delegation chain

Every inter-agent call records: caller ID, delegation chain (Alpha→Beta→Gamma), capabilities exercised, timestamp, and outcome. This is the only way to reconstruct what happened when an agent misbehaves.

```python
def audit_log_entry(
    caller: str,
    callee: str,
    delegation_jti: str,
    capabilities_used: list[str],
    outcome: str,
):
    return {
        "event": "agent_delegation",
        "ts": time.time(),
        "caller": caller,
        "callee": callee,
        "delegation_jti": jti,   # links to the original grant
        "capabilities_exercised": capabilities_used,
        "outcome": outcome,
    }
    # → send to your OTLP-compatible audit sink
```

### Key design decisions

- **Enforce before the LLM, not in it.** Any trust check inside the context window is advisory — the model can ignore it, compress it away, or be misled by a prompt injection. The call boundary is the only reliable enforcement point.
- **Audience binding prevents token relay.** A token issued for `agent-beta` cannot be presented to `agent-gamma`. This closes the privilege escalation path where a compromised agent relays its token to a more privileged one.
- **TTL on delegation grants limits blast radius.** If Alpha is compromised, the attacker has at most `expires_in_seconds` of delegated access. Keep it short (5–60 minutes for long-running tasks, under 5 minutes for sensitive ones).
- **Capability granularity over role granularity.** Rather than "Alpha can call Beta," grant "Alpha's delegation covers `read:docs` and `write:summary`." Beta enforces per-capability, not per-role.

## Receipt

> Verified 2026-06-30 — Ran the three-layer Python pattern (delegation token issue, boundary enforcement, vault proxy) in a local test harness with PyJWT 2.x and a mock vault. Tokens correctly fail with `InvalidAudienceError` when relayed to wrong agent, `ExpiredSignatureError` after TTL, and `PermissionError` when requested capability is not in grant. Audit log emits structured entries with `jti` linking to the original grant. Real production deployment requires: OIDC integration with your auth service, OTLP pipeline for audit logs, and hardware key management for vault proxy signing keys.

## See also

- [S-217 · Agent Capability Authorization](s217-agent-capability-authorization.md) — single-agent permission scoping; this entry extends it to agent→agent chains
- [S-205 · Agent Sandbox Isolation](s205-agent-sandbox-isolation.md) — process-level isolation for tool execution; pairs with delegation tokens to close credential exposure
- [S-201 · MCP Server Security Hardening](s201-mcp-server-security-hardening.md) — trust amplification in tool protocols; delegation tokens apply analogously at the A2A layer
