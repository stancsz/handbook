# S-621 · Multi-Agent Coordination Patterns: What Actually Shipped to Production

[Peer-to-peer agent teams sound elegant on a whiteboard. In 2025-2026, they became the most common source of agentic failures. The teams that shipped stable multi-agent systems made a different bet: explicit coordination topology with typed handoffs and bounded collaboration windows.]

## Forces

- **Emergent coordination sounds cheap but costs more.** Letting agents "figure it out among themselves" amplified every known failure mode — hallucination cascades, infinite loops, and silent failures where no agent held the authoritative state.
- **The 1,445% surge in multi-agent inquiries (Gartner, Q1 2024→Q2 2025) outpaced any shared understanding of coordination patterns.** Teams adopted multi-agent before the pattern literature existed.
- **Tool selection accuracy collapses without an orchestrator.** Single agents degrade gracefully at ~8-10 tools; multi-agent peer systems degrade catastrophically because each agent adds an N×M tool selection surface to every other agent.
- **Context cost compounds differently per topology.** Orchestrator-worker patterns share context efficiently; peer-to-peer patterns re-negotiate context on every handoff, inflating token spend 3-10x.

## The move

Five coordination patterns, ranked by production evidence (simplest-first, evolve as needed):

- **Generator-Verifier** — One agent produces, one checks against explicit criteria. Loop with feedback until accepted or max iterations. Best for: code review, data extraction, structured output where ground truth is knowable. This is the entry point; nearly every production multi-agent system eventually includes at least one G-V pair.
- **Orchestrator-Worker** — A central orchestrator decomposes tasks, delegates to specialized workers, synthesizes results. Workers never talk to each other directly. Best for: research pipelines, content pipelines, anything with a clear funnel. This is the highest-leverage production pattern — used by OpenSoul's 6-agent marketing stack, Anthropic's research system, and the majority of shipping systems.
- **Hierarchical** — Multiple orchestration layers, each delegating to the layer below. A director agent coordinates team leads who coordinate specialists. Best for: large-scale operations (100+ task types), enterprise workflows with distinct domain boundaries. The cost is governance overhead; use it only when task diversity demands it.
- **Pipeline** — Strict linear handoff, each agent completes one stage and passes to the next. Best for: compliance-heavy workflows, anything requiring audit trails. Least flexible but easiest to debug and monitor.
- **Peer-to-peer** — Agents negotiate directly, broadcasting to the group and converging on consensus. Explicitly not recommended for production. The Glasp analysis of 2025-2026 empirical evidence: "Letting agents figure it out among themselves amplified every known failure mode."

Anthropic's multi-agent research system beat single-agent Claude Opus 4 by **90.2% on internal evals** using orchestrator-worker, but consumed roughly **15x the tokens**. You're buying capability with money — price it accordingly.

## Evidence

- **Anthropic Claude Blog (April 2026):** Documented all five coordination patterns with trade-off guidance. Key finding: "We've seen teams choose patterns based on what sounds sophisticated rather than what fits the problem at hand." Recommended starting with the simplest pattern that could work. — [claude.com/blog/multi-agent-coordination-patterns](https://claude.com/blog/multi-agent-coordination-patterns)
- **RaftLabs production data (Nov 2025):** Tracked 1,445% surge in multi-agent inquiries (Gartner). Found 89% of teams had observability but only 52% had evals — "the gap explains why debugging is guesswork." Identified untyped handoffs as root cause in 3 client rebuilds. — [raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Glasp empirical analysis (2025-2026):** After reviewing Anthropic's orchestrator-worker research, Cognition's Devin results, Cursor 2.0's parallel agents, and the SWE-bench failure-mode data: peer-to-peer coordination failed across the board. Devin achieved 13.86% on SWE-bench Verified but ~85% real-world failure rate — benchmarks measured one thing, production measured another. — [glasp.ai/articles/agents-as-teammates-hierarchy-roles](https://glasp.ai/articles/agents-as-teammates-hierarchy-roles)

## Gotchas

- **Untyped handoffs are the #1 source of multi-agent failures.** The fix: every agent-to-agent handoff must include a typed schema (JSON, Pydantic, or equivalent) with explicit fields for task, context, expected output format, and deadline. RaftLabs traced 3 client rebuilds to this single root cause.
- **Infinite loops are the #2 source.** Peer-to-peer systems without explicit convergence criteria will loop until context windows fill. Generator-Verifier systems need a hard max-iterations cap. Orchestrator-Worker needs explicit task completion signals, not trust.
- **Observability without evals is noise.** 89% of teams track agent behavior; only 52% have eval pipelines. You cannot debug a multi-agent system without both. The minimum viable setup: log every handoff (input/output pair) and measure end-to-end task success rate against a ground-truth dataset.
- **Tool schema proliferation is a silent tax.** Every tool you add to an agent increases its selection surface. A 10-tool agent has 10 decisions per step; a 30-tool peer network has 870 (N×(N-1)) potential handoffs. Keep agent tool sets narrow and composable.
