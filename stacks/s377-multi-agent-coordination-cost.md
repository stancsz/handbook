# S-377 · The Multi-Agent Coordination Tax

When you split one agent into two, you don't just double the work — you create a new category of failure that didn't exist before. Coordination overhead is the most underestimated cost in agentic systems, and most teams discover it too late.

## Forces

- **Individual agents are easier to reason about; teams of agents are harder to debug** — each agent boundary adds observability debt, failure coupling, and communication ambiguity
- **Context window temptation vs. context compartmentalization** — large windows let you avoid splitting, but middle-context degradation cuts retrieval accuracy by up to 73% regardless of window size
- **Coordination cost grows non-linearly** — two agents communicate in one channel; five agents have ten potential channels; most teams underestimate this until their system crawls
- **Demo magic vs. production reality** — one team measured a 37-point success rate drop (92% demo → 55% prod) with the first split, because coordination failure was never in their test harness
- **Pattern choice matters more than model choice** — logistics multi-agent systems show 27% throughput gains and 22% cost reduction from pattern selection alone, independent of LLM quality

## The Move

**Apply the "Add an Agent" checklist before splitting.** Split only when at least two of these are true: sub-tasks have genuinely different tool sets, sub-tasks benefit from different model sizes, explicit safety or audit boundaries are needed between domains, or the coordination overhead has a clear termination condition.

**Match the coordination pattern to the dependency structure:**

- **Sequential pipeline** — fixed linear order, like Unix pipes. Use for progressive refinement where each agent transforms output the next consumes. Lowest overhead. Highest determinism.
- **Hierarchical (supervisor)** — one manager agent routes to specialist agents and synthesizes. Use when you need centralized routing logic and the manager is reliable enough to be the bottleneck.
- **Peer network** — agents share a blackboard or broadcast to each other. Use for research or exploration tasks where multiple perspectives must converge without a predetermined order.
- **Sequential → Hierarchical migration** — start sequential to find where contention happens, then extract a supervisor for hot paths. Most teams do this backward and end up with a broken hierarchy they can't untangle.

**Enforce explicit termination at every agent boundary.** Without it, multi-agent conversations loop indefinitely, each round adding LLM calls and cost. Add max-iterations guards, output schema contracts, and signal-style DONE states that propagate across boundaries.

**Instrument coordination, not just execution.** At minimum, log: which agent was called, with what context, how long it took, what it decided, and whether that decision was ratified by the next agent. LangSmith traces and Arize Phoenix spans both support this, but custom OTel spans with LLM-specific semantic conventions are the production standard.

## Evidence

- **Multi-agent systems blog (Comet):** Context degradation in monolithic agents ("Lost in the Middle") degrades retrieval accuracy up to 73% for information buried in middle context sections, regardless of window size — multi-agent compartmentalization is the architectural response — https://www.comet.com/site/blog/multi-agent-systems
- **Multi-Agent System Design Patterns for Production (Thread Transfer, Jul 2025):** ChatDev achieves 33.3% correctness on real programming tasks; AppWorld shows 86.7% failure on cross-app workflows; logistics systems demonstrate 27% throughput gains and 22% cost reduction from pattern selection alone — https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns
- **State of Agentic AI 2025 (Technspire, Dec 2025):** Four categories consistently shipped: developer tooling (tight feedback loops), internal ops automation (bounded blast radius), research/analysis (clear success criteria), customer-facing chat (with heavy guardrails). Open-ended autonomy failed in regulated environments; deterministic guardrails and narrow scope were prerequisites for production — https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons
- **Agent Observability Engineering (QubitTool, May 2026):** 90% of agent failures fall into 5 patterns; three-pillar observability (traces, evals, debugging) maps to: "what happened," "how good was it," "why did it fail" — https://qubittool.com/blog/agent-observability-engineering
- **Framework decision guide (benconally/ai-agent-framework-decision-guide):** LangGraph for stateful production workflows, CrewAI for fastest demo-to-prototype path, AutoGen/AG2 for conversational agent teams, OpenAI/Claude Agent SDKs for first-party simplicity — https://github.com/benconally/ai-agent-framework-decision-guide

## Gotchas

- **Starting with a hierarchy is a premature commitment** — the agent roles, routing logic, and escalation paths are rarely correct on first design. Start sequential, extract a supervisor only after seeing where contention and routing logic emerge.
- **Multi-agent eval is harder than single-agent eval** — HITL (human-in-the-loop) becomes critical because of emergent inter-agent behaviors that automated metrics miss. Amazon's agentic systems team specifically calls out evaluating inter-agent communication, conflict resolution, and logical consistency as requiring human oversight — not automatable in production today.
- **Cost compounds silently** — one team tracked $847/month against a $200/month budget because agent loops weren't terminated and context grew with every round. Instrument cost per agent per session from day one.
- **Tool overlap causes agent conflict** — two agents with overlapping tool capabilities will both attempt the same task and produce contradictory outputs. Define tool ownership at the architecture level, not at runtime.
