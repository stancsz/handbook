# S-575 · Multi-Agent Is Not Multiplied Intelligence: When Agents Work in Parallel, They Divide It

The instinct is to throw more agents at a hard problem. A planner agent, a researcher agent, a writer agent, a reviewer agent — each doing its thing in parallel. The math feels obvious: four agents working simultaneously should solve problems four times faster. Instead, they solve them worse. Research published in 2025 and corroborated across HN production threads shows that independent multi-agent parallel execution amplifies errors by up to 17.2x, while the same budget of reasoning tokens fragmented across coordination messages produces shallower solutions than a single agent would. The move is to default to one agent with clear tool access, and split only when you have a documented, measured reason.

## Forces

- **Parallelism feels like leverage.** The web's developer mental model comes from map-reduce and worker queues — independent tasks, no shared state, linear scaling. Agents don't follow this. Every additional agent adds coordination overhead and shares a fixed reasoning-token budget.
- **Independent agents amplify noise, not signal.** When agents work on the same problem without communicating, each one generates a slightly different wrong answer. Those errors compound rather than cancel, because LLMs don't vote toward truth — they vote toward the most plausible sounding consensus.
- **The token budget is zero-sum.** A fixed reasoning budget split across N agents means each one gets 1/N of the deep, recursive reasoning a single agent would apply. Sequential reasoning tasks degrade 39–70% with multi-agent variants versus the same budget applied by one agent.
- **Coordination latency is real.** Each handoff between agents is a full LLM round-trip. A 5-step workflow across 5 agents isn't 5x faster than 5 sequential steps by one agent — it's potentially slower, with added state-transfer risk at every boundary.

## The Move

**Default to one agent. Split only on evidence.**

- **Start with a single agent and a well-defined toolset.** One agent with access to search, code execution, file operations, and a retrieval system handles the vast majority of complex tasks better than a team of specialists.
- **Split on a measured bottleneck, not a theoretical one.** If the single agent consistently produces shallow output on step 3 of a 10-step process, that's a reason to extract a specialist for step 3 — not to redesign the whole workflow as a crew.
- **Use hierarchical coordination, not peer-to-peer.** A single orchestrator dispatching to specialist nodes keeps token budgets consolidated at the decision point. Peer-to-peer communication without a coordinator is what produces the 17.2x error amplification.
- **Count coordination messages against your reasoning budget.** Every inter-agent handoff is a token cost. Model it explicitly: if you have a 4,800-token budget, two agents talking three times means 1,200 tokens of that budget consumed by coordination, not reasoning.
- **Set hard task-type gates.** Multi-agent shines for inherently parallelizable work (multi-source research, simultaneous document analysis) and for role-based quality gates (a writer and a compliance reviewer checking each other's output). It reliably fails for sequential reasoning, tight-coupled planning, and anything requiring a single coherent world model.

## Evidence

- **Research paper (2025):** Independent multi-agent systems (parallel agents, no communication) amplify errors by 17.2x. Token-budget-matched configurations show SAS outperforms MAS by 39–70% on sequential reasoning tasks. Centralized/hybrid coordination yields 8% better performance than SAS alone. — ["Towards a science of scaling agent systems"](https://news.ycombinator.com/item?id=46847958) on Hacker News citing the original paper
- **HN production thread (2025):** A solo developer building a SaaS product with Claude Code as an "engineering team" iterated through multiple multi-agent architectures. Their documented "CEO incident" — where a high-authority agent spawned 20 sub-roles that immediately began writing memos to each other instead of working — led to a strict three-role hierarchy (Architect, Builder, Reviewer) with Markdown-mediated coordination instead of direct inter-agent communication. Result: 24 interactive pages, 60+ API endpoints, 311 database migrations, Kubernetes deployment — all with 3 roles, not 20. — [Hacker News](https://news.ycombinator.com/item?id=47245373)
- **Framework comparison (2026):** LangGraph benchmarks show graph-based orchestration with a single coordinator node handles 5-revision workflows with 40% lower p95 latency than peer-to-peer crew architectures, because checkpoint serialization between 2 nodes costs less than coordination messages between 5. — [Tacavar](https://tacavar.com/blog/ai-agent-frameworks-compared-2026/), April 2026

## Gotchas

- **CrewAI and AutoGen make peer-to-peer easy.** Their abstractions are elegant, but elegant abstractions hide the coordination cost. A 6-agent crew in CrewAI with parallel task execution can look like a clean architecture diagram and perform 4x worse than a single-agent graph with conditional edges.
- **The demo looks great.** Two researchers pulling from different sources simultaneously, synthesizing results — it works beautifully in demos with clean inputs. Real data is messier, sources conflict, and the merge logic is your least-tested code.
- **Adding an agent is reversible. The coordination overhead is not.** It's easy to add a new agent role. It's hard to remove it once three other agents have been written to depend on its output format.
