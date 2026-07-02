# Knowledge Pulse

> Institutional memory for the handbook chapter writer cron job.
> Updated after each run. Used to rank ideas, kill duplicates, and distill patterns.

## Ideas Bank

| ID | Title | Tags | Urgency | Gap | Specificity | Timeliness | Density | Composite | Status | Discovered | LastSeen |
|----|-------|------|---------|-----|-------------|------------|---------|-----------|--------|------------|----------|
| I-001 | Agentic Compensation Keys | idempotency, side-effects, retry, compensation, autonomous | 9 | 9 | 9 | 9 | 7 | **8.75** | WRITTEN — S-352 | 2026-07-02 | 2026-07-02 |
| I-002 | Agent Autonomy Levels (Bounded Autonomy) | autonomy levels, SAE taxonomy, L0-L5, governance, read-to-write gate, bounded autonomy, CSA, EU AI Act, trust calibration | 9 | 9 | 8 | 9 | 9 | **8.75** | WRITTEN — S-355 | 2026-07-02 | 2026-07-02 |
| I-003 | Long-Running Agent Orchestration (Planner-Worker) | planner-worker, temporal layers, strategic-tactical-operational, task decomposition, long-horizon, CORPGEN, replan, 35-minute wall | 8 | 9 | 9 | 8 | 7 | **8.35** | WRITTEN — S-357 | 2026-07-02 | 2026-07-02 |
| I-004 | Governance Decay: Context Compaction Silently Erases Safety Constraints | governance-decay, constraint-eviction, compaction, safety, standing-policies, context-window, constraint-pinning, safety-erosion, constraintrot | 9 | 10 | 9 | 10 | 8 | **9.35** | WRITTEN — S-360 | 2026-07-02 | 2026-07-02 |
| I-005 | Budget-Aware Agents: Cost as First-Class Behavioral Dimension | budget-awareness, cost-self-regulation, token-budget, cost-per-outcome, agent-economics, cost-mode-switching, context-accumulation, resource-constrained-agent | 9 | 9 | 8 | 9 | 8 | **8.65** | WRITTEN — S-362 | 2026-07-02 | 2026-07-02 |
|| I-006 | MCP Supply Chain: From `npx` to Production Catalog | mcp-supply-chain, artifact-pinning, sbom, slsa, ci-cd, signed-digest, mcp-registry, artifact-security, catalog-governance, artifact-provenance | 9 | 9 | 9 | 10 | 8 | **9.10** | WRITTEN — S-365 | 2026-07-02 | 2026-07-02 |
|| I-007 | Agent Span Tracing: Observable Agent Sessions | opentelemetry, span, trace, observability, session-span, tool-call-trace, retrieval-trace, llm-span, trace-eval, otel-agent, agent-debugging, lineage, trace-to-eval | 9 | 9 | 9 | 10 | 8 | **9.10** | WRITTEN — S-368 | 2026-07-02 | 2026-07-02 |

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
| Governance Decay | Context compaction (summarization/eviction) silently erases in-context safety constraints — violation rates jump from 0% to 30–59% without model or prompt changes. Compaction optimizes for task continuity, not constraint preservation. Defense: Constraint Pinning (~47 pinned tokens restores 0% violations). | I-004 | Chen, arXiv:2606.22528 (27 Jun 2026). The same mechanism that prevents context overflow also destroys safety guarantees. |
| Phase-State Machines | Action records need explicit lifecycle states (PENDING → COMMITTED → COMPENSATING → COMPENSATED) to survive distributed retries and multi-agent handoffs. | I-001 | Analogous to saga pattern in distributed transactions. |
| Blast Radius Isolation | Compensation actions must themselves be idempotent. Using the compensation key as the idempotency key for the reversal prevents double-credit. | I-001 | Confirmed via Cordum's production guide. |
| Agent Span Tracing | Every LLM call, tool invocation, and state transition is a typed, timestamped span in a trace tree. Session root span → LLM spans → tool spans (retrieval/action/compute) → nested compaction/handoff spans. Enables trace-driven eval (isolating which step failed) and post-hoc causality analysis across agent handoffs. Tiered export by span type (LLM to Langfuse, tools to Datadog, full tree to S3). | I-007 | OpenTelemetry SDK semantics. Fills observability gap between S-100 (agentic RAG) and S-331 (LLM-as-judge). |

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
governance → I-002, I-004
eu-ai-act → I-002
bounded-autonomy → I-002
read-to-write → I-002
escalation → I-002
planner-worker → I-003
task-decomposition → I-003
long-horizon → I-003
replan → I-003
temporal-layers → I-003
governance-decay → I-004
constraint-eviction → I-004
compaction → I-004
safety → I-002, I-004
standing-policies → I-004
constraint-pinning → I-004
safety-erosion → I-004
constraintrot → I-004
guardrails → I-002, I-004
budget-aware → I-005
cost-self-regulation → I-005
token-budget → I-005
cost-per-outcome → I-005
agent-economics → I-003, I-005
context-accumulation → I-003, I-005
mcp-supply-chain → I-006
trace → I-007
observability → I-007
tracing → I-007
span → I-007
opentelemetry → I-007
eval → I-007
artifact-pinning → I-006
sbom → I-006
catalog-governance → I-006
```

## Recent Decisions

| Run Date | Idea ID | Decision | Rationale |
|----------|---------|----------|-----------|
| 2026-07-02 | I-007 | WRITTEN — S-368 | Agent Span Tracing (observable agent sessions) — gap: observability for multi-turn agents is completely uncovered despite being a top-3 production pain point. Tracing per-LLM-call, per-tool-call, and per-retrieval spans with OpenTelemetry enables trace-driven eval (isolating which step failed) and cross-agent causality analysis. Tiered export to Langfuse/Braintrust (LLM spans), Datadog (tool spans), and S3 (full tree for audit). Connects to S-100 (retrieval spans), S-331 (LLM-as-judge eval), S-362 (cost per span), and S-93 (error recording). Confirmed via Zylos observability research, Databricks MLflow OTel guide, and Digital Applied sandbox analysis. |
| 2026-07-02 | I-004 | WRITTEN — S-360 | Governance Decay (context compaction silently erases safety constraints) — completely uncovered in the handbook. arXiv:2606.22528 (Chen, 27 Jun 2026) just published. Violation rates jump 0%→59% with no model/prompt changes. The same compaction systems teams deploy to avoid context overflow are simultaneously destroying safety guarantees. Directly related to S-355 (bounded autonomy — L3+ agents are highest risk), S-198 (tool-call guardrails — enforcement downstream of where decay happens). |
| 2026-07-02 | I-005 | WRITTEN — S-362 | Budget-Aware Agents (cost as first-class behavioral dimension) — gap: cost observability (s322, s346, f192) is covered but budget-embedded agent behavior is not. Key pattern: 3-mode cost system (full→conservative→terminate) at 50%/80% budget thresholds, cost tracker as an explicit state object, cost-per-step projections enabling early termination before budget exhaustion. Connects to S-355 (bounded autonomy — budget as governance constraint) and S-356 (context accumulation cost compounding). |
| 2026-07-02 | I-006 | WRITTEN — S-365 | MCP Supply Chain (from npx to production catalog) — gap: MCP is covered in S-10 but the supply-chain security implications of installing arbitrary server packages are not. Key pattern: artifact pinning + SBOM + signed digest + catalog governance mirror the npm security model that failed. Confirmed via Zylos MCP security research, Anthropic MCP audit guide, OWASP A06:2025. Tiered defense (pinning → SBOM → signature verification → catalog governance) closes the full chain. |
| 2026-07-02 | I-003 | WRITTEN — S-357 | Long-Running Agent Orchestration (Planner-Worker Temporal Layer Pattern) — gap: S-05 covers multi-agent but not the temporal decomposition that makes long-horizon agents reliable. Key pattern: strategic/tactical/operational separation with 3.5x completion improvement (15.2% vs 4.3% baseline). Confirmed via Zylos CORPGEN framework. Planner runs once at strategic level; worker runs at operational level within temporal fence; no re-deriving intent mid-execution. |
| 2026-07-02 | I-002 | WRITTEN — S-355 | Agent Autonomy Levels (Bounded Autonomy) — gap: no existing entry maps the SAE-inspired L0-L5 autonomy taxonomy to agent production decisions. Key pattern: production ceiling is L3-L4; L5 is unsafe for enterprise; the read-to-write escalation gate is the single most actionable heuristic. Confirmed across CSA v2.0, Zylos CORPGEN, and EU AI Act obligations. |
|| 2026-07-02 | I-005 | WRITTEN — S-362 | Budget-Aware Agents (cost as first-class behavioral dimension) — gap: cost observability (s322, s346, f192) is covered but budget-embedded agent behavior is not. Key pattern: 3-mode cost system (full→conservative→terminate) at 50%/80% budget thresholds, cost tracker as an explicit state object, cost-per-step projections enabling early termination before budget exhaustion. Connects to S-355 (bounded autonomy — budget as governance constraint) and S-356 (context accumulation cost compounding). |
| 2026-07-02 | I-005 | WRITTEN — S-362 | Budget-Aware Agents (cost as first-class behavioral dimension) — gap: cost observability (s322, s346, f192) is covered but budget-embedded agent behavior is not. Key pattern: 3-mode cost system (full→conservative→terminate) at 50%/80% budget thresholds, cost tracker injection into context, cost-aware tool selection. Timely: AgentMarketCap (Apr 2026) shows 40–60% cost reduction via budget-aware design; Orq.ai FinOps (Jun 2026) on cost-per-outcome KPIs. NOT covered by s346 (token cost trap — focuses on multiplicative compounding economics) or f192 (cost velocity circuit breaker — reactive, not behavioral). |
| 2026-07-02 | I-006 | WRITTEN — S-365 | MCP Supply Chain (artifact integrity from npx to production catalog) — gap: MCP server hardening (s201), attack surface (s261), and protocol convergence (s359) are covered, but the CI/CD artifact pipeline for MCP servers (hash-pinning, SBOM, signed digests, catalog governance gates) is completely missing. Key pattern: treating MCP servers as production artifacts with the same rigor as container images. Timely: JFrog detected active MCP server exploits in Q1 2026; Kong MCP Registry, Cisco/CrowdStrike MCP governance, and OBOT.ai's pipeline hardening guide all published in mid-2026. The npx→production gap is where the next major MCP security incident will come from. |
| 2026-07-02 | I-001 | WRITTEN — S-352 | Compensation keys (distinct from idempotency keys) cover the layer above: reversing correctly-executed wrong-intent actions. All existing entries (S-93, S-181, F-107) cover prevention/deduplication — none cover autonomous reversal. Gap confirmed by Cordum, AgentMag, and early GitHub discussions on agentic compensation. |
| 2026-07-02 | I-003 | WRITTEN — S-357 | Long-Running Agent Orchestration (Planner-Worker, CORPGEN three-layer temporal decomposition). Completely uncovered in handbook — zero entries on task decomposition, planner-worker, or strategic/tactical/operational layer separation. 3.5x completion improvement and 90% cost reduction are concrete and verifiable. Runner-up: Synthetic Data Pipelines (R-13 covers research angle, stacks thin but not a gap), Constitutional Guardrails (S-349 already covers four-layer enforcement). |

## Meta

- Created: 2026-07-02
- Last Updated: 2026-07-02
- Total ideas discovered: 1
- Total patterns distilled: 4
