# S-448 · Orchestration Framework Selection: The Three Architectures

You need to build a multi-agent system and every guide tells you to "pick the right framework" without telling you what that actually means. LangGraph, CrewAI, and Microsoft Agent Framework (ex-AutoGen) represent three fundamentally different mental models for the same problem — choosing one because it has the most GitHub stars is how teams end up six months deep with a system they can't debug, extend, or cost-control.

## Forces

- **The mental model mismatch is the real trap.** Each framework embeds a specific philosophy about agent coordination. LangGraph gives you a flowchart you execute. CrewAI gives you a team you manage. Microsoft Agent Framework puts agents in a room and lets them figure it out. These aren't feature differences — they determine what is easy, what is hard, and what is impossible in your system
- **AutoGen is in maintenance mode — and it matters.** Microsoft formally transitioned AutoGen to legacy in October 2025, steering new users to Microsoft Agent Framework 1.0 GA (announced April 3, 2026). Teams that built on AutoGen v0.2 are now on an island
- **CrewAI's ergonomics seduce teams past their complexity threshold.** The role/task abstraction is fast to start with, but custom control flows (anything outside sequential/hierarchical) require fighting the framework's opinions rather than working with them
- **LangGraph is the safest long-term bet for production — but it's not free.** You get precise control over state, branching, and recovery, but you build your own abstractions on top of the primitives. Teams that treat the graph API as the solution rather than the building block end up with over-engineered graphs

## The move

Match the framework to the coordination pattern, not the community size.

**Choose LangGraph when:**
- You need production-grade durability: checkpointing, interrupt-and-resume, human-in-the-loop approval gates
- You need to model cyclical or conditional state (loops, retry branches, conditional routing)
- You're in a regulated industry needing audit logs and rollback points
- Your team has the engineering bandwidth to build abstractions on top of graph primitives

**Choose CrewAI when:**
- Your workflow fits the sequential or hierarchical process pattern (research → write → edit, or supervisor → specialists)
- Speed of initial delivery matters more than flexibility at the edges
- You're building content pipelines, support automation, or marketing workflows with stable agent roles
- You want a managed platform path (CrewAI launched their cloud in 2025)

**Choose Microsoft Agent Framework when:**
- Your use case is fundamentally multi-party: agents debating, reviewing each other's work, reaching consensus
- You're in a Microsoft-heavy environment (.NET stack, Azure, Semantic Kernel already in use)
- You need the most diverse conversation patterns for modeling complex organizational workflows

**The decision tree in one line:** If your agents need to have conversations with each other, Microsoft Agent Framework. If your agents need to follow a predictable workflow with clear handoffs, CrewAI. If your agents need to survive production failures with stateful recovery, LangGraph.

## Evidence

- **Benchmark data:** CrewAI delivered 38% lower p95 latency than AutoGen for typical enterprise workflows, and hierarchical/sequential task pipelines reduced production failures by 40% compared to AutoGen's conversational model — [Markaicode production framework comparison, June 2026](https://markaicode.com/best/best-agent-framework-production-multi-agent)
- **Enterprise adoption signal:** LangGraph has 90M monthly downloads with production deployments at Uber, JP Morgan, BlackRock, Cisco, LinkedIn, and Klarna; 57% of organizations now have AI agents in production with quality (not cost) as the primary deployment barrier — [Alphabold LangGraph production analysis](https://www.alphabold.com/langgraph-agents-in-production)
- **Production deployment pain:** "If you've built something with CrewAI, LangGraph, or similar frameworks, you know the drill: it works great locally, then you spend days figuring out infrastructure, scaling, monitoring, and artifact management just to get it running for real users" — [Show HN: Crewship, HN discussion](https://news.ycombinator.com/item?id=47180745)
- **Stack stratification:** The agent stack is splitting into specialized layers — sandboxing (Modal, E2B, Firecracker), orchestration, memory, and observability each becoming distinct disciplines rather than features of a monolithic framework — [HN comment on Show HN: Local-First Linux MicroVMs, 2025](https://news.ycombinator.com/item?id=47114201)
- **Multi-agent lessons:** "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count. In 2023 demos looked great. In 2024 production deployments mostly looked cursed. In 2025–2026 a handful of patterns emerged that actually work — and a lot of patterns that don't" — [TURION.AI multi-agent orchestration field notes, March 2026](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Framework comparison:** LangGraph = "I build the flowchart, the framework executes it"; CrewAI = "I hire a team, assign tasks, they figure out the rest"; Microsoft Agent Framework = "I put agents in a room, let them talk until solved" — [TURION.AI LangGraph vs CrewAI vs AutoGen comparison, May 2026](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)

## Gotchas

- **AutoGen maintenance mode is a real risk for new projects.** Microsoft Agent Framework 1.0 GA (Python, .NET) is the successor. If you're starting greenfield enterprise work, pick a different framework or be prepared to migrate within 12 months
- **CrewAI's role/task abstraction hits a wall past 2-3 agents.** Beyond that, fan-out patterns and custom handoff logic require working against the framework rather than with it. If you know you'll need complex coordination, start with LangGraph even if it takes longer
- **LangGraph gives you primitives, not solutions.** Teams that build the entire workflow as a single monolithic graph lose the debuggability benefit. Break large graphs into subgraphs with explicit interfaces — the graph structure should mirror your team's understanding of the system
- **Orchestration framework choice locks downstream decisions.** Memory stores (checkpointing backends), observability tooling (tracing integration), and sandboxing layer (how tools execute) all depend on your orchestration substrate. Pick first, then choose compatible tools for the other layers
- **Cost predictability requires explicit design in all three frameworks.** Multi-agent fan-out multiplies LLM calls (5-10x if unmonitored per Data-Gate production lessons). Define cost budgets per agent, use circuit breakers, and route routine tasks to smaller models
