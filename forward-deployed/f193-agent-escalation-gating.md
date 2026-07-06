# F-193 · Agent Escalation Gating

When your agent is mid-task at 11 PM, the user's approval window has closed, and the next step is irreversible — send the wire, delete the record, publish the draft — you have a problem that prompting cannot solve. Evals detect problems after the fact. Observability tells you something is wrong. Escalation gating is the enforcement layer that stops irreversible damage before it happens by inserting human decision points where automated trust breaks down. The discipline is new, the tooling is immature, and 63% of organizations cannot enforce purpose limitations on their AI agents (Kiteworks 2026). That gap is where incidents live.

## Forces

- **LLM confidence is systematically miscalibrated.** Models trained with RLHF express highest confidence on incorrect outputs. A claimed 90% confidence often corresponds to ~75% real-world accuracy. Chaining three agents at ~75% per step yields ~42% probability all steps are correct — the quantitative case for escalation gates.
- **Irreversible actions have zero undo.** `DELETE`, `send_email`, `exec_sql UPDATE`, `POST /payments` — the agent's next tool call might permanently change state. A circuit breaker (F-192) handles budget and rate failures; escalation gating handles decision authority failures.
- **63% of organizations cannot enforce purpose limitations on their agents, 60% cannot terminate a misbehaving agent, and 55% cannot isolate agents from network access.** (Kiteworks 2026 Data Security Risk Forecast.) The tooling to do these things exists but is not deployed.
- **Synchronous approval UX kills agent throughput.** Blocking the agent loop to wait for a human approval is acceptable for tier-1 irreversible actions; it is catastrophic for agents processing thousands of items per hour. Async escalation patterns are required for production scale.
- **The attack surface compounds across agent chains.** A sub-agent with delegated permissions cannot escalate to its parent. A supervisor agent that spawned ten sub-agents during a loop has no unified visibility into which ones need human review.

## The move

Escalation gating has three components: a **risk tier classifier** that evaluates each pending action, a **gate executor** that either blocks, pauses, or delegates based on tier, and a **resolution handler** that records the human decision and resumes the agent loop.

### 1. Classify by consequence, not confidence

Four tiers, mapped to action type and scope:

| Tier | Label | Definition | Response |
|------|-------|-----------|---------|
| 0 | Read-only | No state change, no external system | Proceed automatically |
| 1 | Bounded write | Revertable change, rollback exists | Proceed; log for audit |
| 2 | Unbounded write | Permanent or wide-scope change | **Pause + async approval** |
| 3 | Critical | Financial, legal, or safety consequence | **Block + synchronous approval** |

Classify at tool-definition time, not at call time. Embed the tier in the tool metadata:

```python
TOOL_REGISTRY = {
    "send_email":     {"tier": 2, "scope": "single_recipient", "rollback": False},
    "exec_sql":       {"tier": 3, "scope": "table",             "rollback": True},
    "write_file":     {"tier": 1, "scope": "file",              "rollback": True},
    "http_post":      {"tier": 3, "scope": "endpoint",          "rollback": False},
    "read_dashboard": {"tier": 0, "scope": "none",              "rollback": None},
}
```

### 2. Gate execution with async for tier 2, sync for tier 3

```python
import asyncio
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional
import uuid

class RiskTier(IntEnum):
    READ_ONLY = 0
    BOUNDED_WRITE = 1
    UNBOUNDED_WRITE = 2
    CRITICAL = 3

@dataclass
class EscalationRequest:
    request_id: str
    agent_id: str
    tool_name: str
    args: dict
    tier: RiskTier
    context_snippet: str  # last 3 turns of agent reasoning
    status: str = "pending"  # pending | approved | denied | timeout
    responder_id: Optional[str] = None
    resolution_note: Optional[str] = None

class EscalationGate:
    def __init__(self, redis_url: str, escalation_queue: str):
        self.redis = redis.from_url(redis_url)
        self.queue = escalation_queue

    async def evaluate(self, tool_name: str, args: dict) -> bool:
        """Returns True if the action should proceed. False if gated."""
        tier = TOOL_REGISTRY.get(tool_name, {}).get("tier", RiskTier.BOUNDED_WRITE)
        
        if tier == RiskTier.READ_ONLY:
            return True  # no gate
        
        if tier == RiskTier.BOUNDED_WRITE:
            await self._log_action(tool_name, args, tier)
            return True  # proceed with audit trail
        
        if tier == RiskTier.UNBOUNDED_WRITE:
            # Async escalation: enqueue, return False to pause agent loop
            req = self._build_request(tool_name, args, tier)
            await self._enqueue_async(req)
            return False  # agent loop pauses here
        
        # tier == RiskTier.CRITICAL
        # Sync escalation: block until human approves or denies
        req = self._build_request(tool_name, args, tier)
        return await self._wait_sync(req, timeout_seconds=300)

    async def _wait_sync(self, req: EscalationRequest, timeout_seconds: int) -> bool:
        """Block agent loop, wait for human decision."""
        await self._enqueue_sync(req)
        result = await self._poll(req.request_id, timeout=timeout_seconds)
        if result is None:
            # Timeout — default deny for critical actions
            await self._log_denial(req, "timeout")
            return False
        return result.status == "approved"

    async def _poll(self, request_id: str, timeout: int) -> Optional[EscalationRequest]:
        """Poll Redis for resolution. Replace with your notification system."""
        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(5)
            elapsed += 5
            raw = self.redis.get(f"escalation:{request_id}")
            if raw:
                return EscalationRequest(**json.loads(raw))
        return None

    def _build_request(self, tool_name: str, args: dict, tier: RiskTier) -> EscalationRequest:
        return EscalationRequest(
            request_id=str(uuid.uuid4()),
            agent_id=self.agent_id,
            tool_name=tool_name,
            args=args,
            tier=tier,
            context_snippet=self._get_reasoning_context()
        )

    def _get_reasoning_context(self) -> str:
        # Capture last N turns from agent's reasoning trace
        return "\n".join(self.reasoning_buffer[-3:])

    async def _enqueue_async(self, req: EscalationRequest):
        """Enqueue to Slack/Teams/PagerDuty for non-blocking review."""
        self.redis.setex(f"escalation:{req.request_id}", 3600, json.dumps(asdict(req)))
        await self._notify(req)  # your Slack/email integration

    async def _enqueue_sync(self, req: EscalationRequest):
        """Push urgent alert with auto-page for critical tier."""
        await self._notify(req, urgent=True)  # PagerDuty/escalation path

    async def resume_from_gate(self, request_id: str, approved: bool, note: str = ""):
        """Called by approval UI/webhook when human responds."""
        status = "approved" if approved else "denied"
        key = f"escalation:{request_id}"
        raw = self.redis.get(key)
        if raw:
            req = EscalationRequest(**json.loads(raw))
            req.status = status
            req.resolution_note = note
            self.redis.setex(key, 86400, json.dumps(asdict(req)))
```

### 3. Integrate into agent loop

```python
async def agent_loop(prompt: str, gate: EscalationGate):
    messages = [{"role": "user", "content": prompt}]
    reasoning_buffer = []
    
    while True:
        # Agent reasons
        response = await llm.chat(messages)
        reasoning_buffer.append(response.reasoning)
        
        # Agent decides to use a tool
        tool_calls = response.tool_calls
        if not tool_calls:
            break  # done
        
        for tc in tool_calls:
            should_proceed = await gate.evaluate(tc.name, tc.args)
            
            if not should_proceed:
                # Agent is paused. Polling loop handles resume.
                # Store pending continuations and re-inject when gate resolves.
                await gate.store_pending_continuation(tc, messages)
                await gate.wait_for_resolution(tc.request_id)
                messages.append(gate.get_resolution_message(tc.request_id))
                break  # restart loop with resolved state
            else:
                result = await tc.execute()
                messages.append({"role": "tool", "name": tc.name, "content": result})
```

### 4. Kill switch — fleet-level emergency stop

Escalation gating handles per-action decisions. A kill switch handles the emergency case where the agent is already misbehaving and needs to stop *everything*:

```python
class KillSwitch:
    """Fast, auditable fleet kill switch. Blocks all state-changing actions."""
    
    def __init__(self, redis: Redis):
        self.redis = redis
        self.flag_key = "agent:fleet:kill_switch"
    
    def is_active(self) -> bool:
        return self.redis.get(self.flag_key) == b"ACTIVE"
    
    async def trip(self, actor: str, reason: str, scope: str = "fleet"):
        """
        scope: 'fleet' (all agents) | 'agent:<id>' (single) | 'tool:<name>' (tool-wide)
        """
        payload = {"actor": actor, "reason": reason, "scope": scope, "ts": time.time()}
        self.redis.setex(self.flag_key, 86400, json.dumps(payload))
        # Emit audit event to SIEM
        await audit_log.write("kill_switch_activated", payload)
    
    def resume(self, actor: str, resume_from: str = "last_checkpoint"):
        """Resume from last checkpoint or explicit step."""
        self.redis.delete(self.flag_key)
        audit_log.write("kill_switch_resumed", {"actor": actor, "resume_from": resume_from})
```

## Receipt

> Receipt pending — 2026-07-01

## See also

- [F-180 · AI Incident Commander](f180-ai-incident-commander.md) — owning the full diagnostic stack after escalation fires
- [F-192 · Cost Velocity Circuit Breaker](f192-cost-velocity-circuit-breaker.md) — automated budget enforcement that complements escalation gates
- [S-217 · Agent Capability Authorization](s217-agent-capability-authorization.md) — permission scoping that gates should respect at invocation time
