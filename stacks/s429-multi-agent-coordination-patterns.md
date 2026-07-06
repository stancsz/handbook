# S-429 · Multi-Agent Coordination: When to Split and How

A single agent works until it doesn't — then teams reach for multi-agent architectures and immediately face a harder problem: coordination overhead, shared state, and failure modes that don't exist in single-agent systems. Most teams split too early, and the ones who get it right have a discipline around coordination patterns that most tutorials skip entirely.

## Forces

- **Coordination tax vs. specialization gain.** Splitting agents lets each specialize, but adds message-passing latency, shared memory complexity, and failure propagation. The gain must outweigh the tax — and it's not obvious when it does.
- **Shared context is the hidden dependency.** Single agents share context trivially. Multi-agent systems require explicit mechanisms: shared memory stores, structured state passing, or a supervisor that aggregates outputs. Teams that skip this end up with agents that can't see each other's work.
- **Failure modes change type.** A single agent fails at a task. A multi-agent system can fail because agents disagree, deadlock on dependencies, or cascade failures across the graph. Tracing these failures requires observability that most teams add too late.
- **The stack is stratifying into layers.** Sandbox/execution environments (E2B, Modal, Firecracker) are becoming their own dedicated layer — separate from orchestration, separate from the model. Treating them as an afterthought causes security and isolation problems at scale.

## The move

**Match coordination topology to task structure, not to the coolness of the architecture.**

- **Start with one agent.** Most use cases don't need splitting. Add agents only when you have a concrete bottleneck: a task that requires genuinely different tools/knowledge, or measurable parallelization gains. If you can't name the specific failure mode you're solving by splitting, don't split.
- **Use hierarchical coordination for sequential dependencies.** A supervisor agent owns the top-level plan and delegates to specialist agents. LangGraph's `conditional_edges` + `StateGraph` is the standard implementation. This pattern handles "do research, then write, then review" chains cleanly.
- **Use peer coordination for independent parallel work.** Multiple agents with the same context work on sub-tasks simultaneously, reporting back to a fan-in point. Effective when tasks are embarrassingly parallel and don't have data dependencies between them.
- **Implement structured shared state from day one.** Don't rely on context window sharing for cross-agent memory. Use a shared vector store (Qdrant, Pinecone) or a structured session store. Agents should be able to retrieve each other's intermediate outputs, not just their own.
- **Instrument for traces before you need them.** PostHog's practice of "traces hour" — a weekly meeting where the team manually reviews real LLM interaction traces — is a better starting point than any eval library. You find failure modes that automated tests miss. Phoenix, LangSmith, or even structured JSON logging all work; pick one and wire it in at agent initialization.
- **Isolate agents at the process level, not thread level.** Sandboxing each agent as a separate process (or container) prevents memory bleed and enables independent scaling. E2B, Modal, and Firecracker-based approaches are becoming standard for this layer.

## Evidence

- **Survey:** Only 5% of surveyed teams (1,837 respondents) had agents live in production as of early 2025 — and most of those teams were still struggling with observability and guardrails, not model capability. — *Cleanlab State of AI Agents in Production 2025* — https://cleanlab.ai/ai-agents-in-production-2025
- **Engineering post:** PostHog runs a weekly "traces hour" to manually analyze real LLM traces before running evals. They found that users cared about consistent performance and clear failure modes — not the breadth of agent capabilities. — *PostHog Blog: What We Wish We Knew About Building AI Agents* — https://posthog.com/newsletter/building-ai-agents
- **HN post:** Opensoul ships 6 agents (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) coordinated through a Paperclip orchestration layer with a Director agent managing task delegation. All agents run on scheduled heartbeats with explicit work queues. — *Hacker News Show HN: Opensoul* — https://news.ycombinator.com/item?id=47336615
- **Blog post:** Philipp D. Dubach argues the agent stack is stratifying into six layers with distinct defensibility profiles — and that context, not models, sits at the highest lock-in layer. Sandboxing is emerging as its own dedicated layer. — *Philipp Dubach: Don't Go Monolithic; The Agent Stack Is Stratifying* — https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/

## Gotchas

- **Splitting too early.** If you can't articulate the specific bottleneck (not "it'll be more scalable" but "this agent needs tool X that blocks tool Y"), you're adding complexity without evidence. Start simple.
- **Forgetting shared memory.** Agents that can't see each other's intermediate outputs will make redundant calls or reach incorrect conclusions. Structured shared state is not optional in multi-agent systems — it's the backbone.
- **Skipping observability until something breaks.** Multi-agent failures cascade in ways that are hard to reconstruct from logs. Trace data (which agent called which, what state was passed, what the output was) is the only way to debug coordination failures.
- **Over-engineering the topology.** A three-layer hierarchy for a two-step task is as bad as a single agent for a ten-step one. The coordination pattern should reflect the task structure, not a general architectural principle.
