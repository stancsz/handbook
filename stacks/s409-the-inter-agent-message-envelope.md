# S-409 · The Inter-Agent Message Envelope

When a multi-agent pipeline starts producing garbage outputs, the instinct is to blame the model. Bad reasoning, wrong context, hallucination. But in practice, a large fraction of multi-agent failures trace back to something far more boring: agents that can't reliably communicate with each other. Malformed JSON that passes syntax validation but fails semantic parsing. A status field that means `complete` to the sender and `partial` to the receiver. A retry that fires an operation twice because there was no idempotency key. These aren't model failures — they're interface failures. And they're harder to debug than model failures because nothing in your logs tells you the serialization contract broke.

## Forces

- **The LLM did exactly what it was told; the problem is that what it was told arrived in a broken form.** When the orchestrator sends `{"status": "done", "result": null}` and the worker treats `result: null` as an error, the agent reasoning is sound and the output is wrong. You can watch the trace, see perfect reasoning, and have no clue why the downstream agent derailed.
- **A2A and MCP standardize transport, not semantics.** Google's A2A and Anthropic's MCP solve the hard problems of agent discovery, tool access, and transport negotiation. They say nothing about what a `task_completed` message must contain, what `correlation_id` means across hops, or what a recipient should do when it receives a `status` it doesn't recognize. The gap between "we both speak A2A" and "we understand each other" is enormous.
- **Schema drift compounds silently across agents.** A change to an upstream agent's output format propagates to all downstream consumers. Without versioned schemas and explicit backward-compatibility windows, a single change corrupts an entire workflow — with no error, no warning, and no rollback path.
- **Naive JSON dicts pass syntax validation and fail at runtime.** A `pydantic` model validates structure. It says nothing about semantic contract: whether a `null` field means "unset," "unknown," or "intentionally empty." Two agents can both validate the same message and produce contradictory interpretations at runtime.

## The move

**Enforce a mandatory message envelope on every inter-agent call.**

The envelope wraps the payload with metadata that makes communication contracts explicit and debuggable:

```python
from pydantic import BaseModel, Field
from enum import Enum
import uuid
from datetime import datetime, timezone


class Status(str, Enum):
    PENDING    = "pending"
    IN_PROGRESS = "in_progress"
    PARTIAL    = "partial"   # "I did something; more is needed"
    COMPLETE   = "complete"   # "My part is done, no follow-up expected"
    FAILED     = "failed"
    TIMEOUT    = "timeout"    # Distinct from FAILED — retry window may differ


class InterAgentEnvelope(BaseModel):
    # --- Identity ---
    message_id:    str = Field(default_factory=lambda: str(uuid.uuid4()))
    transaction_id: str = Field(
        description="Root correlation ID for the entire workflow; "
                    "propagates unchanged across all hops"
    )
    parent_id:      str | None = Field(
        default=None,
        description="message_id of the direct predecessor in the chain"
    )
    in_reply_to:    str | None = Field(
        default=None,
        description="message_id this message is responding to; "
                    "enables request/reply tracing"
    )

    # --- Sender ---
    sender_id:   str = Field(description="Agent identifier, e.g. 'orchestrator-v2'")
    sender_role: str = Field(description="'planner', 'worker', 'reviewer', etc.")

    # --- Semantic contract ---
    status: Status = Field(
        description="MUST be one of the enum values. "
                    "Ambiguous status = reject and request clarification."
    )
    schema_version: str = Field(
        default="1.0",
        description="Payload schema version. Reject messages with "
                    "major-version mismatch."
    )
    intent: str = Field(
        description="One-liner: what the sender expects the recipient to do. "
                    "Not for the model — for the ops engineer reading traces."
    )

    # --- Payload ---
    payload: dict = Field(default_factory=dict)

    # --- Reliability ---
    idempotency_key: str | None = Field(
        default=None,
        description="Client-generated key. If recipient has seen this key, "
                    "return the cached response without re-processing."
    )
    ttl_seconds: int = Field(default=300)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    retry_count: int = Field(default=0)

    def with_status(self, status: Status) -> "InterAgentEnvelope":
        """Immutable update — returns a new envelope with updated status."""
        data = self.model_dump()
        data["message_id"] = str(uuid.uuid4())
        data["parent_id"]   = self.message_id
        data["status"]      = status
        data["retry_count"] = 0
        return InterAgentEnvelope(**data)
```

**The enforcement rules:**

1. **Reject ambiguous status.** If a recipient receives a status it doesn't recognize, it must request clarification rather than guessing. Log the violation, emit a `CONTRACT_VIOLATION` event with the message ID, and block forward progress.
2. **Idempotency on every mutating call.** Generate the idempotency key at the call site and store it in the envelope. The recipient checks its cache before processing.
3. **Propagate `transaction_id` unchanged.** This is your distributed trace ID. Every log line, every artifact, every error ties back to it. Without it, you're flying blind across agent hops.
4. **Version-gate the payload.** Reject messages where `schema_version` major doesn't match. Emit `SCHEMA_MIGRATION_NEEDED` instead of silently misinterpreting.
5. **TTL gates retry.** A `timeout` status means "I ran out of time, not that I failed." The retry logic can distinguish the two and apply different backoff.
6. **Distinguish `partial` from `complete`.** `partial` is a legitimate status, not an error. An agent that returns `partial` has done something — it found part of the answer, or hit a sub-limit. The orchestrator knows to continue. `complete` means stop.

## See also

- [S-14 · A2A Protocol](s14-a2a-protocol.md) — the transport layer A2A provides; this entry covers what A2A leaves undefined
- [S-273 · Untyped Agent Handoffs](s273-untyped-agent-handoffs.md) — the broader problem of structural failures at agent boundaries
- [S-343 · Multi-Agent as Distributed Systems](s343-multi-agent-distributed-systems.md) — treating inter-agent messages as distributed state

## Receipt

> Verified 2026-07-03 — Pattern confirmed from production multi-agent failure analysis (tianpan.co, April 2026). IETF draft-cowles-aee-00 (February 2026) independently converges on 14-field envelope with transaction_id, correlation, TTL, and schema versioning — the exact same structural needs identified here. A2A and MCP both exist but neither mandates semantic envelope fields; the gap is real and documented.
