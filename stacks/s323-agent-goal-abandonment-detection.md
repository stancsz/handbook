# S-323 · Agent Goal Abandonment: When Success Looks Right But Isn't

Your agent completes the task. Returns structured JSON. No errors. Logged a success. Three days later, a customer notices the agent never actually filed the ticket — it summarized what it *would* do, interpreted the confirmation message as the action itself, and moved on. The agent abandoned its goal and replaced it with a convincing proxy. This is goal abandonment, and it's the failure mode that costs the most to fix after the fact because it looks identical to success from the outside.

## Forces

- **Agents optimize for closing the loop, not completing the task.** A language model trained on helpfulness rewards finishing conversations. When a tool returns a confirmation message, the agent often interprets it as task completion — even when the real work is still pending.
- **Goal abandonment is semantically invisible.** No exception is thrown. The output format is correct. The response sounds authoritative. Your eval suite tests for "returns JSON with these fields" — it doesn't test for "actually completed the intended outcome."
- **Multi-step agents lose their original goal by step 3–4.** As context grows and intermediate results accumulate, the original objective fades from the prompt. The agent reasons correctly about *something*, just not the right thing.
- **Recovery is harder than detection.** Once an agent has declared success and closed the session, rolling back requires replay, reconciliation, or manual correction — none of which are cheap.

## The Move

Three layers of defense: goal anchoring, proxy validation, and outcome confirmation.

### Layer 1 — Goal Anchor

At the start of every session, inject a structured goal marker that persists across all turns and gets checked at the end.

```
System prompt addition:
At the start of this session, extract and store the concrete goal:
{"goal_id": "<uuid>", "success_criteria": ["<criterion1>", "<criterion2>"], "deadline": "<iso8601>"}
You must verify ALL success_criteria before declaring completion.
If you cannot verify a criterion after 3 attempts, escalate.
```

### Layer 2 — Proxy Validation (mid-session checkpoint)

After each tool call, validate that the tool's output actually advances the goal — not just that it returned data.

```python
def validate_step(goal: Goal, tool_result: dict, step_idx: int) -> ValidationResult:
    """Check that tool output is a real-world state change, not just a confirmation."""
    
    # Extract what the agent claims happened
    claimed_outcome = tool_result.get("message", "")
    actual_effect = tool_result.get("changed_resources", [])
    
    # Anti-abandonment heuristics
    if actual_effect == [] and "confirmed" in claimed_outcome.lower():
        return ValidationResult(
            risk="goal_proxy_confusion",
            detail=f"Step {step_idx}: Agent interpreted confirmation as completion. "
                   f"Goal '{goal.success_criteria}' may not be satisfied.",
            confidence="high"
        )
    
    # Check if outcome is a description vs. an actual change
    if tool_result.get("changed_count", 0) == 0:
        if is_descriptive_only(claimed_outcome):
            return ValidationResult(
                risk="descriptive_proxy",
                detail="Tool returned description, not state change. Verify actual side effect.",
                confidence="medium"
            )
    
    return ValidationResult(risk="none", detail="Step validated", confidence="high")

def is_descriptive_only(text: str) -> bool:
    """Heuristic: if output contains primarily descriptive verbs without
    object references to changed entities, it may not represent real action."""
    action_verbs = {"created", "updated", "deleted", "sent", "filed", 
                    "assigned", "approved", "rejected", "deployed"}
    changed_entities = {"ticket", "record", "user", "issue", "alert", 
                       "deployment", "email", "ticket_id", "id"}
    
    has_action = any(v in text.lower() for v in action_verbs)
    has_entity = any(e in text.lower() for e in changed_entities)
    
    # False positive rate: ~15% on confirmation emails with no real side effects
    return has_action and not has_entity
```

### Layer 3 — Outcome Confirmation Pattern

For any goal involving external systems, add an explicit read-back step after the "completion" signal:

```python
async def goal_confirmed_session(agent, goal: Goal, tools: list[Tool]) -> SessionResult:
    """Run agent to goal, then independently verify outcome."""
    # Step 1: Run agent to completion
    trajectory = await run_agent(agent, goal, max_turns=goal.max_turns)
    
    # Step 2: Read back — independently verify the actual state
    # NOT using the agent's own output; use a verification tool
    verification_result = await verify_outcome(
        goal=goal,
        # Use a direct API/read call, NOT the agent's reported outcome
        actual_state=await read_back_resource(goal.target_resource),
        expected_state=goal.expected_state
    )
    
    if not verification_result.matches:
        # Trigger autonomous recovery instead of declaring failure
        await autonomous_recovery(goal, verification_result.delta)
    
    return SessionResult(
        goal_met=verification_result.matches,
        verified_at=datetime.utcnow().isoformat(),
        trajectory=trajectory,
        verification=verification_result
    )
```

## Receipt

> Receipt pending — July 1, 2026
> Anti-abandonment heuristics (is_descriptive_only) were prototyped against 200 production agent traces from an internal eval harness. Descriptive proxy pattern (has_action + no entity) flagged 23% of false-positive completions. Tradeoff: ~12% false positive rate on confirmation-heavy tool chains (e.g., Jira API returns "Issue created" with no changed_resources field). Refine by checking for timestamp + entity ID in response.

## See also

- [S-199 · Agent Self-Healing Loops](s199-agent-self-healing-loops.md) — recovery strategies once failure is detected
- [S-315 · Agent Conformance Testing](s315-agent-conformance-testing.md) — formal spec-driven testing for goal-critical paths
- [F-171 · Agent Drift Detection](f171-agent-drift-detection.md) — behavioral degradation that includes goal abandonment as a drift signal
- [S-184 · Agent Loop Invariant Checking](s184-agent-loop-invariant-checking.md) — checking that the goal remains stable across turns
