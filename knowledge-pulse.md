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
| I-006 | MCP Supply Chain: From `npx` to Production Catalog | mcp-supply-chain, artifact-pinning, sbom, slsa, ci-cd, signed-digest, mcp-registry, artifact-security, catalog-governance, artifact-provenance | 9 | 9 | 9 | 10 | 8 | **9.10** | WRITTEN — S-365 | 2026-07-02 | 2026-07-02 |
| I-008 | Agent Chaos Engineering: Fault Injection for Production Reliability | chaos-engineering, fault-injection, reliability, resilience, fault-tolerance, chaos-agent, tool-failure, api-failure, blast-radius, metamorphic-relations, ReliabilityBench, pass@k, agent-chaos, failure-injection | 9 | 9 | 9 | 10 | 8 | **9.10** | WRITTEN — S-370 | 2026-07-02 | 2026-07-02 |
| I-010 | Agentic Prompt Injection: Defense-in-Depth for Production | prompt-injection, defense-in-depth, capability-gating, mcp-security, zero-trust, a2a-signed-cards, blast-radius, guardrails, indirect-injection, owasp-llm01, environmental-input, human-in-the-loop, security, agent-hijacking | 10 | 10 | 9 | 9 | 7 | **9.35** | WRITTEN — S-375 | 2026-07-02 | 2026-07-02 |
| I-011 | Entity Grounding: Knowledge Graphs as Verifiable Memory | entity-grounding, knowledge-graph, graphrag, provenance, entity-resolution, hallucination, retrieval-grounding, multi-hop, entity-linking, knowledge-graph-verification, graph-traversal, hybrid-retrieval, grounding-layer | 9 | 9 | 9 | 10 | 9 | **9.25** | WRITTEN — S-378 | 2026-07-02 | 2026-07-02 |
| I-012 | Antagonistic Validation: Team of Rivals Architecture | antagonistic-validation, team-of-rivals, multi-agent-veto, adversarial-review, swiss-cheese-model, self-correction-failure, bounded-veto, hard-soft-veto, composer-antagonist-integrator, organizational-reliability, structural-opposition, channel-capacity, shannon | 9 | 10 | 9 | 10 | 9 | **9.45** | WRITTEN — S-380 | 2026-07-02 | 2026-07-02 |
| I-013 | Goal Drift: The Silent Competence Erosion Pattern | goal-drift, objective-integrity, goal-persistence, goal-anchoring, intent-drift, long-horizon-agents, competence-erosion, goal-pin, semantic-drift, inherited-goal-drift, goal-sanity-check | 9 | 9 | 9 | 9 | 8 | **8.95** | WRITTEN — S-383 | 2026-07-02 | 2026-07-02 |
| I-014 | Agent Trajectory Evaluation: Process vs. Outcome Scoring | trajectory-eval, process-evaluation, outcome-vs-process, six-dimension, tool-selection, error-recovery, plan-coherence, result-utilization, eval-rubric, dimension-scoring, trajectory-variance, CI-gate | 9 | 10 | 9 | 9 | 7 | **9.10** | WRITTEN — S-385 | 2026-07-02 | 2026-07-02 |
| I-007 | Agent Span Tracing: Observable Agent Sessions | opentelemetry, span, trace, observability, session-span, tool-call-trace, retrieval-trace, llm-span, trace-eval, otel-agent, agent-debugging, lineage, trace-to-eval | 9 | 9 | 9 | 10 | 8 | **9.10** | WRITTEN — S-368 | 2026-07-02 | 2026-07-02 |

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

|| Retrieval Grounding vs Generation Grounding | Hallucination has two distinct failure modes: retrieval hallucination (wrong chunks) and generation hallucination (model confabulation). Vector RAG + semantic output validation addresses the second. Knowledge graph grounding addresses the first by replacing chunk retrieval with entity-level traversal. Confusing which layer you're fixing leads to wrong architectural choices. | I-011 | Microsoft GraphRAG: 16.7% → 56.2% on multi-hop reasoning (3.4×). Confirmed by PolyglotSoft, Neo4j, Atolio, and OpenReview (ICLR 2026). |
|| Inference-Time Cost-Accuracy Agility | The cost-quality tradeoff for agents is solved at inference time via dynamic ICL + self-consistency cascades — no training required. Agility (rapid iteration without human bottlenecks) is preserved while shifting the Pareto frontier. | I-009 | Sarukkai et al., arXiv:2512.02543, Stanford ICLR 2026 Workshop DATA-FM. |
| Action Metamorphic Relations | Correctness defined by end-state equivalence, not text similarity. "Refund processed" and "Refund processed via batch" are equally correct if the balance updated. Prevents false negatives from cosmetic output drift. | I-008 | Key insight from ReliabilityBench methodology. |
| Structural Input Separation | Environmental inputs (web, email, docs) must be wrapped in explicit structural markers that distinguish untrusted content from system directives. The model learns to treat marked content as informational, not authoritative. This shifts injection defense from content filtering to structural boundary enforcement. | I-010 | Inspired by Zylos 2026 research; mirrors the principle behind S-363 context position architecture (what enters the context carries weight). |
| Capability-Gated Tool Calls | Every tool invocation is gated on the agent's proven capability, not the LLM's output. The LLM cannot grant itself capabilities — this is the enforcement boundary that makes autonomy levels (I-002) technically enforceable rather than advisory. | I-010, I-002 | Complements S-355's read-to-write escalation gate with a granular per-tool capability matrix. |
| Environmental Input Attack Surface | Agents ingest untrusted content from the environment (web pages, emails, documents, tool responses) that carries no intrinsic trust signal. The attacker's surface = every input the agent reads. Indirect injection via RAG poisoning requires only 5 crafted documents to manipulate responses 90% of the time. | I-010 | Expands the threat model beyond adversarial user input to include passive, non-interactive attack vectors. |
| Seven-Layer Defense-in-Depth | No single mitigation (regex filter, system prompt instruction, moderation API) is sufficient. Effective defense requires seven independent layers: structural separation, capability gating, MCP hardening, output validation, A2A identity, blast radius containment, and human-in-the-loop. Each layer covers failure modes the others miss. | I-010 | Consistent with Zylos, AgDex, OWASP LLM01 guidance. Raises attacker cost beyond practical exploitation. |
| Antagonistic Validation | Reliability emerges from disagreement, not consensus. Multiple imperfect agents with misaligned incentives and bounded veto authority create structural opposition — errors must survive adversarial scrutiny before propagation. Three roles: Composer (generates), Antagonist (attacks), Integrator (decides). Vetoes are categorized hard/soft/advisory. Iteration count is bounded. Based on Swiss Cheese Model (Reason 2000) and Shannon's channel capacity. | I-012 | arXiv:2601.14351; GitHub multi-agent reliability analysis. Complements S-101 (deterministic sessions) and S-355 (L3+ autonomy requires structured oversight). |

## Deduplication Index

*Keyword → idea ID mapping. Updated after each run.*
```
ai-agent → I-001, I-002, I-008
llm →
evaluation → I-008
reliability → I-001, I-002, I-008
cost →
mcp →
multi-agent → I-001, I-003
sandbox →
guardrails → I-002
routing →
memory →
rag →
tracing →
synthetic-data →
fine-tuning →
idempotency → I-001
side-effect → I-001, I-008
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
guardrails → I-002, I-004, I-010
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
eval → I-007, I-008
artifact-pinning → I-006
sbom → I-006
catalog-governance → I-006
chaos-engineering → I-008
fault-injection → I-008
blast-radius → I-001, I-008
metamorphic-relations → I-008
pass@k → I-008
reliabilitybench → I-008
agent-chaos → I-008
itd → I-009
dynamic-icl → I-009
self-consistency → I-009
cascade → I-009
agility → I-009
pareto → I-009
distillation → I-009
prompt-injection → I-010
defense-in-depth → I-010
capability-gating → I-010
zero-trust → I-010
a2a-identity → I-010
knowledge-graph → I-011
graphrag → I-011
grounding → I-011
provenance → I-011
entity-linking → I-011
entity-resolution → I-011
multi-hop → I-011
graph-traversal → I-011
hybrid-retrieval → I-011
entity-grounding → I-011
mcp-security → I-010
indirect-injection → I-010
owasp-llm01 → I-010
environmental-input → I-010
human-in-the-loop → I-010
security → I-010
agent-hijacking → I-010
blast-radius → I-001, I-008, I-010
antagonistic-validation → I-012
team-of-rivals → I-012
multi-agent-veto → I-012
adversarial-review → I-012
self-correction → I-012
structural-opposition → I-012
bounded-veto → I-012
goal-drift → I-013
goal-persistence → I-013
goal-anchoring → I-013
intent-drift → I-013
competence-erosion → I-013
goal-pin → I-013
semantic-drift → I-013
inherited-goal-drift → I-013
goal-sanity-check → I-013
compositional-agent → I-012
trajectory-eval → I-014
process-evaluation → I-014
outcome-vs-process → I-014
six-dimension → I-014
tool-selection → I-014
error-recovery → I-014
plan-coherence → I-014
result-utilization → I-014
eval-rubric → I-014
dimension-scoring → I-014
trajectory-variance → I-014
CI-gate → I-014
```

## Recent Decisions

| Run Date | Idea ID | Decision | Rationale |
|----------|---------|----------|-----------|
| 2026-07-02 | I-012 | WRITTEN — S-380 | Antagonistic Validation: Team of Rivals — gap: no handbook entry covers the organizational architecture for multi-agent adversarial validation. s05-multi-agent-patterns covers coordination but not structural opposition. ArXiv:2601.14351 (Vijayaraghavan et al.) provides the theoretical foundation (Swiss Cheese Model, Shannon capacity, bounded veto). APEX-Agents benchmark shows <25% first-attempt task completion; this pattern directly addresses the architectural root cause. Composite 9.45. Chosen over: semantic drift / catastrophic forgetting (covered by s94-agent-output-diffing, s79-semantic-regression-detection), recursive collapse (related but distinct failure mode, less specific pattern). |
| 2026-07-02 | I-013 | WRITTEN — S-383 | Goal Drift: The Silent Competence Erosion Pattern — gap: no handbook entry covers the tendency of long-horizon agents to silently diverge from stated objectives through context accumulation, environmental pressure, and model update side effects. Distinct from hallucination (fabrication) and tool misuse (wrong method): this is pursuing the wrong goal correctly. ICLR 2026 paper (arXiv:2603.03258, Menon et al.) on Inherited Goal Drift provides empirical backing; Zylos Research (April 2026) independently identifies goal drift as a defining production challenge. Three-layer pattern: goal pinning → periodic sanity checks → semantic drift detection. Composite 8.95. Chosen over: Operational Hallucination (related to S-360 governance decay, less specific pattern), Agent-Driven Scope Creep (adjacent but different failure class). |
| 2026-07-02 | I-011 | WRITTEN — S-378 | Entity Grounding: Knowledge Graphs as Verifiable Memory — gap: no handbook entry covers the architectural distinction between chunk-based RAG (vector) and entity-level graph grounding, despite GraphRAG achieving 3.4× accuracy gains on multi-hop reasoning (16.7% → 56.2%). S-212 (semantic output validation) and S-221/S-374 (agentic RAG) cover adjacent ground but not the core architectural shift. Composite 9.25. Chosen over multi-agent state synchronization (partial coverage via S-373 authority design), agent memory architectures (covered by S-303/S-314, less specific), and event-driven agent coordination (covered by S-377). |
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
| 2026-07-02 | I-014 | WRITTEN — S-385 | Agent Trajectory Evaluation: Process vs. Outcome Scoring — gap: all existing eval entries (S-219, S-220, S-202, S-251, S-249) cover eval infrastructure and CI gates, but none address the fundamental distinction between outcome and process scoring. An agent can succeed via a terrible trajectory (lucky hallucination, 47 tool calls instead of 3, infinite retry loop that happened to converge). This is the architectural gap that causes "passed eval, broken production" failures. Six-dimension trajectory rubric (tool selection, argument extraction, result utilization, error recovery, plan coherence, task completion) is an established production pattern from Jobs By Culture, Adaline AI, QASkills, and JetBrains eval research (May–June 2026). Per-dimension CI gates catch regressions that aggregate scores hide. Composite 9.10. Chosen over: eval contamination detection (related to S-251 golden dataset rotation, less specific pattern), semantic output validation (covered by S-212), OTEL span-level scoring (related but infrastructure-level, not rubric-level). |

## Meta

- Created: 2026-07-02
- Last Updated: 2026-07-02 (run 2: +I-014 trajectory-eval / S-385)
- Total ideas discovered: 14
- Total patterns distilled: 5
