# Knowledge Pulse

> Institutional memory for the handbook chapter writer cron job.
> Updated after each run. Used to rank ideas, kill duplicates, and distill patterns.

## Ideas Bank

| ID | Title | Tags | Urgency | Gap | Specificity | Timeliness | Density | Composite | Status | Discovered | LastSeen |
|----|-------|------|---------|-----|-------------|------------|---------|-----------|--------|------------|----------|
| I-001 | Agentic Compensation Keys | idempotency, side-effects, retry, compensation, autonomous | 9 | 9 | 9 | 9 | 7 | **8.75** | WRITTEN — S-352 | 2026-07-02 | 2026-07-02 |
| I-002 | Agent Autonomy Levels (Bounded Autonomy) | autonomy levels, SAE taxonomy, L0-L5, governance, read-to-write gate, bounded autonomy, CSA, EU AI Act, trust calibration | 9 | 9 | 8 | 9 | 9 | **8.75** | WRITTEN — S-355 | 2026-07-02 | 2026-07-02 |
| I-003 | Long-Running Agent Orchestration (Planner-Worker) | planner-worker, temporal layers, strategic-tactical-operational, task decomposition, long-horizon, CORPGEN, replan, 35-minute wall | 8 | 9 | 9 | 8 | 7 | **8.35** | WRITTEN — S-357 | 2026-07-02 | 2026-07-02 |

*Composite = Urgency×0.35 + Gap×0.25 + Specificity×0.20 + Timeliness×0.10 + Density×0.10*

## Pattern Log

| Pattern | Description | Supporting Idea IDs | Notes |
|---------|-------------|---------------------|-------|
| L0–L5 Autonomy Taxonomy | Inspired by SAE J3016 automotive standards; the dividing line is L2 vs L3 (pre-action approval vs post-action audit). Production ceiling is L3–L4. L5 is explicitly unsafe for enterprise across CSA, ASDLC, Zylos, and SAE frameworks. | I-002 | Critical convergence: all independent frameworks agree on the same levels. |
| Bounded Autonomy | Agents get wide latitude within enforceable fences; escalation is mandatory at defined boundaries. The absence of an explicit level is not L0 — it is "whatever the agent can get away with." | I-002 | L3+ requires undo stack + governance agent overlay. |
| Read-to-Write Escalation Gate | The transition from reading information to modifying external systems is the single most actionable governance heuristic. Confirmed across CSA, Zylos, and Vitalora. Every escalation taxonomy converges here. | I-002 | This is a technical gate (function), not a policy document. |
| Governance Agent Overlay | For L4+ multi-agent systems: a dedicated rule-engine (not LLM) monitors agents, detects policy violations, and can autonomously demote privileges. Governance agent is deterministic — no LLM in the enforcement path. | I-002 | Sourced from CSA v2.0 + Zylos. Prevents circular LLM dependency. |
| Three-Layer Key Model | Intent key / Execution key / Compensation key — each encodes a different phase and survives agent restarts. | I-001 | Deterministic hashing from action metadata (not UUIDs) so any process can find and operate. |
| Three-Layer Temporal Decomposition | Strategic (months) → Tactical (days) → Operational (minutes) layers separate intent from execution. The worker never re-derives intent — it reads tactical context from memory. 3.5x completion improvement (15.2% vs 4.3% baseline). CORPGEN from Zylos. | I-003 | Planner fires 2x max per session: initial decompose + replan-on-failure. Calling planner every step is the #1 anti-pattern. |
| Planner-Worker Cost Asymmetry | Capable model (Sonnet-4/o4) = ~5% of calls (planning); cheap model (Haiku/Llama 8B) = ~95% (execution). Up to 90% cost reduction vs single-agent. Split is about call frequency, not model quality. | I-003 | Architecture pays for planning overhead by making execution cheap. Pairs with compensation keys (I-001) for recovery. |
| Phase-State Machines | Action records need explicit lifecycle states (PENDING → COMMITTED → COMPENSATING → COMPENSATED) to survive distributed retries and multi-agent handoffs. | I-001 | Analogous to saga pattern in distributed transactions. |
| Blast Radius Isolation | Compensation actions must themselves be idempotent. Using the compensation key as the idempotency key for the reversal prevents double-credit. | I-001 | Confirmed via Cordum's production guide. |

*When a pattern accumulates 3+ supporting ideas, synthesize a synthesis note below.*

## Synthesis Notes

*Add synthesized insights here when pattern density ≥ 3*

## Deduplication Index

*Keyword → idea ID mapping. Updated after each run.*
```
ai-agent → I-001, I-002, I-003
llm →
evaluation →
reliability → I-001, I-002
cost → I-003
mcp →
multi-agent → I-001, I-003
sandbox →
guardrails → I-002
routing →
memory → I-003
rag →
tracing →
synthetic-data →
fine-tuning →
idempotency → I-001
side-effect → I-001
compensation → I-001
retry → I-001, I-003
circuit-breaker →
autonomy → I-002, I-003
governance → I-002
eu-ai-act → I-002
bounded-autonomy → I-002
read-to-write → I-002
escalation → I-002
planner-worker → I-003
task-decomposition → I-003
long-horizon → I-003
replan → I-003
temporal-layers → I-003
```

## Recent Decisions

| Run Date | Idea ID | Decision | Rationale |
|----------|---------|----------|-----------|
| 2026-07-02 | I-002 | WRITTEN — S-355 | Agent Autonomy Levels (L0–L5, bounded autonomy, read-to-write escalation gate) — completely uncovered in the handbook. CSA v2.0 + Zylos + ASDLC all converge on the same taxonomy. EU AI Act Aug 2026 enforcement adds urgency. S-340/S-349 cover guardrails/enforcement; S-78 covers escalation; this entry covers the classification layer those are built on. |
| 2026-07-02 | I-001 | WRITTEN — S-352 | Compensation keys (distinct from idempotency keys) cover the layer above: reversing correctly-executed wrong-intent actions. All existing entries (S-93, S-181, F-107) cover prevention/deduplication — none cover autonomous reversal. Gap confirmed by Cordum, AgentMag, and early GitHub discussions on agentic compensation. |
| 2026-07-02 | I-003 | WRITTEN — S-357 | Long-Running Agent Orchestration (Planner-Worker, CORPGEN three-layer temporal decomposition). Completely uncovered in handbook — zero entries on task decomposition, planner-worker, or strategic/tactical/operational layer separation. 3.5x completion improvement and 90% cost reduction are concrete and verifiable. Runner-up: Synthetic Data Pipelines (R-13 covers research angle, stacks thin but not a gap), Constitutional Guardrails (S-349 already covers four-layer enforcement). |

## Meta

- Created: 2026-07-02
- Last Updated: 2026-07-02
- Total ideas discovered: 1
- Total patterns distilled: 4
