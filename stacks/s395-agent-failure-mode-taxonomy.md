# S-395 · Agent Failure Mode Taxonomy

When your agent does the wrong thing confidently, runs in circles, leaks data, or silently corrupts downstream state — knowing *which* failure mode you're in determines whether you can recover. A year of red teaming and production incidents has produced a working taxonomy. Use it to classify failures, pick the right mitigation, and stop treating all agent errors as the same problem.

## Forces

- **Agents fail in categorically different ways.** A model that produces syntactically valid but logically wrong output behaves differently from one that loops forever. The recovery strategy for each is opposite — a loop needs a hard stop; a wrong answer needs adversarial verification.
- **Failure modes cascade.** A semantic failure in tool parameters feeds a downstream agent bad state, which propagates to a database write, which triggers a compliance violation. Treating the database write as the failure misses the root cause.
- **The taxonomy is empirical, not theoretical.** V1.0 (April 2025) was largely forward-looking. V2.0 (June 2026) is grounded in real red team engagements across OpenClaw, MCP plugins, and computer-use agents. The categories below reflect what actually broke.
- **Most teams have no failure taxonomy.** They see "agent made a bad call" and apply the same mitigation regardless of which failure mode actually occurred. This wastes mitigation effort on the wrong layer and misses the modes that don't surface as obvious errors.

## The Taxonomy

The Microsoft AI Red Team v2.0 taxonomy (June 2026) organizes agent failures into **four primary classes**, each with sub-modes and distinct mitigations.

### Class 1 — Execution Failures

The agent's action doesn't execute or doesn't execute correctly.

- **Tool call failure**: tool is unavailable, returns an error, or times out
- **Permission failure**: agent lacks authorization for the requested action
- **Environment failure**: sandbox crashes, network partition, dependency unavailable
- **Partial execution**: action starts but doesn't complete; state is left inconsistent

**Key signal**: The agent reports a failure *and* takes corrective action. You see an error log and a retry or escalation.
**Mitigation**: Idempotency keys (S-352), dead letter queues, graceful degradation. See also S-370 (Chaos Engineering) for fault injection to surface these before production.

### Class 2 — Semantic Failures

The agent's action executes successfully but does the wrong thing.

- **Wrong tool selected**: agent calls `send_email` instead of `send_invoice`
- **Wrong parameters**: correct tool, wrong arguments — account ID is correct, amount is wrong
- **Incorrect interpretation**: agent reads a response correctly but draws the wrong conclusion
- **Hallucinated tool**: agent invents a tool that doesn't exist and tries to call it

**Key signal**: The action succeeds with no error, but the outcome is wrong. This is the most dangerous class — it produces no failure logs.
**Mitigation**: Antagonistic validation (S-380), structured output with parameter schemas (S-04), output verification layers. Metamorphic testing (S-370) defines correctness by end-state equivalence, not text match.

### Class 3 — Behavioral Failures

The agent behaves in ways that violate intent or policy, without crashing.

- **Goal drift**: agent's objective subtly shifts over long conversations (I-013). "Analyze Q3 revenue" becomes "optimize revenue"
- **Excessive autonomy**: agent takes actions beyond its authorization level (I-002)
- **Data leakage**: agent exposes sensitive information in outputs, logs, or tool calls
- **Constraint erosion**: safety constraints silently drop as context compacts (I-004, S-360)
- **Loop behavior**: agent repeatedly attempts the same action with the same inputs — not a crash, but infinite retry

**Key signal**: The agent completes tasks without errors, but the behavior violates explicit constraints or produces outcomes that are subtly wrong by policy or intent.
**Mitigation**: Autonomy level gating (S-355), governance constraints pinned outside context window (S-360), budget-aware agents with hard ceilings (S-362), loop detection via action fingerprinting.

### Class 4 — Systemic/Cascading Failures

A failure in one component propagates through the agent ecosystem.

- **Context poisoning**: one agent writes corrupted state; downstream agents consume it as truth
- **Tool poisoning**: a tool returns adversarially crafted output; the agent acts on it
- **Orchestrator failure**: the planner-worker coordination breaks; tasks are lost, duplicated, or reordered
- **Dependency escalation**: a transitive dependency (tool-of-a-tool) fails silently; the agent doesn't know something went wrong

**Key signal**: Multiple agents or tools fail simultaneously, or a single failure propagates across multiple steps before detection.
**Mitigation**: Structural opposition (S-380), sandbox isolation (S-392), agent span tracing (S-368), MCP artifact signing (S-365).

## Classifying a Failure

When an incident occurs, ask in order:

1. **Did the action execute?** (Class 1 → check logs, retries, permissions)
2. **Did it do the right thing?** (Class 2 → check verification layer, run adversarial review)
3. **Did it behave within constraints?** (Class 3 → check governance logs, autonomy levels, constraint pinning)
4. **Did it propagate to others?** (Class 4 → check downstream state, isolate affected agents)

The first "yes" determines the class. Apply the class-specific mitigation, not a generic retry.

## Failure Mode Interaction Matrix

| Failure Class | Detection Difficulty | Recovery Speed | Cascades? | Common Mistriage |
|---|---|---|---|---|
| Execution (Class 1) | Low — logs fire | Fast | Sometimes | Treat as Class 2 |
| Semantic (Class 2) | High — no logs | Slow — must verify | Yes | Treat as Class 1 (retry) |
| Behavioral (Class 3) | Medium — policy violation | Variable | Yes | Ignore as "working normally" |
| Systemic (Class 4) | Very High — multi-component | Slow | Already cascading | Fix symptoms, not source |

The most expensive mistriage: Class 2 failures retried as Class 1 failures. Each retry compounds the wrong output with more wrong output.

## See also

- [S-370 · Agent Chaos Engineering](s370-agent-chaos-engineering-fault-injection-testing.md) — fault injection to surface failures before production
- [S-380 · Antagonistic Validation](s380-antagonistic-validation-team-of-rivals.md) — structural opposition catches Class 2 failures
- [S-360 · Governance Decay](s360-governance-decay-context-compaction-safety-erosion.md) — constraint erosion is Class 3
- [S-368 · Agent Span Tracing](s368-agent-span-tracing-observable-agent-sessions.md) — trace lineage helps classify cascading failures
- [S-392 · Agent Sandboxing](s392-agent-sandboxing-the-isolation-layer.md) — isolation prevents Class 4 propagation
- [I-008 · Agent Chaos Engineering (knowledge-pulse)](knowledge-pulse.md) — metamorphic testing for Class 2 detection
- [I-013 · Goal Drift (knowledge-pulse)](knowledge-pulse.md) — Class 3 behavioral failure
