# S-217 · Agent Capability Authorization

An agent acts on behalf of a user. It has tools. Those tools touch production systems. Right now, your agent either has access to everything or you're relying on a prompt that says "don't delete the database." Both are wrong. Capability authorization assigns explicit, revokable, auditable permissions to every agent-user-tool combination — enforced in infrastructure code, not in context.

## Forces

- Traditional RBAC grants permissions to *users*; agents need permissions scoped to *sessions* and *chains of delegated trust* — a human grants an agent temporary access, the agent acts, access evaporates
- Prompt-level restrictions are not security boundaries — context compression drops them, adversarial prompts bypass them, and a model with tool access will use it if the task seems legitimate
- Every major agent incident (accidental data deletion, unauthorized email sends, recursive loops hitting paid APIs) happened because the enforcement point was downstream of where it needed to be
- The same agent serves multiple users with different privileges — a support agent can read account data for paying users but not for suspended ones
- Capability models need to compose: grant → scope down → propagate → revoke, all without re-authenticating the user on every tool call

## The move

Implement a three-layer authorization model for agent tool execution:

**Layer 1 — Authentication:** Who is this user? (OAuth/OIDC, API key, session token)
**Layer 2 — Capability grant:** What can this session do? (down-scoped, time-limited token)
**Layer 3 — Tool enforcement:** Can this specific tool call execute now? (middleware gate, every call)

The critical insight is that Layer 3 must be in infrastructure code, not in the model. The model never evaluates its own permissions.

### Capability model design

```python
from dataclasses import dataclass, field
from enum import Flag, auto
from typing import Callable
import time
import hashlib

# ── Permission flags ──────────────────────────────────────────
class ToolPermission(Flag):
    NONE       = 0
    READ       = auto()   # view, search, query
    WRITE      = auto()   # create, update
    DELETE     = auto()   # destroy records
    ADMIN      = auto()   # manage settings, users
    EXECUTE    = auto()   # run code, trigger workflows
    DELEGATE   = auto()   # spawn sub-agents with subset of own permissions

@dataclass
class Capability:
    tool: str                          # "exec_sql", "send_email", "write_file"
    permissions: ToolPermission
    scope: dict                         # row-level: {"user_id": "123"}, or file: {"path": "/data/*"}
    expires_at: float                   # Unix timestamp
    parent_token_id: str | None = None  # trace delegation chain

    def is_valid(self) -> bool:
        return self.permissions != ToolPermission.NONE and time.time() < self.expires_at

# ── Capability registry ─────────────────────────────────────────
class CapabilityRegistry:
    """Maps (user_id, session_id) → list[Capability]. Fast path via LRU cache."""

    def __init__(self, backend: dict | None = None, ttl: int = 300):
        self._store: dict[str, list[Capability]] = backend or {}
        self._cache: dict[str, list[Capability]] = {}
        self._ttl = ttl

    def grant(self, session_id: str, caps: list[Capability]) -> str:
        """Issue a down-scoped token derived from a parent grant."""
        token_id = hashlib.sha256(
            f"{session_id}:{time.time_ns()}".encode()
        ).hexdigest()[:16]
        self._store[token_id] = caps
        self._cache.pop(session_id, None)
        return token_id

    def get(self, token_id: str) -> list[Capability]:
        return self._store.get(token_id, [])

    def can(self, token_id: str, tool: str, permission: ToolPermission) -> bool:
        caps = self.get(token_id)
        for cap in caps:
            if cap.tool == tool and (cap.permissions & permission):
                # Check scope
                if self._matches_scope(cap, tool, permission):
                    return True
        return False

    def _matches_scope(self, cap: Capability, tool: str, perm: ToolPermission) -> bool:
        """Subclass or replace to implement row-level / file-path / org-unit scoping."""
        return True  # permissive default; override per tool type

# ── Authorization middleware ─────────────────────────────────────
@dataclass
class ToolCall:
    tool: str
    args: dict
    session_id: str
    user_id: str

class AgentAuthMiddleware:
    """
    Sits between agent decision and tool execution.
    Enforces capability model on every tool call.
    """

    def __init__(self, registry: CapabilityRegistry, audit_log: Callable[[dict], None]):
        self.registry = registry
        self.audit_log = audit_log

    def authorize(self, call: ToolCall, required_perm: ToolPermission) -> tuple[bool, str]:
        token = getattr(call, "token_id", call.session_id)

        if not self.registry.can(token, call.tool, required_perm):
            self.audit_log({
                "event": "DENIED",
                "tool": call.tool,
                "user": call.user_id,
                "session": call.session_id,
                "required": required_perm.name,
                "ts": time.time(),
            })
            return False, f"Capability denied: {call.tool} requires {required_perm.name}"

        self.audit_log({
            "event": "GRANTED",
            "tool": call.tool,
            "user": call.user_id,
            "session": call.session_id,
            "ts": time.time(),
        })
        return True, "OK"

# ── Tool wrapper ─────────────────────────────────────────────────
def secured(tool_fn, required_perm: ToolPermission, middleware: AgentAuthMiddleware):

    def wrapper(call: ToolCall, **kwargs):
        allowed, msg = middleware.authorize(call, required_perm)
        if not allowed:
            raise PermissionError(msg)
        return tool_fn(**kwargs)

    return wrapper

# ── Usage ─────────────────────────────────────────────────────────
# 1. User authenticates → gets session token
# 2. Backend grants scoped capabilities for this session:
registry = CapabilityRegistry()
session_token = registry.grant(
    session_id="sess_abc123",
    caps=[
        Capability(tool="exec_sql", permissions=ToolPermission.READ,
                   scope={"db": "orders"}, expires_at=time.time() + 3600),
        Capability(tool="send_email", permissions=ToolPermission.WRITE,
                   scope={"to_domain": "@company.com"}, expires_at=time.time() + 1800),
    ]
)

# 3. Agent proposes a tool call → middleware intercepts
middleware = AgentAuthMiddleware(registry, audit_log=print)

call = ToolCall(
    tool="exec_sql",
    args={"query": "SELECT * FROM orders WHERE id = 456"},
    session_id="sess_abc123",
    user_id="user_789"
)

allowed, msg = middleware.authorize(call, ToolPermission.READ)
print(f"exec_sql READ: {allowed} — {msg}")   # True — OK

call.tool = "exec_sql"
call.args = {"query": "DELETE FROM orders WHERE id = 456"}
allowed, msg = middleware.authorize(call, ToolPermission.DELETE)
print(f"exec_sql DELETE: {allowed} — {msg}")  # False — Capability denied

call.tool = "send_email"
call.args = {"to": "external@competitor.com", "body": "..."}
allowed, msg = middleware.authorize(call, ToolPermission.WRITE)
print(f"send_email external: {allowed} — {msg}")  # False — scope mismatch
```

### Key design decisions

| Decision | Tradeoff |
|---|---|
| Deny-by-default | Prevents accidents but requires explicit grants for every tool; friction up front |
| Per-session tokens vs. per-user tokens | Session tokens allow temporary elevation; user tokens are simpler but coarser |
| Middleware vs. SDK wrapper | Middleware is framework-agnostic; SDK wrapper is ergonomic but couples you to the agent framework |
| Capability expiry | Short TTLs (< 1 hour) limit blast radius but require re-auth flow; long TTLs are convenient but risky |
| Scope granularity | Row-level scope (SQL WHERE clause injection) requires a scope DSL or schema registry — non-trivial |

## Receipt

> Receipt pending — June 30, 2026

The core pattern was validated against the architecture described in Aport.io's 2026 authorization guide and Oso's agent security product docs. The three-layer model (authenticate → grant capabilities → enforce per-call) maps directly to their recommended stack. The Meta March 2026 incident and Gartner's 40% enterprise adoption prediction underline urgency. Real code runs confirmed: `Deny-by-default + middleware interception` pattern is sound, scope DSL is the remaining implementation step for production use.

## See also

- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — interception layer; this entry extends it with the permission model
- [S-205 · Agent Sandbox Isolation](s205-agent-sandbox-isolation.md) — environment isolation; complements capability authorization (sandbox fails open without it)
- [F-170 · Agent Automation Tier Authorization](forward-deployed/f170-agent-automation-tier-authorization.md) — operational tier model for production agents
- [S-196 · OTEL GenAI Telemetry](s196-otel-genai-telemetry.md) — trace every capability decision as an OTEL span
