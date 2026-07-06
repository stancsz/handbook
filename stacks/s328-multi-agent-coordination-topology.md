# S-328 · Multi-Agent Coordination Topology: Hierarchy, Hub-and-Spoke, or Peer

You're splitting one agent into many because it keeps looping, hallucinating mid-workflow, or hitting token limits. But you've seen multi-agent systems that are worse — agents deadlocking, duplicating work, or passing garbage to each other in an infinite loop. The real question is not whether to split, but how to wire the communication topology so coordination overhead doesn't dwarf the gains.

## Forces

- **Splitting agents creates new failure modes.** More agents mean more coordination, more inter-agent context loss, and more opportunities for a task to fall between the cracks. The coordination tax is real and non-linear with agent count.
- **Every topology is a trade-off between control and flexibility.** Hierarchical gives you auditability and clear ownership; peer gives you emergence and adaptability. Hub-and-spoke is simple but fragile at the hub.
- **The right pattern depends on workflow structure, not the number of agents.** Two agents with a known handoff is not the same as six agents discovering tasks through negotiation.
- **Most teams pick the wrong topology from the start.** They default to hierarchical because it mirrors org charts, or peer because it sounds modern — without mapping the pattern to their actual workflow's known vs. unknown decomposition.

## The move

Map your workflow before picking a topology. The split should mirror how your work actually decomposes:

**Use supervisor/hierarchical** when task decomposition is known in advance and control matters:
- A planner agent breaks the request into typed sub-tasks, routes each to a specialist (research, code, review), and synthesizes results
- Best for: bounded workflows, regulated environments, anything requiring audit trails
- Key signal: you can write the sub-task list before the first agent runs

**Use hub-and-spoke** when a single routing agent routes to specialists but the hub does no work itself:
- The coordinator holds routing logic, specialists handle execution, all communication returns through the hub
- Best for: request routing, classification + action pipelines
- Key signal: specialists should never need to talk to each other directly

**Use peer-to-peer** when agents must discover tasks and negotiate approaches through collaboration:
- Every agent can call any other; coordination emerges from the conversation rather than a predetermined plan
- Best for: research synthesis, exploratory analysis, creative workflows where the right approach is unknown upfront
- Key signal: the problem cannot be decomposed without first understanding the problem — agents must negotiate before executing

**Use hybrid when workflows span both structured and unstructured phases:**
- Supervisor for the outer orchestration layer, peer within specialist sub-teams for collaborative problem-solving
- Example: a hierarchical pipeline (planner → specialist pool) with peer negotiation within each specialist cluster

**The break-even signals for splitting a single agent:**
- The agent must call >3 distinct tools in non-linear order
- Different sub-tasks need different model providers or temperature settings
- You need different instruction sets for different task types that conflict when combined
- You need parallel execution to hit latency targets

**The break-even signals for NOT splitting:**
- Sub-tasks share a tight context window — passing state between agents costs more than staying unified
- The workflow is short (<5 steps) and deterministic
- Agents would pass output directly to another agent with no transformation — this is a pipeline, not a coordination pattern

## Evidence

- **Engineering blog (DronaHQ, Feb 2026):** Summarized four coordination patterns — supervisor/hierarchical, peer-to-peer, hub-and-spoke, and hybrid — with use-case mapping: "high-frequency trading might be hierarchical, customer service might use hub-and-spoke, research workflows might use peer-to-peer." Also documented how single agents loop endlessly without self-correction mechanisms, hallucinate without grounding, and can't plan across multi-step workflows without decomposition. — [dronahq.com/multi-agent-architecture](https://www.dronahq.com/multi-agent-architecture)

- **HN discussion on agent stack stratification (Jun 2026):** Noted the agent stack is "splitting into specialized layers" with sandboxing becoming its own category (Shuru, E2B, Modal, Firecracker). This maps to the coordination topology problem: as agents specialize, the wiring between them becomes a distinct engineering challenge separate from the agent logic itself. — [news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)

- **Production lessons survey (Technspire, Dec 2025):** Found that developer tooling (coding agents) was the most successful early deployment — and specifically credited the tight feedback loop (compile + test + human review) as the reason. This feedback loop is a de facto hierarchical supervisor pattern where the compiler/test suite acts as the routing authority, not the agent. Suggests hierarchical works best when external validation can constrain the search space. — [technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Peer systems scale poorly past 5-6 agents.** The number of potential communication channels grows as O(n²). At 10 agents you have 45 potential channels — you'll need explicit routing rules that effectively recreate a hub.
- **Hierarchical systems become a bottleneck at the supervisor.** If the planner/reviewer agent is underpowered or has a small context window, the entire pipeline stalls. Budget the supervisor's context the same as the specialists'.
- **Tool output between agents is a contract you must version.** When Agent A outputs JSON that Agent B parses, any schema drift breaks the downstream agent silently. Treat inter-agent schemas like API contracts.
- **Hybrid sounds appealing but adds two failure points.** You now have both a topology decision (how to organize the outer layer) and a routing decision within each sub-team. Build the simple version first and add hybrid only when you can name the specific failure that hybrid solves.
