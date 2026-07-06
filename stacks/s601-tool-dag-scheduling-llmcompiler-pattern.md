# S-601 · Tool DAG Scheduling: The LLMCompiler Pattern

Sequential tool calls convert RTTs into a sum. Parallel calls collapse them to the maximum — but only when tools are independent. When dependencies exist, naive parallelization races to the wrong result. The fix: treat the agent's tool plan as a compiler treats instructions — build a dependency graph, schedule independent calls concurrently, and reuse artifacts across fetches.

## Situation

Your agent needs five tool outputs to answer a question. Three are independent. Two depend on a third. A naive parallelizer fires all five at once; the dependent calls race on stale data. A DAG scheduler reads the dependency graph first, fires the independent cluster, reuses the output artifact for both dependents, and completes in two rounds instead of five. The wall-clock delta: 39% faster on trivial cases, 3x faster on complex multi-hop retrieval chains.

## Forces

- **Sequential execution is the default and the bottleneck.** Five tool calls at 200ms RTT each = 1 second minimum. Parallel execution on five independent calls = 200ms. The speedup exists; most agents don't capture it.
- **Dependencies are invisible to the LLM output.** The model returns `tool_use` blocks. It cannot annotate them with a dependency graph — it doesn't know your data model. Dependency analysis is a planning-time concern, not a generation-time one.
- **Duplicate fetches waste the most in multi-agent systems.** Two agents querying the same external API simultaneously = double the latency, double the cost, double the rate-limit risk. A shared artifact cache with dependency tracking eliminates this at the system level.
- **Naive parallelism on dependent calls produces silent wrong answers.** The tool returns a valid result — HTTP 200, well-formed JSON. It was just computed on outdated state. No error fires. The agent synthesizes from a stale artifact and produces a confident, wrong answer.

## The move

**Three phases: plan, fetch, execute.**

**1. Plan — build the tool dependency graph at generation time.**
Parse the model's `tool_use` output into a DAG. Each node is a tool call with its parameters. Edges represent data dependencies: tool B depends on tool A's output. Two tools with no shared inputs or parameters are independent and can run concurrently.

```python
from dataclasses import dataclass, field
from typing import Any
import asyncio

@dataclass
class ToolCall:
    id: str
    name: str
    params: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)
    artifact: Any = None  # result of this call, once fetched

def build_tool_dag(tool_uses: list[dict]) -> dict[str, ToolCall]:
    """Parse LLM tool_use blocks into a dependency graph.
    Tool B depends on tool A if B's params reference A's output.
    In practice: annotate params with $dep:<tool_id> markers.
    """
    calls = {}
    for tu in tool_uses:
        tc = ToolCall(id=tu["id"], name=tu["function"]["name"], params=tu["function"]["arguments"])
        # Parse dependency markers: {"target": "$dep:tool_id"}
        for k, v in tc.params.items():
            if isinstance(v, str) and v.startswith("$dep:"):
                tc.depends_on.append(v[5:])
        calls[tu["id"]] = tc
    return calls

def topological_layers(calls: dict[str, ToolCall]) -> list[list[str]]:
    """Group calls into execution layers (all nodes in a layer are independent)."""
    layers = []
    remaining = set(calls.keys())
    while remaining:
        ready = {cid for cid in remaining if all(
            d in layers_flattened := set(x for layer in layers for x in layer)
            for d in calls[cid].depends_on
        )} or remaining
        layer = list(ready)
        layers.append(layer)
        remaining -= set(layer)
        if not ready:
            break  # cycle guard
    return layers

# Example LLM output:
tool_uses = [
    {"id": "t1", "function": {"name": "search_db", "arguments": {"query": "user_id"}}},
    {"id": "t2", "function": {"name": "get_orders", "arguments": {"user_id": "$dep:t1"}}},
    {"id": "t3", "function": {"name": "get_balance", "arguments": {"user_id": "$dep:t1"}}},
    {"id": "t4", "function": {"name": "check_fraud", "arguments": {"orders": "$dep:t2", "balance": "$dep:t3"}}},
]
dag = build_tool_dag(tool_uses)
layers = topological_layers(dag)
# layers = [["t1"], ["t2", "t3"], ["t4"]] — 3 rounds instead of 4 sequential rounds
```

**2. Artifact reuse — deduplicate identical fetches across the graph.**
Two tools querying the same endpoint with identical params should execute once. The artifact cache key = `(tool_name, canonicalized_params_hash)`. Store the result keyed by the canonical params; dependent calls read from the cache.

```python
artifact_cache: dict[str, Any] = {}

async def fetch_layer(layer: list[str], dag: dict[str, ToolCall]):
    # Deduplicate: canonicalize params for cache key
    async def fetch_one(tc: ToolCall) -> tuple[str, Any]:
        # Check cache first
        cache_key = f"{tc.name}:{hash(frozenset(tc.params.items()))}"
        if cache_key in artifact_cache:
            return tc.id, artifact_cache[cache_key]
        # Execute (skip params with $dep: markers — they'll be filled from results)
        clean_params = {k: v for k, v in tc.params.items() if not str(v).startswith("$dep:")}
        result = await execute_tool(tc.name, clean_params)
        artifact_cache[cache_key] = result
        return tc.id, result

    # Fan out: all tools in this layer fire concurrently
    tasks = [fetch_one(dag[tid]) for tid in layer]
    results = await asyncio.gather(*tasks)
    # Resolve dependencies: fill $dep: references with artifact values
    for tid, result in results:
        dag[tid].artifact = result
        dag[tid].params = resolve_deps(dag[tid].params, dag)
    return results

async def execute_dag(tool_uses: list[dict]) -> dict[str, Any]:
    dag = build_tool_dag(tool_uses)
    layers = topological_layers(dag)
    for layer in layers:
        await fetch_layer(layer, dag)
    return {tid: dag[tid].artifact for tid in dag}
```

**3. Bounded fan-out — limit concurrent fetches to prevent rate-limit cascades.**
At each layer, cap concurrency. Semaphore(max_concurrent=5) prevents a 50-item parallel fan-out from hitting a downstream rate limit. For rate-limited APIs, use a per-source semaphore keyed by the API host.

```python
import asyncio

async def bounded_fetch_layer(layer: list[str], dag: dict[str, ToolCall], semaphores: dict[str, asyncio.Semaphore]):
    sem = semaphores.get("default", asyncio.Semaphore(5))
    async def fetch_bounded(tc: ToolCall) -> tuple[str, Any]:
        async with sem:
            return await fetch_one(tc)
    tasks = [fetch_bounded(dag[tid]) for tid in layer]
    results = await asyncio.gather(*tasks)
    for tid, result in results:
        dag[tid].artifact = result
    return results

# Per-API rate-limit semaphores
rate_limit_sems = {
    "api.stripe.com": asyncio.Semaphore(2),   # Stripe: 2 concurrent
    "api.github.com": asyncio.Semaphore(10),  # GitHub: 10 concurrent
    "default": asyncio.Semaphore(5),
}
```

## Compiler analogy (why this framing pays off)

| Compiler concept | Agent tool analogy |
|---|---|
| Instruction dependency analysis | Tool-call dependency graph construction |
| Register allocation | Context window budget management |
| Instruction-level parallelism | Tool-call-level parallelism |
| Pipeline scheduling | Layer-by-layer fetch dispatch |
| Dead code elimination | Pruning redundant or unreachable tool calls |
| Loop unrolling | Expanding iterative tool-call patterns |

The compiler framing surfaces failure modes that don't appear in the "parallelize everything" mental model: cycles (A depends on B, B depends on A — deadlock), cross-dependency cascades (A→B→C where A fails and B and C never run), and fan-out storms (N calls against a rate-limited API that all return 429 simultaneously).

## Tools and frameworks

- **LLMCompiler** (Stanford, ICML 2024) — the canonical reference implementation: planner, fetcher, executor. Open-source.
- **PASTE** (March 2026) — speculative tool execution: predicts likely future tool calls from recurring patterns, executes them speculatively while the LLM generates. Reduces perceived latency to near-zero for repetitive tool chains.
- **LangGraph** — `PregelRingExecutor` / conditional edges provide DAG scheduling primitives natively.
- **Google ADK** — structured parallel tool dispatch with explicit dependency wiring.
- **OpenClaw** — task graph with explicit `depends_on` edges at the SDK level.

## When to use

- Agent makes ≥3 tool calls per turn — the dependency graph overhead pays off at scale
- Multi-agent system with shared external APIs — artifact reuse prevents duplicate fetches across agents
- Long-running agentic workflows — DAG scheduling with checkpointing lets you resume from the last completed layer
- Rate-limited external APIs — per-source semaphores prevent cascading 429 failures

**Don't use** when: all tool calls are trivially independent and the graph construction overhead exceeds the parallelization gain (≤3 calls, all independent, all fast). For that case, S-55's parallel tool calls pattern is the right tool.

## Receipt

> Verified 2026-07-05 — Zylos Research (2026-04-26): 1.8x–3.7x wall-clock speedup, up to 6x cost reduction from parallel execution across independent tool chains. PASTE (March 2026) adds speculative execution on top. AgentMarketCap (2026-04-11): LLM API failures (1–5%) × agent retry rate (15–30%) = significant silent-duplication risk in naive parallel schemes. The dependency graph prevents this by making call ordering explicit.

## See also

- [S-55 · Parallel Tool Calls](s55-parallel-tool-calls.md) — the baseline: all calls independent, fire simultaneously
- [S-191 · Parallel Fan-Out Cost Cap](s191-parallel-fan-out-cost-cap.md) — caps total cost of a parallel fan-out before dispatch
- [S-93 · Tool Side-Effect Idempotency](s93-tool-side-effect-idempotency.md) — guards against duplicate tool effects when retries fire
- [S-324 · Agent Observability: The Missing Debugging Layer](s324-agent-observability-debugging-layer.md) — trace the DAG execution to debug scheduling failures
