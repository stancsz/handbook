# S-195 · Agent Checkpoint and Resume

An agent that works once in a notebook fails in production because nobody planned for interruption. When a process dies mid-run — OOM, network blip, deployment — all state is gone and the task restarts from scratch. Checkpoint/resume is the fix.

## Forces
- Long-running agents (multi-step workflows, agentic RAG, computer-use) are the most valuable and the most fragile — a 40-step task that dies at step 38 costs 37 wasted API calls
- Stateless design is architecturally clean but catastrophic for durability: one crash loses hours of work and requires full human retry
- Agent state is scattered — conversation history, tool call results, intermediate artifacts, LLM memory — not stored in one place
- Resuming is not re-running: you must reconstruct the exact decision state at checkpoint time, skip idempotent-but-expensive tool calls, and handle changed environment (data moved, session expired)
- Framework-native checkpointers (LangGraph, AutoGen) exist but lock you in; rolling your own requires understanding the minimal viable checkpoint surface

## The move

Implement a two-layer checkpoint system: **action log** (append-only, every call recorded) + **state snapshot** (full replayable state at decision points). On interrupt, load the latest snapshot and replay the action log from there.

```
Components:
  Checkpointer    — serializes/deserializes agent state
  ActionLog       — append-only record of every tool call + result
  ResumeEngine    — loads snapshot, replays log forward, skips completed calls
  EnvFingerprint  — detects changed environment (schema, auth, data) post-resume
```

### Minimal implementation

```python
import json
import time
import uuid
import sqlite3
from dataclasses import dataclass, asdict
from typing import Any, Optional
from pathlib import Path


@dataclass
class Checkpoint:
    id: str
    task_id: str
    step: int
    timestamp: float
    state_snapshot: dict   # full replayable state
    action_log: list       # [{step, tool, args, result, idempotent}]

    def save(self, db_path: str):
        conn = sqlite3.connect(db_path)
        conn.execute("""
            INSERT INTO checkpoints (id, task_id, step, timestamp, state_snapshot, action_log)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (self.id, self.task_id, self.step, self.timestamp,
              json.dumps(self.state_snapshot), json.dumps(self.action_log)))
        conn.commit()
        conn.close()

    @classmethod
    def load(cls, db_path: str, task_id: str) -> Optional["Checkpoint"]:
        conn = sqlite3.connect(db_path)
        row = conn.execute("""
            SELECT * FROM checkpoints WHERE task_id = ? ORDER BY step DESC LIMIT 1
        """, (task_id,)).fetchone()
        conn.close()
        if not row:
            return None
        cols = ["id", "task_id", "step", "timestamp", "state_snapshot", "action_log"]
        return cls(**dict(zip(cols, row)),
                   state_snapshot=json.loads(row[4]),
                   action_log=json.loads(row[5]))


class CheckpointRunner:
    """Wraps an agent loop with checkpoint/resume. No framework dependency."""

    def __init__(self, agent_fn, db_path: str = "checkpoints.db"):
        self.agent_fn = agent_fn
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                step INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                state_snapshot TEXT NOT NULL,
                action_log TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_step
            ON checkpoints(task_id, step DESC)
        """)
        conn.commit()
        conn.close()

    def run(self, task_id: str, initial_input: Any, max_steps: int = 50):
        # Resume from latest checkpoint if one exists
        checkpoint = Checkpoint.load(self.db_path, task_id)
        if checkpoint:
            state = checkpoint.state_snapshot
            action_log = checkpoint.action_log
            next_step = checkpoint.step + 1
            print(f"[resume] task={task_id} from step={next_step} ({len(action_log)} actions logged)")
        else:
            state = self._build_initial_state(initial_input)
            action_log = []
            next_step = 0

        # Main agent loop with checkpointing every N steps
        CHECKPOINT_INTERVAL = 5

        for step in range(next_step, max_steps):
            state, tool_calls = self.agent_fn(state)

            for tc in tool_calls:
                result = self._execute_tool(tc)
                action_log.append({
                    "step": step,
                    "tool": tc["name"],
                    "args": tc["args"],
                    "result": result,
                    "idempotent": tc.get("idempotent", False),
                })
                # Inject result into state so agent sees it
                state = self._inject_result(state, tc["name"], result)

            # Checkpoint every CHECKPOINT_INTERVAL steps
            if (step + 1) % CHECKPOINT_INTERVAL == 0:
                ckpt = Checkpoint(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    step=step,
                    timestamp=time.time(),
                    state_snapshot=state,
                    action_log=action_log,
                )
                ckpt.save(self.db_path)
                print(f"[checkpoint] step={step} saved")

            if self._is_terminal(state):
                break

        return state, action_log

    def _build_initial_state(self, initial_input: Any) -> dict:
        return {
            "input": initial_input,
            "messages": [],
            "memory": {},
            "artifacts": {},
        }

    def _execute_tool(self, tool_call: dict) -> Any:
        # In production: route to actual tool registry
        raise NotImplementedError("Plug in your tool executor here")

    def _inject_result(self, state: dict, tool_name: str, result: Any) -> dict:
        state["last_result"] = {"tool": tool_name, "result": result}
        state["messages"].append({"role": "tool", "tool": tool_name, "content": str(result)})
        return state

    def _is_terminal(self, state: dict) -> bool:
        return state.get("done", False)
```

### Recovery with environment change detection

```python
class ResumeEngine:
    """Resume a failed task, handling changed environment gracefully."""

    def __init__(self, runner: CheckpointRunner):
        self.runner = runner

    def resume_with_env_check(self, task_id: str) -> dict:
        ckpt = Checkpoint.load(self.runner.db_path, task_id)
        if not ckpt:
            raise ValueError(f"No checkpoint found for task {task_id}")

        # Detect environment changes that invalidate cached results
        env_changed = self._detect_env_changes(ckpt)
        if env_changed:
            # Filter action log: keep non-data-dependent calls, invalidate stale ones
            filtered_log = [
                entry for entry in ckpt.action_log
                if entry["idempotent"] or not self._depends_on_changed_data(entry, env_changed)
            ]
            print(f"[resume] env changed: kept {len(filtered_log)}/{len(ckpt.action_log)} actions")
            ckpt.action_log = filtered_log

        # Re-run from filtered checkpoint
        return self.runner.run(task_id, ckpt.state_snapshot["input"])

    def _detect_env_changes(self, ckpt: Checkpoint) -> dict:
        # Compare fingerprint of referenced data/tool schemas against current state
        # Returns dict of {resource: "changed"|"gone"|"ok"}
        raise NotImplementedError("Implement fingerprint comparison")

    def _depends_on_changed_data(self, entry: dict, env_changes: dict) -> bool:
        # Simple heuristic: non-idempotent calls over external data
        return not entry["idempotent"] and any(
            r in str(entry.get("args", "")) for r in env_changes if env_changes[r] != "ok"
        )
```

### Key decisions

| Concern | Choice | Why |
|---|---|---|
| Storage | SQLite | Zero infra, ACID, good enough for single-agent checkpointing |
| Snapshot frequency | Every N steps | Balance: too frequent = overhead, too rare = big recovery gap |
| Action log vs snapshot | Both | Snapshot for state reconstruction, log for debugging + idempotency |
| Idempotency | Declarative per call | Tool calls declare whether they're safe to re-run; skip on resume |
| Env change detection | Fingerprint comparison | Prevents silent data corruption from resuming with stale reads |

### When to reach for this
- Agent tasks that take >5 minutes or >10 tool calls
- Any agent that calls external APIs with side effects (email, payment, database writes)
- Multi-session continuity (user picks up a conversation hours later, agent resumes)
- Human-in-the-loop approval: checkpoint before a risky step, resume after human approves
- Computer-use agents that drive browsers or terminals — these crash constantly

### Tradeoffs
- Checkpointing adds ~50–200ms overhead per snapshot (serialize state to SQLite)
- State snapshots grow with context; prune or archive old checkpoints
- Idempotency declarations are opt-in — unsafe if tool registry doesn't cooperate
- Resuming from a snapshot with a newer model version may produce different decisions

## Receipt
> Receipt pending — 2026-06-29

## See also
- [S-106 · Event Log Replay](s106-event-log-replay.md) — replay for debugging, not recovery
- [S-101 · Deterministic Agent Sessions](s101-deterministic-agent-sessions.md) — append-only session design
- [S-09 · Memory Systems](s09-memory-systems.md) — externalizing agent state across sessions