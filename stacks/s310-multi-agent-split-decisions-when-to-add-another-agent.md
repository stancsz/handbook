# S-310 · Multi-Agent Split Decisions: When to Add Another Agent

When your agent starts failing, the reflex is to add another agent. Sometimes it helps. Often it multiplies the failure surface without solving the root cause. The real skill is distinguishing between a role-boundary problem that needs a new agent and a tool-design problem that needs better tooling.

## Forces

- **One agent with many tools gets coordination-right but loses focus.** A single agent juggling 30 tools can route correctly but starts making generic decisions — it doesn't have the specialized context to push a hard query to the right system.
- **Two agents with shared context gets noisy fast.** Now you have coordination overhead, message-passing latency, and alignment drift between two models that may not agree on priorities.
- **The "CEO anti-pattern" creates paralysis.** Giving one agent broad authority and letting it delegate creates a meta-agent that spends more time managing than doing — a common failure reported across multiple HN discussions.
- **Tool complexity and agent count are substitutes, not complements.** Adding agents without removing tools from their predecessors often doubles the surface area without cutting the original problem.

## The move

**Split by epistemic domain, not by task type.** An agent that reasons differently about its inputs belongs in a different agent — not an agent that just does a different task.

- **Add a second agent when:** Tools require fundamentally different retrieval or reasoning contexts (e.g., one agent calls a SQL database, another indexes a document corpus); the two workstreams run on different time horizons (a research agent takes 10 minutes, a notification agent fires in seconds); or the decision-making criteria for one domain would corrupt the other.
- **Keep it one agent when:** The failure is about tool quality (bad schema, missing parameters) rather than tool selection; latency matters and parallel tool calls are the bottleneck; or the "two roles" are actually one role with poor prompting.
- **The coordinator should be dumb.** A Director or Supervisor agent that orchestrates specialized agents should have minimal reasoning — route, collect, merge. Pushing strategy into the coordinator recreates the CEO anti-pattern.
- **Coordinators that do real work lose traceability.** When the supervisor is also a performer, you can't tell if a failure came from routing logic or execution logic. Separate those concerns at the architecture level.
- **Use a shared message bus, not shared state.** Multi-agent systems that share mutable state develop ordering bugs that are nearly impossible to reproduce. An event-driven architecture (even in-process) with immutable message records makes debugging tractable.
- **Start with a sequential pipeline before going concurrent.** A 2-step pipeline (research → write) with clear checkpoints is debuggable. A concurrent swarm where 4 agents fire simultaneously is 10× harder to trace. Graduate to concurrency only after the sequential version is stable.

## Evidence

- **HN Show HN (2025):** A developer building a solo SaaS with Claude Code started with a "CEO agent" given broad authority to delegate. Within hours it had created 20 sub-roles, written detailed regulations for each, and agents started sending memos to each other — the system spent more time managing itself than building. The fix was hard role boundaries with no cross-agent authority, using a shared Markdown log as the only coordination mechanism. — [Multi-agent Claude Code setup (HN)](https://news.ycombinator.com/item?id=47245373)
- **HN Show HN (2025):** Opensoul ships 6 agents (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) where the Director only routes tasks and collects reports — no execution authority. Each agent owns its domain completely. The Director has no visibility into implementation details; it only tracks task status via a work queue. — [Opensoul – Agentic Marketing Stack (HN)](https://news.ycombinator.com/item?id=47336615)
- **Shopify Engineering (2025):** Sidekick's orchestration core separates a "dumb supervisor" (routing) from "domain agents" (execution) across five layers. The supervisor maintains a shared task state; agents read from it and write results back. The human layer sits above everything for approval gates. — [Building Production-Ready Agentic Systems (Shopify Engineering)](https://shopify.engineering/building-production-ready-agentic-systems)

## Gotchas

- **Parallel agents that both write to the same resource create race conditions.** If two agents can both modify the same document, database row, or UI state, you need a mutex or a write-ordering scheme before you deploy to users.
- **Token budgets compound across agents.** A 128K context for a single agent becomes 128K × N agents for N parallel agents. Orchestration overhead (routing messages, merging results) can eat 20–40% of your effective context budget.
- **Adding an agent adds an observability gap.** A failure in a single agent traces to one place. A failure in a 4-agent pipeline requires tracing which agent originated the bad signal, which amplified it, and which failed to catch it.
- **"Role-based" doesn't mean "model-based."** Naming an agent "Researcher" and "Writer" without giving them different system prompts, different tool access, or different retrieval contexts just creates two agents with the same capabilities and twice the failure modes.
