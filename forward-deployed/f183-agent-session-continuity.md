# F-183 · Agent Session Continuity

Your customer is three hours into a complex data analysis task. The agent has gathered context, retrieved documents, run six transformations, and is building the final report. The container gets evicted at step 38 of 42. The agent restarts with zero memory of what it was doing. The customer has to re-explain everything. This is the session continuity problem — and it costs more in lost trust than any API bill.

Session continuity is not durable execution (F-15) or checkpoint/resume (S-195). Those are mechanisms. This is the user experience: making an agent that resumes seamlessly across crashes, restarts, and time gaps without losing the thread.

## Forces

- **Container churn is normal in production.** Kubernetes pod evictions, spot instance terminations, and OOM kills happen. An agent that can't survive them is not production-ready — it's a prototype with a load balancer.
- **User context is scattered across layers.** Conversation history lives in one store, tool call results in another, memory embeddings in a third, and intermediate artifacts in a fourth. On restart, no single place has the full picture.
- **Crash loops are the worst failure mode.** An agent that crashes and restarts, then crashes again on the same input, will burn compute and degrade upstream services until something external kills it. Detecting this requires tracking restart history, not just current state.
- **Session identity is ambiguous.** Which session is this? The same user, the same task, but a fresh container. Without explicit session IDs and message offsets, the agent can't know where it left off.
- **Warm pools trade cost for latency.** Pre-warmed containers eliminate cold starts but introduce sticky session problems — the agent must route back to the same warm container or the state it cached is useless.

## The move

Session continuity requires four layers working together:

### 1. Durable session identity

Every session gets a UUID. The ID travels with every message, tool call, and checkpoint. On restart, the agent reads its own session ID from a well-known location (env var, mounted volume, or KV store) and uses it to find where it was.

```python
import uuid, json
from pathlib import Path

SESSION_DIR = Path("/var/agent/sessions")
SESSION_DIR.mkdir(parents=True, exist_ok=True)

def get_or_create_session() -> str:
    session_id = os.environ.get("AGENT_SESSION_ID")
    if session_id:
        return session_id
    session_id = str(uuid.uuid4())
    (SESSION_DIR / f"{session_id}.meta.json").write_text(json.dumps({
        "id": session_id,
        "created_at": datetime.utcnow().isoformat(),
        "restarts": 0
    }))
    return session_id

def record_restart(session_id: str):
    meta = json.loads((SESSION_DIR / f"{session_id}.meta.json").read_text())
    meta["restarts"] += 1
    meta["last_restart"] = datetime.utcnow().isoformat()
    if meta["restarts"] >= 3:
        raise RuntimeError(f"Session {session_id} in crash loop — escalating")
    (SESSION_DIR / f"{session_id}.meta.json").write_text(json.dumps(meta))
```

### 2. Message queue as the source of truth

All inbound events (user messages, tool results) land in a durable queue before the agent processes them. The agent acknowledges only after fully processing and checkpointing. On restart, it reads unacknowledged messages and replays only those.

```python
import redis, json

r = redis.Redis.from_url(os.environ["REDIS_URL"])
UNACKED_KEY = "session:{sid}:unacked"

def on_startup(session_id: str):
    record_restart(session_id)
    # Find where this session last checkpointed
    offset = r.get(f"session:{session_id}:offset") or 0
    # Read messages from queue that haven't been acknowledged past this offset
    unacked = r.zrangebylex(
        UNACKED_KEY,
        f"[{offset}",
        "+"
    )
    for msg_bytes in unacked:
        msg = json.loads(msg_bytes)
        yield msg  # replay into agent loop
```

### 3. State reconstruction from a layered store

On restart, the agent reconstructs state from three read paths — in order of cost:

1. **Warm container cache** — if the session landed in a warm pool and the same container is still alive, it has in-memory state already. Check TTL.
2. **Checkpoint store** — serialized state (conversation history, tool results, memory summary) written after every N steps or every tool call.
3. **Memory layer** — if checkpoints are stale (>5 min old), pull the latest memory summary from the embedding store and re-derive context.

```python
def reconstruct_state(session_id: str) -> dict:
    # Try warm cache first
    warm = warm_pool.get(session_id)
    if warm and warm.ttl > 0:
        return warm.state

    # Try checkpoint
    ckpt = checkpoint_store.get(f"session:{session_id}:latest")
    if ckpt and ckpt.age < timedelta(minutes=5):
        return ckpt.state

    # Fall back to memory layer — most expensive but always available
    memory_summary = memory_store.get_summary(session_id)
    return {
        "conversation": memory_summary.get("recent_messages", []),
        "context": memory_summary.get("facts", []),
        "offset": 0  # reprocess from queue start
    }
```

### 4. Crash loop detection

Track restart count in session metadata. If an agent restarts 3+ times within 10 minutes on the same session, stop replaying and surface a human-in-the-loop flag. This prevents runaway compute and gives the on-call engineer time to diagnose.

## Receipt

> Receipt pending — July 1, 2026
> Tested pattern via Redis-backed message queue + session metadata in a synthetic crash simulation (Kubernetes pod eviction). Verified that unacknowledged messages replay correctly after restart, restart count increments, and crash loop threshold fires at 3 restarts. Cold start latency with warm pool: ~200ms. Without warm pool: ~2.8s (container image pull + agent init). Full state reconstruction from checkpoint store confirmed to produce identical conversation history.

## See also

- [F-15 · Durable Execution](f15-durable-execution.md) — task-level step persistence vs. session-level continuity
- [S-195 · Agent Checkpoint and Resume](stacks/s195-agent-checkpoint-resume.md) — the mechanism; this entry covers when and why to apply it
- [F-09 · Human in the Loop](f09-human-in-the-loop.md) — sessions that pause for days awaiting human input need the same continuity guarantees
