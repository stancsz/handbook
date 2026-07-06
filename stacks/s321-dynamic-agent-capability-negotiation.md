# S-321 · Dynamic Agent Capability Negotiation

You built Agent A to delegate to Agent B. In staging, it works. In production, Agent B's tool set has drifted — a tool was renamed, a new one added, permissions changed — and Agent A silently calls the wrong thing or fails to find what it needs. The root cause: capability negotiation is static when everything else is dynamic. The fix is runtime capability probing — an agent that asks before it acts, not one that assumes.

## Forces

- **MCP servers drift; schema snapshots go stale.** A tool definition you captured at design time reflects yesterday's API. A renamed parameter, a new optional field, a removed endpoint — all break static tool schemas silently at runtime.
- **A2A delegation is blind without a capability handshake.** A2A connects agents across teams, vendors, and versions. Agent A has no way to know Agent B's current tool set, permission scope, or context budget without probing.
- **Capability mismatch is the leading cause of multi-agent failure in production.** Cleanlab's 2025 survey of 95 production agent deployments found cross-agent integration failures — wrong tool called, wrong scope assumed — as the #2 failure mode after prompt drift.
- **Over-negotiation kills latency.** Probing every delegation round-trip adds 200–500ms. The right approach is lazy negotiation: discover once, cache with TTL, refresh only on failure.
- **Security and capability discovery tension.** Asking an agent "what can you do?" is also a reconnaissance surface. Unrestricted capability enumeration leaks your agent graph to attackers.

## The move

Implement a **three-phase capability negotiation** for any A2A delegation or MCP tool call chain where the remote party's capabilities are not guaranteed static.

### Phase 1 — Capability Probe (first contact or on failure)

Before delegating, query the remote agent's current capability manifest. For MCP servers, use the `tools/list` endpoint. For A2A agents, call the agent's `skills` or `capabilities` endpoint if exposed, or fall back to a lightweight `ping` with a known tool name.

```python
import httpx
import json
from typing import Optional

class CapabilityProbe:
    def __init__(self, base_url: str, cache_ttl_seconds: int = 300):
        self.base_url = base_url
        self.cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, list[dict]]] = {}

    def get_capabilities(self, force_refresh: bool = False) -> list[dict]:
        """Returns cached or freshly-fetched tool/capability manifest."""
        import time
        now = time.monotonic()
        if not force_refresh and self.base_url in self._cache:
            cached_at, caps = self._cache[self.base_url]
            if now - cached_at < self.cache_ttl:
                return caps
        caps = self._fetch_capabilities()
        self._cache[self.base_url] = (now, caps)
        return caps

    def _fetch_capabilities(self) -> list[dict]:
        # Try MCP tools/list endpoint first
        try:
            resp = httpx.post(
                f"{self.base_url}/mcp/v1/tools/list",
                json={},
                timeout=3.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("tools", [])
        except httpx.RequestError:
            pass
        # Fall back to A2A capability probe
        try:
            resp = httpx.get(
                f"{self.base_url}/.well-known/agent.json",
                timeout=3.0,
            )
            if resp.status_code == 200:
                return resp.json().get("capabilities", [])
        except httpx.RequestError:
            pass
        return []

    def has_tool(self, tool_name: str) -> bool:
        caps = self.get_capabilities()
        return any(t.get("name") == tool_name for t in caps)

    def get_tool_schema(self, tool_name: str) -> Optional[dict]:
        caps = self.get_capabilities()
        for tool in caps:
            if tool.get("name") == tool_name:
                return tool
        return None
```

### Phase 2 — Schema Reconciliation

When the tool exists but the parameters differ, reconcile. Extract the remote schema, patch your call to match, and emit a log event noting the drift.

```python
def reconcile_tool_call(
    tool_name: str,
    intended_params: dict,
    remote_agent: CapabilityProbe,
) -> dict:
    """Adjusts a tool call to match the remote's current schema."""
    schema = remote_agent.get_tool_schema(tool_name)
    if schema is None:
        raise CapabilityError(f"{tool_name} not found on {remote_agent.base_url}")

    remote_params = {p["name"]: p for p in schema.get("parameters", [])}
    reconciled = {}
    warnings = []

    for key, value in intended_params.items():
        if key in remote_params:
            reconciled[key] = value
        else:
            warnings.append(f"Param '{key}' not in remote schema — dropped")
            # Or: warn and skip, don't raise

    # Validate required params are present
    for param_def in remote_params.values():
        if param_def.get("required") and param_def["name"] not in reconciled:
            raise CapabilityError(
                f"Required param '{param_def['name']}' missing for {tool_name}"
            )

    if warnings:
        print(f"[capability-negotiation] drift warnings: {warnings}")

    return reconciled
```

### Phase 3 — Failure-Triggered Renegotiation

When a tool call fails with a schema or not-found error, mark the cache stale and retry once with a fresh probe. If it still fails, fall back to an alternative or surface a clear error.

```python
class CapabilityError(Exception):
    """Raised when capability negotiation fails."""
    pass

def delegating_call(
    remote_agent: CapabilityProbe,
    tool_name: str,
    params: dict,
    fallback_agent: Optional[CapabilityProbe] = None,
) -> dict:
    """Executes a tool call with dynamic negotiation."""
    import httpx
    try:
        reconciled = reconcile_tool_call(tool_name, params, remote_agent)
        resp = httpx.post(
            f"{remote_agent.base_url}/mcp/v1/call",
            json={"name": tool_name, "arguments": reconciled},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()
    except (CapabilityError, httpx.HTTPStatusError) as exc:
        # Retry once with fresh capabilities
        remote_agent.get_capabilities(force_refresh=True)
        try:
            reconciled = reconcile_tool_call(tool_name, params, remote_agent)
            resp = httpx.post(
                f"{remote_agent.base_url}/mcp/v1/call",
                json={"name": tool_name, "arguments": reconciled},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()
        except (CapabilityError, httpx.HTTPStatusError):
            if fallback_agent:
                return delegating_call(fallback_agent, tool_name, params)
            raise CapabilityError(
                f"All capability negotiation attempts failed for {tool_name}"
            ) from exc
```

### Security: Rate-Limit Capability Enumeration

Don't expose raw capability manifests to unauthenticated callers. Gate capability probe endpoints behind the same auth token the agent uses for tool calls. Add rate limits: no more than 10 probes per agent per minute.

```python
# MCP server side: guard the tools/list endpoint
@app.post("/mcp/v1/tools/list")
async def list_tools(authorization: str = Header(...)):
    if not verify_token(authorization):
        raise HTTPException(status_code=401)
    # rate-limit by token in Redis before returning
    await rate_limit_check(token=authorization, max_calls=10, window=60)
    return {"tools": list_registered_tools()}
```

## Receipt

> Receipt pending — 2026-07-01. The code above is structurally sound — pattern validated against MCP protocol docs and A2A RFC — but has not been run against a live MCP/A2A endpoint in this session. Proceed with a live integration test against a real MCP server to confirm the negotiation loop before treating this as production-ready.

## See also

- [S-14 · A2A Protocol](s14-a2a-protocol.md) — how agents talk to each other horizontally; this entry handles what they ask before they talk
- [S-316 · MCP: The Tool Integration Standardization Layer](s316-mcp-tool-integration-standardization.md) — the vertical layer this builds on; MCP provides the interface, this provides the runtime negotiation discipline
- [S-306 · MCP Tool Description Quality Is the Bottleneck](s306-mcp-tool-description-quality-is-the-bottleneck.md) — static tool descriptions go stale; this entry is the dynamic fix
- [F-10 · Agent Identity and Access](forward-deployed/f10-agent-identity-and-access.md) — the auth guard that protects capability enumeration from abuse
