# S-567 · The Pilot Grave: Why 70% of Agentic Projects Die Before Production

The demo works. The pilot impresses. The invoice arrives. Six months later: cancelled. This is the agentic AI pilot grave — a documented failure pattern where the distance between "working prototype" and "reliable production system" is wider than any other category of software engineering. 68% of AI agent pilots never reach production deployment, and Gartner projects 40%+ of agentic AI projects will fail outright by 2027.

## Forces

- Building a functional agent POC is approximately 20% of the work; the remaining 80% is production hardening — reliability engineering, observability, cost controls, and failure recovery
- Standard context strategies (vector stores, text chunking) fail under long-running production conditions — agents forget core constraints after a week, facts change and old vectors still surface, and agents re-introduce themselves every morning
- Production costs run 5-15x higher than prototype costs due to infrastructure overhead, monitoring, reliability engineering, and operational maintenance that prototypes never account for
- The sandbox problem: agents that execute code based on untrusted LLM-generated input (emails, Slack, web pages) introduce indirect prompt injection attack surface that Docker containers cannot contain — container namespaces isolate resources but syscalls go directly to the host kernel
- 89% of teams have observability but only 52% have evals — the debugging gap explains why multi-agent failure modes are mostly guesswork
- Enterprises averaging $85,521/month in AI operational costs (2025), with runaway agent loops costing $15 in 10 minutes to $47,000 over 11 days

## The move

The teams that cross the pilot-production chasm treat agent development like safety-critical software — not like web app prototyping.

**Scope ruthlessly at pilot stage.** Four categories consistently shipped in 2025: developer tooling (tight compile-test-review feedback loop), internal operations (ticket triage, access routing, runbooks with clear pass/fail criteria), research synthesis (multi-source aggregation with defined scope), and document processing (structured extraction with validation layers). Everything else stalls.

**Build the memory architecture before the agent.** Production agents need a 7-layer memory stack that handles episodic (conversation history), semantic (world knowledge), procedural (agent skills), working (per-turn scratchpad), archival (completed task history), sensory (raw inputs), and world model layers. Adding vector search on top of a broken memory architecture amplifies the problem — old facts surface confidently alongside new ones.

**Put the circuit breaker at the API call site.** Token budgets, per-agent spend limits, and hard cost circuit breakers must exist at the code level — not in dashboards. A prompt cache hit is worth $0 vs. $0.001-$5.00 per token. Teams that implement semantic caching + model cascading reduce token costs by 40-70% with no measurable quality degradation.

**Sandbox at the isolation tier that matches your threat model.** Standard Docker containers share the host kernel — inadequate for agents executing LLM-generated code. Firecracker microVMs (E2B, Daytona) provide hardware-level isolation with dedicated kernels per sandbox. For untrusted web data ingestion, gVisor user-space kernels intercept syscalls. For the highest-risk workloads, Kata Containers add a full VM layer.

**Default to LangGraph for anything with state.** The 90K+ GitHub stars and production deployments at Uber, LinkedIn, and Klarna reflect real production stability. CrewAI's role-based model gets prototypes running fastest but hits scalability limits within 6-12 months. If the workflow doesn't need state machines, skip both and write Python.

## Evidence

- **Deloitte study (2025):** 68% pilot-to-deploy failure rate — 38% of organizations piloting agents but only 11% have production deployments — cited in [byteiota.com analysis](https://byteiota.com/ai-agent-production-gap-68-pilot-to-deploy-failure/) drawing on Deloitte's Emerging Technology Trends study
- **Gartner (June 2025):** 40%+ of agentic AI projects will fail by 2027 — [RCR Wireless coverage](https://www.rcrwireless.com/20250627/business/agentic-ai-gartner)
- **Sistava production run (~1,000 agents, 2+ months):** Standard context strategies fail at scale; agents forget constraints, re-introduce themselves, and pick wrong tools even after correction; facts change over time but vector similarity scores do not understand chronological decay — [DEV Community: 7-Layer Memory Architecture](https://dev.to/mahmoudz/the-7-layer-memory-architecture-behind-modern-ai-agents-5060)
- **Zylos Research (May 2026):** Enterprises average $85,521/month AI operational costs (2025); 60-85% recoverable through prompt caching, model routing, and budget enforcement; multi-agent workflows cost $5-8 per complex task — [AI Agent Cost Engineering](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)
- **Microsoft Security research (May 2026):** Indirect prompt injection in agent data ingestion pipelines; Docker container isolation insufficient for agents executing LLM-generated code from untrusted sources — cited in [TURION.AI Agent Sandboxing analysis](https://turion.ai/blog/agent-sandboxing-firecracker-gvisor-microvm-architecture)

## Gotchas

- **Vector similarity doesn't understand truth overrides.** When a user switches email providers, the agent still surfaces the old provider in context because the vector score is high. Chronological decay or explicit invalidation logic is needed — not just similarity search.
- **Multi-agent overhead eclipses the gains for most use cases.** AppWorld shows 86.7% failure rate on cross-app workflows. ChatDev achieves 33.3% correctness. Pattern choice matters more than model capability — split agents only when workflow complexity genuinely justifies the coordination cost.
- **The eval gap is where agents go wrong silently.** Teams instrument observability (logs, traces, dashboards) but skip building test suites that measure whether outputs are correct. Without evals, you don't know the agent regressed until a user reports it.
- **Caching without invalidation is worse than no caching.** Semantic caches that never clear serve stale answers confidently. Build TTL and explicit invalidation triggers into any caching layer.
- **Checkpoint table bloat kills Postgres quietly.** A LangGraph graph with 20 nodes running 10,000 times/day produces 200,000 checkpoint rows/day. Without a pruning job, the table accumulates millions of rows and query latency degrades silently over months.
