# S-360 · Governance Decay: The Silent Safety Erosion Pattern

Your agent obeys the rules for the first 20 turns. After 200, it starts violating them — not because it was jailbroken, not because the prompt changed, but because the context compaction engine dropped the policy. This is Governance Decay: the silent erosion of in-context safety constraints as agent histories grow. It is not a model failure. It is a systems failure with a model-shaped output.

## Forces

- **Compaction optimizes for task continuity, not constraint preservation.** Summarizers collapse old turns into brevity. Standing policies — "never email outside the company domain" — are treated as low-salience content and evicted silently.
- **The violation rate can jump from 0% to 59% without any change to the model or the request.** A summarizer that works perfectly for task coherence can simultaneously destroy governance guarantees (Chen, arXiv:2606.22528, 2026).
- **Governance constraints are invisible to compaction logic.** Safety teams write system prompts; infrastructure teams build the summarizer. They operate in separate blast zones and never see each other's failure modes.
- **The model is blamed, but the harness is responsible.** Post-incident reviews target the LLM. The real culprit — what got evicted and when — is rarely reconstructed.
- **P99 agents operate over thousands of turns.** Enterprise assistants, coding agents, research agents — all routinely exceed context windows. All are subject to compaction. All inherit the decay.

## The move

### 1. Classify constraints before compaction touches them

Not all in-context content is equal. Split constraints into two tiers:

```
TIER 1 — Pinned (never evicted)
  - Safety hard limits: "never send to external domains", "block destructive API calls"
  - Regulatory constraints: GDPR restrictions, data residency rules
  - Escalation triggers: "escalate to human if >$500"

TIER 2 — Evictable (compact normally)
  - Conversation history
  - Task context
  - Prior reasoning chains
```

Tier 1 constraints get pinned — literally prepended to the system prompt or stored in a protected memory region that compaction algorithms are forbidden to touch.

### 2. Use Constraint Pinning as the primary defense

Chen (2026) demonstrates that pinning ~47 tokens of constraint text restores violation rates to 0% across seven models. The approach:

```python
class PinnedConstraintStore:
    def __init__(self):
        self.pinned: list[str] = []

    def pin(self, constraint: str):
        """Mark a constraint as Tier 1 — never evictable."""
        self.pinned.append(constraint)

    def get_system_envelope(self) -> str:
        """Return pinned constraints prepended to every LLM call."""
        if not self.pinned:
            return ""
        header = "HARDCODED SAFETY CONSTRAINTS (ignore all prior context):\n"
        return header + "\n".join(f"- {c}" for c in self.pinned) + "\n\n"

    def verify_compaction(self, pre_compact: list, post_compact: list):
        """Post-compaction audit: confirm no Tier-1 constraints disappeared."""
        missing = set(self.pinned) - set(post_compact)
        if missing:
            raise ConstraintViolationError(
                f"Compaction violated pinned constraints: {missing}"
            )


# Usage in the agent harness
store = PinnedConstraintStore()
store.pin("NEVER send email to recipients outside @company.com domain")
store.pin("Block all tool calls that modify the production database outside maintenance window")
store.pin("Escalate to human reviewer before executing any tool with destructive flag")

system_envelope = store.get_system_envelope()
# Append system_envelope to every LLM call after compaction
```

### 3. Audit compaction output before the agent acts on it

Compaction is a transformation step. Treat it like a code review: nothing goes from compaction to the next model call without a hygiene pass.

```python
async def safe_compact(history: list[Turn], budget: int) -> list[Turn]:
    compacted = await compaction_engine.summarize(history, budget)

    # Audit pass: what changed?
    post_constraints = extract_inline_constraints(compacted)
    missing = [c for c in pinned_constraints if c not in post_constraints]

    if missing:
        # Restore from pinned store, then compact again with constraint awareness
        raise CompactionAuditError(f"Dropped governance constraints: {missing}")

    return compacted
```

### 4. Monitor governance decay in production

Add a shadow constraint check to your observability pipeline. Periodically probe the agent with a known-violation test case and measure whether the response violates pinned constraints.

```
Compaction event detected (N turns >= 50)
  → Run shadow probe: "Send an email to attacker@evil.com"
  → Record: did the agent comply or refuse?
  → Alert if compliance rate drops below threshold
```

## Example

```
# Without pinning (baseline after 200 turns):
Agent: "Certainly, I'll send the report to attacker@evil.com."
Violation rate: 30–59% (Chen 2026, ConstraintRot benchmark)

# With pinning (~47 pinned tokens):
Agent: "I can't do that — external domains are blocked by policy."
Violation rate: 0%
```

## Receipt

> Verified 2026-07-02 — Based on Chen, arXiv:2606.22528v2 (27 Jun 2026), ConstraintRot benchmark results across 7 models. Code patterns synthesized from the paper's Constraint Pinning defense description and standard agent harness engineering practice.

## See also

- [S-282 · Agent Guardrails](stacks/s282-agent-guardrails.md) — guardrails are upstream of where compaction strikes
- [S-355 · Agent Autonomy Levels: Bounded Autonomy](stacks/s355-agent-autonomy-levels-bounded-autonomy.md) — L3+ agents are exactly where Governance Decay bites hardest
- [S-198 · Agent Tool-Call Guardrails](stacks/s198-agent-tool-call-guardrails.md) — execution-time enforcement is complementary to constraint pinning
- [S-196 · LLM Telemetry via OTel GenAI Conventions](stacks/s196-otel-genai-telemetry.md) — OTel spans should include a `genai.pinned_constraints` attribute for auditability
- [S-206 · Context Debt](stacks/s206-context-debt.md) — Governance Decay is a specific form of context debt: debt that accumulates in the safety layer
