# S-512 · Multi-Agent Boundaries: When to Split and How to Coordinate

The most common mistake in multi-agent design is splitting by workflow step — "one agent for planning, one for execution, one for review." This produces chatty, brittle systems where agents pass work back and forth constantly. The evidence from production deployments points to a different principle: split agents by *boundary conditions*, not steps.

## Forces

- **Context window pressure vs. coordination overhead.** Single agents hit ceiling fast on complex tasks, but every new agent introduces communication latency, shared-state complexity, and failure surface. The tradeoff is non-linear — splitting wrong can make things worse.
- **Trust and conflict boundaries.** An agent that generates content and grades it has a conflict of interest that degrades evaluation quality. The fix is structural, not prompting.
- **Latency mismatches.** Real-time user-facing responses and background batch processing cannot share an agent without one degrading the other. Timing is a legitimate boundary.
- **Specialization vs. generality.** A generalist agent is cheaper to run but burns more tokens per task. A specialist agent is cheaper per task but adds orchestration overhead. The math changes with task complexity.

## The Move

Draw agent boundaries by *where concerns conflict*, not where work flows. Then choose a coordination model that fits the boundary type.

**1. Split on conflict, not step.** If two agents would have a conflict of interest operating on the same context, split them — even if they do the same kind of work. A coding assistant and a security assessor cannot share context without bias. (Source: FRE|Nxt Labs production guide, April 2026)

**2. Split on latency.** Agents with sub-second requirements (user-facing) and agents with multi-minute requirements (batch processing) must be separate pods, separate queues. Merging them introduces queue priority inversion.

**3. Coordination model follows boundary type:**
- **Supervisor/hierarchy:** Best when one agent owns the outcome and others are specialized tools. The supervisor decomposes, delegates, synthesizes. Use when the top-level decision (what to build, what to approve) is the hard part.
- **Peer/swarm:** Best when multiple agents of equal authority must converge on a shared output. Use for research + writing + review where no single agent is the "boss."
- **Pipeline:** Best for strict sequential transforms where output of one feeds directly into the next. Use for ETL-like flows; avoid for anything requiring iteration or backtracking.

**4. Start with one agent.** The frenxt.com research states it plainly: "Start with one agent and add more only when a genuine boundary appears, because complexity is not free." A well-scoped single agent with good prompting and tools beats a poorly coordinated team of specialists.

**5. Use typed shared state with checkpointing.** Every coordination model needs a shared schema — not raw LLM output passed between agents. Define the contract: what does the research agent return to the writer? Checkpoint on every handoff so failures are recoverable.

**6. Enforce explicit error handling.** Every agent-to-agent call needs retries, fallbacks, and timeouts. When the researcher agent times out, does the writer agent proceed with partial data or escalate? Make this explicit before shipping.

## Evidence

- **Production case study — GenBrain AI (11 agents on GKE):** CTO of GenBrain describes running 11 agents as a production organization since February 2026. Agents include CEO (task decomposition), CTO (architecture/code review), CSO (security), Backend, Frontend, Marketing, DevOps. Coordination uses a supervisor model at the top (CEO) with peer agents below. Each pod has a primary subject namespace. They report that single-agent systems "hit their ceiling fast — one agent's context window cannot hold an entire codebase, all domain knowledge, and the reasoning chains for complex tasks simultaneously." — [agent.ceo/blog](https://agent.ceo/blog/multi-agent-architecture-patterns) (March 2026)

- **Enterprise reference architecture — The Agent Report:** "A production multi-agent system needs four foundations: agent boundaries drawn by audience, timing, or trust (not by workflow step), typed and scoped shared state with checkpointing, explicit error handling with retries, fallbacks, and timeouts, and full-trace observability." Enterprises adopting multi-agent systems cite compliance isolation (healthcare, finance) and conflict of interest separation as the primary drivers. — [the-agent-report.com](https://the-agent-report.com/2025/04/enterprise-agent-stack-architecture/) (April 2025)

- **Benchmark — Multi-agent cost advantage on complex tasks:** Ivern AI's 200-task benchmark across 6 providers found that multi-agent workflows were 40–60% cheaper than single-agent for complex tasks (research + writing + review), because each specialized agent uses fewer tokens than a generalist agent doing everything. For simple tasks, single-agent was cheaper — the overhead of coordination exceeded the savings. — [ivern.ai](https://ivern.ai/blog/ai-agent-cost-benchmark-report-2026) (April 2026, updated July 2026)

- **Sandbox layer convergence:** Between October 2025 and April 2026, every major cloud provider shipped production-grade agent sandboxing: AWS Bedrock AgentCore (microVM-per-session), Google GKE Agent Sandbox (gVisor-based), Microsoft Foundry Hosted Agents (per-session hypervisor), Vercel Sandboxes (GA January 2026), Cloudflare Sandboxes (GA April 2026). "The substrate layer for AI agents transitioned from a specialist startup category to a default cloud feature in roughly the time it takes a typical enterprise procurement cycle." — [agihouse.org](https://blog.agihouse.org/posts/agent-sandboxes) (2026)

## Gotchas

- **Splitting by workflow step is the wrong heuristic.** "One agent for planning, one for execution, one for review" creates chatty interdependencies. Plan what the system needs to *know differently* and *trust differently*, not where the work changes hands.
- **Peer models need explicit arbitration.** In a swarm where no agent is in charge, you need a defined mechanism for resolving conflicts — a voting agent, a tie-breaking rule, or a human-in-the-loop checkpoint. Without it, peer models deadlock or produce inconsistent outputs.
- **Sandbox isolation has cost implications.** Per-session microVMs (AWS, Google, Microsoft) enable strong isolation but add cold-start latency and per-session pricing. For high-volume, low-risk tasks, shared-container sandboxes (Modal, E2B) are cheaper. Match isolation level to trust level, not to the worst-case scenario.
- **Multi-agent debugging requires full trace observability.** When a task fails across 4 agents, you need to know which agent produced the bad input, not just that the final output was wrong. LangSmith traces, Phoenix, or equivalent are not optional at this scale.
