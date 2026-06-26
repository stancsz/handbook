# S-05 · Multi-Agent Patterns

When one agent isn't enough — fan-out, pipeline, and supervisor architectures.

## Forces
- A single agent's context window limits how much work it can hold at once
- Parallel tasks block on a single-threaded agent
- Different subtasks benefit from different models or prompts
- More agents = more coordination overhead and more failure surfaces

## The move

Three patterns cover most real cases. Pick the simplest one that works.

---

### Pattern 1: Pipeline

Agents in sequence. Each takes the previous agent's output as input.

```
Input → [Agent A: extract] → [Agent B: classify] → [Agent C: format] → Output
```

Use when: tasks are sequential with clear handoffs.  
Cost: you pay for each step. Errors compound if not caught at each stage.

---

### Pattern 2: Fan-out (Parallel)

One coordinator dispatches identical or similar work to N workers, then aggregates.

```
             ┌─ [Worker 1] ─┐
Input → [Coordinator] ─ [Worker 2] ─ → [Aggregator] → Output
             └─ [Worker 3] ─┘
```

Use when: work is parallelizable (e.g., process 50 documents, run N independent checks).  
Cost: latency = slowest worker, not sum of all workers.

---

### Pattern 3: Supervisor

A frontier model plans and delegates; cheaper models execute. The supervisor sees all results and decides next steps.

```
[Supervisor (frontier)] ← results
      ↓ tasks
[Worker A]  [Worker B]  [Worker C]
```

Use when: the task requires judgment about what to do next, not just execution.  
In production 2026: supervisor typically uses Claude Opus / GPT-5; workers use Haiku / GPT-4o-mini.

---

### Failure rate math

At a 5% per-step failure rate:
- 5-step pipeline: ~23% chance of at least one failure
- 20-step pipeline: ~64% chance of at least one failure

**Production agents need per-step error rates well below 1% or explicit retry/fallback logic at every step.**

## Receipt
> Receipt pending — 2026-06-25. Failure rate math is arithmetic. Pattern descriptions sourced from public agent framework documentation and the research literature (AAAI 2026 S-DAG paper).

## See also
[S-19](s19-agent-loop.md) · [S-06](s06-model-routing.md) · [S-03](s03-tool-use.md) · [F-02](../forward-deployed/f02-evaluation-at-scale.md)

## Go deeper
Keywords: `LangGraph` · `Claude Agent SDK` · `CrewAI` · `AutoGen` · `supervisor pattern` · `fan-out` · `orchestration`
