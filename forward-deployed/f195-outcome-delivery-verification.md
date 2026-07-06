# F-195 · Outcome Delivery Verification

Your cron ran for 298 seconds. It created the GitHub issue, opened the Jira ticket, and updated the spreadsheet. Every tool call returned success. The framework recorded a green run. The user received nothing — because the Slack notification was step 6 of 6, and the budget cut off at step 5. This is the most dangerous silent failure in production agents: not a crash, not a bad output, but work completed into a void.

## Forces

- **The framework measures the run, not the outcome.** Most agent runtimes (Cron, Temporal, etc.) track whether the agent loop completed, not whether the user received the result. A run that runs out of budget before delivery is indistinguishable from a run that delivered successfully.
- **Delivery is almost always last.** The announce/report/notify step is placed at the end of the agent's task list. When budget or time runs out, it cuts delivery first — the step that tells the user the work is done.
- **"Success" is the wrong signal.** A green run in your dashboard means the agent finished its loop without crashing. It says nothing about whether the side effects reached the intended recipient.
- **The agent's internal model says it succeeded.** Every tool returned success. The agent has no mechanism to know the notification was cut — it recorded completion and moved on.

## The move

Separate **execution verification** from **delivery confirmation**. Treat the side effect as the real artifact, not the agent's self-reported completion.

**1. Instrument side effects as first-class events, not last steps.**

Do not put delivery at the end of the agent's task list. Elevate it to a required checkpoint that gates the "run complete" signal:

```
Agent Loop
├── T1: Create GitHub issue  →  verify(github.issue.exists)
├── T2: Open Jira ticket    →  verify(jira.ticket.exists)
├── T3: Update sheet        →  verify(sheet.row.updated)
├── T4: [delivery step]
└── if not verify_all():
      rollback()
      escalate()
```

**2. The verification function is a read that confirms the write happened.**

Each `verify()` is an out-of-band read — not the tool's own return value. The tool said it succeeded; the verifier independently confirms it:

```python
import time

def verify(check_fn, timeout=30, interval=2):
    """Poll until the side effect is observable, or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if check_fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False

def verify_github_issue(repo: str, title: str, actor: str) -> bool:
    """Confirm the issue was created by the agent, not another process."""
    issues = github_api.list_issues(repo, state="open", creator=actor)
    return any(title in i.title for i in issues)

# Gate: the run is not complete until the issue is verifiable
if not verify(lambda: verify_github_issue("acme/app", "[Cron] Bug report", "bot@acme")):
    raise DeliveryError(f"GitHub issue not confirmed within timeout")
```

**3. Treat delivery failure as a rollback trigger, not a warning.**

If delivery fails after all other steps succeeded, you have a choice: retry delivery (the work is done, just not announced) or rollback (undo the side effects so the next run starts clean). The right call depends on reversibility:

- **Email/Slack notification → retry delivery only.** The work is done; just try again.
- **Database write / record creation → rollback + retry.** The state was modified; roll back first.
- **External system (payment, provisioning) → escalate immediately.** Do not retry blindly.

```python
class OutcomeDeliveryVerifier:
    def __init__(self, rollback_fn=None):
        self.steps = []
        self.rollback_fn = rollback_fn or (lambda: None)

    def add_step(self, name: str, check_fn, rollback_fn=None):
        self.steps.append({"name": name, "check": check_fn, "rollback": rollback_fn})

    def verify_all(self) -> dict[str, bool]:
        results = {}
        for step in self.steps:
            results[step["name"]] = step["check"]()
        return results

    def run(self):
        results = self.verify_all()
        failed = [name for name, ok in results.items() if not ok]

        if failed:
            # Roll back completed steps
            for step in reversed(self.steps):
                if step["rollback"] and results.get(step["name"]):
                    step["rollback"]()
            raise DeliveryError(f"Verification failed for: {failed}")

        # Only now is delivery safe to attempt
        self.deliver(results)
        return results
```

**4. Send the delivery signal before declaring the run complete.**

If the delivery notification is itself a tool call, verify it too:

```python
def deliver_and_confirm(notify_fn, confirm_fn, retries=3):
    for attempt in range(retries):
        notify_fn()
        if confirm_fn():
            return
        time.sleep(2 ** attempt)  # exponential backoff
    raise DeliveryError(f"Delivery confirmation failed after {retries} attempts")
```

## Receipt

> Verified 2026-07-03 — Pattern demonstrated via stub implementation in Pazi.ai's cron failure taxonomy (blog post, April 2026): the "Cron That Succeeds But Never Delivers" failure mode is documented with the 298-second budget-cut example. Verification via out-of-band reads (not tool return values) is recommended across Harness Engineering and Maxim AI observability guides (Q1 2026).

## See also

- [F-181 · Silent Tool Call Failures](f181-silent-tool-call-failures.md) — the upstream problem: tool calls that report success while silently failing
- [S-93 · Tool Side-Effect Idempotency](s93-tool-side-effect-idempotency.md) — preventing the same side effect from happening twice
- [S-32 · Verifiability Divider](s32-verifiability-divider.md) — why checkability is the architectural dividing line for production agents
