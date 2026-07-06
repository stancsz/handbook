# S-574 · Agent Per-Principal, Per-Endpoint: Least Privilege at NHI Scale

A support agent needs to read Stripe charges for a specific customer. A coding agent needs to write files in one repo, not every repo. A data agent needs to read one database schema, not all of them. Instead, each gets a role credential that can do everything — because that's how RBAC works for humans, and nobody changed the design when the principals became software. The result: one compromised agent = blast radius spanning everything the role can touch. At 144 NHI per human, this math is now a governance crisis.

## Forces

- **RBAC was designed for people, not software principals.** Humans have stable roles; agents have tasks. Granting `admin` to a support agent because it sometimes needs elevated access means it can do everything on a bad day.
- **NHI populations are exploding.** The NHI-to-human ratio hit 144:1 in 2025 — up 56% year-over-year — and 1 in 5 machine identities carries full-admin privileges. No human team audits these at human timescales.
- **Agents inherit scopes they never request.** When an MCP server exposes 40 tools and the agent calls one, it has access to 39 others by default. The credential was granted before the task existed.
- **Credential lifetime ≠ task lifetime.** A 24-hour token for a 30-second task leaves a 23-hour 59-minute window of excess privilege.

## The move

Treat every agent as its own first-class principal with credentials brokered and scoped per endpoint — enforced in infrastructure, not context.

### The model: agent-as-principal with per-endpoint least privilege

```
User Request
    ↓
Identity Broker (mint scoped credentials)
    ↓
Agent receives: token → allowed endpoints only
    ↓
Tool call → policy engine validates (endpoint match?)
    ↓
Execute or block
    ↓
Audit log with agent identity + endpoint + outcome
```

### Three concrete patterns

**Pattern 1 — Brokered scoped tokens (best for API-level access)**

The identity broker intercepts the agent's credential request, down-scopes it to exactly the endpoints the task requires, and mints a time-limited token. The agent never sees the parent credential.

```python
from agent_principal import IdentityBroker

broker = IdentityBroker(
    parent_credential=os.environ["STRIPE_ADMIN_KEY"],
    agent_id="support-agent-v3",
    task_id=uuid.uuid4(),
)

# Down-scope: read-only access to specific customer charges
scoped = broker.grant(
    endpoints=["stripe.charges.list", "stripe.charges.retrieve"],
    resources=["cus_1A2B3C"],   # single customer, not all customers
    ttl_seconds=300,             # 5 minutes — task duration only
)

agent = SupportAgent(credential=scoped)
# agent.stripe.list_charges()   ← works
# agent.stripe.refund()         ← PolicyDeniedError at runtime
```

**Pattern 2 — Endpoint allowlist at the tool gate (best for MCP servers)**

For MCP tools with many capabilities, the policy engine evaluates each call against an allowlist before execution. The model never sees the credential's full scope.

```python
from agent_policy import PolicyEngine, EndpointAllowlist

policy = PolicyEngine()

# Register what this agent class is allowed to call
policy.register(
    agent_class="BillingSupport",
    allowlist=EndpointAllowlist(
        allow=["stripe.charges.list", "stripe.charges.retrieve"],
        deny=["stripe.refunds.create", "stripe.customers.delete"],
        resource_constraints={
            "stripe.charges.list": {"customer_id": "required_param"},
        },
    ),
)

async def tool_gate(ctx: ToolContext) -> PolicyResult:
    result = policy.evaluate(
        principal=ctx.agent_id,
        endpoint=ctx.tool_name,
        params=ctx.params,
        resource_owner=ctx.params.get("customer_id"),
    )
    if not result.allowed:
        raise PolicyDeniedError(f"{ctx.agent_id} denied: {result.reason}")
    return result

# Apply as middleware on every MCP tool call
mcp_server.add_middleware(tool_gate)
```

**Pattern 3 — Temporal constraint verification (best for multi-step workflows)**

"Authenticate before accessing data" is a sequence constraint that RBAC cannot express. Verify temporal ordering at runtime.

```python
from agent_policy import TemporalConstraint

workflow = TemporalConstraint(
    name="customer-dispute-resolution",
    steps=[
        Step("authenticate", timeout=30),
        Step("fetch_charges", requires_prior=["authenticate"], timeout=60),
        Step("create_refund", requires_prior=["fetch_charges", "authenticate"], timeout=30),
    ],
)

async def execute_workflow(agent, customer_id: str):
    for step in workflow.steps:
        # Fails fast if sequence violated — agent can't skip steps
        await workflow.verify_preconditions(step, agent.session_state)
        result = await agent.run_step(step.name, customer_id=customer_id)
        workflow.record_completion(step.name)
        agent.session_state["last_step"] = step.name
```

### Policy engine options

| Engine | Strength | Best For |
|--------|----------|----------|
| **OPA / Rego** | Battle-tested, declarative | K8s + cloud-native stacks |
| **Clutch Security** | Agent-native, MCP-aware | Enterprise agent platforms |
| **Guild.ai** | Per-endpoint scoping, 144:1 NHI audits | Compliance-heavy orgs |
| **Custom (Kyverno/Cilium)** | Lightweight, K8s-native | Fast-moving teams |

## Receipt

> Verified 2026-07-04 — Research synthesis from Guild.ai (144:1 NHI ratio, July 2025), Clutch Security agent guardrails documentation, Slava Dubrov's six-layer agent security stack, OWASP ASI Top 10 (ASI03: Identity and Privilege Abuse). Real implementations confirmed at Clutch Security, Guild.ai, and Kyverno agent policy integrations. Policy engine examples derived from documented patterns.

## See also

- [S-217 · Agent Capability Authorization](s217-agent-capability-authorization.md) — three-layer auth model (identity → capability grant → tool enforcement)
- [S-186 · AI Agent NHI Identity Governance](s186-ai-agent-nhi-identity-governance.md) — non-human identity lifecycle, rotation, audit
- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — interception layer between proposed and actual tool execution
- [S-205 · Agent Sandbox Isolation](s205-agent-sandbox-isolation.md) — execution isolation complement to credential scoping
