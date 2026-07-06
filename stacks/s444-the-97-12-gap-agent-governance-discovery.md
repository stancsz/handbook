# S-444 · The 97/12 Gap: Agent Governance Discovery

You have AI agents running in production. You do not know how many, what they can do, or who authorized them. Neither does your security team. The EU AI Act enforcement clock hits zero in 29 days and your compliance team is asking questions you cannot answer. The 97/12 gap — 97% of enterprises running AI agents, 12% with centralized governance — is the defining enterprise AI crisis of 2026, and most engineering teams are still treating it as a policy problem when it is an infrastructure problem.

## Forces

- **The procurement gap is structural.** Enterprise AI adoption now happens through SaaS upgrades, API key provisioning, and model vendor contracts — none of which trigger traditional IT change-management. A capability activation in an already-approved tool can introduce an agent without any new sign-off.
- **The capability surface grows faster than the inventory.** Adding a tool to a platform is one change request. Enabling that tool's agentic mode (autonomous reasoning, multi-step execution, external system access) is often a config toggle — invisible to governance tooling built for vendor-change detection.
- **EU AI Act Article 16 requires node-level audit trails by August 2, 2026.** High-risk AI systems must maintain logs that can reconstruct specific decision sequences. Most agent platforms log session outcomes, not the individual reasoning steps and tool calls that produced them.
- **The 85-percentage-point gap is not a awareness problem.** Enterprises know agents are running. They lack the technical mechanisms to enumerate, classify, and control them — the policy playbook predates the architecture.

## The move

**Treat agent governance discovery as an engineering discipline, not a compliance checklist.**

The pattern has three technical layers:

### 1. Agent Capability Inventory via Execution Tracing

Before you can govern agents, you must enumerate them. This means instrumenting the execution layer — not polling vendors or surveying teams.

```
# Passive agent discovery: enumerate agent sessions from trace infrastructure
# Uses OpenTelemetry GenAI conventions (see S-196)
from opentelemetry import trace

agent_sessions = set()
for span in trace.get_tracer_provider().get_tracer("agent-discovery").get_current_spans():
    attrs = span.attributes
    if attrs.get("genai.system") == "agent":
        agent_sessions.add({
            "session_id": attrs.get("session.id"),
            "capabilities": attrs.get("genai.agent.capabilities"),  # tools, autonomy level
            "principal": attrs.get("genai.agent.principal"),          # who authorized it
            "data_accessed": attrs.get("genai.agent.data_classification"),
        })
```

Key: capture `genai.agent.capabilities` — the actual tool list and autonomy level — not just the vendor name or product tier. A "customer support platform" can be anything from a scripted chatbot to a fully autonomous L4 agent with write access to your CRM.

### 2. The 12-Question Capability State Audit

Rather than cataloging vendors, audit by capability state. Adapted from Agent Mode AI's discovery framework:

| # | Question | What It Reveals |
|---|----------|-----------------|
| 1 | Does it reason across multiple steps without human input? | Autonomy level |
| 2 | Does it access external systems or APIs autonomously? | Read/write surface |
| 3 | Can it modify data in production systems? | High-risk flag (EU AI Act Annex III) |
| 4 | Does it maintain its own state between sessions? | Memory system classification |
| 5 | Can it call other agents or delegate tasks? | Multi-agent coordination |
| 6 | Does it produce outputs used by downstream automated systems? | Semantic exit gate candidates |
| 7 | Does it log individual tool calls or only session outcomes? | Article 16 readiness |
| 8 | Can you revoke its access credentials without a vendor ticket? | NHI/credential governance |
| 9 | Does it retain context from previous interactions? | Context window persistence |
| 10 | Can it take irreversible actions? | Kill-switch readiness |
| 11 | Does it use MCP, A2A, or custom protocols? | Protocol layer classification |
| 12 | What was its capability state 90 days ago? | Drift tracking |

Questions 3, 7, and 10 are EU AI Act hard requirements. Questions 1–2 and 5–6 determine your high-risk classification under Annex III.

### 3. Policy-as-Code Enforcement Pipeline

Discovery without enforcement is just a prettier audit finding. The technical enforcement layer:

```python
# Governance policy encoded as code, not prose
from dataclasses import dataclass
from enum import Enum

class RiskTier(Enum):
    TIER1_WRITE = "tier1_write"    # EU AI Act high-risk: autonomous write access
    TIER2_READ = "tier2_read"     # Autonomous read with external data access
    TIER3_INTERNAL = "tier3"      # Internal-only, human-reviewable

@dataclass
class AgentPolicy:
    tier: RiskTier
    requires_audit_trail: bool = True
    requires_human_approval: bool = False
    requires_kill_switch: bool = False
    max_autonomy_level: int = 3  # L0-L4; L5 explicitly prohibited

# Enforce at the gateway layer — not in the agent
def register_agent(session_id: str, capabilities: list[str], policy: AgentPolicy):
    if policy.requires_audit_trail:
        assert requires_node_level_logging(session_id), \
            f"EU AI Act Article 16: session {session_id} lacks node-level logs"
    if policy.tier == RiskTier.TIER1_WRITE:
        assert policy.requires_kill_switch, \
            "High-risk write agents require a kill switch"
        assert policy.requires_human_approval, \
            "TIER1_WRITE requires pre-action approval gate"
```

The kill switch (Question 10) must be technically enforceable — a button the ops team can press that revokes credentials within seconds, not a vendor support ticket filed at T+24 hours.

## Receipt

> Receipt pending — 2026-07-03

The three-layer pattern (inventory via tracing, capability audit, policy-as-code) was synthesized from Zylos Research's governance framework, ExecLayer's EU AI Act technical requirements, and Agent Mode AI's 12-question capability state audit. Each component is independently verified in production literature. A working implementation with OTel GenAI conventions integration would complete the receipt.

## See also

- [S-355 · Agent Autonomy Levels (Bounded Autonomy)](stacks/s355-agent-autonomy-levels-bounded-autonomy.md) — the L0–L5 taxonomy that underpins risk tier classification; the Read-to-Write gate is Question 3's technical enforcement mechanism
- [S-196 · LLM Telemetry via OTel GenAI Conventions](stacks/s196-otel-genai-telemetry.md) — the instrumentation standard that makes passive agent discovery possible
- [S-213 · The Stratified Agent Stack](stacks/s213-stratified-agent-stack.md) — layer boundaries are where governance controls attach; governance instrumentation belongs in the orchestration layer, not embedded in execution
- [S-420 · Agent Identity Governance: The AI-Principal Paradigm](stacks/s420-agent-identity-governance-the-ai-principal-paradigm.md) — the credential and NHI layer that Question 8 and the kill-switch requirement depend on
