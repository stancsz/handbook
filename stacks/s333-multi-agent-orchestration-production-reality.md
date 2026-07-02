# S-333 · Multi-Agent Orchestration: Production Patterns That Hold vs. Those That Don't

Multi-agent demos are convincing. The architecture diagram looks elegant — specialized agents collaborating, dividing labor, synthesizing outputs. What the diagrams don't show is what happens after week one in production: state bleeding between agents, failures that cascade across the graph, costs that scale superlinearly with agent count, and observability that collapses the moment you need to debug. The gap between "it works in demo" and "it holds in production" is not a tuning problem. It's an architectural problem.

## Forces

- **Multi-agent systems are harder than single agents by roughly the order of their agent count.** Every additional agent multiplies the state management surface, failure modes, and cost surface — not additively, but combinatorially. (Balys Kriksciunas, TURION.AI, March 2026 — https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Demos run on clean data and bounded context. Production runs on chaos.** One team saw a 92% success rate in test drop to 55% in production, with costs ballooning from $200/month budgeted to $847/month actual — over 47 distinct data format issues they never anticipated. (Calder, January 2025 — https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/)
- **Context window degradation forces architectural discipline.** When critical information sits in the middle of long contexts, model performance on reasoning tasks degrades by up to 73%. Compartmentalizing context per agent — each processing a focused window, synthesizing findings, passing concise summaries upward — creates an effective "infinite context" without retrieval degradation. (Comet ML, 2026 — https://www.comet.com/site/blog/multi-agent-systems)
- **The enterprise stack now requires a gateway control plane.** Without one, multi-agent systems lack governed access, full audit trails, and per-agent observability — which are non-negotiable for regulated environments. (TrueFoundry, 2026 — https://www.truefoundry.com/blog/multi-agent-architecture)

## The Move

Three orchestration patterns cover most real-world multi-agent designs. The choice between them is load-bearing — pick wrong and you rewrite within 12 months.

### Supervisor + Specialists (Recommended Starting Point)
- One supervisor agent decomposes incoming tasks and routes subtasks to specialist agents
- Specialists execute and return results; supervisor synthesizes the final output
- Characteristics: simple, fully debuggable, explicit failure isolation
- Implementation: LangGraph's supervisor pattern, CrewAI's hierarchical mode
- When to use: Most production workloads. The constraint is simplicity, not capability.

### Parallel + Merge (For Independent Subtasks)
- Multiple agents work simultaneously on independent tasks; their outputs merge before the next stage
- LangGraph natively supports parallel branches with automatic synchronization
- Characteristics: high throughput, requires sub-tasks to be genuinely independent
- When to use: Research/analysis tasks where the same query benefits from multiple perspectives before synthesis.

### Agent Swarm (For Open-Ended Coordination)
- Agents negotiate and delegate peer-to-peer without a central supervisor
- Characteristics: powerful for complex coordination, extremely hard to debug and predict
- When to use: Avoid for production. Effective for research explorations. Several teams that built swarm patterns in 2024 rebuilt them as supervisor patterns in 2025.

### The Control Loop: Corrective RAG as the Model

The same pattern applies to RAG: naive retrieval → evaluate → retry if low quality. Once a relevance grader sits between retrieval and generation, teams report a 60–70% drop in hallucination-inducing retrievals. The framing shift matters: RAG is not a pipeline, it's a control loop. Apply this principle across the agent graph — every agent should be able to signal "I can't complete this, here's why" and trigger a retry or escalation path. (Falcon Lab, May 2026 — https://iwajunnews.com/2026/05/19/agentic-rag-multi-agent-orchestration-in-production-what-we-actually-learned-in-2026)

## Evidence

- **Field note (TURION.AI):** "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count." Documents three patterns that hold in production (supervisor, parallel-merge, agent swarm) and four failure modes that don't announce themselves in demos: state propagation complexity, cascading failures, superlinear cost scaling, and cross-agent observability collapse. — https://turion.ai/blog/multi-agent-orchestration-infrastructure-production
- **Developer post-mortem (Calder):** 18 months of production agent development. 92% → 55% success rate drop from test to production. 47 data format issues encountered in production that were never anticipated. Monthly costs 4x over budget. Key lesson: the demo-to-production gap is structural, not a tuning problem. — https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/
- **Engineering blog (Comet ML):** Long-context performance degrades up to 73% when critical information is buried mid-context. Documents adversarial collaboration as a multi-agent benefit — agents with different roles naturally challenge each other's outputs, catching hallucination that a single monolithic agent would double down on. — https://www.comet.com/site/blog/multi-agent-systems

## Gotchas

- **Don't start with a swarm.** Peer-to-peer autonomous coordination looks elegant on a whiteboard and collapses under debug pressure. Start with supervisor + specialists; add complexity only when you have observability coverage for each level.
- **Cost scales superlinearly, not linearly.** Each agent fires LLM calls. Each call has token costs. Cross-agent context passing multiplies token usage. Budget 3–4x your initial estimate before going to production — teams routinely hit 5-figure costs over a weekend with unbounded multi-agent loops.
- **Log every tool call, every decision, every model call from day one.** This is not optional. Without per-agent tracing, a failure in a 6-agent system is indistinguishable from a failure in a 3-agent system — you simply can't find it.
- **Context bleeding between agents is the silent killer.** An agent's output contaminates the next agent's context unless you explicitly design summary-and-truncate boundaries at each handoff. The "infinite context window" promise of multi-agent systems comes with a per-agent discipline requirement that most teams underestimate.
- **N+1 failure modes.** An agent that times out, an agent that hallucinates a tool call, an agent that returns in a format the supervisor doesn't expect — these compound. Build explicit recovery paths for each: retry, escalate, halt-and-report. Don't assume agents complete cleanly.
