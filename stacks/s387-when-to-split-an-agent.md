# S-387 · When to Split an Agent — Multi-Agent Decomposition Signals

You have a working single-agent system. It handles your use case. Then the requirements grow, and the obvious move is to spawn another agent. But splitting at the wrong boundary — or splitting too early — introduces coordination overhead that kills the system. The real question isn't "should I use multi-agent?" but "what signals tell me I've crossed the threshold where splitting pays off?"

## Forces

- **A monolithic agent with too many tools degrades.** Prompt capacity is finite; an agent managing 15 tools performs worse than two agents managing 7 each with sharper prompts.
- **Coordiation has real cost.** Every agent split requires explicit message passing, shared context negotiation, and failure propagation handling — overhead that a well-scoped single agent avoids entirely.
- **Context window is not a memory architecture.** Loading a conversation into context and calling it "memory" produces agents that repeat themselves, contradict earlier steps, or lose track of what they were doing.
- **The split decision is irreversible in its complexity.** Adding more agents later is easier than untangling an over-architectured multi-agent system.

## The move

Split when at least one of these conditions holds — and wait until at least one does:

- **Domain boundary is clear.** The subtask requires a fundamentally different knowledge domain, toolset, or access controls than the parent. A coding agent and a market research agent share nothing — they belong apart.
- **The subtask can be reused across multiple parent agents.** If two different workflows need the same capability, it deserves its own service-level agent, not an inline copy.
- **Governance diverges.** If the subtask needs different permissions, audit trails, or human-in-the-loop gates than the parent, coupling them creates security leakage.
- **The workflow benefits from parallelization.** Independent subtasks that can run simultaneously — gather X, gather Y, then synthesize — are natural candidates for split agents.
- **A single agent shows degradation signals.** Prompt inflation (the system prompt keeps growing), tool call confusion (wrong tool for the wrong context), or response quality decline as the agent "manages too much."

**The architecture pattern that works:** Use a **supervisor/hierarchical** pattern for most cases — one orchestrator that plans and delegates to specialist agents. Reserve **peer-to-peer** only for fully decentralized, equal-authority workflows where no agent should own the final decision. The Opensoul marketing agent system exemplifies this: a Director agent handles strategy and team coordination while delegating to five specialist agents (Strategist, Creative, Producer, Growth Marketer, Analyst), each running autonomously on scheduled heartbeats, checking their work queue, and delegating to teammates.

**The architectural pattern that rarely works:** Pure peer-to-peer where all agents are equal and negotiate outcomes without a coordinator — coordination overhead explodes, and no agent has accountability for the final output.

## Evidence

- **HN Show-and-Tell:** Opensoul — an open-source agentic marketing stack — runs 6 agents (Director + 5 specialists) on Paperclip orchestration. Each agent operates autonomously on scheduled heartbeats, checking their queue, executing, delegating to teammates, and reporting. The Director acts as the hierarchical supervisor. — [news.ycombinator.com/item?id=47336615](https://news.ycombinator.com/item?id=47336615) + [github.com/iamevandrake/opensoul](https://github.com/iamevandrake/opensoul)
- **Microsoft Copilot Studio guidance:** Separate agents are warranted when the subtask requires different domain expertise, governance rules, or access controls — or when it can be reused across multiple parent agents. Inline agents suffice when none of these conditions apply. — [learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/multi-agent-patterns](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/multi-agent-patterns)
- **TURION.AI multi-agent patterns analysis:** Hierarchical orchestration (central coordinator delegating to specialists) works for most production use cases. Peer-to-peer suits fully decentralized, equal-authority workflows but introduces coordination complexity that makes it rare in practice. — [turion.ai/blog/multi-agent-collaboration-patterns](https://turion.ai/blog/multi-agent-collaboration-patterns)

## Gotchas

- **Splitting too early is the most common mistake.** If a single agent with focused tools and prompts handles the workflow, adding a second agent is overhead with no benefit. Wait for the degradation signals.
- **Cross-agent context passing is non-trivial.** A specialist agent doesn't automatically inherit the parent's conversation history, state, or goals. You need explicit context handoff — summaries, shared memory stores, or a state graph. Without this, the specialist acts stateless and loses continuity.
- **The agent count ceiling is lower than you think.** Six agents (Opensoul) is near the high end for a production system. Most real-world production systems land at 2–4 specialists plus one orchestrator. More than that and coordination costs dominate.
- **Hierarchical doesn't mean waterfall.** The supervisor should make high-level routing decisions, not micromanage every tool call. If your supervisor agent is calling the same three tools in a fixed order, you've re-created a sequential pipeline and lost the parallelism benefit of splitting.
