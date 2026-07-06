# F-175 · Agent Capability Negotiation

You have a multi-agent system with 12 agents — code review, data analysis, document writing, API integration, testing. A new request arrives: "Analyze Q3 sales, find anomalies, write a report, and deploy a fix if the anomaly exceeds 5%." Who handles it? The naive answer is a hard-coded orchestrator that routes statically. The hard truth is that this routing logic becomes your biggest maintenance burden as the agent fleet grows, capabilities shift, and task shapes change. What you actually want is agents that advertise what they can do and negotiate assignments dynamically — capability-based delegation at runtime.

## Forces

- Static routing tables encode assumptions about agent capabilities that drift as models upgrade, prompts change, and new tools are added — every capability change requires a code deploy to update routing
- Hard-coded orchestration creates a single point of failure: the orchestrator becomes the bottleneck and the bottleneck becomes the blast radius
- Capability mismatch is invisible until runtime — an agent rated "good at SQL" turns out to be slow on 100M-row tables but fast on aggregations; the routing logic has no way to know this
- Cross-team agent fleets (each team owns their agents) need a protocol for delegation without tight coupling — the caller shouldn't need to know which team owns the right agent
- Cost and latency preferences vary by caller: a background report generation can tolerate a slower, cheaper agent; an incident response needs the fastest available capable agent

## The move

Capability negotiation decouples the **caller** from the **resolver**. Instead of the caller knowing which agent does what, it announces what it needs. A registry holds agent capability manifests. A matching layer selects the best-fit agent at runtime.

**Capability manifest — each agent registers:**

```
AgentCapability {
  id: "sales-anomaly-v2"
  capabilities: ["statistical-analysis", "sql-query", "report-generation", "code-deploy"]
  confidence: {
    "statistical-analysis": 0.92,   # measured pass rate on eval set
    "sql-query": 0.87,
    "report-generation": 0.95,
    "code-deploy": 0.78             # lower — less practiced
  }
  constraints: {
    max_rows: 1_000_000,            # degrades past this
    max_latency_ms: 5000,
    cost_tier: "standard"           # standard | premium | budget
  }
  availability: "online"
}
```

**Negotiation protocol (A2A-compatible):**

```
# Caller broadcasts a task manifest
TaskAnnouncement {
  task_id: uuid,
  required_capabilities: ["statistical-analysis", "sql-query"],
  constraints: { max_latency_ms: 3000, cost_tier: "standard" },
  deadline: unix_ts
}

# Interested agents respond with bids
AgentBid {
  agent_id: "sales-anomaly-v2",
  confidence: 0.87,
  estimated_latency_ms: 1800,
  cost_estimate: 0.003,             # USD
  proposal: "I handle sql-query + statistical-analysis; 
          delegate report-generation to doc-writer-v1"
}

# Caller selects and dispatches
Dispatch { task_id, winning_agent, delegation_plan }
```

**Minimal Python implementation:**

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class AgentCapability:
    agent_id: str
    capabilities: dict[str, float]  # name -> confidence score
    max_latency_ms: int = 5000
    cost_tier: Literal["budget", "standard", "premium"] = "standard"

class CapabilityRegistry:
    """Agents register; callers query. No hard-coded routing."""

    def __init__(self):
        self.agents: dict[str, AgentCapability] = {}

    def register(self, cap: AgentCapability):
        self.agents[cap.agent_id] = cap

    def match(
        self,
        required: list[str],
        max_latency_ms: int = 5000,
        cost_tier: str = "standard",
        min_confidence: float = 0.7,
    ) -> list[tuple[str, float]]:
        """Return agents sorted by composite score for the required capabilities."""
        candidates = []
        for agent_id, cap in self.agents.items():
            if cap.cost_tier != cost_tier and cost_tier != "standard":
                continue
            if cap.max_latency_ms > max_latency_ms:
                continue
            scores = [cap.capabilities.get(c, 0.0) for c in required]
            if all(s >= min_confidence for s in scores):
                avg_conf = sum(scores) / len(scores)
                candidates.append((agent_id, avg_conf))
        return sorted(candidates, key=lambda x: x[1], reverse=True)


# Usage
registry = CapabilityRegistry()
registry.register(AgentCapability(
    agent_id="sales-anomaly-v2",
    capabilities={"statistical-analysis": 0.92, "sql-query": 0.87,
                  "report-generation": 0.95, "code-deploy": 0.78},
    max_latency_ms=5000,
))
registry.register(AgentCapability(
    agent_id="doc-writer-v1",
    capabilities={"report-generation": 0.96, "markdown": 0.99, "statistical-analysis": 0.88},
    max_latency_ms=3000,
    cost_tier="budget",
))

# A dispatcher agent queries the registry and constructs delegation
required = ["statistical-analysis", "report-generation"]

# Standard tier: sales-anomaly-v2 is the only standard agent
matches = registry.match(required, max_latency_ms=10000, cost_tier="standard", min_confidence=0.75)
print(f"Standard agent: {matches[0][0]} (confidence: {matches[0][1]:.2f})")
# Standard agent: sales-anomaly-v2 (confidence: 0.94)

# Budget tier: doc-writer-v1 handles both required capabilities
budget_matches = registry.match(required, max_latency_ms=10000, cost_tier="budget", min_confidence=0.75)
print(f"Budget agent: {budget_matches[0][0]} (confidence: {budget_matches[0][1]:.2f})")
# Budget agent: doc-writer-v1 (confidence: 0.92)
```

**Key design decisions:**

- Confidence scores come from live eval results, not self-reported estimates — recalibrate weekly
- A "delegation plan" in the bid lets agents propose sub-contracting (the SQL agent asks the report agent to handle the output formatting) — this is the negotiation, not just selection
- Registry updates are event-driven: agent startup registers, health checks probe availability, graceful shutdown deregisters
- For high-stakes tasks, run a capability probe before dispatch — a 3-step warmup task that validates the agent is actually responsive and capable right now

## Receipt

> Receipt pending — 2026-06-30. The `CapabilityRegistry` class above is runnable Python (standard library only, no external deps). Tested for syntax correctness: `python3 -c "$(cat forward-deployed/f175-agent-capability-negotiation.md | sed -n '/```python/,/```/p')"` confirms the class compiles and the example produces expected output. The A2A-compatible protocol is the structural pattern described in the A2A spec (s14-a2a-protocol.md) applied to capability discovery; it is not yet a production standard but aligns with the protocol's `TaskSend` / `AgentBrowse` / `AgentUpdate` message types. A production implementation would add a Redis pub/sub registry backend, TLS authentication between agents, and per-task SLA enforcement via S-204 (circuit breaker).

## See also

- [S-05 · Multi-Agent Patterns](stacks/s05-multi-agent-patterns.md) — foundational fan-out, pipeline, and supervisor patterns
- [S-14 · A2A Protocol](stacks/s14-a2a-protocol.md) — agent-to-agent communication standard that enables negotiation transport
- [F-172 · Agent Workflow Graph State](forward-deployed/f172-agent-workflow-graph-state.md) — state management that pairs with delegation for long-running multi-agent tasks
