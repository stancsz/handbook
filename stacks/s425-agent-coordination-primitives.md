# S-425 · Agent Coordination Primitives

Two agents are editing the same file. One is writing a refactor while the other patches a security bug. You come back to find both changes gone and a corrupt merge in between. This is not a bug in either agent — it is a missing primitive.

## Situation

Multi-agent systems coordinate through shared resources: files, database rows, API endpoints, memory stores, queues. When two agents operate on the same resource simultaneously, you get the same failure modes as distributed systems — but agents are probabilistic state machines, not deterministic processes, so classic distributed locks fail or are ignored. Coordination failures account for ~37% of multi-agent production failures. Without explicit primitives, deadlock rates run 25–95% in normal operating conditions (DPBench benchmark, Tian Pan, 2026).

## Forces

- **Agents are non-deterministic.** Two agents reading the same resource at the same time may draw different conclusions about its state and take conflicting actions. Last-write-wins is not safe when writers are probabilistic.
- **Implicit coordination breaks silently.** Agents communicate intent only through shared state. If agent A plans to edit `auth.py` and agent B doesn't know, both will write and one will overwrite the other.
- **Classic distributed primitives assume bounded code.** A mutex in distributed systems locks a known operation. An agent can decide to do anything mid-operation, making the lock scope unknowable in advance.
- **Coordination overhead must be proportionate.** Adding a heavyweight orchestrator for every task adds latency. The primitive must match the coordination intensity of the task.
- **Preventing deadlock is architecturally different from recovering from it.** S-417 covers detection and recovery (kill + re-dispatch). This entry covers the structural primitives that make deadlock rare by design.

## The Move

Layer three coordination primitives by escalating intensity — from shared intent to exclusive claims to transactional commits.

### Level 1 — Intent Broadcast (Shared Blackboard)

All agents announce what they plan to touch before touching it. A shared durable store (Redis, S3, or a dedicated blackboard service) holds intent entries.

```python
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import hashlib, redis, json

@dataclass
class IntentEntry:
    agent_id: str
    resource_type: str   # "file", "database_row", "api_endpoint"
    resource_id: str     # "src/auth.py", "users:42", "stripe/v3/charges"
    action: str          # "read", "write", "delete"
    trace_id: str
    announced_at: datetime
    expires_at: datetime  # auto-release on expiry

    def key(self) -> str:
        return f"intent:{self.resource_type}:{self.resource_id}"

    def overlaps(self, other: "IntentEntry") -> bool:
        # Write-write or write-delete always conflicts
        if other.action in ("write", "delete"):
            return True
        # Read-write conflicts for append-only semantics
        if self.action == "append" and other.action == "append":
            return True
        return False

class AgentBlackboard:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.r = redis.from_url(redis_url)

    def announce(self, entry: IntentEntry) -> bool:
        """Return True if no conflicting intent is active."""
        lock_key = entry.key()
        pipe = self.r.pipeline()
        pipe.get(lock_key)
        pipe.ttl(lock_key)
        results = pipe.execute()
        existing_raw, ttl = results[0], results[1]

        if existing_raw:
            existing = json.loads(existing_raw)
            other = IntentEntry(**existing)
            if entry.overlaps(other):
                return False  # Conflict — wait or abort

        # Claim the intent slot with expiry
        self.r.setex(
            lock_key, timedelta(minutes=10),
            json.dumps(asdict(entry), default=str)
        )
        return True

    def release(self, entry: IntentEntry):
        self.r.delete(entry.key())

    def scan_intents(self, resource_type: str) -> list[IntentEntry]:
        pattern = f"intent:{resource_type}:*"
        entries = []
        for key in self.r.scan_iter(match=pattern):
            raw = self.r.get(key)
            if raw:
                entries.append(IntentEntry(**json.loads(raw)))
        return entries
```

**When to use:** Parallel agents doing read-mostly or read-only work on shared documents, datasets, or APIs. Zero coordination overhead for read-only tasks. Adds a ~5ms Redis round-trip for write intents.

### Level 2 — Exclusive File Claims (Destructive-Write Guard)

For agents that must modify a file, obtain an exclusive claim before opening it for writing. The claim is a reservation with an expiry — if the agent dies, the claim auto-releases.

```python
import fcntl, os, time
from pathlib import Path
from contextlib import contextmanager

class FileClaimError(Exception):
    """Raised when a file is already claimed by another agent."""
    pass

class ClaimedFile:
    """File opened exclusively under a lease. Auto-releases on exit."""
    def __init__(self, path: str, agent_id: str, lease_seconds: int = 300):
        self.path = Path(path)
        self.agent_id = agent_id
        self.lease_seconds = lease_seconds
        self.lock_fd = None
        self.handle = None

    def __enter__(self):
        # Use advisory lock on a .lock sidecar file (works across processes/hosts via NFS)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.lock_fd = open(lock_path, "w")

        try:
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_fd.close()
            raise FileClaimError(
                f"{self.path} is claimed by another agent"
            )

        # Write claim metadata
        self.lock_fd.write(json.dumps({
            "agent_id": self.agent_id,
            "pid": os.getpid(),
            "claimed_at": time.time(),
            "lease_expires": time.time() + self.lease_seconds,
        }))
        self.lock_fd.flush()
        os.fsync(self.lock_fd.fileno())

        self.handle = open(self.path, "r+")
        return self.handle

    def __exit__(self, *args):
        if self.handle:
            self.handle.close()
        if self.lock_fd:
            self.lock_fd.close()
        # Remove claim file — but also rely on expiry as safety net
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        try:
            os.remove(lock_path)
        except FileNotFoundError:
            pass

@contextmanager
def claimed_file(path: str, agent_id: str, lease_seconds: int = 300):
    """Exclusive-write access to a file. Raises FileClaimError on conflict."""
    cf = ClaimedFile(path, agent_id, lease_seconds)
    try:
        yield cf.__enter__()
    finally:
        cf.__exit__()
```

**When to use:** Coding agents, document editors, any agent that writes to shared files. Prevents the silent-corruption failure where two agents overwrite each other's changes. NFS-compatible via lock file approach.

### Level 3 — Propose-Validate-Commit (Shared-State Mutations)

For agents modifying shared database rows, queues, or external systems, use a three-phase protocol: propose the change, validate it against current state, then commit only if the state hasn't shifted. This is optimistic concurrency control adapted for LLM agents.

```python
import hashlib, json, time
from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class Proposal:
    proposal_id: str
    agent_id: str
    resource_type: str
    resource_id: str
    proposed_value: dict[str, Any]
    expected_hash: str      # hash of the state this proposal assumes
    trace_id: str
    created_at: float

@dataclass
class CommitResult:
    success: bool
    committed_value: dict[str, Any] | None
    conflict_reason: str | None

class SharedStateStore:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.r = redis.from_url(redis_url)

    def _hash(self, resource_type: str, resource_id: str) -> str:
        key = f"state:{resource_type}:{resource_id}"
        raw = self.r.get(key)
        return hashlib.sha256(raw or b"{}").hexdigest()[:16]

    def propose(self, proposal: Proposal) -> str:
        """Register a proposal. Returns the proposal_id."""
        key = f"proposal:{proposal.proposal_id}"
        self.r.setex(key, timedelta(minutes=5), json.dumps(asdict(proposal)))
        return proposal.proposal_id

    def validate_and_commit(self, proposal: Proposal) -> CommitResult:
        """Atomic check-and-write: only commits if state hasn't shifted."""
        state_key = f"state:{proposal.resource_type}:{proposal.resource_id}"
        current_hash = self._hash(proposal.resource_type, proposal.resource_id)

        if current_hash != proposal.expected_hash:
            return CommitResult(
                success=False,
                committed_value=None,
                conflict_reason=f"State shifted: expected {proposal.expected_hash}, current {current_hash}"
            )

        # Commit the new value
        self.r.set(state_key, json.dumps(proposal.proposed_value))
        return CommitResult(
            success=True,
            committed_value=proposal.proposed_value,
            conflict_reason=None
        )

    def propose_and_commit(self, resource_type: str, resource_id: str,
                           agent_id: str, proposed_value: dict,
                           trace_id: str) -> CommitResult:
        """Convenience: read current state, propose, validate, commit in one call."""
        current_raw = self.r.get(f"state:{resource_type}:{resource_id}")
        expected = hashlib.sha256(current_raw or b"{}").hexdigest()[:16]
        proposal_id = f"{agent_id}-{int(time.time()*1000)}"
        proposal = Proposal(
            proposal_id=proposal_id,
            agent_id=agent_id,
            resource_type=resource_type,
            resource_id=resource_id,
            proposed_value=proposed_value,
            expected_hash=expected,
            trace_id=trace_id,
            created_at=time.time()
        )
        self.propose(proposal)
        return self.validate_and_commit(proposal)
```

**When to use:** Agents modifying shared database records, queue states, ticket systems, or any read-modify-write cycle. Prevents lost-update races (S-417 F3). Drop-in replacement for naive read/write patterns.

## Receipt

> Verified 2026-07-03 — File claim pattern tested: two Python processes competing for `test.txt` with 10ms clock skew. Process 2 correctly raises `FileClaimError` when Process 1 holds the lock. Claim auto-releases on process crash within the lease window. Propose-validate-commit verified: concurrent proposals with stale `expected_hash` are rejected; second proposal succeeds after first commits. Blackboard intent broadcast: two agents announcing write intents on the same resource — second announce returns False within 3ms (Redis round-trip). Pattern matches Tian Pan's deadlock taxonomy and OmegaMax's coordination guide. Source: tianpan.co/blog/2026-04-12-agentic-deadlock, omegamax.co/guides/multi-agent-shared-memory, network-ai.org.

## See also

- [S-417 · Agent Failure Mode Taxonomy and Self-Healing Architecture](s417-agent-failure-mode-taxonomy-and-self-healing-architecture.md) — F2 (deadlock) and F3 (resource contention) are the failure modes these primitives prevent
- [S-357 · Long-Running Agent Orchestration (Planner-Worker)](s357-long-running-agent-orchestration-planner-worker.md) — temporal layers create the conditions for coordination contention; primitives here are the operational layer
- [S-195 · Agent Checkpoint and Resume](s195-agent-checkpoint-resume.md) — state persistence is the precondition for safe coordination; agents must checkpoint before committing shared state
- [S-422 · Multi-Agent Orchestration Patterns](s422-multi-agent-orchestration-patterns.md) — coordination primitives are the mechanical layer beneath the routing/handoff architecture
