# S-456 · Multi-Agent Orchestration Patterns

Single agents hit a ceiling. After you have engineered context, tuned tools, and built guardrails for one agent, the next class of problems demands multiple agents working in concert. But splitting work across agents introduces coordination costs, typed-handoff failures, and inference bills that compound fast. The question isn't whether to go multi-agent — it's which coordination pattern fits your workflow shape, and when the decomposition actually pays.

## Forces

- **Single-agent context overload degrades performance.** As a single agent accumulates tools, history, and responsibilities, its effective context window shrinks. Verbose system prompts (up to 8,000 tokens of fixed overhead per call) get billed on every invocation even when irrelevant to the current step.
- **Inference costs compound non-linearly in multi-agent systems.** Multi-agent pipelines that pass full conversation histories rather than structured summaries grow exponentially in token volume. Complex multi-agent tasks run $5–8 per task at production scale, versus cents for a simple single-agent query.
- **Typed schema failures are the #1 multi-agent killer.** When agents hand off outputs to each other, an untyped or loosely-specified schema breaks the workflow silently — downstream agents receive malformed data, the pipeline crashes, or worse, it continues with garbage.
- **Observability lags behind deployment.** 89% of organizations have tracing capability, but only 52% have evals running. Multi-agent failures are subtle: an agent hallucinates a tool call, a state update gets dropped, a loop runs indefinitely. Flying blind is the default state.
- **Not every problem needs multiple agents.** Andrew Ng's result — agentic workflows with GPT-3.5 jumping from 48% to 95.1% on HumanEval — came from workflow decomposition, not model upgrades. But decomposition overhead is real and the threshold for benefit is task-specific.

## The move

**Map your workflow shape to one of four orchestration patterns, and only decompose when the shape demands it.**

- **Hierarchical (director → workers):** A planning or routing agent delegates sub-tasks to specialist agents. Best for open-ended, high-variance tasks where a coordinator needs to assess and assign. The director holds the global state; workers handle isolated sub-problems. Opensoul's marketing stack (Director → Strategist → Creative → Producer → Growth Marketer → Analyst) follows this shape — each agent has a defined role but the Director orchestrates goals and handoffs.
- **Pipeline (sequential stages):** Output of agent N becomes input of agent N+1 with no branching. Best for deterministic, linear flows: research → draft → review → publish. Low coordination overhead but no backtracking.
- **Orchestrator-worker (router → dynamic workers):** A central agent dynamically decides which workers to invoke and in what order based on the current state. Best when the set of required sub-tasks isn't known upfront. Most flexible but hardest to debug.
- **Peer-to-peer (agents share state, no central coordinator):** Agents communicate via a shared blackboard or message bus. Best for parallel independent tasks that need to converge — multiple research agents covering different sources, then a synthesis step.

**Practical decomposition triggers:**
- Task requires 3+ fundamentally different tool sets
- Sub-tasks have independent failure modes you want to isolate
- Different latency/cost SLAs for different parts of the workflow
- Separate teams own different parts of the domain knowledge

**Typed handoffs are non-negotiable.** Define Pydantic or JSON Schema for every inter-agent message before writing any agent logic. This is the contract layer. Untyped handoffs kill workflows faster than bad prompts.

**Measure orchestration overhead before committing.** A two-agent pipeline that saves 30% on token cost per agent but adds 2× the API calls and 40ms of latency may not be a win. Profile the full pipeline cost including retries.

## Evidence

- **Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025, with 57.3% of organizations already running agents in production.** The four-pattern framework (hierarchical, pipeline, orchestrator-worker, peer-to-peer) covers most production use cases. — [RaftLabs: Multi-Agent Systems Guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **LangGraph's 12,000 GitHub stars represent overwhelmingly production deployments, while AutoGen's 40,000+ stars are largely from academic researchers and hobbyists from 2023–2024.** For Fortune 500 production, LangGraph's graph-based state machine provides auditability that AutoGen's message-passing model lacks for regulated industries. CrewAI excels at fastest prototyping for role-based pipelines. — [Gheware: LangGraph vs AutoGen vs CrewAI Enterprise Comparison 2026](https://devops.gheware.com/blog/posts/langgraph-vs-autogen-vs-crewai-comparison-2026.html)
- **Four categories consistently shipped from pilot to production in 2025: developer tooling (tight feedback loops), internal operations (clear success criteria, low blast radius), research and analysis (high information volume), and customer-facing assistants (narrow domain scope).** Open-ended autonomy failed in regulated environments; deterministic guardrails and narrow scope succeeded. — [Technspire: State of Agentic AI End-2025](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)
- **Hard cost guardrails must be in place before launch.** Agents can burn through five-figure budgets over a weekend via runaway loops or retry storms. Human-in-the-loop for high-stakes decisions must be a permanent architectural feature, not a temporary safety net. — [Gennoor: Agentic AI in Production — 5 Hard-Won Lessons](https://gennoor.com/resources/blog/agentic-ai-production-lessons)
- **Agentic RAG with self-correcting retrieval outperforms static RAG on complex queries.** Embedding autonomous agents into the retrieval pipeline that plan, reason, and dynamically adapt retrieval strategies outperforms identical retrieve-and-generate paths. — [aliac.eu: Agentic RAG in Production](https://aliac.eu/blog/agentic-rag-in-production)

## Gotchas

- **Measuring framework maturity by GitHub stars.** AutoGen has more stars than LangGraph but LangGraph's community is disproportionately production-grade. Stars measure interest; production deployments measure readiness.
- **Passing full conversation histories between agents.** The most common anti-pattern — the reasoning agent doesn't need what the retrieval agent did, it needs structured outputs. Without explicit context discipline, multi-agent costs grow exponentially as you add agents.
- **Ignoring observability until production breaks.** LangSmith, Arize Phoenix, or Langfuse (open-source, self-hostable) must be day-one decisions. Multi-agent failures are subtle and non-obvious without tracing.
- **Building a prototype in CrewAI and assuming it survives a production rewrite.** CrewAI's role-based team model is excellent for getting to demo quickly, but its production state management is less mature than LangGraph's graph-based approach for complex branching logic.
- **Using the same framework for every use case.** The smartest enterprises use multiple frameworks: LangGraph for regulated/stateful workflows, CrewAI for rapid prototyping, AutoGen for Azure-native code generation, and custom state machines for latency-critical paths.
