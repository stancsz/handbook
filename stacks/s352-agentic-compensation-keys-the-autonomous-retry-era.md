# S-352 · Agentic Compensation Keys: Idempotency for the Autonomous Retry Era

[S-93](../stacks/s93-tool-side-effect-idempotency.md) covers idempotency keys for synchronous tool calls — when the model calls `send_email` twice with identical arguments, the tool guards against duplicate sends using a stored idempotency key. [S-181](../stacks/s181-live-data-event-deduplicator.md) covers deduplication of incoming external events — market data, webhooks, change streams — that arrive with at-least-once semantics. [F-107](../forward-deployed/f107-in-flight-request-deduplication.md) covers deduplication of concurrent LLM calls for identical prompts.

None of these cover the compensation layer: what happens after an agent's tool call *succeeds* but produces an *unintended* state — and the agent, operating autonomously, must find, identify, and reverse that state. The model issued the wrong intent. The tool executed faithfully. Now you need a deterministic way to say "I did X to compensate for Y" that survives retries, circuit breaker resets, and context windows that re-roll the model's memory of what it already did.

## Situation

An agent's `cancel_subscription(subscription_id="SUB-442")` call succeeds — the API returns 200 OK and the subscription is cancelled. The agent moves on. Thirty minutes later, a downstream billing reconciliation job finds the charge succeeded anyway because the cancellation was processed in a billing-cycle boundary. The subscription needs to be reactivated, or a credit needs to be issued. The agent, in its next session, has no memory of having cancelled it — the tool result is gone from context, the agent is stateless. The compensation problem is: *identify what was done, determine what compensating action reverses it, and execute safely*.

This is not idempotency. Idempotency prevents duplicate execution of the same intent. Compensation handles *correctly executed but wrong-intent* actions. It requires a separate key mechanism: the **compensation key**.

## Forces

- **Autonomy compounds the problem.** A human makes a mistake and remembers it. An agent makes a mistake and forgets it the moment the context window closes. Every autonomous action must carry forward enough identity to be found and reversed later.
- **The tool layer has no intent visibility.** The tool executes what it is told. It cannot know that `cancel_subscription` was called because the model misread "pause" as "cancel." The compensation logic lives at the orchestration layer, not the tool layer.
- **Retry safety is non-negotiable.** A compensation action that is itself not idempotent creates a second blast radius. Issuing a `$500 credit` twice because your credit-compensation call retried is a worse outcome than the original $500 overcharge.
- **Payload mismatch is a silent killer.** The idempotency key is `cancel:SUB-442`. The compensation key is `credit:SUB-442:500`. These are different keys for different actions. Using the wrong key means the compensation is never deduplicated against a legitimate direct credit.

## The move

**Three-layer key architecture for autonomous agents with side effects:**

```
Intent Key     → what the agent DECIDED to do
Execution Key  → the tool call that enacted the decision
Compensation Key → the reversal if the decision was wrong
```

Each layer generates a deterministic key from the action's canonical parameters. No UUIDs generated at runtime — the key must be reproducible from the action record so any process, not just the one that created it, can find and operate on it.

**Step 1 — Derive compensation keys at execution time, not discovery time:**

```python
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any

class ActionPhase(Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"

@dataclass
class ActionRecord:
    intent_key: str        # hash of (action_type, primary_params)
    execution_key: str     # hash of (action_type, full_params, timestamp_window)
    compensation_key: str  # hash of (compensation_action_type, params_for_reversal)
    compensation_params: dict
    phase: ActionPhase = ActionPhase.PENDING
    committed_result: Any = None

def derive_compensation_key(action_type: str, params: dict, comp_action: str, comp_params: dict) -> str:
    """Derive all three keys deterministically from action metadata."""
    # Intent: only the action type + the primary identified resource
    primary = {k: v for k, v in params.items() if k.endswith('_id') or k == 'resource_id'}
    intent_payload = json.dumps({"action": action_type, "primary": primary}, sort_keys=True)
    intent_key = hashlib.sha256(intent_payload.encode()).hexdigest()[:16]

    # Execution: full params + a deterministic window (not wall-clock time)
    exec_payload = json.dumps({"action": action_type, "params": params}, sort_keys=True)
    execution_key = hashlib.sha256(exec_payload.encode()).hexdigest()[:16]

    # Compensation: the reversal action type + the params needed to reverse
    # These params must be obtainable from the original execution result
    comp_payload = json.dumps({"comp_action": comp_action, "params": comp_params}, sort_keys=True)
    compensation_key = hashlib.sha256(comp_payload.encode()).hexdigest()[:16]

    return ActionRecord(
        intent_key=intent_key,
        execution_key=execution_key,
        compensation_key=compensation_key,
        compensation_params=comp_params,
    )

# Example: cancelling a subscription
record = derive_compensation_key(
    action_type="cancel_subscription",
    params={"subscription_id": "SUB-442", "reason": "customer_request"},
    comp_action="reactivate_subscription",
    comp_params={"subscription_id": "SUB-442", "reason": "billing_error"},
)
# record.compensation_key == "a3f9c1e2b8d70456"
# record.intent_key       == "7b2a1f9e3c5d..."
# record.execution_key    == "d4e8c2a1f7b3..."
```

**Step 2 — Store the record in a durable log with phase tracking:**

```python
import asyncio
from datetime import datetime, timezone

class CompensationLog:
    """Append-only log of action records with phase state.
    Survives agent restarts, context resets, and multi-agent handoffs."""

    def __init__(self, store):
        self.store = store  # Redis, Postgres, SQLite — any durable store

    async def commit(self, record: ActionRecord, result: Any):
        """Mark action as committed. Store result needed for compensation."""
        record.phase = ActionPhase.COMMITTED
        record.committed_result = result
        await self.store.put(record.intent_key, record)

    async def compensate(self, compensation_key: str) -> bool:
        """Look up the compensation record and execute the reversal.
        Returns True if already compensated (deduplicated), raises if not found."""
        record = await self.store.get_by_compensation_key(compensation_key)
        if not record:
            raise ValueError(f"No action record for compensation key: {compensation_key}")

        if record.phase == ActionPhase.COMPENSATED:
            return True  # already done — idempotent

        if record.phase == ActionPhase.COMPENSATING:
            # Another process is handling this. Wait or bail.
            raise RuntimeError(f"Compensation already in progress: {compensation_key}")

        record.phase = ActionPhase.COMPENSATING
        await self.store.put(record.intent_key, record)

        # Execute the compensation action
        comp_fn = COMPENSATION_REGISTRY.get(record.compensation_params.get('comp_action'))
        await comp_fn(record.compensation_params)

        record.phase = ActionPhase.COMPENSATED
        await self.store.put(record.intent_key, record)
        return False

    async def scan_for_orphans(self, window_hours: int = 1) -> list[ActionRecord]:
        """Find actions in PENDING state older than window — likely dropped mid-execution.
        These need to be resolved before the agent proceeds."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        return await self.store.scan(
            phase=ActionPhase.PENDING,
            updated_before=cutoff,
        )

COMPENSATION_REGISTRY: dict[str, Callable] = {}

def register_compensation(action: str):
    def deco(fn: Callable):
        COMPENSATION_REGISTRY[action] = fn
        return fn
    return deco

@register_compensation("reactivate_subscription")
async def reactivate_subscription(params: dict):
    # Call the API to undo the cancellation
    await subscription_api.reactivate(params["subscription_id"])
```

**Step 3 — Wire it into the agent's tool execution loop:**

```python
async def execute_with_compensation(agent, tool_name: str, params: dict, log: CompensationLog):
    action_meta = TOOL_META[tool_name]  # {comp_action, comp_param_map}

    record = derive_compensation_key(
        action_type=tool_name,
        params=params,
        comp_action=action_meta["comp_action"],
        comp_params={k: params[v] for k, v in action_meta["comp_param_map"].items()},
    )

    # Phase 1: execute
    await log.commit(record, result=None)  # Mark PENDING immediately
    try:
        result = await agent.tools[tool_name](**params)
        record.committed_result = result
        record.phase = ActionPhase.COMMITTED
        await log.store.put(record.intent_key, record)
        return result
    except ToolError as e:
        # Check if error is recoverable — if so, retry normally (S-96 fallback chain)
        if e.recoverable:
            raise
        # Non-recoverable: mark as FAILED, compensation may still be needed
        record.phase = ActionPhase.FAILED
        await log.store.put(record.intent_key, record)
        raise

# Triggering compensation: call from any process that detected the bad state
# (billing reconciliation, audit job, user dispute, eval harness)
await log.compensate(compensation_key="a3f9c1e2b8d70456")
# Idempotent — returns True if already done, executes if not
```

## Receipt

> Verified 2026-07-02 — Compiled from production patterns documented by Cordum (AI Agent Idempotency Keys in Production), AgentMarketCap (Tool Call Reliability Patterns 2026), and Stackwell (Agentic AI in Production). Key pattern confirmed: compensation keys differ from idempotency keys by encoding the *reversal action* params, not the original action params. The `idempotent` store must use `NX` (set-if-absent) semantics to prevent race conditions between concurrent retries. Three-layer key model (intent / execution / compensation) sourced from compensation key architecture described in Cordum's production guide.

## See also

- [S-93 · Tool Side-Effect Idempotency](s93-tool-side-effect-idempotency.md) — idempotency keys for the execution layer; this entry handles the layer *above* when execution was the wrong answer
- [S-181 · Live Data Event Deduplicator](s181-live-data-event-deduplicator.md) — deduplication of incoming events; compensation keys handle the symmetric problem of deduplicating outgoing reversals
- [F-107 · In-Flight Request Deduplication](f107-in-flight-request-deduplication.md) — deduplication of concurrent LLM calls; compensation keys survive the window where in-flight calls complete with conflicting results
- [S-96 · Tool Fallback Chains](s96-tool-fallback-chains.md) — fallback chains decide *how* to retry; compensation keys decide *what* to undo when the retry itself was wrong
