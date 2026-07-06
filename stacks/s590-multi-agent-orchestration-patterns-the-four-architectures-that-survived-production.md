# S-590 · Multi-Agent Orchestration Patterns: The Four Architectures That Survived Production

Four orchestration patterns consistently appear in teams that shipped multi-agent systems past the prototype stage. The choice between them determines your failure modes, debugging burden, and cost curve — and most teams pick wrong the first time.

## Forces

- **Single agents hit a context ceiling fast.** One agent's context window can't hold a full codebase, all domain knowledge, and reasoning chains for complex tasks simultaneously.
- **Naive multi-agent adds coordination overhead that eats your gains.** Without a deliberate pattern, agents spend tokens negotiating who does what instead of doing it.
- **Observability outpaces evaluation.** 89% of teams have logging infrastructure but only 52% have evals — making multi-agent debugging mostly guesswork.
- **Cost compounds per agent.** A 4-agent orchestrator-worker workflow runs $5–8 per complex task. Model economics before committing to architecture.
- **Untyped handoffs kill workflows faster than any other issue.** Every agent-to-agent boundary needs a validated schema with version numbering.

## The Move

Choose your orchestration pattern based on task structure, not familiarity:

**1. Hierarchical (CEO → workers)**
- A central orchestrator decomposes tasks and delegates to specialists
- Best for: Complex, multi-domain tasks with a clear strategic layer (e.g., DevOps platform with CEO, Dev, DevOps, Security agents)
- Failure mode: Orchestrator bottleneck; if the top agent fails, the whole system stops
- Add circuit breakers: if an agent fails 3 consecutive tasks, stop delegating to it and escalate

**2. Pipeline (sequential stages)**
- Tasks flow through a fixed sequence of agents, each transforming output
- Best for: Linear workflows where order matters and outputs are compositional (data → extract → transform → validate → deliver)
- Failure mode: Single-point-of-failure at any stage; no task parallelization

**3. Orchestrator-Worker (hub-and-spoke)**
- A central orchestrator plans and assigns sub-tasks; workers execute in parallel; orchestrator synthesizes results
- Best for: Tasks that decompose into independent sub-tasks (e.g., research across multiple sources, parallel document analysis)
- Cost reality: $5–8 per complex task with 4 agents — model this early
- Add dead letter queues: messages failing 3 delivery attempts route to a DLQ with alerting

**4. Peer-to-Peer (fully decentralized)**
- Agents discover each other's capabilities and negotiate directly
- Best for: Highly dynamic environments where capabilities change frequently; research scenarios exploring emergent collaboration
- Weaknesses: Coordination overhead (agents negotiate instead of act), harder to debug, potential for conflicting approaches

**The cross-cutting concern: typed handoffs**
Every inter-agent boundary must validate its schema. Untyped JSON dict handoffs are the #1 multi-agent failure mode. Use Pydantic or similar at every agent boundary, with version numbers.

## Evidence

- **Gartner (2025):** 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. 57% of organizations already have agents in production, but 40% of agentic AI projects are at risk of cancellation by 2027. — [Gartner via RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Production cost study:** A 4-agent orchestrator-worker workflow costs $5–8 per complex task. One team ($847/month actual vs. $200/month budgeted) found the gap came from unanticipated data format edge cases in production — 47 different formats they never tested. — [Calder's Lab](https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/)
- **GenBrain AI (11 agents, production on GKE since Feb 2026):** Runs 11 agents as a production organization: CEO, Dev, DevOps, Security, Data Engineer, QA, Product Manager, Researcher, Customer Success, Financial Analyst, Legal. Uses hierarchical pattern with circuit breakers and compensating actions (e.g., auto-rollback if smoke test fails after deployment). — [Agent.ceo Blog](https://agent.ceo/blog/multi-agent-architecture-patterns)
- **RaftLabs research (Nov 2025):** 89% of teams have observability tooling but only 52% have evals. The gap explains why multi-agent debugging is mostly guesswork. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- **Don't add agents for parallelism you don't need.** A 2-agent system doesn't need the same architecture as an 11-agent system. Start simple; split when you hit the ceiling.
- **Circuit breakers are not optional.** Without them, one broken agent poisons the entire workflow. Set failure thresholds and escalation paths before you ship.
- **Dead letter queues catch what retries miss.** Agents will fail in ways that retry won't fix (malformed input, schema drift). DLQs with alerting catch these.
- **Eval gap is a production risk, not a nice-to-have.** Logging without evals means you know something broke; you don't know why. Build RAGAS or similar evaluation pipelines from day one.
- **Cost compounds per hop.** Every additional agent in a workflow adds inference cost. Profile your cost-per-task early and set circuit breakers on total budget per task.
