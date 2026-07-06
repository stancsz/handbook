# S-616 · Agentic Plan Caching: The 50% Cost Reduction Pattern

[S-607](s607-the-multi-agent-cost-compounding-problem.md) showed that multi-agent costs compound super-linearly. [S-08](s08-prompt-caching.md) showed that repeated context can be cached at the provider level. Neither closes the biggest gap: the same multi-step plan that cost you $4.20 yesterday will cost you $4.20 again today — because the agent re-plans from scratch every time, even though the task structure is identical.

Agentic Plan Caching (APC) — a Stanford/NeurIPS 2025 paper (Zhang et al.) — fixes this. It extracts structured plan templates from successful agent executions and reuses them for new tasks. The result: 50.31% cost reduction, 27.28% latency reduction, at 96.61% accuracy retention.

## Forces

- **Re-planning is the dominant cost in agentic loops.** For complex tasks, the planning/reasoning phase (CoT, tool selection, self-correction) consumes 60–80% of total tokens. The actual task execution is cheap by comparison.
- **Existing caches fail agents on three axes.** KV caches are model-specific (one model's cache is useless to another). Context caches are data-dependent (different documents break reuse). Neither captures the *structural plan* that transcends specific inputs.
- **Task surfaces repeat even when inputs don't.** A customer support agent handles 500 variants of "I can't log in" per day. A coding agent processes 200 variations of "fix this bug." The underlying plan — diagnose → verify → apply fix → test — is the same every time.
- **The plan cache must adapt, not just retrieve.** Exact-match plan retrieval fails; the system needs a learned similarity function to find plans close enough to adapt.

## The move

APC stores **plan templates** — sequences of tool-call patterns annotated with their preconditions — extracted from successful agent trajectories. When a new task arrives, it retrieves the most similar stored plan, adapts it to the current context, and executes. If no close plan exists, it falls back to full planning.

Four-step cycle: **Extract → Store → Adapt → Retrieve.**

### Plan Template Structure

Each stored template is a (task_signature, tool_sequence, precondition, outcome) tuple.

```python
from dataclasses import dataclass
from typing import Optional
import hashlib

@dataclass
class PlanTemplate:
    task_signature: str          # LLM-as-hash of tool+arg schema (not values)
    tool_sequence: list[str]    # ordered list of tool names
    arg_schema_hash: str        # hash of required argument types
    precondition: str            # natural language description of when this applies
    success_rate: float          # rolling success rate from execution logs
    adaptation_hints: list[str]  # what parameters vary vs. stay fixed

    def signature(self) -> str:
        # Tool-sequence hash — captures STRUCTURE, not specific values
        return hashlib.sha256(
            "|".join(self.tool_sequence).encode()
        ).hexdigest()[:16]

    def similar_to(self, other: "PlanTemplate") -> float:
        # Jaccard similarity on tool sequences
        set_a, set_b = set(self.tool_sequence), set(other.tool_sequence)
        return len(set_a & set_b) / len(set_a | set_b)
```

### APC Cache Manager

```python
class APCache:
    def __init__(self, similarity_threshold: float = 0.75):
        self.templates: dict[str, list[PlanTemplate]] = {}  # sig → candidates
        self.similarity_threshold = similarity_threshold

    def extract_from_trajectory(self, trajectory: dict) -> Optional[PlanTemplate]:
        """Extract a plan template from a completed agent run."""
        steps = trajectory.get("tool_calls", [])
        if len(steps) < 2:
            return None

        tool_seq = [s["tool"] for s in steps]
        task_sig = PlanTemplate(
            task_signature=hashlib.sha256(
                str(sorted(s["tool_schema"].keys())).encode()
            ).hexdigest()[:16],
            tool_sequence=tool_seq,
            arg_schema_hash=hashlib.sha256(
                str(trajectory.get("arg_types", [])).encode()
            ).hexdigest()[:16],
            precondition=trajectory.get("task_description", ""),
            success_rate=1.0,
            adaptation_hints=self._infer_adaptation_hints(steps),
        )
        return task_sig

    def _infer_adaptation_hints(self, steps: list) -> list[str]:
        """Classify each tool arg as FIXED or VARIABLE across this trajectory."""
        hints = []
        for step in steps:
            args = step.get("arguments", {})
            for k, v in args.items():
                # If values differ across similar steps → VARIABLE (cache this)
                # If values are always the same constant → FIXED (don't bother caching)
                hints.append(f"{step['tool']}.{k}={'VAR' if isinstance(v, str) else 'FIXED'}")
        return hints

    def retrieve(self, incoming: PlanTemplate) -> Optional[PlanTemplate]:
        """Find the best reusable plan for this task."""
        candidates = self.templates.get(incoming.signature(), [])
        if not candidates:
            return None

        # Score by: structural similarity + recent success rate
        scored = []
        for t in candidates:
            sim = t.similar_to(incoming)
            score = sim * 0.6 + t.success_rate * 0.4
            scored.append((score, t))

        best_score, best = max(scored)
        if best_score >= self.similarity_threshold:
            return best
        return None

    def adapt(self, template: PlanTemplate, incoming: PlanTemplate) -> list[dict]:
        """Adapt a stored plan to current context: swap VARIABLE args."""
        adapted_steps = []
        for step in template.tool_sequence:
            new_args = {}
            for hint in template.adaptation_hints:
                tool_name, hint_str = hint.rsplit(".", 1)
                if tool_name == step and "=VAR" in hint_str:
                    # Try to extract from incoming task context
                    # (simplified — real impl uses LLM to fill in)
                    pass
            adapted_steps.append({"tool": step, "arguments": new_args})
        return adapted_steps
```

### Integration with a ReAct Agent

```python
class APCAgent:
    def __init__(self, llm, tools: list, cache: APCache):
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.cache = cache
        self.successful_trajectories: list = []

    def run(self, task: str) -> str:
        # Step 1: Attempt plan cache retrieval
        incoming = self._task_to_template(task)
        cached_plan = self.cache.retrieve(incoming)

        if cached_plan:
            print(f"[APC HIT] Adapting plan with {len(cached_plan.tool_sequence)} steps")
            steps = self.cache.adapt(cached_plan, incoming)
            return self._execute_plan(steps, task)

        # Step 2: Fall back to full planning
        print("[APC MISS] Full planning — no reusable plan found")
        trajectory = self._run_react_loop(task)
        self.successful_trajectories.append(trajectory)

        # Step 3: Extract and store on success
        template = self.cache.extract_from_trajectory(trajectory)
        if template:
            sig = template.signature()
            if sig not in self.cache.templates:
                self.cache.templates[sig] = []
            self.cache.templates[sig].append(template)

        return trajectory.get("final_output", "")

    def _task_to_template(self, task: str) -> PlanTemplate:
        # Use LLM-as-hash: ask the LLM to describe the tool/arg schema
        # needed for this task, hash that description
        schema_description = self.llm.generate(
            f"Describe the minimal tool-call sequence needed for: {task}"
        )
        return PlanTemplate(
            task_signature=hashlib.sha256(schema_description.encode()).hexdigest()[:16],
            tool_sequence=[],  # filled by cache logic
            arg_schema_hash="",
            precondition=task,
            success_rate=1.0,
            adaptation_hints=[],
        )

    def _run_react_loop(self, task: str) -> dict:
        # Standard ReAct loop — returns full trajectory
        trajectory = {"tool_calls": [], "task_description": task}
        # ... (standard implementation)
        return trajectory

    def _execute_plan(self, steps: list[dict], task: str) -> str:
        # Execute a cached/adapted plan directly
        context = {"task": task, "results": {}}
        for step in steps:
            tool = self.tools[step["tool"]]
            result = tool.execute(**step["arguments"])
            context["results"][step["tool"]] = result
        return context["results"].get("_final", "")
```

## Receipt

> Verified 2026-07-05 — Stanford APC paper (arXiv:2506.14852, NeurIPS 2025): 50.31% average cost reduction, 27.28% latency reduction, 96.61% accuracy retention across 6 benchmarks (TravelPlanner, MOSS, WebShop, ToolBench, API-Bank, PopEval). APC outperformed naive no-cache, context-cache-only, and semantic-cache-only baselines on all benchmarks. The technique is model-agnostic (unlike KV cache) and structure-aware (unlike semantic cache).

## See also

- [S-08 · Prompt Caching](s08-prompt-caching.md) — provider-level input caching; APC sits *above* this as the task-level equivalent
- [S-607 · The Multi-Agent Cost Compounding Problem](s607-the-multi-agent-cost-compounding-problem.md) — the cost context APC solves
- [S-126 · Event-Driven Cache Invalidation](s126-event-driven-cache-invalidation.md) — TTL-based invalidation; APC uses success-rate invalidation instead
