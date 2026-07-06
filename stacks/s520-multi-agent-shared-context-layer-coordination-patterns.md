# S-520 · The Shared Context Layer: How Production Multi-Agent Systems Actually Coordinate

When a pricing agent approves a discount that the fulfillment agent already voided, and the support agent promises something neither of them can deliver, the failure isn't the agents — it's the absence of a shared context layer. In 2025-2026, multi-agent deployments have converged on a core architectural insight: coordination between agents is fundamentally a problem of shared, consistent, current state, not a problem of smarter prompts.

## Forces

- **Two-thirds of the agentic AI market now runs on coordinated multi-agent systems** — single-agent architectures are the exception in production, not the rule. (Gartner tracked a 1,445% surge in multi-agent inquiries Q1 2024 to Q2 2025; 57% of organizations already running agents in production as of late 2025.)
- **Agents operating on the same data without coordination produce contradictory outcomes** — pricing voids what fulfillment promised, risk blocks what support already approved. LLMs will confidently execute on stale or inconsistent state unless the architecture prevents it.
- **Naive shared state (a database both agents write to) introduces race conditions and silent corruption** — agents are non-deterministic; the order of tool execution is not guaranteed; retry behavior compounds the problem.
- **Invisible inference cost compounding** — every multi-agent task that requires coordination generates 5-20+ LLM calls, driving real costs to $5-8 per complex task and making coordination failures doubly expensive.

## The move

The pattern that separates working multi-agent systems from broken ones is a **shared context layer** that sits between agents, not inside them. It provides consistent, current, authoritative state to every agent. Everything else — event-driven handoffs, semantic contracts, conflict detection — builds on top of this foundation.

### Layer 1: Shared Context (the non-negotiable base)

- **Treat context as a service, not a database.** Agents read from and write to an abstraction layer that guarantees consistency. Direct DB access by agents creates race conditions.
- **Use typed schemas for every inter-agent message.** Untyped JSON passed between agents is a silent bug. A "ContractReview" schema with required fields prevents the "pricing said yes but risk never saw it" failure.
- **Serve reads from a feature store, not a transactional DB.** Agents need low-latency reads of current state; they don't need full ACID semantics for reads. Writes go through a transaction layer that emits events.
- **Include provenance metadata on every context entry.** When an agent retrieves state, it should know when it was written, by which agent, and what version. This is the difference between debugging and guessing.

### Layer 2: Coordination Protocols (built on the context layer)

- **Event-driven handoffs over polling.** Instead of Agent A waiting for Agent B to finish, Agent A emits a `TaskCompleted` event with a typed payload. Agent B subscribes and acts when the event arrives. Eliminates polling latency and tight coupling.
- **Single-writer principle per resource.** Assign one agent as the authoritative writer for any given entity (pricing decisions, customer records, order state). Other agents read and suggest; the designated owner confirms. Prevents concurrent overwrites.
- **Semantic contracts instead of "trust the LLM."** A contract specifies: what Agent A promises to have done before handing off to Agent B, what Agent B requires to begin, and what happens if the contract is violated. Enforce these programmatically, not through prompt engineering alone.

### Layer 3: Failure Recovery

- **Checkpoint management for long-running multi-agent tasks.** At each handoff point, write a durable checkpoint. On failure, restart from the last checkpoint rather than from scratch. With 5-20 LLM calls per task, re-running from zero is expensive.
- **Conflict detection as a first-class concern.** When two agents write to overlapping state (e.g., both modify a customer record), detect the conflict before it propagates. The pattern: last-write-wins for idempotent fields; escalation to a third agent or human for conflicting business decisions.
- **Network observability for agent-to-agent communication.** Latency spikes, dropped handoff events, and schema drift between agents are the new equivalent of network partition. Instrument handoff events with trace IDs that span agent boundaries.

## Evidence

- **Blog — Tacnode (Boyd Stowe):** Eight production-tested coordination patterns for multi-agent systems — shared context, event-driven handoffs, semantic contracts, single-writer principle, real-time feature serving, conflict detection, network observability, and checkpoint management. Author documents real failures: "pricing voids what fulfillment promised, risk blocks what support already approved." — [Tacnode](https://tacnode.io/post/multi-agent-architecture)
- **Blog — RaftLabs:** Multi-agent architecture patterns guide covering hierarchical, pipeline, orchestrator-worker, and peer-to-peer patterns. Reports 1,445% surge in multi-agent inquiries (Gartner Q1 2024 to Q2 2025), 57% of organizations already running agents in production. Key failure points identified: contracts between agents (typed schemas), observability gap (89% have tracing, only 52% have evals), inference cost compounding ($5-8 per complex task). — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Blog — TURION.AI:** Deep dive on hierarchical vs peer-to-peer vs hybrid multi-agent collaboration patterns. Argues that choice of coordination architecture determines system reliability and cost efficiency. — [TURION.AI](https://turion.ai/blog/multi-agent-collaboration-patterns)

## Gotchas

- **Adding agents without adding coordination infrastructure amplifies failure modes.** A system of 4 uncoordinated agents is harder to debug than a system of 4 agents with a shared context layer. More agents → more handoff points → more failure surface.
- **LLM non-determinism makes shared state races worse.** A retry of an agent action may produce a different result. If that action wrote to shared state, you now have a non-deterministic write. Design for idempotent writes or use a transaction log that replays deterministically.
- **Typed schemas between agents drift silently.** If Agent A evolves its output schema and Agent B is still consuming the old schema, the failure is silent until a human notices. Treat inter-agent schemas as API contracts with versioning.
- **Observability across agent boundaries is an afterthought in most implementations.** LangSmith, Phoenix, or custom tracing can span handoffs if trace IDs are propagated. Without this, debugging a failure across 4 agents requires reconstructing the conversation from logs — if they exist.
