# S-338 · Multi-Agent Orchestration: Topology Is the Product

Two teams can use the same framework, same models, same tools — and one system is 6× faster and more reliable. The variable is orchestration topology: how agents are arranged, how they communicate, and where state lives. The production consensus is forming around specific topologies that actually work, and a set of failure modes that sink most teams on first attempt.

## Forces

- **The gap between "multi-agent" demos and production is mostly topology, not model quality.** The agents are fine. The wiring between them determines whether you get coherence or chaos.
- **Google's Agent Bake-Off showed 6× latency reduction** (1 hour → 10 minutes) from decomposed multi-agent architecture alone — larger gains than any model upgrade.
- **AdaptOrch (2026) research found 12–23% performance gains** from orchestration topology changes across SWE-bench and RAG benchmarks — larger than the difference between most LLMs.
- **Most "multi-agent" systems are actually supervisor+specialist in disguise.** True peer networks remain largely theoretical in production.
- **The typed-schema problem compounds across every agent boundary.** Every handoff is a translation event; untyped schemas silently corrupt data at scale.

## The Move

**Start hierarchical. Go peer only when you have a specific reason.**

### Supervisor + Specialists: The Production Default

- One supervisor agent decomposes the task and routes subtasks to specialist agents by capability
- Specialists execute in isolation and return structured results; supervisor integrates
- Simple, debuggable, and the pattern behind most successful production multi-agent systems
- Implemented natively in LangGraph (supervisor pattern), CrewAI (hierarchical mode), and AutoGen (group chat with manager)
- **This is what 80% of teams need.** Ship it before reaching for anything more exotic.

### Planning → Execution Split: The Highest-ROI Topology Pattern

- Separate the "think about what to do" step from "do it"
- A planner agent determines the sequence and tools; an executor agent carries them out
- Prevents executor agents from getting lost in mid-task reasoning loops
- AdaptOrch research confirms this split delivers 12–23% gains across benchmarks — the single most validated topology choice
- Google's Agent Bake-Off: decomposed multi-agent (planner+executors) reduced processing from 1 hour to 10 minutes on complex tasks

### Typed Schemas at Every Handoff Boundary

- Define Pydantic or Zod schemas for every agent-to-agent message contract
- Untyped handoffs silently corrupt: a list becomes a string, a date becomes a datetime, a null propagates
- This is the #1 source of silent production failures in multi-agent systems — no error, just wrong answers
- LangGraph's structured output support and CrewAI's output schemas are designed for exactly this
- Enforce schema validation at the boundary, not inside the agent

### Limit Handoff Depth: The Cascade Problem

- Every agent handoff compounds hallucination risk and latency
- Implement a `max_handoffs=N` guard (typically 3–5) — after N rounds without resolution, escalate or fail explicitly
- Silent cascading failures are the second most common production failure mode: one agent produces a slightly wrong output, the next agent treats it as ground truth, errors compound
- LangGraph's built-in step counting and CrewAI's verbose mode help track this; external observability (LangSmith, Phoenix) is required at scale

### Parallelize Where Possible

- Independent specialist tasks should execute concurrently, not serially
- LangGraph's `defer=True` (v0.1+) enables parallel sub-graph execution with automatic sync — but requires explicit `send()` API configuration
- CrewAI's process modes: `Process.hierarchical` (sequential) vs `Process.concurrent` (parallel)
- AutoGen's group chat supports concurrent agent participation
- **Watch for `defer=True` parallel sync bugs** — the LangGraph pattern that trips up most teams in v0.1 deployments

## Evidence

- **Research paper (AdaptOrch, 2026):** Orchestration topology delivers 12–23% performance gains across SWE-bench and RAG benchmarks — larger than model selection differences. Topology is the lever. — [arXiv/AdaptOrch](https://arxiv.org/abs/2503.05291)
- **Engineering blog (Google Agent Bake-Off):** Decomposed multi-agent architecture reduced complex task processing from 1 hour to 10 minutes — a 6× improvement from topology changes alone. — [Google Research](https://arxiv.org/abs/2511.01259)
- **Field note (TURION.AI, March 2026):** "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count." Supervisor+specialists is the pattern that survives contact with production; true peer networks remain largely theoretical. — [TURION.AI field note](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Comparison analysis (Gheware DevOps, January 2026):** LangGraph leads on production state management with steep learning curve; CrewAI leads on prototyping speed; AutoGen leads for Azure/enterprise. "Default to LangGraph unless you have strong reasons not to." — [Gheware comparison](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Decision guide (Internative, 2026):** Framework selection decision tree: 3+ engineers dedicated to AI infra → LangGraph or CrewAI viable; 0–2 → managed platform. Linear workflow → CrewAI or LangGraph; complex branching → LangGraph. — [Internative guide](https://internative.net/insights/blog/langgraph-vs-crewai-vs-autogen-2026-comparison)

## Gotchas

- **LangGraph's `defer=True` parallel execution has subtle bugs in v0.1.** The `send()` API for streaming sub-graph results back to the parent requires careful state synchronization. Test parallel paths explicitly; don't assume sequential-equivalent behavior.
- **CrewAI's built-in agents are designed for hierarchical (sequential) processes by default.** Concurrent mode exists but requires explicit configuration. The documentation defaults lead teams toward serial execution.
- **Observability across agent boundaries is the most underinvested area.** LangSmith covers LangGraph well; other frameworks require custom instrumentation. A multi-agent run with no cross-boundary traces is undebuggable in production.
- **Multi-agent LLM calls compound cost faster than you expect.** Every handoff is an additional LLM call. A 5-agent pipeline can easily be 10–20× more expensive per task than a single-agent approach. Measure cost per task before scaling.
