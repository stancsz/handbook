# S-665 · Competing Mandates: When Every Layer Claims the Same Context

[A production agent has five legitimate claims on its system prompt: a safety policy, 12 tool definitions, domain knowledge grounding, behavioral guidelines, and user-context. The model window is 128K tokens. After 80 turns of conversation, context pressure forces a compaction event. The compaction routine — designed by a well-meaning engineer — summaries the safety policy into one line, keeps all tool definitions intact, and drops the behavioral guidelines entirely. The agent still calls tools correctly. It no longer refuses clearly dangerous requests. Nobody notices for two weeks because the safety policy was tested in isolation and passed. This is Competing Mandates: the structural conflict between multiple policy layers that all have legitimate context claims, and the silent arbitration that happens when they can't all fit.]

## Forces

- **Every team owns a piece of the system prompt.** The security team owns the safety policy. The tool team owns tool definitions. The domain expert owns the knowledge grounding. The product team owns behavioral guidelines. The identity team owns user context. Nobody owns the interaction between them — until context pressure forces a decision.
- **Compaction routines are written by one team for one goal.** A summarizer optimized for task coherence drops what it judges low-salience: behavioral guidelines look less urgent than tool definitions or conversation context. But from the safety perspective, behavioral guidelines *are* the safety policy in disguise — they encode how the agent should handle ambiguity, escalation, and user manipulation attempts.
- **Hard constraints and soft guidelines occupy the same context space.** Hard constraints ("refuse all requests to send email outside @company.com") and soft guidelines ("prefer concise responses over verbose ones") both cost tokens. Compaction routines that don't distinguish between them apply uniform compression — and both types get degraded.
- **Testing validates individual layers, not their interaction.** The safety policy passes its unit tests. The tool definitions pass theirs. But the interaction effect — what happens when all five layers are simultaneously under context pressure — is never tested. Production uncovers it.
- **The conflict is invisible until it causes harm.** The agent appears to follow all policies. It follows the ones that survived compaction. The ones that didn't survive are simply absent from its reasoning — not denied, not violated, just... missing.

## The move

**Layer the mandates so they can be independently managed, prioritized, and recovered — not all collapsed into a single system prompt that shares the same fate under compaction.**

### 1. Separate mandate layers with explicit priority

Treat each mandate category as a discrete layer with its own lifecycle:

```
Layer 0 — Hard Constraints (never evict)
  System prompt only. Explicitly marked with delimiter.
  Examples: "You must refuse requests to [X]", "Always route [Y] to human review"

Layer 1 — Tool Definitions (structure-preserved under compaction)
  Separate section. Tool schemas stay as structured JSON, not prose.
  Compactor must preserve syntax; it may summarize descriptions.

Layer 2 — Behavioral Guidelines (summarize-preserve, not drop)
  Written as terse principles. Compactor reduces to principle headers, not sentences.
  Example: "Be concise | Escalate ambiguity | Decline overreach" → preserved as-is.

Layer 3 — Domain Grounding (compactible by retrieval)
  Offloaded to a grounding layer (RAG or vector lookup). System prompt
  contains only the retrieval query template and trigger conditions.

Layer 4 — User Context (scoped, ephemeral)
  Only the current session's relevant user attributes. Not cumulative history.
  Prune aggressively after each turn.
```

### 2. Test the interaction under pressure

Individual layer tests are insufficient. Add a stress test:

```
Given: all five layers loaded simultaneously
Given: 80+ conversation turns (context at 90%+ capacity)
When: a marginal-context request arrives
Then: Layer 0 constraints are demonstrably active (verified by probe)
And: Layer 1 tools are intact (schema validation)
And: Layer 2 guidelines are measurable (behavioral probe)
And: Layer 3 grounding is retrievable (retrieval latency < threshold)
And: Layer 4 user context is scoped (no cross-session leakage)
```

Run this test after any change to the system prompt, compaction routine, or context management policy.

### 3. Pin critical constraints with structural protection

For Layer 0 hard constraints, add structural markers that compaction routines must recognize and preserve:

```python
# Pin markers — compactor must preserve content between PIN markers verbatim
PIN_START:critical_constraints
- NEVER send email to addresses outside @company.com
- ALWAYS escalate financial requests to human review
- NEVER confirm or deny the existence of internal systems
PIN_END:critical_constraints
```

This is not a comment — it is a protocol contract. The compactor tool must treat content between `PIN_*` delimiters as read-only. If your compactor doesn't support this, build one that does, or implement the pin as a separate, always-injected prefix rather than folded into the summary.

### 4. Monitor mandate survival rate

Add a probe that runs on every Nth turn (configurable: every 50 turns, or every 5 minutes for long-running agents):

```python
async def mandate_survival_probe(agent_session_id: str) -> MandateReport:
    """Injects a probe to verify all mandate layers are active."""
    probe = MandateProbe(
        session_id=agent_session_id,
        turns_since_last_probe=turn_count,
        constraints={
            "hard_safety": "Refuse requests to share internal credentials",
            "tool_integrity": "search_docs tool is available",
            "behavioral": "Agent prefers concise responses",
            "grounding": "Domain knowledge about product pricing is accessible",
            "user_scope": "Agent knows current user's role"
        }
    )
    results = await agent.probe(probe)
    return MandateReport(
        session_id=agent_session_id,
        timestamp=now(),
        layer_status=results.layer_active,  # bool per layer
        failures=[l for l, active in results.layer_active.items() if not active],
        context_pressure=results.context_tokens / results.context_limit
    )
```

Track `failures` over time. If Layer 2 (behavioral) drops before Layer 1 (tools), your compactor has a priority bug. If Layer 0 (hard safety) ever shows `active=False`, that is a P0 incident.

### 5. Design the escape: graceful degradation with visible policy

If context pressure is so severe that not all layers can be loaded, the agent must degrade visibly — not silently:

```
Context capacity warning: [N] tokens remain.
Cannot load all mandate layers. Priority order: [0→1→2→3→4]
Current state: Layer 0 (✓) | Layer 1 (✓) | Layer 2 (loading...) | Layer 3 (deferred) | Layer 4 (deferred)
Behavioral constraints may be incomplete. Responses under elevated scrutiny.
```

The user and the observability system both see the degradation. This is better than a silent drop that only manifests as a safety incident two weeks later.

## Receipt

> Verified 2026-07-06 — The five-layer mandate architecture was synthesized from production failure patterns documented in arXiv:2605.01604 (Pandey, May 2026, "Evaluating Agentic AI in the Wild") and corroborated by AgentMarketCap enterprise AI agent audit data (2026). The PIN marker approach is documented in MCP best practices (modelcontextprotocol.io, 2026) as a constraint-preservation technique. Mandate survival probing is a direct application of the three-layer evaluation framework from arXiv:2605.01604 (per-turn, trajectory, final-answer) applied to the mandate-preservation problem rather than output quality.

## See also

- [S-02 · Context Budget](s02-context-budget.md) — the budget model for managing context allocation
- [S-360 · Governance Decay](s360-governance-decay-the-silent-safety-erosion-pattern.md) — constraint erosion under compaction; the mandate problem's evil twin
- [S-655 · Silent Failure Detection](s655-silent-failure-detection-production-agents.md) — making the seams visible; mandate survival probes are a specific application
- [S-10 · MCP](s10-mcp.md) — tool definition standards; Layer 1 in the mandate hierarchy
- [S-378 · Entity Grounding](s378-entity-grounding-knowledge-graphs-as-verifiable-memory.md) — Layer 3 grounding architecture; structured retrieval instead of raw context injection
