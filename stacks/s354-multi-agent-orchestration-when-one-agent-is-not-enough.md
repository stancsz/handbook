# S-354 · Multi-Agent Orchestration: When One Agent Is Not Enough

Single agents drift on hard problems — they lose context halfway through, make confident wrong turns, and have no second opinion. Multi-agent orchestration solves this but immediately creates a harder problem: getting agents to cooperate rather than collide. The production challenge is not building agents; it is coordinating them.

## Forces

- **Context window is finite but problems are not.** A single agent handling a 10-step workflow burns through its context with every tool call, degrading mid-task. Splitting work across specialized agents keeps each one operating in a tight, relevant context window.
- **The coordination overhead is non-trivial.** Adding a second agent means handling handoffs, shared state, result aggregation, and failure propagation. The coordination cost can exceed the benefit if the split is wrong.
- **The demo-to-production gap is wider for multi-agent systems.** Single-agent demos look impressive. Multi-agent systems fail in new ways — agents deadlock, loop, override each other's outputs, or corrupt shared state. The observability requirements multiply.
- **State management is the hardest part.** Every multi-agent architecture eventually becomes a distributed state problem. Who holds the plan? What happens if the coordinator crashes? How do you resume from a mid-step failure?

## The Move

### Know when to split

Split agents when: tasks are parallelizable, required expertise is genuinely different (code review vs. test generation), one agent needs a second opinion before proceeding, or context saturation degrades performance. Do not split to parallelize sequential work — the coordination cost of merging results often exceeds the time saved.

### Pick an architecture shape

**Centralized (coordinator pattern):** A single orchestrator agent holds the plan, assigns subtasks to specialist agents, collects outputs, and synthesizes the final result. Easier to observe and debug. Single point of failure if the coordinator goes off-track. Best for: structured workflows where the overall plan is known upfront.

**Decentralized (peer-to-peer):** Agents coordinate among themselves without a central conductor. More resilient and flexible, but harder to trace and audit. Best for: open-ended research tasks, creative exploration, or systems where no agent has global visibility.

**Hybrid:** A lightweight coordinator assigns high-level goals; specialist agents own execution within their domain. Combines the debuggability of centralized with the resilience of peer-to-peer. Most common in mature production systems.

### Use the right framework for your shape

LangGraph (90K+ GitHub stars) uses **state machine** semantics — you define nodes (agents or actions) and edges (transitions), with conditional routing. The graph is explicit, serializable, and supports time-travel debugging and human-in-the-loop interruptions. Adopted in production by Uber, LinkedIn, and Klarna. Best when you need fine-grained control over execution flow and need to audit or replay agent runs.

CrewAI uses **role/task/crew** semantics — agents are assigned roles with clear responsibilities, tasks have explicit inputs and expected outputs, and crews define the collaboration protocol. Faster to prototype with than LangGraph. The opinionated structure maps well to how product teams think about workflows. Best when you need to ship fast and the workflow is reasonably structured.

AutoGen (Microsoft) uses **conversational peer** semantics — agents talk to each other as equals, with flexible message-passing. Steeper learning curve, deeper customization. Best for research teams, Azure-native shops, or when you need dynamic conversation flows that don't fit a predetermined structure.

### Treat state like a first-class concern

Store agent state externally (Redis, PostgreSQL, or a graph database) rather than in memory. This enables: (1) resume-from-failure without restarting the entire workflow, (2) audit trails for compliance, and (3) human-in-the-loop review of intermediate steps before a downstream agent consumes them.

### Instrument before you need it

Multi-agent failures are painful precisely because you cannot reproduce them easily. Log every agent's input context, reasoning trace, tool calls made, tool results received, and final output. Use structured traces (LangSmith, Arize Phoenix, or custom JSONL + S3) that link parent-child agent relationships so you can trace a failure from output back to its root cause.

## Evidence

- **Qodo (formerly CodiumAI)** migrated from rigid predefined flows to a LangGraph-based coding agent. Key driver: Claude Sonnet 3.5's release enabled more dynamic, flexible agent behavior — but that flexibility required explicit graph-based control flow rather than implicit linear scripts. They specifically valued LangGraph's ability to "be opinionated where needed" while remaining flexible at the edges. — [Qodo engineering blog](https://www.qodo.ai/blog/why-we-chose-langgraph-to-build-our-coding-agent/)
- **HN Ask: "What is the underlying stack behind multi-agent platforms?" (2025):** Practitioners reported LangGraph for stateful multi-agent pipelines, Temporal for workflow durability, custom event-driven architectures using Kafka, and Redis for shared agent state. A recurring theme: "LangGraph is low-level but has useful features like time travel and human-in-the-loop." — [Hacker News](https://news.ycombinator.com/item?id=48074184)
- **Zylos Research (2026)** documented that 60–85% of production agent spend is recoverable through caching and routing — but teams only discover optimization opportunities after their first runaway agent loop. Runaway loops cost teams anywhere from $15 in ten minutes to $47,000 over eleven days. Multi-agent systems amplify this risk because each agent-to-agent call is another opportunity for a cost-multiplier loop. — [Zylos Research](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/)

## Gotchas

- **Do not split agents for sequential work.** If task B depends on task A's output, running them in parallel saves nothing and adds merge complexity. Split only for genuinely parallel or loosely coupled subtasks.
- **The "agent loop" failure is real and expensive.** Without max-step limits, conversation-turn budgets, and per-call cost circuit breakers, a multi-agent system can cost thousands of dollars in minutes. Set hard limits before deployment.
- **Output validation at every handoff.** An agent's output is only as trustworthy as your validation of it before passing it to the next agent. Never assume the upstream agent was correct — build a lightweight verification step, even if it's just a schema check.
- **Framework choice is sticky.** Switching from CrewAI to LangGraph mid-production is painful. CrewAI's fast prototyping advantage is real, but if you need time-travel debugging, interrupt-and-revise workflows, or fine-grained state management, LangGraph pays off over time.
- **Shared memory is a footgun.** Letting agents read each other's intermediate state sounds useful but creates tight coupling and race conditions. Prefer explicit message-passing with well-defined contracts over shared mutable state.
