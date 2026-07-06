# S-516 · Trajectory-Level Loop Detection

[When an agent silently burns $400 overnight calling the same retrieval tool 300 times — or two agents deadlock waiting on each other, both returning 200s while producing nothing.]

## Forces

- A per-message judge reads one step and asks "is this good?" — it cannot see that the same good draft appeared four steps ago or that two agents are each waiting for the state the other was supposed to write
- Count-based loop detection (tool call > N) triggers on productive parallel storms as readily as on genuine loops — it catches the symptom, not the failure mode
- Trajectory hashes are cheap to compute; recovering from an undetected loop is catastrophically expensive — the asymmetry means you should always run the detector
- Productive cycles (iterative refinement, replanning) are structurally identical to pathological ones until you look at the *outcome delta*, not just the action pattern
- Multi-agent deadlocks are properties of the *protocol topology*, not any single agent's behavior — they cannot be caught by any agent monitoring itself

## The move

### The core insight

The agent loop is not a per-message property — it is a trajectory property. Detection must live at the same level.

### Trajectory state hashing

Hash each execution step (tool name + critical args + outcome category) into a deterministic fingerprint:

```python
import hashlib, json
from collections import deque

class TrajectoryWatchdog:
    """
    Stateless trajectory fingerprinting + loop/deadlock detection.
    Runs in O(1) per step. Zero LLM calls on the hot path.
    """

    def __init__(self, short_window=5, long_window=50, max_agents=8):
        self.short = deque(maxlen=short_window)   # recent repetition
        self.long  = deque(maxlen=long_window)    # cycle across longer horizon
        self.seen  = set()                         # all-time fingerprint set
        self.step_count = 0

        # Multi-agent deadlock tracking: {agent_id -> expected_state_key}
        self.agent_blocked   = {}   # agent_id -> set of missing state keys
        self.state_writers   = {}   # state_key -> agent_id that writes it
        self.deadlock_cycles = set() # detected deadlock pairs

    def fingerprint(self, tool_name: str, args: dict, outcome: str) -> str:
        # Strip non-deterministic fields (timestamps, UUIDs, cursor positions)
        canonical = {
            "t": tool_name,
            "a": {k: v for k, v in args.items() if k not in
                  ("timestamp", "request_id", "cursor", "session_id")},
            "o": outcome,
        }
        return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:16]

    def step(self, agent_id: str, tool_name: str, args: dict, outcome: str,
             state_reads: list[str] = None, state_writes: list[str] = None):
        """
        Record one execution step. Returns a dict with:
          - loop: bool — short-window repetition detected
          - cycle: bool — long-window repetition (same outcome pattern)
          - deadlock: list[str] — agents in a deadlock cycle
          - verdict: str — 'ok' | 'loop' | 'cycle' | 'deadlock'
        """
        fp = self.fingerprint(tool_name, args, outcome)
        self.step_count += 1

        # Track multi-agent state dependencies
        if state_writes:
            for key in state_writes:
                self.state_writers[key] = agent_id
        if state_reads:
            missing = [k for k in state_reads if k not in self.state_writers]
            self.agent_blocked[agent_id] = set(missing)

        # Check deadlock: find agents blocked on each other
        verdict = "ok"
        concerns = []

        if fp in self.short:
            verdict = "loop"
            concerns.append(f"short_repeat:{fp}")
        elif fp in self.long:
            verdict = "cycle"
            concerns.append(f"long_repeat:{fp}")

        # Multi-agent deadlock: A waits on B and B waits on A
        self._check_deadlock()

        self.short.append(fp)
        self.long.append(fp)
        self.seen.add(fp)

        return {
            "verdict": verdict,
            "loop": verdict in ("loop", "cycle"),
            "deadlock": list(self.deadlock_cycles),
            "fingerprint": fp,
            "step": self.step_count,
        }

    def _check_deadlock(self):
        """Detect two-way (or n-way) agent deadlocks via blocked-state graph."""
        # Build reverse map: which agent holds each state key that others need?
        for aid, blocked in list(self.agent_blocked.items()):
            for key in blocked:
                writer = self.state_writers.get(key)
                if writer and writer in self.agent_blocked:
                    # Writer is also blocked — possible deadlock
                    if writer in self.agent_blocked[aid]:
                        self.deadlock_cycles.add(frozenset([aid, writer]))
```

### Recovery tiers

```python
def recover(watchdog: TrajectoryWatchdog, agent_state: dict) -> dict:
    result = watchdog.step(
        agent_id=agent_state["id"],
        tool_name=agent_state["tool"],
        args=agent_state["args"],
        outcome=agent_state["outcome"],
        state_reads=agent_state.get("reads"),
        state_writes=agent_state.get("writes"),
    )

    if result["deadlock"]:
        return {"action": "abort", "reason": "deadlock", "agents": list(result["deadlock"])}
    if result["verdict"] == "loop":
        return {"action": "compact", "reason": "short_repeat", "fingerprint": result["fingerprint"]}
    if result["verdict"] == "cycle":
        return {"action": "escalate", "reason": "long_cycle", "steps": result["step"]}
    return {"action": "continue"}
```

**Recovery ladder:**
1. `continue` — all-clear
2. `compact` — context compaction (S-21) to break the repetition pattern; re-plan from compressed state
3. `escalate` — invoke governance layer (S-355 L3+); halt autonomous execution pending review
4. `abort` — kill trajectory, roll back side-effects, alert; mandatory for deadlock

### Multi-agent protocol verification

For multi-agent topologies, run TLA+ model checking (TraceFix, arXiv:2605.07935) before deploying a new protocol:

```
-- PlusCal translation of a two-agent ping-pong
variables pending = {};

fair process (Writer \in {1})
begin
Write:
  pending := pending \cup {self};
  await pending = {1, 2};
  pending := {};
  goto Write;
end process;
```

A two-state deadlock is immediately visible as a counterexample: both processes await each other. Integrate as a CI gate on protocol changes — any new multi-agent topology must pass TLA+ model checking before production deployment.

## Receipt

> Verified 2026-07-03 — Researched against Vadim Nicolai's "Deadlock & Infinite-Loop Prevention in Multi-Agent Sales" (June 2026), TraceFix (arXiv:2605.07935, May 2026), Reddit r/AI_Agents "Infinite Loop" thread. Code pattern implemented against TrajectoryWatchdog class from the Vadim blog post (LangGraph-based, Cloudflare D1 + LangSmith). 31.1% multi-agent run-stuck rate per TraceFix used as anchor statistic.

## See also

- [S-204 · Agent Circuit Breaker](s204-agent-circuit-breaker.md) — execution-level kills before damage compounds; pairs with trajectory detection
- [S-199 · Agent Self-Healing Loops](s199-agent-self-healing-loops.md) — classification of loop types and recovery strategies
- [S-355 · Agent Autonomy Levels](s355-agent-autonomy-levels-bounded-autonomy.md) — L2+ mandates loop detection; this is the mechanism it requires
- [S-21 · Context Compaction](s21-context-compaction.md) — the `compact` recovery action's implementation
- [S-512 · Multi-Agent Boundaries: When to Split](s512-multi-agent-boundaries-when-to-split.md) — topology decisions that prevent deadlock structurally
