# S-566 · Loop Engineering: The Control Layer Around Agent Execution

The quality of an AI agent is 20% model, 80% loop. The loop is the harness — the control layer that determines when the agent stops, how it checks its own work, and what happens when it fails. Loop engineering is the discipline of designing that control layer. It emerged as a distinct practice in mid-2026 when practitioners including Boris Cherny (Claude Code creator at Anthropic) and Peter Steinberger recognized that prompting had reached its ceiling: the next frontier is not what you tell the model, but how you run it.

## Situation

You deploy a coding agent. It works in demos. In production, it loops forever on one task, silently fails on another, and burns $800 in API credits on a third. You didn't give it bad instructions. You gave it no loop — no termination condition, no progress check, no recovery path. The model was fine. The harness was missing.

## Forces

- **Agents loop by design** — the same feature that makes them powerful (ReAct-style reasoning-action-observation cycles) is also their most dangerous failure mode
- **Default termination is subjective** — unlike deterministic code where a loop ends at a known condition, an LLM agent decides "I'm done" with no guarantee it actually is
- **The loop is where money disappears** — a 10-turn loop at $0.50/turn looks harmless in development; it costs $450/hour in production at scale
- **The shift is already happening** — Cherny: "Loops are the step from agents to the next thing." Steinberger: "You shouldn't be prompting agents anymore. You should be designing loops that prompt agents."

## The Move

### The 10-Loop Taxonomy

The discipline has converged on a 10-pattern taxonomy, from basic to production-grade. Most teams use patterns 1–4. The production failures come from skipping 7–10.

**1. ReAct Loop (Foundation)**
The basic agentic loop: think → act → observe → repeat. The substrate for every other pattern. No stopping condition beyond a hard max-steps cap.

```python
context = [{"role": "user", "content": goal}]
for step in range(max_steps):
    response = llm.complete(context, tools=available_tools)
    if response.is_final:
        return response.content
    result = execute_tool(response.tool_name, response.tool_args)
    context.append({"role": "tool", "content": f"{response.tool_name}: {result}"})
```

**2. Ralph Loop (Iterative Attempt)**
Ralph adds a layer: attempt → evaluate → revise → repeat. The evaluation step is external, not in-context. The agent tries a task, an external judge (human, script, or LLM) evaluates success, and the agent revises. The key difference from ReAct is that "done" is determined outside the loop, not by the model's self-assessment.

```
for attempt in range(max_attempts):
    output = agent.attempt(task)
    if evaluator.check(output): return output
    feedback = evaluator.get_feedback(output)
    agent.revise(feedback)
```

**3. Goal Loop (/goal Command)**
The /goal command in Claude Code and similar tools lets the agent define its own sub-goals. The harness treats the goal as the stopping condition, not the individual step. This is the highest-autonomy variant — the agent manages its own loop, constrained only by the goal boundary.

**4. Checkpoint Loop (State Snapshot)**
Snapshots agent state at each iteration. If the loop degrades or cycles, you can restore from the last good checkpoint. Essential for long-horizon tasks where context overflow is a real risk.

**5. Terminating ReAct (Conditional Stop)**
Add a function that evaluates whether the current output satisfies the task. Terminate when the evaluator returns true, not when max_steps is reached. The evaluator can be a script, a regex check, a unit test runner, or an LLM-as-judge.

```python
def is_satisfied(output, task):
    return (
        check_schema(output) and
        test_with_fixtures(output) and
        cost < budget
    )
```

**6. Parallel Survey Loop**
Spawn N agents solving the same problem independently, collect all outputs, then select the best via a scoring function. Useful when you have multiple valid solution paths and want to hedge against single-path failure.

**7. Bounded Execution (Hard Limits)**
Hard limits that cannot be overridden by the agent: max iterations, max time, max cost. Unlike soft limits (the agent "should" stop), bounded execution means the harness terminates the loop regardless of what the agent reports.

```python
for attempt in range(max_attempts):
    if time_elapsed() > 300: break       # 5-minute wall clock
    if cost_accumulated() > 5.00: break # per-task dollar cap
    if iteration_count > 20: break       # step ceiling
```

**8. Circuit Breaker (Progress-Gated Continuation)**
Trip the circuit if the agent fails to make measurable progress for N consecutive steps. "Progress" means: different output than the previous step, closer to a measurable goal, or a tool call that produced new information. If the agent repeats the same action with the same result twice in a row, trip.

```python
last_output = None
stall_count = 0
for step in range(max_steps):
    output = agent.step(context)
    if output == last_output:
        stall_count += 1
        if stall_count >= 3:
            raise CircuitBreakerTripped("Agent stalled on repeated output")
    else:
        stall_count = 0
    last_output = output
```

**9. Demote and Specialize (Loop-to-Script Offload)**
If the agent consistently performs the same computational task (parsing, formatting, text manipulation), offload it to a deterministic script. The loop keeps the high-value decisions — what to do next — and delegates mechanical work to compiled code. This is the "distill and demote" pattern from BD Tech Talks.

**10. Multi-Loop Orchestration**
Nested loops: a high-level planner loop delegates sub-tasks to worker loops. Each worker loop has its own termination logic appropriate to its task. The planner coordinates, retries failed workers, and manages the overall state. This is the CORPGEN / planner-worker pattern from S-357 taken to its full form.

### Choosing the Right Loop

| Task | Loop Type | Key Property |
|------|-----------|-------------|
| One-shot question | None (direct call) | Don't loop at all |
| Tool-based task, known end condition | Terminating ReAct | Testable success criteria |
| Open-ended exploration | Ralph Loop | External evaluator gates continuation |
| Long-horizon coding task | Bounded + Checkpoint | Hard limits + state recovery |
| High-stakes autonomous task | Circuit Breaker + Bounded | Progress gating + cost ceiling |
| Multiple solution paths | Parallel Survey | Hedge against single-path failure |
| Complex multi-step project | Multi-Loop Orchestration | Hierarchical planning |

## Receipt

> Verified 2026-07-04 — Sources: Data Science Dojo "10 Loop Engineering Design Patterns for AI Builders" (June 24, 2026), BD Tech Talks "Demystifying Loop Engineering" (June 22, 2026), TechTalks interview with Boris Cherny (Anthropic), Peter Steinberger (@steipete, June 7, 2026), OpenAI "Harness Engineering: Leveraging Codex in an Agent-First World" (February 11, 2026). Patterns 1–4 are well-documented in academic and practitioner literature. Patterns 5–10 are synthesized from practitioner consensus across multiple independent sources.

## See also

- [S-357 · Long-Running Agent Orchestration](stacks/s357-long-running-agent-orchestration-planner-worker-pattern.md) — planner-worker temporal layering
- [S-554 · Agent Cost Engineering](stacks/s554-agent-cost-engineering-the-circuit-breaker-problem.md) — circuit breaker for runaway spend
- [S-561 · The Self-Correction Gap](stacks/s561-the-self-correction-gap-when-agents-cant-self-heal.md) — LLM-as-judge for loop quality gates
- [S-549 · Agentic Production Failure Modes](stacks/s549-agentic-production-failure-modes.md) — failure taxonomy for production agents
