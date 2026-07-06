# S-441 · The Multi-Agent Boundary Problem

Your single agent works fine until it doesn't — then you split it into five agents and spend six weeks debugging hand-offs between them. The real question isn't "how many agents" but "where do the boundaries go." Teams that get this wrong end up with worse debuggability and more coordination overhead than they started with.

## Forces

- **One agent is simpler to reason about — until it isn't.** Conflicting concerns (e.g., a helpful assistant vs. an impartial assessor) cannot share context without bias, but splitting adds communication cost
- **Adding agents multiplies failure modes.** Each agent is an LLM call chain, which means each is a potential failure, hallucination, and latency spike; FRENXT Labs calls this "complexity is not free"
- **Naive boundaries (by workflow step) are the most common mistake.** Splitting on "planner → researcher → writer" sounds logical but creates tight coupling that makes debugging harder, not easier
- **Multi-agent pipelines are 40–60% cheaper for complex tasks** (Ivern 2026, 200-task benchmark) — but only if boundaries are right

## The Move

Draw agent boundaries by **domain concern, not workflow step**. The triggers that justify a new agent:

- **Conflicting goals** — two tasks where one agent's success corrupts the other's output (e.g., a code-generator that also evaluates its own work)
- **Different latency contracts** — a sub-second user-facing agent and a minutes-long background task cannot share a runtime
- **Different trust levels** — internal data access vs. user-facing responses require separate agent identities and separate permission scopes
- **Different update cadences** — if one component changes weekly and another quarterly, coupling them into one agent means unnecessary redeployments

When starting: build one agent with typed internal modules. Add a second agent only when you encounter one of the four triggers above.

## Evidence

- **FRENXT Labs research:** "Agent boundaries should be drawn by audience, timing, or trust — not by workflow step. Start with one agent and add more only when a genuine boundary appears." — [Multi-Agent System Architecture: A Practical Guide for Production](https://www.frenxt.com/research/multi-agent-architecture-guide), April 2026
- **Microsoft ISE:** "Moving from prototype to production requires intentional design around scalability, latency control, and predictable outcomes. Core requirements: accurate agent selection, optimized LLM usage, efficient orchestration, and scalability." — [Patterns for Building a Scalable Multi-Agent System](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale), November 2025
- **Data-Gate:** "Over-engineering from day one is the most common mistake. Teams starting with multi-agent architecture before understanding their problem domain spend months debugging agent coordination instead of solving user problems." — [Multi-Agent Systems in Production: Lessons from the Field](https://data-gate.ch/multi-agent-systems-production-lessons), 2026

## Gotchas

- **Tight context coupling** — agents that pass large shared state to each other effectively become one agent; use scoped, typed state with checkpointing instead of raw message dumps
- **Silent failures at handoff boundaries** — without full-trace observability (LangSmith, Phoenix, or custom), a failed agent in a pipeline returns a generic error with no lineage; this is the #1 reason multi-agent debugging is harder than single-agent
- **Over-provisioning model tier** — multi-agent setups often route every sub-task to the same frontier model; model cascading (fast/cheap for triage, slow/powerful for final synthesis) cuts cost 40–60% on complex tasks
- **Indirect injection in multi-agent pipelines** — agents that browse or interact with external content (web pages, user uploads) in a pipeline are vulnerable to injection; even basic guardrails degrade once agents have real tools (HN comment, Octomind team)
