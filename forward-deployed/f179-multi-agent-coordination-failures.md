# F-179 · Multi-Agent Coordination Failures

Multi-agent systems fail at 41–86.7% in production. The culprit isn't the individual agents — it's the protocol between them.

## Forces
- A single agent at 95% per-step reliability becomes ~60% over 12 steps — and that's with *one* agent. Two agents in a pipeline multiply the failure surface.
- MAST research (NeurIPS 2025), validated across 1,600+ execution traces and 14 failure modes, found 79% of production breakdowns trace to two root causes: specification ambiguity and coordination failures — not bad models.
- Adding more agents doesn't scale linearly — each new agent is a new coordination surface, a new message protocol, a new shared-state problem.
- The failure modes are structurally different from single-agent failures: you can't just add a retry loop.

## The move

**The MAST failure taxonomy maps 14 failure modes to three root categories:**

### 1. Specification Ambiguity (role/task confusion)
Agents misinterpret their roles or the task boundary. One agent assumes another already handled something. They duplicate work or leave gaps.

```
# Symptoms
- Agents produce overlapping outputs
- Task scope creep: agent A expands the task beyond what B expects
- Silent omissions: something should be done, nobody does it

# Fixes
- Write explicit role contracts: name, responsibility, what is NOT mine
- Enumerate task boundaries in the supervisor prompt, not just "collaborate"
- Add a routing layer that classifies incoming requests into agent responsibility slots before dispatch
```

### 2. Coordination Breakdowns (message passing failures)
Agents drift out of shared context. They work from stale state. They don't know when to yield control or wait for input.

```
# Symptoms
- Agent B acts before Agent A has written its result
- Circular loops: A calls B, B calls A
- Partial outputs: one agent finishes but its consumer can't parse the format

# Fixes
- Use structured message schemas with typed outputs, not free-text summaries
- Implement a shared state checkpoint between pipeline stages — no agent reads state older than its last checkpoint
- Add explicit yield points: "wait for B's output in channel X before proceeding"
- Enforce timeout + escalation: if B doesn't respond within N seconds, route to supervisor
```

### 3. Verification Gaps (no one checks the handoff)
Agents trust each other's outputs implicitly. A hallucinated intermediate result propagates forward and corrupts the final output.

```
# Symptoms
- Final output looks polished but is wrong because upstream hallucinated
- No trace from final answer back to which agent produced which intermediate fact
- Debugging requires manually reconstructing the execution trace

# Fixes
- Every agent-to-agent handoff goes through a verification step (can be lightweight LLM-as-judge)
- Tag every intermediate output with provenance: which agent, which model, which tool calls
- Log at message-passing level, not just at tool-call level
```

**Operational patterns that reduce failure rates:**

```
# Supervisor pattern with explicit state machine
# Agents don't call each other — they write to a shared state and the
# supervisor transitions the state machine

states = ["idle", "planning", "researching", "synthesizing", "done", "failed"]

def supervisor(state, agent_outputs):
    match state:
        case "planning":       return transition("researching", planner_plan())
        case "researching":    return transition("synthesizing", researcher_search(plan))
        case "synthesizing":   return transition("done", synthesizer_merge(results))
        case "failed":        return escalate(debug_trace(state, agent_outputs))

# Every transition is logged. Every agent reads only from state, never from
# another agent's direct output.
```

```
# Explicit acknowledgment protocol
# Agent A doesn't "call" Agent B — it writes a message to B's queue and
# waits for an ACK. B's ACK includes a checksum of what B understood.

msg_id = queue.write(to="researcher", payload=task_spec, expected_format="findings[]")
ack = queue.wait_ack(msg_id, timeout=30)
assert ack.checksum == task_spec.checksum, "Agent B misunderstood the task"
```

## Receipt
> Receipt pending — June 30, 2026

## See also
- [F-03 · Failure Modes](f03-failure-modes.md) — single-agent failure taxonomy
- [F-11 · Agent Reliability](f11-agent-reliability.md) — pass@k and per-step reliability compounding
- [S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — architectural patterns for multi-agent design
