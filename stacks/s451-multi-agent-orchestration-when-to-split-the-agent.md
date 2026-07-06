# S-451 · Multi-Agent Orchestration: When to Split the Agent

You've built a capable single agent. It handles your core task well. Then scope creeps: it needs to do research, draft, review, and publish — and suddenly it's hallucinating on 30% of tasks, latency is unpredictable, and you can't isolate which step is failing. The instinct is to add more context and better prompts. The real fix is splitting into multiple agents — but the decision of when and how to split is where most teams get it wrong.

## Forces

- **A single agent's context window is a shared resource, not a solution.** Adding more capabilities to one agent means it must hold more context per call, burning tokens and degrading reasoning quality for all tasks simultaneously.
- **Failures in monolithic agents cascade invisibly.** When one step fails inside a single agent, the failure is absorbed into the next reasoning step with no trace — debugging requires replaying the entire session.
- **Different task types need different models and tools.** A research step benefits from web access and a fast, cheap model; a code generation step needs a high-capability model and a sandbox. One agent forces a compromise on both.
- **Adding agents adds coordination overhead.** Every new agent boundary is a handoff that can fail, delay, or corrupt data. The overhead is real — splitting without a clear reason makes things worse.

## The move

**Split when: (1)** the task has distinct domain boundaries — different tools, different model requirements, different failure modes; **(2)** you need independent scaling — some steps are I/O-bound, others compute-bound; **(3)** debugging requires isolation — you need to know which step failed without replaying the whole pipeline.

**Use a supervisor/hierarchical pattern** when one agent should own the orchestration decision. The supervisor receives the top-level goal, delegates to specialists, reviews outputs, and decides next steps. LangGraph's graph architecture handles this cleanly: the supervisor node routes to specialist nodes with typed edges.

**Use a sequential pipeline** when steps have strict data dependencies — each step requires the full output of the previous step. Research → Draft → Edit → Fact-check is a canonical case. Simpler to reason about and debug, but no parallelism.

**Use a peer network** (AutoGen-style) when agents should collaborate on equal footing with emergent coordination — appropriate for open-ended research tasks where no single agent has the full picture. Higher ceiling, lower floor: harder to predict and debug.

**The key discipline: treat the agent boundary as a contract.** Define the input schema, output schema, and failure mode for each agent before building. The inter-agent contract is more important than the intra-agent prompt.

## Evidence

- **Framework comparison:** LangGraph (graph/state-machine), CrewAI (role-based teams), and Microsoft Agent Framework 1.0 GA / AutoGen (conversational) each encode a different coordination model. Turion.ai's production analysis: "LangGraph: I build the flowchart, the framework executes it. CrewAI: I hire a team, assign tasks, they figure out the rest. AutoGen: I put agents in a room, let them talk until the problem is solved." The right choice depends on whether you need explicit control (LangGraph) or emergent behavior (AutoGen). — [TURION.AI 2026 comparison](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)
- **Token cost multiplier:** Multi-agent systems consume 70–230x more tokens than a simple chatbot response. A typical chatbot uses 200–500 tokens; an agent task averages 47,000 tokens. Code generation plus testing tasks routinely hit 120K–200K+ tokens per task. The per-token cost compounds rapidly in multi-agent systems where each agent call re-passes context. — [dataku.ai 50-task study](https://dataku.ai/blog/real-cost-of-ai-agents-token-usage-50-tasks)
- **Multi-agent reliability gap:** "Building agent systems that are reliable at scale is fundamentally different than building a chatbot. Non-determinism compounds across agent chains; failures propagate; debugging is opaque." Production teams report 57% of companies now have AI agents in production (2026), but the gap between demo and reliable deployment is consistently underestimated. — [DevStarsJ architecture patterns post](https://devstarsj.github.io/ai/architecture/2026/03/14/multi-agent-ai-architecture-patterns-2026)

## Gotchas

- **Splitting before you have observability is a mistake.** You can't tell if a split helped if you can't measure each agent's failure rate, latency, and token consumption independently. Instrument first, split second.
- **AutoGen's emergent coordination is powerful but unpredictable.** Peer-agent conversations can produce creative solutions a supervisor pattern would miss — but they also produce infinite loops, goal abandonment, and non-reproducible outputs. Use for open-ended research, not bounded tasks.
- **Context passing between agents is a cost hotspot.** Every agent boundary re-injects context into the next LLM call. Design minimal handoff schemas — pass structured data, not full conversation history.
- **Model selection per agent matters more than you think.** A small fast model (Gemini 2.0 Flash at 31K tokens/task) handles research steps at 1/3 the cost of GPT-4o (43K tokens/task). Route accordingly rather than using one model for the whole pipeline.
