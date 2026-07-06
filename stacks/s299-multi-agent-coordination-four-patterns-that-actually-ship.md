# S-299 · Multi-Agent Coordination: Four Patterns That Actually Ship

Most teams add a second agent because "one agent isn't enough." Then they discover that two agents without a coordination strategy costs 2–5x more in tokens for the same work, and debugging a broken handoff is harder than debugging either agent alone. The question isn't how many agents to run — it's which coordination pattern matches the actual shape of the work.

## Forces

- **Multi-agent costs compound before it pays.** A complex orchestrator-worker task runs $5–8 per invocation in inference costs. Before splitting work, the quality gain must justify the cost and latency hit — and for most bounded tasks, it doesn't.
- **Coordination patterns aren't interchangeable.** Supervisor, peer/handoff, market, and shared-state each impose different debugging surfaces, latency profiles, and failure modes. Picking the wrong one creates invisible coupling that shows up at 2 a.m.
- **The default should be single-agent.** Multi-agent earns its place only when genuine boundaries exist — different access controls, different tools, different models, or different expertise domains. The intuition that "more agents do better" is wrong more often than right.
- **Tracing exists; evals don't.** 89% of teams have agent tracing, but only 52% have evals. The coordination pattern determines how debuggable a failure is — and supervisor patterns win here because the supervisor's trace shows the full decision path.

## The move

Match the coordination pattern to the actual shape of work, not the team size. Four patterns cover most production cases:

- **Supervisor (controller delegates):** A single orchestrator decides which sub-agents to call and in what order. Best when task decomposition is deterministic — you always need the same steps, just with different data. Easiest to trace and debug. Weakest on parallelism.
- **Peer (handoff):** Agents hand off to each other by stage. Natural fit for funnel-style work — lead-qualify → nurture → close → onboard. Each agent owns its stage. Clean separation, poor when stages need to share context mid-handoff.
- **Market (bidding):** Each agent bids on tasks based on its capabilities and load. Best for task-distribution at scale with heterogeneous workers — a roster of specialists where you don't want a single point of bottleneck. Most complex to implement; highest overhead.
- **Shared-state (workspace):** Agents read and write to a shared context/workspace. Best for collaborative generation tasks — multiple specialists refining a shared artifact. Requires the most careful conflict-resolution logic.

Token budgets per role are a practical tool: assign a fixed compute budget (e.g., Planner 30%, Retriever 20%, Validator 15%, Synthesizer 35%) to prevent any single agent from blowing the cost budget on a single query.

## Evidence

- **Practitioner blog (Gravity Fast):** Four patterns — supervisor, peer, market, shared-state — cover production needs. "Supervisor is easiest to debug because the supervisor's trace shows the full decision path." "Multi-agent costs 2–5x more in tokens for the same work. Worth it when specialization measurably improves quality." — [gravity.fast/blog/ai-agent-multi-agent-coordination](https://gravity.fast/blog/ai-agent-multi-agent-coordination)
- **Industry analysis (RaftLabs, 100+ AI products shipped):** Gartner tracked 1,445% surge in multi-agent inquiries Q1 2024 → Q2 2025. 57% of organizations have agents in production. 89% have tracing; only 52% have evals. Inference costs compound to $5–8 per complex task in orchestrator-worker workflows. — [raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **HN Show (Opensoul/Paperclip):** 6-agent marketing agency pattern — Director (strategy + coordination), Strategist (research), Creative (copy + brand), Producer (editorial calendar), Growth Marketer (SEO + acquisition), Analyst (attribution). Agents run autonomously on scheduled heartbeats, check work queues, delegate to teammates. — [news.ycombinator.com/item?id=47336615](https://news.ycombinator.com/item?id=47336615)
- **AWS AI blog (Amazon):** Multi-agent evaluation requires HITL because of "increased complexity and potential for unexpected emergent behaviors that automated metrics might fail to capture." Specifically: inter-agent communication, agent specialization alignment, conflict resolution, and logical consistency across agents. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)

## Gotchas

- **Adding agents without a coordination pattern is adding chaos.** Without explicit handoff rules, agents share context through implicit prompts, creating invisible dependencies that break in production.
- **Market pattern sounds elegant, adds latency.** Bidding rounds require each agent to evaluate a task before anyone starts working. For time-sensitive workflows, the overhead outweighs the load-balancing benefit.
- **Role-specialized agents drift out of role.** Without explicit system prompts reinforced per-invocation, a "Creative" agent starts answering strategy questions because it saw context from the Strategist. Freeze role boundaries in code, not just in documentation.
