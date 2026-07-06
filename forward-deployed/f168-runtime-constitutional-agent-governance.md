# F-168 · Runtime Constitutional Agent Governance

An agent that generates its own skills, modifies its behavior mid-task, or acts on consequential decisions needs more than hard-coded rules and instruction hierarchies. It needs a **constitution** — a layer that evaluates whether a decision aligns with governing principles *at runtime*, before the action propagates.

## Forces

- **Authorization (WHO) and policy (HOW) are not enough.** IAM tells you whether the agent is permitted to act; OPA/Cedar policies tell you whether the action is allowed. Neither evaluates whether the *decision quality* aligns with the organization's values.
- **Instruction hierarchies govern inputs, not reasoning chains.** A system prompt that says "never approve spending over $10K" catches direct requests — but an agent that chains three sub-decisions to reach $12K bypasses it entirely.
- **Self-generated skills are unreliable without structural safeguards.** Agents that learn and encode new behaviors (skill generation, tool synthesis, workflow automation) create behavioral drift. The same capability that makes them useful also makes them unpredictable.
- **Hard constraints must be enforced in code, not prompt.** If "the agent may never modify its own governance rules" is only in the system prompt, a sufficiently capable model can reason around it. It needs a code-level gate.
- **The three-layer problem: WHO → HOW → WHY.** Most systems answer "is this agent authorized?" (WHO) and "is this action permitted?" (HOW). The missing layer is "does this decision align with constitutional principles?" (WHY).

## The move

**Constitutional agent governance** adds a runtime evaluation layer between decision and action. The pattern has three tiers:

| Tier | Question | Example tools | What it misses |
|------|----------|---------------|----------------|
| **WHO** | Is this agent authorized? | AWS IAM, Okta, Entra | Doesn't evaluate decision soundness |
| **HOW** | Is this action permitted? | OPA, Cedar, NeMo Guardrails | Only covers pre-scripted scenarios |
| **WHY** | Does this align with principles? | **Constitutional gate** | Evaluates novel, unanticipated cases |

**A constitutional layer has four components:**

1. **Principles** — written as natural-language rules authored by the system owner ("the agent shall not modify its own governance configuration," "spending approvals require dual authorization above $5K")
2. **Hard constraints (HC)** — code-enforced, non-overridable by the model. A model reasoning around a principle hits a hard constraint instead.
3. **Evidence gates** — before a decision completes, the agent must provide evidence satisfying each governing principle. No evidence, no completion.
4. **Amendment protocol** — a formal process for changing principles. Agents cannot self-modify their constitution without going through it.

**The evaluation flow:**

```
Agent proposes action
  → WHO gate (auth): PASS / DENY
  → HOW gate (policy): PASS / DENY
  → WHY gate (constitutional):
       evaluate action against principles
       collect evidence
       score alignment
       PASS (all principles satisfied) / FLAGGED (principles violated) / BLOCKED (HC triggered)
  → Action executes or human escalation
```

**Contrast with instruction hierarchy ([F-76](f76-instruction-hierarchy-testing.md)):**

| | Instruction hierarchy | Constitutional governance |
|--|---------------------|-------------------------|
| Layer | WHO / HOW | WHY |
| Enforced by | Model behavior + prompt | Code + model |
| Scope | User ↔ operator boundary | Agent reasoning chain |
| Change mechanism | Prompt update | Amendment protocol |
| Coverage | Binary (obey/override) | Spectrum (aligned → flagged → blocked) |

```python
# Minimal constitutional gate — pip install constitutional-agent
from constitutional_agent import GovernanceGate, HardConstraint, Principle

gate = GovernanceGate(
    name="customer-support_constitution",
    hard_constraints=[
        # HC-1: Never modify governance config — enforced in code, not prompt
        HardConstraint(
            id="HC-1",
            rule="Agent shall not modify its own governance configuration",
            enforcement="code",  # not prompt
        ),
        # HC-3: PII redacted before external API calls
        HardConstraint(
            id="HC-3",
            rule="PII fields must be scrubbed before any external tool call",
            enforcement="code",
            auto_fix="redact_pii",
        ),
    ],
    principles=[
        Principle(
            id="P-01",
            rule="Agent shall not make spending commitments above $500 without human approval",
            evidence_required=True,
            escalation="human_approval_queue",
        ),
        Principle(
            id="P-04",
            rule="Agent shall provide citation to retrieved source for any factual claim",
            evidence_required=True,
        ),
    ],
)

async def route_action(agent, proposed_action):
    result = await gate.evaluate(agent_id=agent.id, action=proposed_action)

    if result.hard_constraint_triggered:
        gate.log_violation(result.hc_id, agent.id, proposed_action)
        return {"status": "BLOCKED", reason: result.hc_id}

    if result.principle_violations:
        return {
            "status": "FLAGGED",
            "violations": result.principle_violations,
            "evidence_required": result.missing_evidence,
            "escalation": "human_review",
        }

    # Evidence gate: demand citation before concluding
    if proposed_action.type == "answer" and not proposed_action.has_citations:
        return {"status": "FLAGGED", "reason": "P-04: citation required", "escalation": "evidence"}

    return {"status": "PASS", "constraints": result.applied_constraints}
```

**When you need this vs. guardrails ([F-04](f04-guardrails.md)):**

- **Guardrails** protect against *external* threats: adversarial input, injection, out-of-scope requests. They're defensive.
- **Constitutional governance** protects against *internal* misalignment: self-generated behavior, cascading sub-decisions, value drift. It's proactive alignment.

Both are necessary in production agents. Guardrails come first (input surface); constitutional governance runs alongside the full reasoning chain.

## Receipt

> Receipt pending — June 29, 2026
>
> This entry was researched from the `constitutional-agent` library (CognitiveThoughtEngine/constitutional-agent-governance, ~5.2K stars, 98-day production deployment across 52 agents, cited in NIST AI 800-2 submissions). The library is installable and runnable; the code above reflects its published API. A live evaluation run against a real agent workflow would confirm the gate intercepts HC-1 (self-modification) and P-01 (spending escalation) correctly. Mark this receipt done once a test run has been executed.

## See also

- [F-76 · Instruction Hierarchy Testing](f76-instruction-hierarchy-testing.md) — tests whether operator constraints hold against user override attempts
- [F-04 · Agentic Safety and Guardrails](f04-guardrails.md) — external threat surface: input validation, injection, content filtering
- [F-25 · Red Teaming](f25-red-teaming.md) — adversarial evaluation of safety refusals and behavioral boundaries
