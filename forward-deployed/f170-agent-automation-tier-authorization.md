# F-170 · Agent Automation Tier Authorization

An agent that can read your email and one that can approve refunds and wire money need fundamentally different security models — yet most teams give them the same trust by default. The fix: tier every agent by operational consequence, then hard-wire the authorization boundary at each tier.

## Forces

- **Agents carry identity but lack scope.** An LLM-powered system with OAuth tokens has the same credentials as a human — but no annual review, no manager approval, no least-privilege onboarding.
- **"Move fast and ship it" collapses at stakes.** The CISA "Careful Adoption of Agentic AI Services" guide (May 2026) explicitly calls out that the security model for an agent that modifies contracts is *not* the security model for a chatbot — and most teams don't make that distinction in code.
- **The capability-deployment gap is real.** A May 2026 industry study (arXiv:2605.14675, 16 practitioners across 12 companies) found four companies with strong experimental agentic capabilities that *could not ship to production* because no verified authorization boundary existed — human-in-the-loop was the only fallback.
- **Tiers collapse under pressure.** When a deadline hits, an agent deployed at Tier 1 (informational only) quietly gets elevated to act. Without code-enforced scope, the boundary only exists on a wiki page.

## The move

Define four automation tiers, map each to an authorization schema, and enforce tier assignment as a first-class property of every tool invocation.

### The four tiers

| Tier | Label | What it can do | Authorization |
|------|-------|----------------|---------------|
| 0 | Observational | Read, search, summarize, draft | No gate — read-only scope on credentials |
| 1 | Advisory | Recommend, flag, route, escalate | Auto-approve; log every recommendation |
| 2 | Delegated | Execute within known bounds: send templated email, update ticket, create draft PR | Pre-flight check: dry-run + human confirmation for stakes above threshold |
| 3 | Autonomous | Act with business consequence: approve refund ≤ $X, close ticket, post to public channel | Policy engine approval (OPA/Cedar), circuit breaker, full audit trail |

### Enforce at the tool layer, not the prompt

```python
from enum import IntEnum
from dataclasses import dataclass
from typing import Callable
import opentelemetry.trace as otel

class AutoTier(IntEnum):
    OBSERVATIONAL = 0   # read-only scope
    ADVISORY      = 1   # recommend, no side effects
    DELEGATED     = 2   # bounded writes
    AUTONOMOUS    = 3   # business-consequential actions

@dataclass
class ToolDef:
    name: str
    tier: AutoTier
    max_stake: float | None = None   # dollar cap for Tier 2
    requires_confirmation: bool = False
    policy_scope: str | None = None  # OPA scope path

# ── Registry ────────────────────────────────────────────────────────────────
TOOL_TIERS: dict[str, ToolDef] = {
    "search_knowledge_base":  ToolDef("search_knowledge_base",  AutoTier.OBSERVATIONAL),
    "summarize_document":    ToolDef("summarize_document",    AutoTier.OBSERVATIONAL),
    "flag_anomaly":          ToolDef("flag_anomaly",          AutoTier.ADVISORY),
    "send_draft_email":      ToolDef("send_draft_email",      AutoTier.DELEGATED,
                                      requires_confirmation=True),
    "approve_refund":        ToolDef("approve_refund",        AutoTier.AUTONOMOUS,
                                      max_stake=200.0,
                                      policy_scope="agent.approve_refund"),
    "wire_transfer":         ToolDef("wire_transfer",         AutoTier.AUTONOMOUS,
                                      policy_scope="agent.wire_transfer"),
}

def enforce_tier(
    tool_name: str,
    stake: float,
    context: dict,
    policy_engine: Callable[[str, dict], bool],
    tracer: otel.Tracer,
) -> bool:
    """
    Returns True if the tool call is authorized.
    Raises PermissionError on denial.
    """
    tool_def = TOOL_TIERS.get(tool_name)
    if tool_def is None:
        raise PermissionError(f"Tool '{tool_name}' not in registry — deny by default")

    with tracer.start_as_current_span(f"tier_auth.{tool_name}") as span:
        span.set_attribute("agent.tier", tool_def.tier.name)
        span.set_attribute("agent.stake", stake)
        span.set_attribute("agent.tool", tool_name)

        # Tier 0–1: auto-approved
        if tool_def.tier <= AutoTier.ADVISORY:
            span.set_attribute("agent.auth_result", "approved_auto")
            return True

        # Tier 2: stake cap check
        if tool_def.tier == AutoTier.DELEGATED:
            if tool_def.max_stake and stake > tool_def.max_stake:
                span.set_attribute("agent.auth_result", "denied_stake_cap")
                raise PermissionError(f"Stake ${stake} exceeds cap ${tool_def.max_stake}")
            span.set_attribute("agent.auth_result", "approved_stake_check")
            return True

        # Tier 3: policy engine
        if tool_def.tier == AutoTier.AUTONOMOUS:
            policy_scope = tool_def.policy_scope or tool_name
            allowed = policy_engine(policy_scope, {**context, "stake": stake})
            span.set_attribute("agent.auth_result", "approved" if allowed else "denied_policy")
            if not allowed:
                raise PermissionError(f"Policy denied: {policy_scope}")
            return True

    raise PermissionError(f"Unknown tier for '{tool_name}'")


# ── Example policy engine (replace with OPA/Cedar in production) ────────────
def simple_policy_engine(scope: str, ctx: dict) -> bool:
    policies = {
        "agent.approve_refund": lambda c: c.get("stake", 0) <= 200,
        "agent.wire_transfer":  lambda c: c.get("stake", 0) <= 0,  # never auto-approve
    }
    fn = policies.get(scope, lambda c: False)
    return fn(ctx)
```

### Dynamic tier escalation at runtime

```python
async def agent_loop_with_tiers(
    agent_id: str,
    task: str,
    tools: list[str],
    policy_engine,
    tracer,
    escalation_callback: Callable,
):
    """Agents can request higher tier; escalation callback handles human approval."""
    for tool in tools:
        stake = estimate_stake(tool, task)

        # Attempt authorization
        try:
            enforce_tier(tool, stake, {"agent_id": agent_id, "task": task},
                         policy_engine, tracer)
            await execute_tool(tool, task)
        except PermissionError as e:
            # Tier boundary hit — escalate
            tier = TOOL_TIERS[tool].tier
            if tier >= AutoTier.AUTONOMOUS:
                confirmed = await escalation_callback(
                    agent_id=agent_id,
                    tool=tool,
                    stake=stake,
                    reason=str(e),
                )
                if confirmed:
                    await execute_tool(tool, task)
            else:
                raise  # Tier 2 confirmation was declined
```

## Receipt

> Receipt pending — June 29, 2026
> The code above reflects the four-tier authorization model from CISA's May 2026 "Careful Adoption of Agentic AI Services" guidance and the capability-deployment gap findings from arXiv:2605.14675 (Alvanakis et al., May 2026). Functional verification pending runtime integration test against an OPA policy engine.

## See also

- [F-168](f168-runtime-constitutional-agent-governance.md) · Runtime Constitutional Agent Governance — runtime principle evaluation vs. hard-coded policy
- [F-169](f169-eu-ai-act-article-12-agent-trail.md) · EU AI Act Article 12 Agent Audit Trail — logging requirements at each automation tier
- [F-06](f06-agent-sandboxing.md) · Agent Sandboxing — isolation layers that complement authorization tiers
- [F-80](f80-agent-to-agent-authentication.md) · Agent-to-Agent Authentication — identity enforcement when agents delegate to sub-agents
