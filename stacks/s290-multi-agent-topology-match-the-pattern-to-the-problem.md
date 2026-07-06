# S-290 · Multi-Agent Topology: Match the Pattern to the Problem Before It Bankrupts You

Multi-agent systems have crossed the chasm — 72% of enterprise AI projects run them in production (up from 23% in 2024), and 57% of organizations report live agents. But 65% of teams hit a wall within 12 months and face rewrites. The single biggest cause: picking the wrong coordination topology for the problem type.

## Forces

- **Coordination overhead scales non-linearly.** Peer-to-peer works fine for 3-4 agents. At 8+ it collapses into an exponential number of bilateral relationships. Most teams prototype peer-to-peer, get burned at production scale, and have to retrofit a hierarchy.
- **Pattern choice is an irreversible architectural bet.** You can swap your LLM provider in an afternoon. Changing your coordination topology means rewriting agent responsibilities, message schemas, and state management.
- **Multi-agent token consumption runs ~15x higher than single-agent interactions.** The cost profile isn't obvious until you've already committed to a pattern.
- **GitHub adoption signals production readiness, not correctness.** LangGraph's 90K+ stars don't tell you which pattern fits your use case.

## The Move

Map your problem type to one of three canonical topologies. Treat these as mutually exclusive for a given subsystem — mixing them creates invisible coordination debt.

### 1. Supervisor/Worker (Hierarchical) — Pick this when:
- Tasks are decomposable and the decomposition is predictable
- You need auditability: who did what, when, with what context
- Cost control matters: a single dispatcher routes to workers, minimizing cross-agent chatter

The supervisor owns the top-level plan and delegates sub-tasks to specialists. Workers report back; the supervisor synthesizes. This is the Opensoul marketing agency model — a Director agent coordinates Strategist, Creative, Producer, Growth Marketer, and Analyst. Each has a defined role; the Director handles routing and quality gates.

### 2. Peer-to-Peer — Pick this when:
- Agents have overlapping capabilities and context-dependent expertise
- The system needs to be resilient to individual agent failure
- You're building an open ecosystem where agents join dynamically (e.g., agent marketplaces)

Every agent can invoke any other agent directly. No central dispatcher. Coordination emerges from message-passing. The tradeoff: you lose centralized observability. Every agent boundary is a potential silent failure point. This pattern is where teams get burned.

### 3. Marketplace — Pick this when:
- Task types are highly heterogeneous and unknown at design time
- You want agents to compete or bid on tasks (quality optimization)
- Dynamic capability matching matters more than predictable routing

Agents register capabilities; a broker matches incoming tasks to the best-fit agent. This is the least common in production but appears in research stacks and enterprise knowledge management systems where query types are unpredictable.

### The 2026 Production Consensus

LangGraph is the default framework choice for serious production multi-agent systems. Teams that start with CrewAI for prototyping routinely migrate within 6-12 months when they hit its ceiling. LangGraph's explicit state machine approach maps naturally to all three topologies.

Tier your models: use Sonnet 4 or GPT-4o for coordination agents (high reasoning quality, lower volume) and Haiku or GPT-4o-mini for task agents (high volume, lower per-call cost).

## Evidence

- **HN Show HN:** Opensoul — 6-agent marketing agency stack using Paperclip orchestration, with Director/Strategist/Creative/Producer/Growth Marketer/Analyst roles running on scheduled heartbeats, delegating work autonomously — [https://news.ycombinator.com/item?id=47336615](https://news.ycombinator.com/item?id=47336615)
- **RockB Multi-Agent Design Guide (2026):** 1,445% surge in multi-agent inquiries (Q1 2024 → Q2 2025 per Gartner); multi-agent token consumption ~15x higher than single-agent; explicit decision tree for choosing Supervisor/Worker vs Peer vs Marketplace; coordination overhead scales non-linearly in peer patterns — [https://baeseokjae.github.io/posts/multi-agent-system-design-guide-2026](https://baeseokjae.github.io/posts/multi-agent-system-design-guide-2026)
- **arXiv Taxonomy of Hierarchical Multi-Agent Systems:** 5-axis taxonomy (control hierarchy, information flow, role delegation, temporal layering, communication structure) with concrete tradeoffs per axis; $12.2B in multi-agent funding through Q1 2024 — [https://arxiv.org/html/2508.12683v1](https://arxiv.org/html/2508.12683v1)
- **Gheware DevOps Blog (2026 comparison):** 65% of teams hit a wall within 12 months and rewrite; LangGraph recommended as default over CrewAI for production due to ceiling; 80% of Fortune 500 exploring AI agents — [https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **LangChain State of AI Agents Survey 2026:** 57.3% of organizations report agents in production; 72% of enterprise AI projects use multi-agent architectures; 171% average ROI reported — cited in RockB guide

## Gotchas

- **Starting peer-to-peer because it feels "simpler" is a prototype trap.** At 3 agents it is simpler. At 8 agents you've built a debugging nightmare with no central point to instrument.
- **Don't skip the checkpointing strategy.** When a multi-agent workflow runs for hours and an agent crashes at step 7, you need to resume from a known state — not replay from scratch at $50K/token.
- **The 15x token multiplier means your single-agent cost model is useless.** Budget multi-agent at 15-20x the per-task cost of the equivalent single-agent workflow.
- **"We can always refactor the topology later" is usually false.** Agent responsibilities, message contracts, and shared state become tightly coupled. Topology changes at month 6 typically require a full rewrite of agent logic.
- **LangGraph's flexibility is also its hazard.** Its low opinionation means teams make bad topology decisions because the framework doesn't guide them toward a sensible default. Invest time in the architecture doc before writing the first node.
