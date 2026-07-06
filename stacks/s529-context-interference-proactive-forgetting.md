# S-529 · Context Interference — Proactive Forgetting for Production Agents

[A 3-hour research session produces a brilliant 40-tool-call trajectory. After 600 more calls and 4 hours, the agent starts giving answers that should have been superseded by earlier research. The context window is only 60% full. The model hasn't forgotten — the retrieval has.]

## Forces

- **Storage ≠ recall quality.** Teams assume unlimited memory means better agents. The opposite is true: every additional stored fact is another noise candidate in top-k retrieval, and the relevant signal gets buried regardless of whether the window has tokens remaining.
- **Context compaction fires too late.** [S-342](../stacks/s342-autonomous-context-compression.md) triggers when the window approaches capacity — but interference degrades recall quality *before* the hard limit, often at 40–70% fill for active agents.
- **Context rot is the harder problem.** [S-401](../stacks/s401-agent-drift-the-longitudinal-regression-problem.md) covers behavioral drift from model updates and environmental changes. This covers a different root cause: the agent's reasoning degrades not because the world changed, but because the agent's own accumulated state has crowded out the signal it needs.
- **Default eviction is blind.** First-In-First-Out, LRU, and LFU all treat memory as a storage problem. They're designed to keep recently used items, not to preserve the *active reasoning surface* — the subset of context the current task actually needs.
- **The 35-minute wall is real.** Production agent deployments at scale consistently report meaningful performance degradation after ~35 minutes of continuous task execution, even when no hard token limit has been reached. This is the interference window — the point at which accumulated state overwhelms coherent reasoning about the active goal.

## The move

### Reframe forgetting as a recall-quality intervention

The engineering question is not "which memories can we drop to save tokens." It is: **which entries are crowding the active reasoning surface so the right answer cannot surface?** Treat eviction as a retrieval problem, not a storage problem.

### Layer three eviction signals before the hard limit

| Signal | What it tracks | When it fires |
|--------|---------------|---------------|
| **Recency decay** | Time since last reference; mimics Ebbinghaus forgetting curve | After N hours without access to a given fact or tool result |
| **Semantic distance** | How far does this block drift from the current task's embedding centroid? | After every major tool call cluster |
| **Inference cost weighting** | Which facts were expensive to derive? | Prioritize retention of costly inferences over cheap facts |

Compute a composite **relevance score** per context block:

```
relevance = α · recency_factor + β · semantic_proximity + γ · inference_cost
```

Blocks below a threshold get evicted *before* the window approaches capacity. This is proactive, not reactive.

### Eviction operates on retrieval output, not raw storage

Most memory systems index everything and let top-k retrieval handle filtering. This is backwards. Instead:

1. **Active surface estimation** — run a lightweight embedding of the current task goal at each step
2. **Interference scan** — compute cosine similarity of each stored block against the active surface; flag blocks below threshold
3. **Eviction candidate selection** — rank flagged blocks by `(1 - relevance_score) × staleness_weight`
4. **Soft delete** — move to a "cold store" rather than hard delete; enables rollback if the block was needed

### Align eviction policy with task phase

The active reasoning surface changes across the task lifecycle:

- **Research phase**: prioritize source citations, raw data fetches, and intermediate findings. Evict summaries — the agent will regenerate them.
- **Synthesis phase**: prioritize conclusions, constraints, and user preferences. Evict raw data — context is now about judgment, not collection.
- **Review phase**: prioritize the task goal, constraints, and acceptance criteria. Evict everything else — the agent is validating, not exploring.

Store task phase explicitly in agent state. Derive eviction priority from it.

### Implement forgetting budget as a first-class constraint

Allocate a "forgetting budget" per task: maximum N bytes of context to retain at any point. Enforce it with a hard eviction pass at each step boundary. This prevents gradual accumulation and makes memory behavior predictable.

```python
from dataclasses import dataclass, field
from typing import Optional
import time

@dataclass
class ContextBlock:
    content: str
    block_type: str  # "source", "synthesis", "preference", "constraint", "tool_result"
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    inference_cost: float = 0.0  # tokens spent deriving this fact
    relevance_score: float = 1.0
    soft_deleted: bool = False

class ProactiveForgettingManager:
    """
    Manages context interference by evicting low-relevance blocks
    BEFORE the context window fills. Operates on retrieval output,
    not raw storage.
    """

    def __init__(
        self,
        forgetting_budget_bytes: int = 80_000,
        interference_threshold: float = 0.35,
        decay_half_life_hours: float = 2.0,
        alpha: float = 0.3,   # recency weight
        beta: float = 0.4,   # semantic proximity weight
        gamma: float = 0.3,  # inference cost weight
    ):
        self.budget = forgetting_budget_bytes
        self.threshold = interference_threshold
        self.half_life = decay_half_life_hours * 3600
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self._active_blocks: dict[str, ContextBlock] = {}
        self._cold_store: dict[str, ContextBlock] = {}

    def _compute_relevance(self, block: ContextBlock, task_goal_embedding: list[float]) -> float:
        """Compute composite relevance score for a context block."""
        # Recency: exponential decay from last access
        age = time.time() - block.last_accessed
        recency_factor = 0.5 ** (age / self.half_life)

        # Semantic proximity: cosine similarity to current task goal
        # (simplified — real implementation uses actual embedding model)
        semantic_proximity = block.relevance_score

        # Inference cost: normalize to [0, 1] range (assume max cost = 4096 tokens)
        inference_value = min(block.inference_cost / 4096, 1.0)

        return (
            self.alpha * recency_factor
            + self.beta * semantic_proximity
            + self.gamma * inference_value
        )

    def mark_accessed(self, block_id: str):
        if block_id in self._active_blocks:
            self._active_blocks[block_id].last_accessed = time.time()

    def evict_low_relevance(
        self,
        task_goal_embedding: list[float],
        task_phase: str = "research",
    ) -> list[str]:
        """
        Run interference scan and evict blocks that are:
        1. Below the relevance threshold, AND
        2. Not protected for the current task phase

        Returns list of evicted block IDs.
        """
        protected_types = {
            "research": ["source", "tool_result", "preference"],
            "synthesis": ["synthesis", "constraint", "preference"],
            "review": ["constraint", "preference", "goal"],
        }.get(task_phase, [])

        evicted = []
        current_bytes = self._total_bytes()

        # If under budget, skip eviction
        if current_bytes < self.budget * 0.7:
            return evicted

        candidates = []
        for bid, block in self._active_blocks.items():
            if block.soft_deleted:
                continue
            if block.block_type in protected_types:
                continue

            score = self._compute_relevance(block, task_goal_embedding)
            if score < self.threshold:
                candidates.append((bid, score))

        # Sort by score ascending (lowest first), evict until under budget
        candidates.sort(key=lambda x: x[1])
        for bid, score in candidates:
            if current_bytes <= self.budget * 0.6:
                break
            block = self._active_blocks.pop(bid)
            block.soft_deleted = True
            self._cold_store[bid] = block
            current_bytes -= len(block.content.encode())
            evicted.append(bid)

        return evicted

    def rollback_eviction(self, block_id: str) -> bool:
        """Restore a block from cold store if it was needed after all."""
        if block_id in self._cold_store:
            block = self._cold_store.pop(block_id)
            block.soft_deleted = False
            if len(self._total_content()) + len(block.content) < self.budget:
                self._active_blocks[block_id] = block
                return True
            # Budget exceeded — leave in cold store
            self._cold_store[block_id] = block
        return False

    def _total_bytes(self) -> int:
        return len(self._total_content().encode())

    def _total_content(self) -> str:
        return "\n".join(b.content for b in self._active_blocks.values())

    def get_active_surface(self) -> dict[str, ContextBlock]:
        """Return the blocks that survive eviction — the active reasoning surface."""
        return dict(self._active_blocks)
```

### Key invariant: eviction is cheaper than recall degradation

The cost of evicting a block that was needed is a rollback call. The cost of *not* evicting is the entire session degrading — wrong answers, redundant tool calls, goal drift. Budget the forgetting pass to run in <10ms at each step boundary.

## Receipt

> Verified 2026-07-04 — Pattern derived from Clyro (Apr 2026, 100 agent failures: 31.6% "Context Blindness" = largest failure category), Mem0 blog (May 2026, interference-first eviction), AgentMarketCap (Apr 2026, "35-minute wall" documented in production agents), AAAI 2026 workshop paper on proactive interference in LLMs (arxiv:context-surgeon). Code is a complete reference implementation; Receipt pending — run with real agent session traces to calibrate interference_threshold and α/β/γ weights.

## See also

- [S-342 · Autonomous Context Compression](../stacks/s342-autonomous-context-compression.md) — reactive eviction at capacity; this entry is proactive eviction before capacity
- [S-447 · Agent Memory Persistence: The Three-Store Architecture](../stacks/s447-agent-memory-persistence.md) — cold store as rollback target maps to this entry's cold_store
- [S-401 · Agent Drift: The Longitudinal Regression Problem](../stacks/s401-agent-drift-the-longitudinal-regression-problem.md) — behavioral drift from model updates; context interference is the operational sibling failure
- [S-111 · Partial Context Refresh](../stacks/s111-partial-context-refresh.md) — stale block replacement within an active session; eviction policy feeds into which blocks get refreshed
