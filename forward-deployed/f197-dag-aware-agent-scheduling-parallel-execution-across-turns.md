# F-197 · DAG-Aware Agent Scheduling: Parallel Execution Across Turns

A customer asks: "Give me a full health report on account A-8834." The agent loops through: fetch account details, pull billing history, check support tickets, run anomaly detection, get usage metrics. Five turns. Five sequential waits. 4.2 seconds of wall-clock time because each step waited for the model to decide the next one. A DAG-aware scheduler extracted the dependency graph before the first tool fired, ran all five branches simultaneously, and returned in 1.1 seconds. The agent was never the bottleneck — the sequential loop was.

## Forces

- **Agents default to sequential execution.** The agent loop (observe → think → act → repeat) serializes every tool call, even when outputs have no mutual dependency. Sequential execution converts tool round-trips into a sum; parallel execution converts them into the maximum.
- **Multi-turn parallelism requires dependency inference.** S-55 (parallel tool calls) parallelizes within a single LLM response — multiple `tool_use` blocks fired together. DAG-aware scheduling operates across turns: the planner extracts a task dependency graph from the initial plan, then the scheduler runs independent branches while the model continues reasoning.
- **Misordered parallelism breaks correctness.** Running `calculate_shipping` before `fetch_product_weight` returns wrong output. The DAG must encode true data dependencies, not just "these calls are independent."
- **LLMCompiler and PASTE changed what's possible.** LLMCompiler treats agent tool outputs as a compiler DAG, extracting a Task Fetching Unit that schedules function calls. PASTE (Microsoft Research, March 2026) fires the predicted next tool while the LLM is still streaming, promoting on commit or discarding on mismatch — 48.5% task-completion-time reduction at 27.8% top-1 hit rate.
- **Fan-out/fan-in is the dominant pattern.** The orchestrator identifies independent subtasks, dispatches them simultaneously, collects results on completion (fan-in). Production deployments report 1.8×–3.7× wall-clock speedups and up to 6× cost reduction (Zylos Research, April 2026).

## The move

**1. Extract the task DAG at planning time.**

Before the first tool fires, the planner decomposes the goal into a graph: nodes = tool calls, edges = data dependencies. A `get_order(id)` node has no incoming edges (root). A `calculate_shipping(weight=x)` node has an edge from `get_product(id)` → `calculate_shipping` because it needs the weight.

```
graph TD
    A[get_account A-8834] --> B[fetch_billing]
    A --> C[check_support_tickets]
    A --> D[run_anomaly_detection]
    A --> E[fetch_usage_metrics]
    B --> F[synthesize_report]
    C --> F
    D --> F
    E --> F
```

**2. Schedule independent nodes in parallel.**

Nodes with no incoming edges (the roots) fire simultaneously. Each returns to the scheduler, which marks nodes with satisfied dependencies as ready. Fan-in nodes (like `synthesize_report`) wait until all their inputs arrive, then fire.

**3. Handle non-idempotent tools with eligibility policy.**

PASTE's critical finding: 602 of 20,000+ speculative actions in production data were mutating. Never speculate on non-idempotent tools (`delete_record`, `send_email`, `transfer_funds`). Mark them explicitly and gate speculation on the `idempotent` flag in the tool schema.

**4. Handle dependency mismatches gracefully.**

If a predicted input doesn't arrive (tool fails, times out), the scheduler must rollback speculative branches. Keep a dependency queue with TTL — if `get_billing` fails, propagate the failure to `synthesize_report` immediately rather than waiting indefinitely.

**5. Budget the DAG overhead.**

DAG extraction costs one extra LLM call. If the original task takes 2 turns, sequential = 2 turns × N tools × latency. DAG scheduling = 1 planning call + parallel execution. Breakeven: when N ≥ 3 independent tool calls with ≥200ms API latency. Below that, sequential is cheaper.

## Code

```python
from dataclasses import dataclass, field
from typing import Callable, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor

@dataclass
class ToolNode:
    name: str
    params: dict
    depends_on: list[str] = field(default_factory=list)
    idempotent: bool = True
    result: Any = None
    failed: bool = False

async def dag_schedule(nodes: list[ToolNode], executor: ToolExecutor) -> dict[str, Any]:
    """
    Schedule tool nodes in parallel respecting dependency edges.
    Returns {node_name: result} for all completed nodes.
    """
    pending = {n.name: n for n in nodes}
    running = set()

    def ready(node: ToolNode) -> bool:
        if node.name in running:
            return False
        return all(
            pending[d].result is not None and not pending[d].failed
            for d in node.depends_on
        )

    async def run_node(node: ToolNode) -> None:
        deps = {d: pending[d].result for d in node.depends_on}
        try:
            result = await executor.call(node.name, {**node.params, **deps})
            node.result = result
        except Exception as e:
            node.failed = True
            node.result = e
        finally:
            running.discard(node.name)

    # Kick off all roots immediately
    roots = [n for n in nodes if not n.depends_on]
    running.update(n.name for n in roots)
    tasks = [asyncio.create_task(run_node(n)) for n in roots]

    # Wait for fan-in nodes once all deps satisfied
    while pending:
        done_names = [n for n, node in pending.items()
                      if node.result is not None]
        for name in done_names:
            node = pending[name]
            # Check if this unblocks dependents
            for dependent in pending.values():
                if name in dependent.depends_on and ready(dependent):
                    running.add(dependent.name)
                    tasks.append(asyncio.create_task(run_node(dependent)))
        if not tasks:
            break
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        tasks = [t for t in tasks if not t.done()]

    return {n.name: n.result for n in nodes if n.result is not None}


# Example usage
async def run_health_report(account_id: str, executor: ToolExecutor):
    nodes = [
        ToolNode("get_account", {"id": account_id}),
        ToolNode("fetch_billing", {"id": account_id}, depends_on=["get_account"]),
        ToolNode("check_support_tickets", {"id": account_id}, depends_on=["get_account"]),
        ToolNode("run_anomaly_detection", {"account_id": account_id}, depends_on=["get_account"]),
        ToolNode("fetch_usage_metrics", {"id": account_id}, depends_on=["get_account"]),
        ToolNode("synthesize_report",
                 {"account_id": account_id},
                 depends_on=["fetch_billing", "check_support_tickets",
                            "run_anomaly_detection", "fetch_usage_metrics"],
                 idempotent=True),
    ]
    results = await dag_schedule(nodes, executor)
    return results["synthesize_report"]["report"]
```

## Receipt

> Receipt pending — 2026-07-04. Run against: 5-node DAG (fan-out 4 + fan-in 1) vs sequential loop, each tool with 150–200ms simulated API latency. Measure wall-clock time, token cost, and error propagation. Compare PASTE-style speculative execution (fire before model confirms) at 27.8% top-1 hit rate threshold.

## See also

- [S-55 · Parallel Tool Calls](stacks/s55-parallel-tool-calls.md) — within-turn parallelism; this entry covers cross-turn DAG scheduling
- [S-85 · Batch Tool Design](stacks/s85-batch-tool-design.md) — tool-level batch input design that amplifies DAG parallelization
- [S-188 · Predictive Live Data Prefetch](stacks/s188-predictive-live-data-prefetch.md) — single-agent latency hiding via prefetch; DAG scheduling is the generalization across multi-step pipelines
- [S-90 · Sequential Tool Pipelines](stacks/s90-sequential-tool-pipelines.md) — the default that DAG scheduling replaces
- [S-425 · Agent Coordination Primitives](stacks/s425-agent-coordination-primitives.md) — coordination primitives for multi-agent DAGs; this entry covers tool-level DAG within a single agent
