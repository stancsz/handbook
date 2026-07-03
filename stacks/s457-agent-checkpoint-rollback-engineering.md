# S-457 · Agent Checkpoint & Rollback Engineering

When an agent's tool call succeeds but produces unintended state — a dropped table, a deleted partition, a misfired notification — and you need to recover without undoing everything the agent did that was correct.

## Forces

- **Agent mistakes live in external state, not code.** A traditional bug lives in source control. Fix it, redeploy. An agent mistake has already mutated your database, filesystem, or upstream APIs. The fix is not in the code — it is in the state.
- **No automatic transaction boundary exists.** Database ACID transactions don't span `POST /api/orders`, `send_email()`, and `update_sheets()`. The agent's tool calls are individually atomic but collectively opaque. When failure happens mid-sequence, knowing which mutations need reversal — and in what order — is non-trivial.
- **Reversibility is command-type-dependent.** File deletion looks reversible (restore from backup) but downstream consumers already processed the missing data. Database updates look reversible (write old values back) but downstream reads already acted on the new state. Config changes require restarts. The reversibility assumption embedded in most rollback designs is wrong.
- **Global rollback is too blunt.** In multi-tenant systems, rolling back the last action undoes good work for tenants who weren't affected. Tenant-aware rollback — surgical, per-tenant recovery — is the right primitive.
- **Context loss makes things worse.** When a long-running agent loses context and produces broken code across 47 files, the agent doesn't know what it broke. Manual recovery requires replaying the session — which requires a complete event log the agent runtime doesn't automatically produce.

## The move

Three-layer pattern: **snapshot → registry → replay**.

### Layer 1: Checkpoint before mutation

Before any tool call that writes to external state, snapshot the relevant resource. The scope of "relevant" is a design decision — row-level for databases, prefix-level for object stores, diff-level for files.

```python
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime, timezone
import sqlite3, json

@dataclass
class Checkpoint:
    tool_name: str
    resource_id: str      # what was touched
    snapshot: str         # serialized state before mutation
    action_plan: str       # what the agent intended to do
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    idempotency_key: str = ""

@dataclass
class UndoEntry:
    checkpoint: Checkpoint
    compensate_fn: str     # name of compensating operation
    compensate_args: dict
    status: str = "pending"  # pending | applied | failed

class AgentUndoRegistry:
    def __init__(self, db_path=".agent-undo.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name, resource_id, snapshot, action_plan,
                timestamp, idempotency_key
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS undo_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id, compensate_fn, compensate_args,
                status, applied_at
            )
        """)

    def checkpoint_before(self, tool_name: str, resource_id: str,
                          snapshot: str, action_plan: str) -> int:
        cur = self.conn.execute(
            """INSERT INTO checkpoints
               (tool_name, resource_id, snapshot, action_plan, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (tool_name, resource_id, snapshot, action_plan,
             datetime.now(timezone.utc).isoformat())
        )
        self.conn.commit()
        return cur.lastrowid

    def log_undo(self, checkpoint_id: int, compensate_fn: str,
                  compensate_args: dict):
        self.conn.execute(
            """INSERT INTO undo_log
               (checkpoint_id, compensate_fn, compensate_args, status)
               VALUES (?, ?, ?, 'pending')""",
            (checkpoint_id, compensate_fn, json.dumps(compensate_args))
        )
        self.conn.commit()

    def rollback(self, checkpoint_id: int) -> bool:
        row = self.conn.execute(
            "SELECT * FROM undo_log WHERE checkpoint_id = ? AND status = 'pending'",
            (checkpoint_id,)
        ).fetchone()
        if not row:
            return False
        _, _, compensate_fn, compensate_args_json, status = row
        args = json.loads(compensate_args_json)
        fn = self._resolve_compensation(compensate_fn)
        fn(**args)
        self.conn.execute(
            "UPDATE undo_log SET status='applied', applied_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), row[0])
        )
        self.conn.commit()
        return True

    def rollback_all_since(self, checkpoint_id: int):
        """Tenant-aware: roll back every pending undo from most recent back."""
        rows = self.conn.execute(
            """SELECT id FROM undo_log
               WHERE checkpoint_id >= ? AND status = 'pending'
               ORDER BY id DESC""",
            (checkpoint_id,)
        ).fetchall()
        for (undo_id,) in rows:
            self.rollback_by_undo_id(undo_id)

    def _resolve_compensation(self, fn_name: str):
        # registry of known compensation functions
        return {"restore_table": self._restore_table,
                "restore_s3_prefix": self._restore_s3_prefix,
                "restore_file": self._restore_file}.get(fn_name, lambda **_: None)
```

### Layer 2: Decorator integration

Wrap tool calls automatically — the agent runtime doesn't need to know.

```python
def with_rollback(registry: AgentUndoRegistry,
                  resource_id_fn, snapshot_fn, compensate_fn, compensate_args_fn):
    """Decorator: snapshot before, register undo entry after."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            resource_id = resource_id_fn(*args, **kwargs)
            snapshot = snapshot_fn(resource_id)
            plan = f"{func.__name__}({args}, {kwargs})"
            ckpt_id = registry.checkpoint_before(
                func.__name__, resource_id, snapshot, plan
            )
            result = func(*args, **kwargs)
            # Register compensation *after* the call succeeds
            registry.log_undo(ckpt_id, compensate_fn, compensate_args_fn(args, kwargs))
            return result
        return wrapper
    return decorator

# Example: protect a database tool call
@with_rollback(
    registry=undo_reg,
    resource_id_fn=lambda conn, sql, **_: f"db:{conn}/{sql.split('FROM')[1].split()[0] if 'FROM' in sql else 'table'}",
    snapshot_fn=lambda rid: db.dump_table(rid),
    compensate_fn="restore_table",
    compensate_args_fn=lambda args, kwargs: {"conn": args[0], "table": kwargs.get("table"), "snapshot": ""}
)
def execute_sql(conn, sql, **kwargs):
    return db.run(conn, sql)
```

### Layer 3: Tenant-aware selective rollback

```python
class TenantAwareRollback:
    """Roll back only affected tenants, leave others untouched."""
    def __init__(self, base_registry: AgentUndoRegistry):
        self.base = base_registry

    def rollback_tenant(self, tenant_id: str, checkpoint_id: int) -> dict:
        """Surgical recovery for one tenant's state only."""
        rows = self.base.conn.execute(
            """SELECT u.* FROM undo_log u
               JOIN checkpoints c ON u.checkpoint_id = c.id
               WHERE u.checkpoint_id >= ?
                 AND u.status = 'pending'
                 AND c.resource_id LIKE ?
               ORDER BY u.id DESC""",
            (checkpoint_id, f"tenant:{tenant_id}:%")
        ).fetchall()
        applied = []
        for row in rows:
            # Extract and apply only this tenant's compensation
            self.base.rollback_by_undo_id(row[0])
            applied.append(row[0])
        return {"tenant_id": tenant_id, "undone": len(applied)}
```

### Key decision: what is NOT rollback-able

| Action | Rollback Mechanism | Limitation |
|--------|-------------------|------------|
| File write | Restore from snapshot | Downstream readers already consumed old content |
| Database row update | Write-back old values | Dependent transactions already fired |
| Config change | Restore + restart | Active processes need restart; race window during rollback |
| External API call | Idempotency key replay | Not always supported by the target |
| Email / notification | Recall / apology | Email recall is unreliable; notifications are fire-and-forget |

**Rule:** anything that crossed a trust boundary after the agent's call cannot be rolled back. Design the agent's tool set to minimize irreversible boundary crossings, and for those that remain, build compensating actions rather than true rollbacks.

## Receipt

> Verified 2026-07-03 — AgentMarketCap (April 2026) reports Gartner projecting 40% enterprise agent adoption by 2026. Three real incident patterns confirmed: `DROP TABLE` before backup, S3 prefix misidentification deleting 6 months of logs, context loss producing broken code across 47 files. GitHub's `agent-undo` project (97 commits, Apache-2.0) implements filesystem snapshot + one-command rollback via SQLite, confirming this as a recognized production pattern. how2.sh published tenant-aware rollback architecture with per-tenant checkpoint isolation in February 2026. Reversibility table cross-validated against Expacti blog (April 2026). Pattern density: connects to S-352 (compensation keys), S-101 (deterministic sessions), S-106 (event log replay), S-253 (agent sandboxing).

## See also

- [S-352 · Agentic Compensation Keys](s352-agentic-compensation-keys.md) — pre-action compensation; this entry covers post-action recovery
- [S-101 · Deterministic Agent Sessions](s101-deterministic-agent-sessions.md) — append-only event logs enable replay
- [S-106 · Event Log Replay](s106-event-log-replay.md) — reconstructing what the agent saw at time T
- [S-253 · Agent Sandboxing](s253-agent-sandboxing-as-a-first-class-layer.md) — containment limits blast radius; rollback fixes what containment didn't prevent
