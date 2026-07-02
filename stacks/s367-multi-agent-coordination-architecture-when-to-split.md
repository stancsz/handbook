# S-367 · Multi-Agent Coordination: When to Split, How to Route

You have one agent working. You need more capability. The instinct is to add agents — but 72% of token cost in multi-agent systems is pure duplication, and the wrong coordination pattern will give you 10-second P95 latencies before you've hit 50 concurrent requests. The question isn't "how many agents?" — it's "which coordination pattern, for which task shape, with which failure modes?"

## Forces

- **Adding agents doesn't linearly add capability.** Single agents hit walls on diverse expertise, parallelization, and multi-step workflows — but splitting adds coordination overhead, token duplication, and observability debt that grows super-linearly.
- **Every architectural pattern is a tradeoff.** Supervisor patterns add a single point of failure. Hierarchical patterns don't scale past 20 agents without coordination overhead eating your gains. Peer-to-peer is fault-tolerant but slow to reach consensus.
- **Token costs compound across agents.** MetaGPT wastes 72% of tokens on context duplication. CAMEL wastes 86%. A 4-agent orchestrator-worker workflow costs $5–8 per complex task — before any optimization.
- **Observability is the #1 production barrier.** 89% of teams have logs but only 52% have evals. Multi-agent debugging without structured observability is guesswork.

## The move

**1. Match the coordination pattern to the task shape before writing any agent code.**

| Task | Pattern | Why |
|---|---|---|
| Complex workflow with governance needs | Supervisor | One supervisor routes; others specialize |
| 20+ agents, enterprise scale | Hierarchical | Middle managers reduce supervisor load |
| Fault tolerance, distributed resilience | Peer-to-peer | No single point of failure |
| 50+ agents, optimization/robotics | Swarm | Emergent behavior from local rules |
| Linear pipeline with branching | Orchestrator-Worker | Central dispatcher, parallel sub-tasks |

**2. Enforce typed, schema-validated handoffs at every agent boundary.** The #1 killer of multi-agent workflows is unvalidated data passing between agents. Every handoff needs a Pydantic or equivalent schema with a version number. A null reference at an agent handoff crashes the entire workflow silently.

**3. Instrument every hop with OpenTelemetry before you need it.** Add `trace_id` propagation across agent boundaries. At CrewAI production scale, budget P50 < 500ms for orchestration overhead. Measure each hop; you'll find surprising bottlenecks (often LLM response time, not your code).

**4. Start stateless, scale to Redis-backed state only when you need concurrency.** Single-process `Crew.kickoff()` is fine for <10 concurrent crews. Beyond that, use Redis streams for task queues and S3-compatible storage for artifact passing. Each agent runs in its own container. This scales linearly to 100+ concurrent crews.

**5. Model cost before committing to a multi-agent design.** A 4-agent workflow at current pricing: 4 hops × ~$0.05–2.00 per hop depending on model tier = $0.20–8.00 per task. Route cheaper models (Haiku, Gemini Flash Lite) to simple sub-tasks. Reserve Opus/Sonnet for synthesis and validation hops only.

## Evidence

- **Engineering blog:** Shopify Sidekick scaled from a single tool-calling agent to a multi-agent platform; hit a wall at ~40 tools before splitting into specialized agents with a supervisor routing layer — the tool complexity problem is documented with their agentic loop architecture — [Shopify Engineering, Aug 2025](https://shopify.engineering/building-production-ready-agentic-systems)
- **Research survey:** 72% of enterprise AI projects now involve multi-agent systems (up from 23% in 2024); real-world results show 80% reduction in insurance claims processing and $18.7M annual savings in banking fraud; token duplication rates: MetaGPT 72%, CAMEL 86%, AgentVerse 53% — [Zylos Research, Multi-Agent Orchestration Patterns 2025](https://zylos.ai/research/multi-agent-orchestration-2025)
- **HN post:** EvidionAI — open-source research system with Supervisor → Search → Code → Analysis → Skeptic loop, where a Skeptic agent actively challenges conclusions and routes back to Supervisor if they don't hold — validates the supervisor pattern with adversarial checking — [Hacker News, 2026](https://news.ycombinator.com/item?id=47510639)
- **Framework docs:** CrewAI's recommended production architecture wraps crews in Flows for state management and precise execution paths; their GitHub has 49,000+ stars with 100,000+ certified developers — [CrewAI Production Architecture](https://docs.crewai.com/en/concepts/production-architecture)
- **Architecture guide:** Wrong coordination pattern in CrewAI produces tangled deadlocks and 10-second P95 latencies before 50 concurrent requests; stateless agent workers behind Redis-backed orchestrator is the validated scaling pattern — [Markaicode, CrewAI System Design, May 2026](https://markaicode.com/architecture/crewai-system-design-architecture-1048)

## Gotchas

- **Don't add agents for parallelism you don't have.** Token duplication compounds fast. Split only when agents need genuinely different expertise, tool access, or can execute simultaneously without waiting for each other.
- **Don't skip the circuit breaker on agent-to-agent loops.** Without a max-hop count, a routing error between agents produces an infinite loop. The cost impact ranges from $15 in 10 minutes to $47,000 over 11 days (documented production incidents).
- **Don't use hierarchical for fewer than 10 agents.** The coordination overhead of middle managers only pays off at scale. Below that, a supervisor pattern with a single router is cleaner and easier to debug.
