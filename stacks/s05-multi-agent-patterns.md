# S-05 · Multi-Agent Patterns

When one agent isn't enough — fan-out, pipeline, and supervisor architectures.

## Forces
- A single agent's context window limits how much work it can hold at once
- Parallel tasks block on a single-threaded agent
- Different subtasks benefit from different models or prompts
- More agents = more coordination overhead, more cost, and more failure surfaces
- The #1 production failure isn't the wrong pattern — it's context inconsistency between agents that don't share state cleanly

## The move

**First, question whether you need more than one agent.** A single agent with the same tools and context matches or beats multi-agent on most tasks at roughly half the cost — anything past a sequential pipeline runs ≥2× the tokens. Reach for multiple agents only when you have genuine specialization, parallelizable independent subtasks, or open-ended work one loop can't hold. This is [Law 1](../laws.md) applied to architecture.

When you do, three patterns cover most real cases. Pick the simplest one that works.

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

> Verified 2026-06-25 — a two-stage **pipeline** run against llama3.2 via Ollama (localhost:11435), each stage consuming the previous stage's output:

```
[extract]   in=2533 out=3  -> "Marie Curie"
[transform] in=2524 out=2  -> "Chemistry"
PIPELINE RESULT: {"person":"Marie Curie","field":"Chemistry"}
```

Two real lessons from the run: (1) **cost compounds** — a trivial 2-step pipeline still paid full input cost *twice* (~5,057 input tokens), which is why "anything past a pipeline costs ≥2×" bites. (2) **error compounds silently** — the source sentence said *Physics* (her 1903 prize), but stage 2 only received the name, not the context, and answered "Chemistry" from its own knowledge. Each handoff that drops context is a place the pipeline can drift. The failure-rate math above is arithmetic; the single-vs-multi cost figures are from 2026 orchestration studies (directional).

## See also
[S-23](s23-workflows-vs-agents.md) · [S-19](s19-agent-loop.md) · [S-06](s06-model-routing.md) · [S-03](s03-tool-use.md) · [F-02](../forward-deployed/f02-evaluation-at-scale.md) · [F-11](../forward-deployed/f11-agent-reliability.md)

## Go deeper
Keywords: `LangGraph` · `Claude Agent SDK` · `CrewAI` · `AutoGen` · `supervisor pattern` · `fan-out` · `orchestration`
