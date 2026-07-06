# S-627 · Action Completion Verification: When "Done" Doesn't Mean Done

Your agent called the ticketing API, got a `201 Created`, and logged "Ticket #48291 created successfully." Three hours later, the ops team finds the ticket was created in the wrong tenant account — the API authenticated as the wrong org, the error response was empty, and the agent had no way to know. The run looked perfect. The tool returned success. The task never happened.

This is the Action Completion Verification problem: the agent receives a success response from a tool, but the underlying system state never changed as intended — and the agent has no signal to tell the difference.

## Forces

- **Success codes are not state guarantees.** HTTP 200/201, database INSERT returning a row ID, and queue acknowledgment all mean "I received your request." They do not mean "the operation succeeded in the way you intended." A 201 can create a resource in the wrong scope. A DB write can violate a constraint silently. A queue message can be published and immediately dropped.
- **The agent's loop ends at the tool return.** After a tool returns, the agent typically generates its next action or produces a final response. There is no built-in step that verifies the resulting state matches the intended outcome. The completion signal is the tool response — not the system state.
- **Downstream systems trust the agent's "Done."** If the agent reports task complete, downstream integrations — escalation workflows, audit logs, customer notifications — take action on that claim. A false positive completion cascades through every system that trusts it.
- **Read-back verification adds latency.** The obvious fix — read back the system state after every write — doubles or triples the latency of every agent action. Teams avoid it for performance reasons, then discover the problem in production.
- **Idempotency keys mask the failure mode.** Tools that use idempotency keys will return success on replay, even when the original operation failed. The agent's retry logic reinforces the false belief that the action happened.

## The move

Split every agent action that modifies external state into a **write-then-verify** pattern:

```python
def verified_action(agent, tool_name, args, invariant_check):
    """
    agent: the agent/session
    tool_name: name of the mutating tool
    args: arguments to the tool
    invariant_check: a read-only function that returns True if the state is correct
    """
    # Step 1: Execute the action
    result = agent.tools.call(tool_name, **args)

    # Step 2: Check the response code is consistent with intent
    if not _response_is_success(result):
        raise ActionFailed(f"{tool_name} returned error: {result}")

    # Step 3: Verify state changed as intended (the read-back)
    if invariant_check and not invariant_check():
        # The tool succeeded but the state didn't change as intended
        raise StateMismatch(
            f"{tool_name} reported success but state verification failed. "
            f"Tool response: {result}. Reverting."
        )

    return result
```

**The `invariant_check` is the critical component.** It should verify the *specific* state change you care about — not just "did anything change" but "did the right thing change in the right way."

**Examples of invariant checks:**

```python
# Ticket creation: verify it exists in the right project
def check_ticket_created(ticket_id, expected_project_id):
    ticket = jira_client.get_ticket(ticket_id)
    return ticket["project_id"] == expected_project_id

# Database write: verify the row was written with correct values
def check_user_prefs(user_id, expected_key, expected_value):
    row = db.query("SELECT value FROM user_prefs WHERE user_id = ?", user_id)
    return row and row["value"] == expected_value

# Email send: verify recipient and subject match intent
def check_email_sent(message_id, expected_recipient):
    status = email_provider.get_status(message_id)
    return status["state"] == "delivered" and status["recipient"] == expected_recipient

# Payment: verify transaction settled, not just authorized
def check_payment_settled(payment_id, expected_amount):
    tx = payment_api.get_transaction(payment_id)
    return tx["status"] == "settled" and tx["amount"] == expected_amount
```

**Selective verification** — not every action needs full read-back. Cost of verification must be weighed against blast radius:

| Blast radius of failure | Verification level |
|------------------------|--------------------|
| Financial transaction, legal action, irreversible write | Full invariant check, mandatory |
| Customer-visible state (email, ticket, notification) | Semantic response check + partial read-back |
| Internal state (logging, metrics, cache update) | Response code only |
| Read-only operations | None required |

**The compensating action** — when `StateMismatch` fires, the agent should either retry with corrected args or escalate. Never silently swallow a mismatch and report completion:

```python
def handle_state_mismatch(tool_name, args, error, agent_session):
    # Option 1: Retry with corrected args (if failure was transient)
    corrected_args = diagnose_and_fix(args, error)
    if corrected_args:
        return verified_action(agent, tool_name, corrected_args, ...)
    # Option 2: Escalate — mark task as FAILED, not DONE
    agent_session.mark_blocked(
        reason=f"Action {tool_name} verified as incomplete: {error}",
        escalation="human"
    )
    return None
```

## Receipt

> Verified 2026-07-05 — Pattern confirmed across: Pazi.ai incident reports (wrong-tenant ticket creation), Harness Engineering case study (stale token causing silent email send failure), multiple practitioner reports (SaaS Science June 2026, Noveum.ai). Verified against S-212 (output validation) — this pattern is orthogonal: S-212 validates generated content, S-627 validates executed state. Distinct from F-195 (outcome delivery verification): F-195 covers whether the user received the outcome; S-627 covers whether the action actually changed system state. Both layers are required.

## See also

- [S-212 · Semantic Output Validation Gate](stacks/s212-semantic-output-validation-gate.md) — validates generated content quality before output
- [F-195 · Outcome Delivery Verification](forward-deployed/f195-outcome-delivery-verification.md) — ensures the outcome reached the user
- [S-561 · The Self-Correction Gap](stacks/s561-the-self-correction-gap-when-agents-cant-self-heal.md) — agent awareness of its own failure
