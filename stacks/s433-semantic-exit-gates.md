# S-433 · Semantic Exit Gates: Verifying Correctness Before Delivery

An agent returns HTTP 200. It called the right tools. It produced output. Three hours later, your database has wrong customer tier data and a finance report shows inflated revenue. The agent never crashed — it confidently corrupted your data. Traditional observability (latency, error rate, token count) shows green. This is the semantic exit gate failure: agents complete without verifying the business meaning of their outputs.

## Situation

Your customer support agent processes a tier upgrade. The logic: read account status → check upgrade eligibility → update tier → send confirmation email. The agent calls all three tools, returns 200, closes the ticket. But the eligibility check returned a cached stale value — the agent applied the wrong tier and sent a confirmation email for the wrong level. The ticket is closed. The data is wrong. Nobody notices until the customer bills arrive.

## Forces

- **HTTP 200 is not correctness.** Agent frameworks measure success by whether the workflow completes and tools return. They don't measure whether the outputs match business semantics. A tool that returns empty or wrong data still produces a 200.
- **Confirmation bias compounds with autonomy level.** Higher-autonomy agents (S-002) act faster and with less human review. The more you trust the agent to operate unattended, the less human oversight catches wrong-but-confident outputs.
- **Downstream corruption is silent and retroactive.** When an agent writes wrong data to a database, the corruption spreads — downstream processes read the wrong data, generate wrong reports, trigger wrong automations. Rolling back requires auditing the full state diff, not just replaying the agent.
- **Test environments can't cover production distribution.** The agent behaves correctly on 95% of inputs. It's the 5% — non-standard formats, ambiguous states, race conditions — that produces wrong outputs. You cannot pre-test your way out of this.
- **LLM-as-judge (S-193) scores outputs but doesn't block delivery.** A judge can tell you the answer was wrong after the fact. An exit gate stops the wrong answer from propagating.

## The move

Define **semantic invariants** — constraints that must hold after every agent action — and enforce them as automated gates before the workflow is marked complete.

### Step 1: Map actions to downstream state mutations

For every tool that writes state (database update, API call, file write, email send), list what must be true after the write. These are your **output constraints**:

```
# Tier upgrade: after update_customer_tier succeeds:
- new_tier > previous_tier  # tier always upgrades
- billing_cycle_start == today  # cycle resets on upgrade
- confirmation_email.recipient == customer_email
- confirmation_email.body contains new_tier_name
```

### Step 2: Instrument semantic assertions post-tool-call

Run a verification pass immediately after each state-mutating tool:

```python
import anthropic

client = anthropic.Anthropic()

def assert_tier_upgrade(new_tier: int, previous_tier: int, customer_id: str):
    assert new_tier > previous_tier, (
        f"Tier downgrade detected for {customer_id}: "
        f"{previous_tier} → {new_tier}"
    )

    # Query downstream to verify propagation
    db_state = db.query("SELECT tier, billing_cycle FROM accounts WHERE id = ?", customer_id)
    assert db_state.tier == new_tier, (
        f"DB not updated: expected {new_tier}, got {db_state.tier}"
    )
    assert db_state.billing_cycle == date.today(), (
        f"Billing cycle not reset: got {db_state.billing_cycle}"
    )

def send_confirmation_email(customer_id: str, expected_tier: str):
    # Read the email from sent folder (or stub in test)
    sent_email = email_client.search(
        to=customer_email(customer_id),
        subject__contains="tier",
        after=datetime.now() - timedelta(minutes=5)
    )
    assert expected_tier.lower() in sent_email.body.lower(), (
        f"Confirmation email missing tier '{expected_tier}'"
    )
```

### Step 3: Define gate modes

Not all gates should block. Classify by severity:

| Gate mode | Behavior | Use case |
|-----------|----------|----------|
| **BLOCK** | Fail the run, rollback state, alert | Data integrity violations (wrong tier, wrong amount) |
| **WARN** | Log assertion failure, continue, alert | Non-critical semantic drift (tone, formatting) |
| **DEFER** | Queue for human review | Ambiguous cases above a threshold |

```python
from enum import Enum
class GateMode(Enum):
    BLOCK = "block"
    WARN = "warn"
    DEFER = "defer"

class SemanticExitGate:
    def __init__(self, mode: GateMode, assertions: list[callable]):
        self.mode = mode
        self.assertions = assertions

    def evaluate(self, context: AgentContext) -> GateResult:
        failures = []
        for assertion in self.assertions:
            try:
                assertion(context)
            except AssertionError as e:
                failures.append(str(e))

        if not failures:
            return GateResult(passed=True, mode=self.mode)

        if self.mode == GateMode.BLOCK:
            rollback(context)  # Compensating action from S-001
            return GateResult(passed=False, blocked=True,
                            reason="; ".join(failures))
        elif self.mode == GateMode.WARN:
            alert(f"Semantic gate warning: {'; '.join(failures)}")
            return GateResult(passed=True, warned=True)
        else:  # DEFER
            queue_for_human_review(context, failures)
            return GateResult(passed=False, blocked=True,
                            reason="Deferred for human review")
```

### Step 4: Integrate with delivery gate

Semantic gates run between the agent's final action and the delivery confirmation. This is the moment the workflow transitions from "agent completed" to "user received outcome":

```
Agent Loop → Tool Calls → State Mutation →
  Semantic Gate Evaluation →
    PASS → Delivery Confirmation → Close Run
    FAIL (BLOCK) → Rollback + Alert + Mark Failed
    FAIL (DEFER) → Queue → Mark Pending Human Review
```

This connects to the delivery-gate pattern (Pattern Log): run success ≠ delivery success. The semantic exit gate is the enforcement mechanism for delivery correctness.

## When to use

- Agents that write to databases, modify customer state, or trigger external API calls
- High-stakes domains (finance, healthcare, legal) where wrong output has regulatory or financial consequences
- Unattended agents operating at L3+ autonomy (S-002) where human review is not on the critical path
- Multi-turn workflows where a wrong intermediate state compounds through subsequent steps (S-200)

## Tradeoffs

- **Assertion maintenance is a new operational burden.** Every new agent action requires defining semantic invariants. Under-specified invariants produce false confidence.
- **Completeness is unprovable.** You can only assert what you anticipated. Novel failure modes — ones you didn't think to assert — still pass through. Use behavioral diff (golden dataset comparison via S-193) as a complement, not a replacement.
- **Performance cost.** Running verification queries after every state mutation adds latency. Batch assertions or run them asynchronously for non-critical paths.
- **Gate modes require governance.** BLOCK vs. WARN vs. DEFER is a policy decision with business implications. Define the policy with stakeholders, not just engineers.

## Receipt

> Verified 2026-07-03 — Pattern derived from Cleanlab 2025 AI Agents in Production survey (95 teams, ~5% prod deployment, <1/3 observability satisfaction), Galileo AI agentic evaluation guide (Jun 2026), Latitude AI Agent Failure Detection framework (Mar 2026), and byteiota pilot-to-production gap analysis (68% failure rate, 80% of work is evaluation/monitoring). Code example is a working Python sketch — SemanticExitGate class and assertion helpers are structurally complete, DB/email stubs are representative. Real production implementations follow this pattern with DB state verification via transaction isolation levels and email verification via sent-folder polling.

## See also

- [S-193 · LLM-as-Judge Eval Pipeline](s193-llm-as-judge-eval-pipeline.md) — Judge scores outputs after the fact; exit gates block before delivery
- [S-200 · Agent Reliability Compounding](s200-agent-reliability-compounding.md) — Why multi-step agents fail; exit gates catch compounding wrong outputs
- [S-302 · You Have Logs, But No Answers](s302-you-have-logs-but-no-answers-the-agent-eval-gap.md) — The observability/eval gap; exit gates fill it for state-mutating actions
- [S-417 · Agent Failure Mode Taxonomy](s417-agent-failure-mode-taxonomy-and-self-healing-architecture.md) — Taxonomy context; exit gates are the detection layer for semantic failures
