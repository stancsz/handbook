# S-518 · Multi-Agent Coordination Patterns: Choosing Your Agent Topology

When a single agent starts producing contradictory outputs, looping on easy sub-problems, or silently failing on hard ones — the fix is not a better prompt. It is a different agent topology. The question is not "how many agents" but "how do they hand off, resolve conflicts, and share context."

## Forces

- **Typed handoffs are the make-or-break of multi-agent systems** — untyped handoffs (plain text passing) cause agents to silently misinterpret each other's outputs, leading to failures that look like LLM quality problems but are actually integration failures. RaftLabs calls this the #1 killer of multi-agent workflows.
- **89% of teams have observability but only 52% have evals** — the gap means debugging multi-agent failures is largely guesswork until you instrument for it.
- **Inference costs compound to $5-8 per complex task** in a 4-agent workflow — the topology you choose determines how many LLM calls fire per task.
- **65% of teams hit a wall within 12 months** and rewrite their orchestration layer — usually because they picked a topology that worked for the demo but collapsed under production complexity.
- **Gartner tracked a 1,445% surge in multi-agent inquiries** from Q1 2024 to Q2 2025, with 57% of organizations already running agents in production.

## The Move

Four topologies cover most production use cases. Choose based on task decomposition predictability, not team size.

### 1. Supervisor (centralized delegator)

One orchestrator agent owns the task, decomposes it, delegates to workers, synthesizes results. Think "project manager with a team."

- Best for: Semi-structured tasks where you need a single answer or coherent output — research synthesis, strategic analysis, report generation.
- The supervisor must have typed schema contracts with each worker so outputs are machine-readable, not prose.
- Failure mode: The supervisor becomes a bottleneck and a single point of failure. If it misclassifies a sub-task, the whole workflow goes wrong.

### 2. Hierarchical (multi-level)

A senior agent delegates to mid-level agents who delegate to specialists. Common in enterprise: Director → Strategist → Creative → Analyst.

- Best for: Marketing agencies, complex workflows with domain specializations (Opensoul/Paperclip runs 6 agents this way).
- Prevents the supervisor bottleneck by distributing decomposition decisions across levels.
- Tacnode identifies 8 coordination patterns within this topology: shared context layer, event-driven handoffs, semantic contracts, single-writer principle.

### 3. Pipeline (sequential refinement)

Agents process work in sequence, each refining the previous output. No agent talks to a previous stage — only the next.

- Best for: Content workflows: draft → review → edit → fact-check → publish.
- The most predictable topology: you can trace data flow, cost is linear in stages, and failures are localized.
- The tradeoff: linear cost and latency. A 5-stage pipeline costs 5x a single agent and takes 5x the time.

### 4. Swarm (autonomous parallel)

Autonomous agents work in parallel with minimal coordination, discovering collaboration as they go.

- Best for: Exploration tasks where you want diverse perspectives — market research, brainstorming, competitive analysis.
- The hardest to debug. Agents can produce contradictory recommendations with no arbitration mechanism.
- Tacnode's production-tested patterns for swarm: distributed consensus, priority queues, semantic contracts enforced at handoff boundaries.

### 5. Orchestrator-Worker (fan-out/fan-in)

A single orchestrator dispatches identical sub-tasks to multiple workers in parallel, then aggregates. Map-reduce for agents.

- Best for: Batch processing — analyzing 100 documents, summarizing 50 emails, extracting data from 200 records.
- The highest throughput topology. Cost is dominated by the parallel fan-out; aggregation is cheap.
- Key constraint: workers must be stateless and idempotent since execution order is non-deterministic.

## Evidence

- **RaftLabs:** "Untyped handoffs kill multi-agent workflows faster than any other issue." — [Multi-Agent Systems: Architecture Patterns for AI](https://www.raftlabs.com/blog/multi-agent-systems-guide), Nov 2025. 1,445% surge in multi-agent inquiries (Gartner Q1 2024 → Q2 2025); 57% of orgs already in production; 89% have observability but only 52% have evals; inference costs compound to $5-8 per complex task; 65% of teams rewrite within 12 months.
- **Tacnode:** "When AI agents conflict, you get duplicate orders, race conditions, and angry customers." Documents 8 production-tested coordination patterns including single-writer principle, semantic contracts, distributed consensus. — [Multi-Agent Architecture: 8 Coordination Patterns That Actually Work](https://tacnode.io/post/multi-agent-architecture), Jan 2026.
- **Hacker News (Evan/iamevandrake):** Opensoul ships 6 agents in hierarchical topology — Director (strategy/coordinator), Strategist, Creative, Producer, Growth Marketer, Analyst — running autonomously on scheduled heartbeats. Built on Paperclip. — [Show HN: Opensoul – Open-source agentic marketing stack](https://news.ycombinator.com/item?id=47336615), Mar 2025.
- **Fast.io:** Documents 4 primary orchestration patterns (supervisor, pipeline, swarm, hierarchical) and identifies shared storage (not shared state) as the coordination challenge that trips up most teams. — [Multi-Agent Orchestration Patterns: Complete Guide 2026](https://fast.io/resources/multi-agent-orchestration-patterns).

## Gotchas

- **Do not use swarm topology for anything that requires a single ground truth.** Agents will diverge and there is no built-in arbitration. Use supervisor or pipeline instead.
- **Typed schema contracts at handoffs are not optional.** Pass structured JSON or pydantic objects, not prose summaries. Tacnode's "semantic contracts" pattern enforces this: the receiving agent validates input against a schema before processing.
- **Pipeline latency is the price of predictability.** If you need sub-second responses, pipeline is the wrong topology. If you need auditable, traceable output, pipeline is almost always right.
- **Fan-out/aggregation costs are dominated by the parallel phase.** Instrument each worker independently so you can see which sub-task type is driving your bill.
- **Start with supervisor, not swarm.** Most teams that reach for swarm want the intellectual appeal of autonomous agents but need the discipline of centralized control. Supervisor topology surfaces failures faster and costs less to debug.
