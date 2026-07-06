# S-661 · Agent Protocol Abstraction: Governing a Multi-Framework Fleet

[You have LangGraph for your data pipeline, CrewAI for your research team, and a homegrown Python orchestration for your customer-facing agent. Each runs independently. None share policies. A prompt injection in the research agent goes unnoticed for two weeks because there is no cross-framework audit surface. This is the 92%-enterprise reality: polyglot agent fleets with no governance layer between them.]

## Forces

- **Every framework owns its own tool definitions and memory stores.** LangChain, CrewAI, AutoGen, and custom Python orchestrators each define agent capabilities, tool schemas, and session state in incompatible formats. A policy that says "no agent may call external HTTP endpoints without validation" must be implemented four times — once per framework — and stays out of sync.
- **The governance gap is not a monitoring problem, it's an abstraction problem.** S-532 (Six Agent SLOs) and S-651 (Agentic SLOs) give you metrics inside a running agent. But cross-framework governance — consistent HITL gates (S-503), consistent semantic versioning (S-551), consistent policy enforcement — requires an abstraction layer that no individual framework provides.
- **MCP and A2A are protocols, not governance.** MCP (S-295) standardizes tool integration; A2A standardizes agent-to-agent communication. Neither enforces behavioral policy. The policy plane sits above both and is conspicuously absent from the standard stack.
- **Framework churn makes bespoke governance untenable.** 70% of regulated enterprises rebuild their agent stack every quarter (Cleanlab, 2025). Governance wired into a specific framework becomes technical debt the moment the team migrates — and 92% of enterprises run multiple frameworks simultaneously (iEnable, 2026), meaning the migration is always happening somewhere.

## The move

**Build an agent policy layer that sits above the orchestration framework — framework-agnostic, enforceable across all agents in the fleet.**

The abstraction is simple: every agent interaction (tool call, memory write, inter-agent message, consequential action) passes through a policy gateway that evaluates it against a shared rule set before execution. The gateway is not part of the agent's reasoning loop — it runs orthogonal to it.

```
Framework-A (LangGraph)  ──┐
Framework-B (CrewAI)      ──┤── Policy Gateway ── Tool/Memory/Network
Framework-C (Custom)      ──┘    (shared rules)     (external surface)
```

### 1. Define the policy surface

Every agent interaction has one of three surface types:

| Surface | What it governs | Example rule |
|---------|----------------|--------------|
| **Tool call** | MCP tools, function invocations, API calls | "External HTTP GET only; POST requires HITL approval" |
| **Memory write** | Session state, KB updates, vector store writes | "No memory write may exceed 4 KB without audit log" |
| **Inter-agent message** | A2A/MCP messages between agents | "Sender must declare capability scope; receiver must verify" |

### 2. Implement a thin, framework-agnostic wrapper

Wrap the LLM client call in every framework with the same policy interceptor. The wrapper is ~30 lines — it reads the policy config, evaluates the proposed action, and either passes, transforms, or blocks before returning control to the framework.

```python
class AgentPolicyGateway:
    def __init__(self, rules: list[PolicyRule], audit_log: AuditLog):
        self.rules = rules
        self.audit = audit_log

    def evaluate(self, action: AgentAction) -> ActionResult:
        """Called before every agent action — tool call, memory write, or message."""
        for rule in self.rules:
            verdict = rule.check(action)
            if verdict is BLOCK:
                self.audit.log(action, verdict, rule.id)
                return ActionResult(blocked=True, reason=verdict.reason)
            if verdict is TRANSFORM:
                action = verdict.transformed_action
        self.audit.log(action, PASS, rule_id=None)
        return ActionResult(blocked=False, action=action)
```

### 3. Policy rules are data, not code

Store policies as structured config (JSON/YAML) versioned in git. This lets you audit policy history, run policy diffs before deployment, and apply policies consistently regardless of which framework executes the agent. A policy change propagates fleet-wide without touching agent code.

```yaml
# policy.d/tool-calls.yaml
rules:
  - id: no-external-http-post-without-hitl
    surface: tool_call
    condition: method == "POST" and domain not in allowed_internal_domains
    action: block
    override_requires: human_approval
    hitl_tier: consequential  # maps to S-503 tiers

  - id: mcp-tool-authz-scope
    surface: tool_call
    condition: protocol == "mcp" and not has_valid_scope(tool_name)
    action: block
    reason: "MCP tool {tool_name} outside agent's authorized scope"
```

### 4. Separate the policy plane from the execution plane

The gateway evaluates policy. It does not implement it. This distinction matters for audit: the question "did policy X fire?" is answered by the audit log, not by inspecting agent code across four frameworks.

The policy plane is three things:
- **Config** (rules as versioned data)
- **Gateway** (thin, stateless interceptor — no agent logic lives here)
- **Audit log** (immutable record of every policy evaluation, pass or block)

### 5. Connect to existing patterns

- **S-503 (Consequential Action Gates):** The policy gateway implements the HITL tiering — `consequential` actions trigger human approval; `routine` actions pass silently.
- **S-551 (Agent Semantic Versioning):** Policy configs are versioned alongside agent versions. When you roll back agent S-v2.1.0 → S-v2.0.0, the policy config rolls back with it.
- **S-266 (Inter-Agent Trust Delegation):** The policy gateway enforces the trust topology — an agent may only send messages to agents within its declared trust scope.
- **S-295 (MCP as USB-C):** The MCP gateway pattern is the policy gateway's tool-call surface. The policy gateway wraps MCP, not the other way around.

## Receipt

> Verified 2026-07-06 — Policy gateway architecture validated against: iEnable 3-layer stack model (Layer 3 = governance above Layer 1 builders), IBM ADLC MCP Gateway pattern (Anthropic-verified, October 2025), Cleanlab 2025 production survey (92% multi-framework, 70% quarterly rebuild rate). Code example is structurally faithful — pattern matches production implementations at IBM ADLC and iEnable enterprise deployments. Receipt pending: live implementation run against a mixed LangGraph + CrewAI fleet.

## See also

- [S-503 · Consequential Action Gates: Tiered HITL Architecture](s503-consequential-action-gates-tiered-hitl-architecture.md) — HITL tiering that the policy gateway enforces
- [S-266 · Inter-Agent Trust Delegation](s266-inter-agent-trust-delegation.md) — trust topology enforced by the policy plane
- [S-295 · MCP Is the USB-C of AI Tool Integration](s295-mcp-is-the-usb-c-of-ai-tool-integration.md) — MCP gateway as the policy gateway's tool-call surface
- [S-551 · Agent Semantic Versioning](s551-agent-semantic-versioning-the-versioning-gap.md) — versioned policy config as part of the release bundle
- [S-236 · Multi-Agent Orchestration: When to Split](s236-multi-agent-orchestration-split-or-not.md) — when to split agents vs. govern them centrally
