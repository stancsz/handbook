# S-263 · Six Multi-Agent Patterns — and the Cost Truth Nobody Talks About

Multi-agent systems are surging: 1,445% more enterprise inquiries than Q1 2024 (Gartner), organizations averaging 12 agents in production, 67% growth expected in two years. But 40% of pilots die within six months — not because coordination fails, but because teams pick the wrong orchestration pattern and don't know how it breaks. And nobody publishes what it actually costs.

## Forces

- **The right pattern is domain-specific.** Orchestrator-worker works for cross-functional tasks; hierarchical is built for management chains; pipeline is optimal for sequential transformations. Picking the wrong one means rewriting the coordination layer after launch.
- **Context degradation kills single agents.** Model reasoning degrades by up to 73% when critical information is buried mid-context. Safety guardrails get buried, persona bleeds between roles, and the model hallucinates libraries that don't exist. Splitting into specialized agents is the fix — but it multiplies cost.
- **Cost compounds across agents.** Princeton NLP found single agents match multi-agent performance in 64% of benchmarks at half the cost. Multi-agent adds ~2.1 percentage points of accuracy at roughly 2x cost. Teams don't model this before committing to architecture.
- **Typed handoffs are the #1 operational killer.** Every unvalidated agent-to-agent boundary is a place where the system silently corrupts state. Schema versioning at handoff boundaries is non-negotiable in production.

## The Move

Match your orchestration pattern to your problem structure, not your framework preference. Validate handoff schemas at every boundary. Model cost per task before you commit to multi-agent.

**Six patterns, ranked by when to use them:**

1. **Orchestrator-Worker** — One central agent decomposes tasks, delegates to specialists, assembles results. Workers use cheaper models; the orchestrator uses capable reasoning. Best for cross-functional tasks (e.g., a research task needing search + analysis + writing). Cost: ~$5–8 per complex task with 4-agent setup.
2. **Hierarchical** — A manager agent sits above specialist agents, routing tasks down a chain of command. Mirrors org charts. Best for management workflows (director → strategist → creative → producer). Avoid if you need parallelism — it's slow by design.
3. **Pipeline** — Data flows through a fixed sequence of agents, each transforming output for the next. Best for sequential transformations (crawl → parse → extract → validate → store). Failure is easy to trace; adding parallelism is hard.
4. **Supervisor** — A single routing agent decides which specialist handles each request using tool-calling. Minimal overhead, no inter-agent communication. Best for simple dispatch problems with clear categories.
5. **Swarm** — Agents negotiate directly with each other in a peer network, no central coordinator. Best for open-ended creative or research problems. Hardest to debug — use only when the problem genuinely has no right answer path.
6. **Agent-as-Judge** — A separate evaluation agent scores outputs at each stage, deciding whether to retry, escalate, or accept. Adds latency and cost but catches quality drift. Best for high-stakes outputs where quality variance is unacceptable.

**Handoff schema rules (non-negotiable in production):**
- Every agent-to-agent boundary needs a validated JSON schema with version numbering
- Include explicit error states — don't let agents assume a downstream agent will handle null gracefully
- Log handoff inputs and outputs at the schema level, not just the LLM call level

**Cost modeling before architecture:**
- Single agent benchmark: cost per task baseline
- Multi-agent multiplier: 2x for 2 agents, ~4x for 4-agent orchestrator-worker
- Re-evaluate at 10+ agents — add orchestration overhead and token costs compound
- Set per-task cost ceilings with automatic rollback triggers

## Evidence

- **Gartner:** 1,445% surge in multi-agent inquiries Q1 2024 → Q2 2025; organizations average 12 agents; 40% pilot failure within 6 months of production deployment — [beam.ai orchestration patterns post](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production) (Jun 25, 2026)
- **Princeton NLP:** Single agents match multi-agent performance in 64% of benchmarks at half the cost; multi-agent adds 2.1 percentage points accuracy at roughly 2x cost — [beam.ai orchestration patterns post](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production) (Jun 25, 2026)
- **Comet ML:** Model reasoning performance degrades up to 73% when critical information is buried in mid-context; persona "bleeding" between agent roles causes hallucination of non-existent libraries — [Multi-Agent Systems blog](https://www.comet.com/site/blog/multi-agent-systems/) (Jan 5, 2026)
- **ODSEA (Turion.ai):** LangGraph: graph nodes + cyclical state for production control. CrewAI: role-based team hierarchy for fast prototyping. Microsoft Agent Framework 1.0 GA (Apr 2026): conversational chains. 65% of teams hit a wall within 12 months and rewrite — [Turion.ai 2026 comparison](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026) (May 7, 2026)
- **Raft Labs:** 89% of teams have observability tooling but only 52% have evals; this gap explains why multi-agent debugging is mostly guesswork — [Multi-agent systems guide](https://www.raftlabs.com/blog/multi-agent-systems-guide/) (2026)
- **Production memory architecture:** Hot/cold memory pipeline: events → PII redaction → memory decider (LLM rubric) → embeddings → hybrid search (BM25 + vector + RRF reranking). Three-tier: working memory (task state during execution), episodic (session context), semantic (cross-session knowledge). Tools: Zep/Graphiti (temporal knowledge graph), Mem0 (cross-entity memory service), Azure AI Search (hybrid retrieval) — [Medium production memory post](https://medium.com/@betanu701/a-production-ready-hot-cold-memory-architecture-for-multi-tenant-ai-agents-59de7dbe0d23) (2025)

## Gotchas

- **Don't pick a framework, pick a pattern.** LangGraph gives you fine-grained graph control; CrewAI gives you role-based speed. Neither wins universally. ODSEA's team rebuilt their entire Agent Platform v2 on LangGraph after evaluating all three in production conditions — the framework followed the architectural decision, not the other way around.
- **Not investing in evals early enough.** With 89% observability coverage but only 52% eval coverage, teams can see where their agents go wrong but can't automatically judge whether the output is right. Build eval pipelines from day one — retrofitting them when quality drift appears is too late.
- **Building the durable event bus too late.** An in-process event bus is fast and simple, but events are lost on crash. The durable event bus (backed by Kafka/Redpanda) should have been the default from day one, with in-process as the development-only option — not the other way around.
- **Over-engineering memory before you have data to tune it.** Three-tier memory with hybrid retrieval sounds impressive, but the tuning (similarity thresholds, keyword weights, merge strategies) only works when you have enough real agent interactions to calibrate against.
- **Sandboxing is becoming its own specialized layer.** E2B, Modal, Shuru, Firecracker wrappers — the agent runtime sandbox is decoupling from the orchestration layer. This is a 2025-2026 trend that changes how you think about security boundaries.
