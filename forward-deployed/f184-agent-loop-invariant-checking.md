# F-184 · Agent Loop Invariant Checking

An agent that has been running for 23 steps suddenly starts outputting nonsense. Not a crash — it's still calling tools, returning 200s, producing syntactically correct JSON. Nobody notices for six hours because there's no internal checkpoint asking "is this still on-track?" The agent was off-rails at step 8 and nobody found out until the output reached a human. Loop invariant checking is the answer: lightweight self-diagnostic checks woven into each iteration of the agent loop, designed to catch off-rail conditions before damage compounds.

## Forces

- **Agents fail by drifting, not by crashing.** The most dangerous agent failures are silent — a model that keeps producing plausible-but-wrong outputs, or one stuck in a subtle loop producing 200s while accumulating damage. No exception fires. No alert fires. The agent "works" until a human notices.
- **Existing checks are perimeter defenses, not self-awareness.** Guardrails (S-282) check outputs before they leave the system. Eval harnesses (S-219, S-230) run offline on batches. Neither lives inside the agent loop checking whether the loop itself is healthy.
- **Adding LLM calls to every step is cost-prohibitive.** A full LLM-as-judge check on every step doubles or triples token cost. Invariant checking must be cheap enough to run every iteration — that means deterministic checks, not probabilistic ones.
- **The gap between guardrails and evals is where agents drift silently.** Guardrails stop bad outputs. Evals catch regressions in CI. But between those two, an agent can produce a hundred wrong intermediate steps with no gate firing.

## The move

Three invariant tiers, cheapest first. Run them in order; stop at the first failure:

### Tier 1 — Deterministic invariants (every step, zero extra LLM cost)

```python
def check_invariants(state: AgentState, config: InvariantConfig) -> InvariantResult:
    """Cheap checks that run every step. Fail-fast on structural problems."""

    violations = []

    # Context budget check — are we about to overflow?
    used = count_tokens(state.conversation_history + state.pending_input)
    if used > config.max_tokens * 0.9:
        violations.append(InvariantViolation(
            type="context_budget_critical",
            step=state.step_count,
            detail=f"{used} tokens used, {config.max_tokens} max"
        ))

    # Loop detection — have we called the same tool N times without progress?
    recent_tool_calls = state.tool_call_history[-config.loop_detection_window:]
    tool_counts = Counter(call["tool"] for call in recent_tool_calls)
    for tool, count in tool_counts.items():
        if count >= config.max_repeated_tool_calls:
            violations.append(InvariantViolation(
                type="tool_loop_detected",
                step=state.step_count,
                detail=f"Tool '{tool}' called {count}x in last {config.loop_detection_window} steps"
            ))

    # Task drift check — does recent output still relate to the original goal?
    goal_keywords = set(state.goal_keywords)  # extracted from task prompt at step 0
    recent_output = truncate(state.pending_output, max_chars=500)
    output_keywords = extract_keywords(recent_output)
    overlap = goal_keywords & output_keywords
    if len(overlap) < config.min_goal_overlap_ratio * len(goal_keywords):
        violations.append(InvariantViolation(
            type="task_drift_suspected",
            step=state.step_count,
            detail=f"Only {len(overlap)}/{len(goal_keywords)} goal keywords present in recent output"
        ))

    # Step budget exhaustion
    if state.step_count >= config.max_steps:
        violations.append(InvariantViolation(
            type="step_budget_exhausted",
            step=state.step_count,
            detail="Agent has reached maximum step count"
        ))

    return InvariantResult(
        passed=len(violations) == 0,
        violations=violations,
        tier=1
    )
```

### Tier 2 — Lightweight semantic checks (on failure signals only)

Only invoke when Tier 1 flags a concern, or every N steps as a heartbeat:

```python
def lightweight_semantic_check(state: AgentState) -> bool:
    """Minimal LLM call: 'Yes/no is this on track?' — used sparingly."""
    # One-shot, short-context check — not a full judge
    prompt = f"""Task: {state.original_goal[:200]}
Last 3 tool results: {[t.get('summary', str(t)[:100]) for t in state.tool_call_history[-3:]]}
Is the agent still working toward the original task? Answer YES or NO and briefly explain."""
    
    response = llm.call(prompt, model="cheap-fast-model", max_tokens=30)
    return "YES" in response.upper()
```

### Tier 3 — Full trajectory review (on loop exit or failure)

On every task completion (success or failure), run a retrospective:

```python
def trajectory_review(state: AgentState) -> TrajectoryReport:
    """Post-run analysis: what went wrong, where, and was it recoverable?"""
    
    steps_with_errors = [s for s in state.steps if s.get("error")]
    loops_detected = sum(1 for v in state.violations if "loop" in v.type)
    drift_events = sum(1 for v in state.violations if "drift" in v.type)
    
    return TrajectoryReport(
        total_steps=state.step_count,
        error_steps=len(steps_with_errors),
        loops_detected=loops_detected,
        drift_events=drift_events,
        recoverable=(loops_detected == 0 and drift_events <= 1),
        step_that_needed_intervention=_find_first_violation_step(state.violations)
    )
```

### Hook it into the agent loop

```python
def agent_loop(task: str, config: AgentConfig) -> AgentResult:
    state = AgentState(goal=task, goal_keywords=extract_keywords(task))
    
    while state.step_count < config.max_steps:
        # Standard agent step
        response = llm.complete(state.to_messages())
        state.pending_output = response.content
        state.tool_calls = response.tool_calls or []
        
        # Run invariant checks BEFORE executing tools
        result = check_invariants(state, config.invariants)
        
        if not result.passed:
            log.warning(f"Invariant violation at step {state.step_count}: {result.violations}")
            if result.tier == 1 and any("loop" in v.type or "drift" in v.type for v in result.violations):
                # Try self-correction before giving up
                state.pending_output = llm.complete(
                    f"Your last response drifted from the task '{task}'. "
                    f"Re-read the task and produce a corrected next action."
                )
                continue  # re-check on next iteration
            raise AgentInvariantError(result.violations)
        
        # Execute tools, record state, loop
        execute_tools(state)
    
    return trajectory_review(state)
```

## Receipt

> Receipt pending — July 1, 2026

## See also

- [S-204 · Agent Circuit Breaker](stacks/s204-agent-circuit-breaker.md) — complementary: circuit breaker cuts power; invariant checking cuts *misalignment* before power is applied
- [S-212 · Semantic Output Validation Gate](stacks/s212-semantic-output-validation-gate.md) — validates *outputs* against ground truth; this entry validates *process* against goal
- [S-274 · Agent Failure Localization](stacks/s274-agent-failure-localization.md) — finds which step broke; invariant checking prevents that step from ever being reached by catching drift early
