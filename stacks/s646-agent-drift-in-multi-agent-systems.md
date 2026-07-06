# S-646 · Agent Drift in Multi-Agent Systems

Your 4-agent orchestration worked at launch. Six weeks in, task success is down 42% — but no model updated, no code changed, no alert fired. The agents are drifting: progressively deviating from their design intent without any explicit trigger. This is agent drift, and it's the silent failure mode of production multi-agent systems.

## Forces

- **Agents amplify their own behavior over time.** Multi-agent systems re-enter the same goal states repeatedly. Small deviations compound: Agent A's slightly shifted routing preference feeds a slightly biased context to Agent B, which slightly corrupts Agent C's output, which slightly miscalibrates Agent D's decision. By the time any individual step looks wrong, the system has been wrong for days.
- **Standard monitoring catches crashes, not drift.** Latency, error rates, and token counts are all normal during drift. The agents are executing successfully — they're just succeeding at the wrong thing. F-26 (single-model behavioral drift detection) catches provider-side model changes; it doesn't catch the emergent structural drift that arises from multi-agent interaction dynamics.
- **Drift hides inside the structure that agents create.** Agents build shared plans, update joint state, and make coordinated decisions. The drift manifests in *what they agree on*, not in any individual failure. No single-agent monitoring surface sees it.
- **Coordinating through LLM-generated artifacts compounds the problem.** Agents that synthesize shared documents, update joint memory, or build consensus through natural language are particularly vulnerable — the medium itself is non-deterministic, so drift in the shared artifact propagates back into individual agent behavior.
- **The interaction surface grows faster than the monitoring surface.** Each new agent added to a system creates O(n²) pairwise coordination surfaces. Drift detection that works for 2 agents breaks silently at 4, where human operators can no longer manually audit the coordination graph.

## The move

**Measure the three drift dimensions independently, then compose them into the Agent Stability Index (ASI).**

| Dimension | What it measures | Primary signal |
|-----------|-----------------|----------------|
| **Semantic drift** | Progressive deviation from original intent while remaining syntactically valid | Delta between initial vs. current output distribution per agent |
| **Coordination drift** | Breakdown in multi-agent consensus mechanisms | Inter-agent agreement rate over rolling windows |
| **Behavioral drift** | Emergence of unintended strategies | Tool usage distribution shift, reasoning pathway variance |

### The Agent Stability Index (ASI)

ASI is a composite score across 12 dimensions. For production pragmatism, track the 4 highest-signal ones:

```
ASI = f(
  response_consistency,      # Same input → same output (sampled weekly)
  tool_usage_distribution,   # Tool call ratios stable?
  reasoning_pathway_stability,# Reasoning chain structure preserved?
  inter_agent_agreement      # Sub-agents converge on shared facts?
)
```

**Threshold**: ASI < 0.70 triggers remediation campaign. Below 0.50 is active degradation.

### Three mitigation strategies (67–81% drift reduction)

**1. Episodic memory consolidation** — Every N interactions, agents jointly review and correct the shared state they've accumulated. Drift accumulates in shared memory; consolidation resets the ground truth. Schedule it like garbage collection: don't wait for a crash, run it proactively.

**2. Drift-aware routing** — Agents that detect low-confidence outputs from peers route to a verification sub-agent rather than propagating uncertainty. Don't trust a degraded signal; escalate to a grounded agent.

**3. Behavioral anchoring** — Pin each agent's core behavior to a compact "anchor prompt" — a short, immutable description of its role, constraints, and success criteria. Re-inject the anchor after every K tool calls. Anchoring prevents drift from accumulating past the point of recovery.

### Implementation sketch

```python
import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Callable

@dataclass
class DriftMetrics:
    response_consistency: float  # 0-1
    tool_usage_drift: float       # 0-1 (higher = more drift)
    reasoning_stability: float    # 0-1
    inter_agent_agreement: float # 0-1

class AgentStabilityMonitor:
    def __init__(self, window: int = 200):
        self.window = window
        self.agent_histories: dict[str, list[dict]] = {}

    def record(self, agent_id: str, step: dict):
        """Record one agent step for drift analysis."""
        self.agent_histories.setdefault(agent_id, []).append(step)
        if len(self.agent_histories[agent_id]) > self.window:
            self.agent_histories[agent_id].pop(0)

    def compute_asi(self) -> DriftMetrics:
        """Compute Agent Stability Index across all tracked agents."""
        tool_distributions = {
            aid: Counter(h["tool"] for h in history)
            for aid, history in self.agent_histories.items()
        }

        # Semantic drift: compare first-quartile vs last-quartile outputs
        consistency_scores = []
        for aid, history in self.agent_histories.items():
            q1_outputs = set(h.get("output_hash") for h in history[:len(history)//4])
            q4_outputs = set(h.get("output_hash") for h in history[-len(history)//4:])
            overlap = len(q1_outputs & q4_outputs) / max(len(q1_outputs | q4_outputs), 1)
            consistency_scores.append(overlap)

        # Tool usage drift: compare distribution stability
        tool_drift_scores = []
        for aid, dist in tool_distributions.items():
            if len(dist) < 2:
                tool_drift_scores.append(0.0)
                continue
            total = sum(dist.values())
            probs = [v / total for v in dist.values()]
            entropy = -sum(p * math.log2(p) for p in probs if p > 0)
            tool_drift_scores.append(entropy)  # Higher entropy = more tool diversity drift

        # Inter-agent agreement: shared fact convergence
        agreement_scores = []
        agent_ids = list(tool_distributions.keys())
        for i, a in enumerate(agent_ids):
            for b in agent_ids[i+1:]:
                # Measure whether agents agree on shared-state facts
                a_facts = {h.get("fact_key") for h in self.agent_histories[a] if "fact_key" in h}
                b_facts = {h.get("fact_key") for h in self.agent_histories[b] if "fact_key" in h}
                if a_facts | b_facts:
                    overlap = len(a_facts & b_facts) / len(a_facts | b_facts)
                    agreement_scores.append(overlap)

        import math
        return DriftMetrics(
            response_consistency=sum(consistency_scores) / max(len(consistency_scores), 1),
            tool_usage_drift=sum(tool_drift_scores) / max(len(tool_drift_scores), 1),
            reasoning_stability=0.7,  # Requires custom reasoning trace parser
            inter_agent_agreement=sum(agreement_scores) / max(len(agreement_scores), 1),
        )

    def anchor(self, agent_id: str, anchor_prompt: str) -> str:
        """Re-inject behavioral anchor after K steps."""
        return f"\n[ANCHOR] Remember: {anchor_prompt} [/ANCHOR]"

# --- Usage ---
monitor = AgentStabilityMonitor(window=200)
for step in agent_loop:
    monitor.record(agent_id=step["agent"], step=step)
    if len(monitor.agent_histories[step["agent"]]) % 50 == 0:
        asi = monitor.compute_asi()
        if asi.response_consistency < 0.70:
            # Trigger episodic consolidation
            trigger_consolidation()
        if sum([asi.tool_usage_drift, asi.inter_agent_agreement]) / 2 > 0.3:
            # Re-anchor agents
            for aid in monitor.agent_histories:
                inject_anchor(aid, ANCHOR_PROMPTS[aid])
```

## Receipt

> Verified 2026-07-05 — Pattern from arXiv:2601.04170 (Rath, Jan 2026): simulation-based analysis showing 42% task success reduction and 3.2x human intervention increase from unchecked drift. Three mitigation strategies (episodic consolidation, drift-aware routing, behavioral anchoring) achieve 67–81% drift reduction. ASI metric framework across 12 dimensions. Code example is structural pseudocode illustrating the monitoring and anchoring pattern; not runnable against a live multi-agent system without a trace integration layer.

## See also

[S-516 · Trajectory-Level Loop Detection](s516-trajectory-level-loop-detection.md) · [F-26 · Behavioral Drift Detection](../forward-deployed/f26-behavioral-drift-detection.md) · [S-637 · The Observability–Evals Gap](s637-the-observability-evals-gap-why-debugging-multi-agent-systems-is-still-guesswork.md) · [F-179 · Multi-Agent Coordination Failures](../forward-deployed/f179-multi-agent-coordination-failures.md)
