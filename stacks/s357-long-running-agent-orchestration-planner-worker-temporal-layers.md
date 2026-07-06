# S-357 · Long-Running Agent Orchestration: The Planner-Worker Temporal Layer Pattern

A single agent handles a 10-minute task. But a 10-hour task — research, code review, PR automation, enterprise workflow — breaks it. Performance degrades after 35 minutes of human time. Failure rates compound. Context gets poisoned. The model re-derives intent it already resolved. Long-running agents need a different architecture: explicit temporal layers that separate *what we're doing* from *what we're doing right now*.

## Forces

- **Task duration doubles every 7 months.** Zylos Research tracks AI task duration from minutes to hours. By late 2026, agents routinely handle 2-hour tasks. By 2028, full workdays. Teams building single-agent monoliths will hit the wall.
- **Doubling task duration quadruples the failure rate.** This is not a linear degradation — it is exponential. Without structured recovery mechanisms, a 4-hour task is 16x more likely to fail than a 1-hour task.
- **The model re-derives strategic intent on every operational call.** A worker agent that calls `get_customer_record()` should not re-derive the business goal that led to this action. Context separation is a performance feature, not just an organizational one.
- **Planner-Worker reduces cost by up to 90%.** A capable model (Sonnet 4 / o4) plans; a cheap model (Haiku / Llama 3.1 8B) executes. The planning call is ~5% of total steps; the execution calls are ~95%.
- **Enterprise adoption surging 8x.** 5% of enterprises in early 2025 → 40% by end of 2026. Long-running agents are no longer research — they are production infrastructure.

## The move

The **CORPGEN** pattern (Corporate Agent Generation, Zylos Research, 2026) defines three temporal layers:

```
Strategic (monthly)    ← High-level goals, milestones. Rarely updated.
       ↓
Tactical (daily)       ← Actionable tasks with priority ranking. Updated each session.
       ↓
Operational (per-cycle) ← Individual tool calls. Selected from current state + memory.
```

**The dividing line**: a model making an operational decision does not re-derive strategic intent. It retrieves the tactical context and acts within it. This alone produces a **3.5x improvement** in task completion rate over standalone agents (15.2% vs 4.3% at 100% workload).

### Minimal working example

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, Any


class Layer(Enum):
    STRATEGIC = "strategic"   # months
    TACTICAL = "tactical"    # days
    OPERATIONAL = "operational"  # minutes


@dataclass
class PlanNode:
    id: str
    layer: Layer
    description: str
    status: str = "pending"  # pending | in_progress | done | blocked
    children: list["PlanNode"] = field(default_factory=list)
    parent_id: str | None = None
    priority: int = 0
    max_retries: int = 3
    retry_count: int = 0


class PlannerAgent:
    """Strategic + Tactical planner. Called infrequently, uses capable model."""

    def __init__(self, capable_client):
        self.client = capable_client

    def decompose(self, goal: str, context: dict) -> list[PlanNode]:
        prompt = f"""Decompose this goal into STRATEGIC → TACTICAL layers.
Goal: {goal}
Context: {context}

Return a JSON plan with exactly two tiers."""
        # In production: use o4/GPT-4.5 class model
        response = self.client.messages.create(
            model="claude-sonnet-4",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        # Parse → return list[PlanNode] at TACTICAL layer
        return self._parse_plan(response.content)

    def replan(self, failed_node: PlanNode, context: dict) -> PlanNode:
        """Replan around a blocked node — called only on failure."""
        prompt = f"""Task blocked: {failed_node.description}
Context: {context}
Replan: decompose into new operational steps that avoid the blocking condition."""
        response = self.client.messages.create(
            model="claude-sonnet-4",
            messages=[{"role": "user", "content": prompt}]
        )
        return self._parse_single_node(response.content)


class WorkerAgent:
    """Operational executor. Called per step, uses cheap model."""

    def __init__(self, cheap_client, tools: list):
        self.client = cheap_client
        self.tools = tools

    def execute(self, node: PlanNode, memory: Any) -> dict:
        """Execute ONE tactical node. Do not re-derive intent."""
        # Retrieve tactical context from memory — do NOT re-call planner
        ctx = memory.retrieve(f"tactical:{node.parent_id}")
        prompt = f"""You are executing: {node.description}
Tactical context: {ctx}
Available tools: {[t.name for t in self.tools]}

Execute ONE step. Return tool call or final answer."""
        response = self.client.messages.create(
            model="claude-haiku-4",  # Cheap model — no planning needed
            messages=[{"role": "user", "content": prompt}],
            tools=[{"name": t.name, "description": t.description} for t in self.tools]
        )
        return self._process_response(response)


class Orchestrator:
    """Drives the three-layer loop. Calls planner sparingly, worker frequently."""

    def __init__(self, planner: PlannerAgent, worker: WorkerAgent, memory: Any):
        self.planner = planner
        self.worker = worker
        self.memory = memory
        self.plan: list[PlanNode] = []

    def run(self, goal: str, context: dict) -> dict:
        # LAYER 1: Strategic + Tactical decomposition (capable model, one call)
        self.plan = self.planner.decompose(goal, context)
        self.memory.store("strategic:current", self.plan[0])

        results = []
        for node in self._priority_sorted(self.plan):
            if node.layer != Layer.OPERATIONAL:
                continue
            # LAYER 2: Per-step execution (cheap model, many calls)
            result = self._execute_with_retry(node)
            results.append(result)
            # LAYER 3: Memory write after each step — enables recovery
            self.memory.store(f"result:{node.id}", result)

            if result.get("status") == "blocked":
                # Replan only on failure — not on every step
                replanned = self.planner.replan(node, context)
                self._merge_replan(node, replanned)

        return self._aggregate(results)

    def _execute_with_retry(self, node: PlanNode) -> dict:
        for attempt in range(node.max_retries):
            result = self.worker.execute(node, self.memory)
            if result.get("status") != "failed":
                return result
        return {"status": "blocked", "node": node.id}

    def _priority_sorted(self, nodes: list[PlanNode]) -> list[PlanNode]:
        return sorted(nodes, key=lambda n: n.priority, reverse=True)

    def _merge_replan(self, blocked: PlanNode, replanned: PlanNode):
        """Swap blocked node with replanned alternatives."""
        blocked.status = "blocked"
        self.plan.extend(replanned.children)

    def _aggregate(self, results: list[dict]) -> dict:
        return {"status": "done", "steps": len(results), "results": results}
```

### Key architectural decisions

**1. Planner is called sparingly.** One call per session at most. If the planner is called on every step, you have a single-agent with extra overhead. The planner's job is to set up a tactical context that the worker reads and follows without re-deriving.

**2. Memory is the handoff mechanism.** The worker retrieves `tactical:{parent_id}` from memory. This is the only coupling point between layers. The strategic goal lives at layer 1; the worker never sees it.

**3. Replan only on failure.** A blocked node triggers a replan call. This is the second (and only) time the capable planner fires. Running the planner on every step is the most common planner-worker anti-pattern.

**4. Context isolation per sub-agent.** For complex sub-operations (web research, code execution), isolate the sub-agent's context from the parent. Prevents cross-task contamination. Use separate vector stores or thread IDs.

**5. The 35-minute degradation wall.** Every agent system degrades after 35 minutes of continuous operation. Break long tasks at natural checkpoints (per-tactical-node completion) rather than letting context grow unbounded.

## Receipt

> Verified 2026-07-02 — Zylos Research (CORPGEN, 2026-05-14, 2026-01-16) reports 3.5x task completion improvement (15.2% vs 4.3% baseline) at 100% workload using three-layer decomposition. Planner-Worker pattern shows up to 90% cost reduction (capable model = 5% of calls, cheap model = 95%). 90% enterprise adoption of multi-agent systems in production. Devin (Cognition) deployed at Goldman Sachs: hundreds of thousands of PRs merged, 20% efficiency gains. Task duration doubling every 7 months tracked across METR benchmark (Claude Mythos ≥16hr at 50% reliability, ≥2hr at 80% reliability as of May 2026).

## See also
- [S-341 · The Multi-Agent Coordination Decision](s341-multi-agent-coordination-decision.md) — when to split agents; this entry covers the *intra-agent* layer split, S-341 covers the *inter-agent* split
- [S-352 · Agentic Compensation Keys](s352-agentic-compensation-keys-the-autonomous-retry-era.md) — the retry and undo mechanisms that make replan practical
- [S-355 · Agent Autonomy Levels](s355-agent-autonomy-levels-bounded-autonomy.md) — L0–L5; planner-worker is an L3+ pattern (post-action audit, bounded execution)
- [S-340 · The Agent Stack Is Stratifying](s340-agent-stack-stratification.md) — stack layers; the planner-worker pattern maps to the orchestration + execution layers
