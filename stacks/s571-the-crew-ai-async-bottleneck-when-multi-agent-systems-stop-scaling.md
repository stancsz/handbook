# S-571 · The CrewAI Async Bottleneck: When Multi-Agent Systems Stop Scaling

A working CrewAI system with 5 agents and 10 concurrent users runs fine. Add 50 concurrent requests and P95 latency jumps from 800ms to 12 seconds — not because the agents are slow, but because the shared async message bus saturates. This is the CrewAI async bottleneck: the most common production failure mode in multi-agent deployments, and it has a documented solution.

## Forces

- **Throughput vs. latency tradeoff:** CrewAI's native async loop handles agent coordination in-process — simple and correct for prototypes, a serialization point at scale
- **Stateful orchestration couples coordination to execution:** the agent that dispatches tasks also executes them, meaning a blocked task blocks the dispatcher
- **Memory growth is unbounded within a crew:** conversation history, tool results, and intermediate outputs accumulate per-agent unless explicitly trimmed, and this compounds under concurrent load
- **Naive horizontal scaling makes it worse:** spinning up more CrewAI instances without decoupling the message bus creates thundering-herd problems on shared state

## The Move

**Decouple orchestration from execution using Redis-backed task streams.**

Instead of running agents in-process within CrewAI's async loop, treat each agent as a stateless worker that pulls tasks from a Redis stream. The crew coordinator becomes a lightweight dispatcher; agents become horizontally scalable workers.

### Core Pattern (CrewAI v0.50+, Python 3.12)

```
┌─────────────────┐     Redis Stream     ┌─────────────────┐
│  Crew Coordinator│ ─── (task queue) ──→│  Agent Worker A │  (container 1)
│  (dispatch only) │                      │  Agent Worker B │  (container 2)
└─────────────────┘                      │  Agent Worker C │  (container 3)
                                          └─────────────────┘
       ↑ results flow back via separate response stream
```

### Specific Implementation Steps

1. **Extract agent logic into standalone workers.** Each agent runs as an independent FastAPI service in its own container. Agent A and Agent B are separate deployments, not separate threads in the same process.

2. **Use one Redis stream per crew, not one global stream.** A single shared stream creates head-of-line blocking. Namespaced streams (`crew:marketing:{task_id}`) isolate crew workloads.

3. **Route through S3-compatible object store for large payloads.** Agent-to-agent data (documents, intermediate outputs) goes through object storage, not Redis. Redis carries only task metadata and lightweight control signals.

4. **Set per-task timeout and max retries at the stream consumer level.** Not in the agent prompt — in the Redis consumer configuration. This prevents zombie tasks from accumulating.

5. **Handle concurrency at the worker level with a semaphore.** Each agent container limits concurrent executions to `n` (tuned to the model's rate limits), not unlimited parallelism.

### Production Numbers (AWS EKS, m5.xlarge nodes, 4 vCPU)

- **Before decoupling:** 50 concurrent requests → P95 = 12s, error rate = 8%
- **After decoupling:** 500 concurrent tasks → P95 < 2s, error rate < 0.1%
- **Scaling behavior:** linear horizontal scaling up to 100+ concurrent crews

## Evidence

- **Engineering blog (Markaicode):** "The single most common production failure in CrewAI multi-agent systems is not agent logic but the asynchronous message bus — a bottleneck that brings 95th percentile request latency from 800ms to 12s." Tested on CrewAI v0.50.0, Python 3.12, AWS EKS clusters — [markaicode.com/architecture/crewai-multi-agent-production-architecture-avoiding-the-async-bottleneck-2026](https://markaicode.com/architecture/crewai-multi-agent-production-architecture-avoiding-the-async-bottleneck-2026)
- **Engineering blog (Markaicode):** Redis-backed task orchestrator with one stream per crew achieves 500 tasks/min at P95 < 2s. Tested on AWS EKS (m5.xlarge, 4 vCPU). — [markaicode.com/architecture/crewai-system-design-architecture-1048](https://markaicode.com/architecture/crewai-system-design-architecture-1048)
- **CrewAI official docs:** "Wrapping [Crews] in a Flow provides the necessary structure for a robust, scalable application" — recommended pattern is Flow-first, not Crew-first — [docs.crewai.com/v1.15.0/en/concepts/production-architecture](https://docs.crewai.com/v1.15.0/en/concepts/production-architecture)

## Gotchas

- **Isolating agents into separate containers means losing CrewAI's built-in shared memory.** You must re-implement inter-agent memory yourself — typically via a shared Redis instance or a dedicated vector store for agent context.
- **The Redis stream pattern trades simplicity for operational complexity.** You now have a Redis cluster, an object store, and multiple agent services to monitor. This is the right trade at scale, but it's over-engineering for a team of two.
- **Timeout configuration is load-dependent.** A task that completes in 400ms at 10 concurrent requests may take 3s at 200 concurrent requests because model rate limits kick in. Set timeouts conservatively and route to fallback models when primary model queues back up.
- **CrewAI's native hierarchical mode (manager agent delegation) does not survive this decoupling.** The manager is part of the in-process crew. If you need hierarchical coordination in a decoupled architecture, implement the manager role as a separate service that reads from the Redis stream and dispatches sub-tasks.
