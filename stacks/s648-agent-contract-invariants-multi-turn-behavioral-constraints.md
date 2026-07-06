# S-648 · Agent Contract Invariants: Multi-Turn Behavioral Constraints

When a single tool-call guardrail approves each action in isolation, the agent can still produce catastrophic outcomes through a sequence of individually-approved calls. "Send an email" is approved. So is "look up recipient address." So is "attach the file." None of these individually violates policy — but the combination, executed 50 times per hour, is a mass-surveillance breach. Single-call guardrails cannot see sequences. The fix is runtime invariant enforcement: behavioral constraints that evaluate over conversation state, not per-turn permissions.

## Forces

- **Sequences are invisible to per-call guardrails.** S-198 (tool-call guardrails) intercepts individual calls. S-349 (four-layer enforcement) defines the planes. Neither enforces constraints that emerge from accumulated behavior across turns — "this agent has sent 47 emails in the last hour" is not visible to a guardrail that only sees one call at a time.
- **State-dependent permissions.** Whether an action is acceptable depends on accumulated state: has the user confirmed this recipient? Is the file destination inside the allowed scope? Is the agent still within its operational budget? Per-call checks have no memory.
- **Invariant drift is silent.** An invariant like "never exceed $10/session" starts passing. Over 50 turns of small overages, the agent accumulates a $12 bill. The per-call guardrail never fires; the outcome is still wrong.

## The move

**1. Name the invariant explicitly.** Every agent gets a declared invariant set before deployment:

```python
class AgentContract:
    """The behavioral contract for an agent instance."""

    # Rate invariants — enforce over rolling windows
    max_emails_per_hour: int = 3
    max_tool_calls_per_session: int = 500

    # Scope invariants — enforce per operation
    allowed_file_paths: list[str] = ["/project/src", "/project/tests"]
    allowed_email_domains: list[str] = ["@company.com"]

    # Budget invariants — enforce per session
    max_token_budget: int = 200_000
    max_cost_usd: float = 10.0

    # Relational invariants — enforce across agent relationships
    requires_user_confirmation_for_external_email: bool = True
    requires_approval_above_usd: float = 100.0
```

**2. Track state in the harness, not in the prompt.** The invariant tracker lives in the execution harness, not in the agent's context window:

```python
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timedelta
import time

@dataclass
class InvariantTracker:
    """Runtime behavioral constraint tracker — not in the agent's head."""

    contract: AgentContract

    # Sliding-window counters
    email_timestamps: deque = field(default_factory=deque)
    tool_call_count: int = 0
    token_count: int = 0
    cost_usd: float = 0.0

    def check_email(self, recipient: str) -> tuple[bool, str]:
        """Check if sending an email violates the invariant set."""
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)

        # Purge timestamps outside the rolling window
        while self.email_timestamps and self.email_timestamps[0] < hour_ago:
            self.email_timestamps.popleft()

        if len(self.email_timestamps) >= self.contract.max_emails_per_hour:
            return False, f"Rate limit: max {self.contract.max_emails_per_hour}/hour"

        if not recipient.endswith(self.contract.allowed_email_domains[0]):
            return False, f"Domain {recipient} not in allowlist"

        return True, "approved"

    def check_file_write(self, path: str) -> tuple[bool, str]:
        """Scope invariant: file writes must stay within declared paths."""
        allowed = any(path.startswith(p) for p in self.contract.allowed_file_paths)
        if not allowed:
            return False, f"Path {path} outside allowed scope: {self.contract.allowed_file_paths}"
        return True, "approved"

    def check_budget(self, additional_tokens: int, additional_cost: float) -> tuple[bool, str]:
        """Budget invariant: hard stop on token and cost accumulation."""
        if self.token_count + additional_tokens > self.contract.max_token_budget:
            return False, f"Token budget exceeded: {self.contract.max_token_budget}"
        if self.cost_usd + additional_cost > self.contract.max_cost_usd:
            return False, f"Cost budget exceeded: ${self.contract.max_cost_usd}"
        return True, "approved"

    def record_email(self):
        self.email_timestamps.append(datetime.utcnow())

    def record_tool_call(self, tokens_used: int, cost_usd: float):
        self.token_count += tokens_used
        self.cost_usd += cost_usd
        self.tool_call_count += 1
```

**3. Intercept before execution, not after.** The invariant check happens in the harness's pre-execution hook:

```python
async def execute_with_contract(
    agent,
    tracker: InvariantTracker,
    tool_name: str,
    tool_args: dict,
    llm_result,
):
    """Run the tool call only if all invariants hold."""

    tokens = estimate_tokens(llm_result)
    cost = estimate_cost(tokens)

    # Check budget first — cheapest to fail
    ok, msg = tracker.check_budget(tokens, cost)
    if not ok:
        agent.abort(f"Budget invariant violated: {msg}")

    # Check tool-specific invariants
    if tool_name == "send_email":
        recipient = tool_args.get("recipient", "")
        ok, msg = tracker.check_email(recipient)
        if not ok:
            agent.abort(f"Email invariant violated: {msg}")
        tracker.record_email()

    elif tool_name in ("write_file", "create_file"):
        path = tool_args.get("path", "")
        ok, msg = tracker.check_file_write(path)
        if not ok:
            agent.abort(f"Scope invariant violated: {msg}")

    # Record usage after passing all checks
    tracker.record_tool_call(tokens, cost)

    return await agent.execute(tool_name, tool_args)
```

**4. Escalate violations, don't just block.** When an invariant fires, the escalation path should match the severity:

```python
def handle_violation(tracker, invariant_name, detail):
    if "rate" in invariant_name.lower():
        # Soft violation: queue for human approval
        queue_for_approval(f"EMAIL_RATE_LIMIT", tracker.contract, detail)
    elif "scope" in invariant_name.lower():
        # Hard violation: abort, alert, log
        alert_security(f"SCOPE_VIOLATION: {detail}")
        raise AgentContractViolation(f"Hard invariant violated: {detail}")
    elif "budget" in invariant_name.lower():
        # Budget: pause agent, notify operator
        pause_agent("budget_exhausted")
        notify_operator("Agent budget threshold reached")
```

## Receipt

> Receipt pending — 2026-07-05

## See also

- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — per-call interception layer
- [S-349 · Agentic Guardrails: The Four-Layer Enforcement Plane](s349-agentic-guardrails-four-layer-enforcement-plane.md) — the broader enforcement taxonomy
- [S-355 · Agent Autonomy Levels: Bounded Autonomy](s355-agent-autonomy-levels-bounded-autonomy.md) — mapping agents to autonomy levels
- [S-068 · Budget-Aware Agents](s068-budget-aware-agents-cost-as-first-class-behavioral-dimension.md) — cost as a behavioral dimension
