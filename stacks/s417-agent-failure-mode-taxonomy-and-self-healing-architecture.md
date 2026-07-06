# S-417 · Agent Failure Mode Taxonomy and Self-Healing Architecture

Your agent loops for 35 minutes. Your budget triples. Your engineer discovers it four hours later. This is not a bug — it is the shape of agents.

## Situation

Production AI agent systems fail in ways that traditional software does not. A conventional web service crashes and logs a stack trace. An agent may silently loop for 35 minutes, spawn redundant subprocesses that contend for shared resources, accumulate context until the model halts, or take an irreversible action before a human can intervene. The failure modes are qualitatively different — and so are the remedies. Fault tolerance for AI agents is not optional engineering hygiene. It is the core engineering challenge of the agentic era.

## Forces

- **Agents are probabilistic state machines, not deterministic functions.** A conventional service either succeeds or crashes with a trace. An agent can succeed in its internal model while corrupting external state — and keep going.
- **Failure is invisible by default.** Loop detectors, budget watchers, and watchdog supervisors do not exist in a bare agent loop. You see the problem when the invoice arrives.
- **Irreversibility is the dangerous edge case.** An agent that calls `DELETE /users/bulk` with a bad filter has already done the damage before you can intervene. Rollback is not recovery — rollback is damage control.
- **Failure cascades compound non-linearly.** A 10-step pipeline where each step has 85% reliability succeeds ~20% of the time. The compounding math is brutal, and most teams never compute it.
- **Traditional fault tolerance patterns (circuit breakers, retries) were designed for deterministic systems.** Applying them blindly to agents causes new failure modes.

## The move

Build a self-healing architecture in three layers: **detect**, **contain**, **recover**.

### Layer 1 — Failure Mode Taxonomy

Classify agent failures into five types, each with a distinct detection and recovery signature:

**Type F1 — Loop (repeated action without progress)**
The agent calls `search_database` → no results → rephrases query → calls `search_database` again. Same result. Repeat.
Detection: action fingerprint + outcome fingerprint stored per step window. Flag when the same action+outcome pair appears 3+ times within N steps.
Recovery: inject a steer prompt that references the specific failure ("the previous 3 attempts to find X all returned empty — here is what to try instead"). Steer > kill.

**Type F2 — Deadlock (circular tool dependency)**
Agent A waits for Agent B's output. Agent B is waiting for Agent C. Agent C is waiting for Agent A.
Detection: DAG cycle detection on the pending task graph. Timeout on inter-agent handoff channels (>30s default).
Recovery: supervisor agent detects the circular wait, kills the pending tasks, re-dispatches with a topological sort that breaks the cycle.

**Type F3 — Resource contention (parallel agents fighting over shared state)**
Two agent instances both read `counter = 5`, both increment, both write `6`. Lost update. Or: both acquire the same file lock.
Detection: resource lock tracing via the span layer (S-368). Flag when N+ concurrent writes target the same entity within a time window.
Recovery: idempotent writes with compensation keys (S-352). If non-idempotent: queue with ordered delivery instead of parallel dispatch.

**Type F4 — Silent corruption (model continues with bad data)**
A tool returns malformed JSON. The agent wraps it in a fallback value and continues. Three steps later, the output is nonsense.
Detection: semantic verification on tool outputs (S-393). Confidence scoring on model responses. Output entropy monitoring.
Recovery: replay from last verified checkpoint. S-352 compensation keys undo the downstream writes. Flag for re-retrieval of the corrupted upstream data.

**Type F5 — Irreversible action without approval**
The agent calls `git push --force`. It was in the plan. Nobody approved it.
Detection: read-to-write gate (I-002 — Bounded Autonomy). Every destructive action must pass an approval check before the tool call executes, not after.
Recovery: S-352 compensation keys if available. F-51 rollback if not. Post-incident: tighten the action registry and approval threshold.

### Layer 2 — Containment Architecture

**Supervisor tree (not flat agent pool)**
```
supervisor (S-368 span parent)
  ├── planner agent
  │     └── tool executor
  └── watchdog (sibling, not child)
        ├── loop detector
        ├── budget tracker
        └── circuit breaker
```
The watchdog sibling is critical. It cannot be a child of the agent it monitors — a loop inside the agent also loops inside the watchdog. It must be a peer with independent health checks.

**Circuit breaker for LLM calls**
```python
class AgentCircuitBreaker:
    def __init__(self, failure_threshold=5, reset_window=60):
        self.failures = deque(maxlen=failure_threshold)
        self.window = reset_window

    def call(self, fn, *args, **kwargs):
        try:
            result = fn(*args, **kwargs)
            self.failures.clear()
            return result
        except (RateLimitError, TimeoutError, ModelOverloadedError) as e:
            self.failures.append(time.time())
            if len(self.failures) == self.failures.maxlen:
                self._trip()
                raise CircuitOpen(f"{fn.__name__} circuit open for {self.window}s")
            raise  # let retry logic handle it
```

**Budget watcher**
```python
class BudgetWatcher:
    def __init__(self, token_budget=8000, cost_budget_usd=0.50):
        self.tokens = 0
        self.cost = 0.0

    def step(self, input_tokens, output_tokens, cost_per_1k):
        self.tokens += input_tokens + output_tokens
        self.cost += (input_tokens + output_tokens) / 1000 * cost_per_1k

        if self.tokens > self.token_budget:
            raise BudgetExceeded(f"token budget {self.tokens}/{self.token_budget}")
        if self.cost > self.cost_budget_usd:
            raise BudgetExceeded(f"cost budget ${self.cost:.3f}/${self.cost_budget_usd:.2f}")
```

### Layer 3 — Recovery Patterns

| Failure Type | First Response | Recovery | Escalation |
|---|---|---|---|
| F1 Loop | Steer prompt (2 tries) | Kill + replan | Human review |
| F2 Deadlock | Kill all pending | Topo-resort + dispatch | Human review |
| F3 Contention | Retry with lock | S-352 compensation keys | Schema review |
| F4 Corruption | Replay from checkpoint | S-352 + S-393 | Data source review |
| F5 Irreversible | S-352 if available | F-51 manual rollback | Process review |

**Steer vs. kill rule:** If no side effects have occurred yet, steer. If the agent already made an irreversible call or wrote bad data, kill. Generic "stay on track" prompts do not work — the steer prompt must reference the specific failure and suggest a concrete alternative.

## The Compounding Math

```
pct_survive = 0.85  # each step succeeds 85% of the time
steps = 10
overall = pct_survive ** steps
print(f"{steps} steps @ 85%: {overall:.1%} survive")
# 10 steps: 20% survive
# 15 steps: 12% survive
```

A 10-step pipeline where each step has 85% reliability succeeds ~20% of the time. The math is invisible until it hits production. Design for fewer steps, idempotent steps, and early abort on failure — not perfect execution of a long chain.

## Receipt

> Receipt pending — 2026-07-03

## See also

[S-352](s352-agentic-compensation-keys-the-autonomous-retry-era.md) · [S-370](s370-agent-chaos-engineering-fault-injection-testing.md) · [S-413](s413-production-reliability-gap.md) · [F-51](../forward-deployed/f51-agent-action-rollback.md) · [S-368](s368-agent-span-tracing-observable-agent-sessions.md)
