# S-580 · Multi-Agent Patterns — The 4 Orchestration Topologies That Survive Production

Splitting one agent into many doesn't automatically make a system smarter. It trades one class of problems for another — context overflow for coordination overhead, serial bottlenecks for untyped handoff failures. The teams that get multi-agent right aren't the ones who split the most. They're the ones who chose the right topology for the coordination problem they actually have.

## Forces

- **Splitting improves specialization but adds serialization.** Every agent boundary is a serialization point. A 6-agent pipeline where each step adds 2s latency costs 12s end-to-end regardless of parallelism.
- **More agents means more handoff failure modes.** Each agent-to-agent boundary is a potential point of untyped data corruption, missing context, and silent failures that only surface in production.
- **The "dump everything in one agent" ceiling is real, but so is the "assume more agents = better" ceiling.** Performance degrades past ~12 tools or ~5 sequential steps in a single agent. But 4 specialized agents with poor topology selection can underperform 1 well-prompted agent.
- **Orchestration topology matters more than model choice in multi-agent systems.** AdaptOrch (2026) showed topology selection delivers 12–23% gains on SWE-bench independent of model size — a finding most teams discover empirically after burning through model comparisons.

## The Move

Map your coordination problem to one of four topologies. Don't pick the fancier one.

**1. Hierarchical** — A director/orchestrator agent decomposes tasks and delegates to specialist agents. Best when: a single root task branches into independent subtasks. The orchestrator owns "what gets done and in what order." Example: Opensoul's marketing stack (Director → Strategist, Creative, Producer, Growth Marketer, Analyst).

**2. Pipeline** — Tasks flow through a fixed sequence of agents, each transforming output. Best when: order matters and each stage is a discrete transformation. Example: content pipeline (researcher → writer → editor → publisher). Latency = sum of all stages — add concurrency only where stages are genuinely independent.

**3. Orchestrator-Worker** — A central agent dynamically decides which workers to invoke and how many in parallel, based on the task. Best when: task shape varies at runtime and you can't predefine the sequence. Workers are stateless transforms; the orchestrator holds the plan.

**4. Peer-to-Peer** — Agents communicate directly without a central coordinator, negotiating roles and resolving conflicts among themselves. Best when: agents have equal authority and the problem requires negotiation (e.g., conflicting constraints). Hardest to debug. RaftLabs reports this is the least common in production for that reason.

**Practical rule:** Split by responsibility boundary, not by step count. If two agents need the same system prompt and access to the same tools, they probably shouldn't be separate agents. If two agents own different failure domains, they should be separate.

**Design handoff contracts explicitly.** The #1 killer of multi-agent systems in production is untyped handoffs — Agent A passes Agent B a dict with a key that B renamed, or a list B expects as a string. Define the schema at every handoff boundary. CrewAI's Flow-first approach (2025 docs) explicitly calls this out: wrap agent teams in a Flow to enforce typed state transitions between steps.

## Evidence

- **Benchmark:** Google internal experiments found distributed multi-agent processing cut task time from 1 hour to 10 minutes (6×) by replacing a monolithic agent with topology-aware distribution — [HN discussion on agent stack stratification](https://news.ycombinator.com/item?id=47114201)
- **Research:** AdaptOrch (2026) showed orchestration topology delivers 12–23% independent gains on SWE-bench, concluding "topology matters more than model choice" — [MACGPU 2026 Multi-Agent Production Guide](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html)
- **Industry data:** 1,445% surge in multi-agent system inquiries (Gartner, Q1 2024 → Q2 2025); 57% of organizations already have agents in production — [RaftLabs Multi-Agent Systems Guide, Nov 2025](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Case study:** Opensoul ships 6 agents (Director/Strategist/Creative/Producer/Growth Marketer/Analyst) as a pre-configured marketing agency stack on Paperclip orchestration — [Show HN, mid-2025](https://news.ycombinator.com/item?id=47336615)

## Gotchas

- **Five steps at 95% accuracy each = 77% end-to-end accuracy.** Each agent boundary is a multiplication of failure probability. The eval framework must measure end-to-end outcome, not per-agent quality.
- **89% of teams have observability; only 52% have evals.** You can see that your agents are running. You can't easily prove they're doing the right thing. Amazon's evaluation framework (2025) specifically calls out that multi-agent HITL (human-in-the-loop) evaluation is essential for catching inter-agent coordination failures that automated metrics miss — [AWS ML Blog, Evaluating AI Agents](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Inference costs compound: $5–8 per complex task for a 4-agent orchestrator-worker workflow** (RaftLabs). Before splitting, confirm the task value justifies the per-run cost. Multi-agent isn't free parallelism — each agent call is a separate token budget.
- **CrewAI's Flow-first recommendation is load-bearing.** Their 2025 production docs explicitly advise wrapping agent crews in Flow objects for state management and typed handoffs. Skipping this is the most common production mistake teams make when migrating from prototype to ship — [CrewAI Production Architecture Docs](https://docs.crewai.com/v1.15.0/en/concepts/production-architecture)
