# S-663 · Multi-Agent Coordination: Picking the Right Pattern Before You Add the Second Agent

[You have a working single-agent system. It handles the happy path well but starts making errors when the task scope grows. The reflex is to split it into two agents. But the coordination overhead of that split — handoff schemas, shared context, failure propagation — can make things worse. The wrong pattern at the wrong time turns a clean system into an undebuggable mess of inter-agent loops and silent failures.]

## Forces

- **More agents does not mean better results.** AppWorld benchmarks show 86.7% failure on cross-app workflows with naive multi-agent setups. Logistics systems — which have genuinely bounded, structured work — show 27% throughput gains. The domain matters more than the architecture.
- **Every coordination pattern has a hidden tax.** Peer-to-peer handoffs sound clean but create non-deterministic ordering. Hierarchical supervisors are easy to trace but create a bottleneck. Market-based bidding adds LLM calls on every task split.
- **The observability gap is real.** 89% of teams have tracing infrastructure but only 52% run evals (RaftLabs, Nov 2025). When a multi-agent workflow fails, teams cannot tell whether the issue is a bad agent decision, a bad handoff, or a bad tool response — because they only instrument one of those three.
- **Typed schemas at agent boundaries are not optional.** Untyped handoffs are the single fastest way to introduce silent failures that pass unit tests and fail in production. Every inter-agent message needs a schema with version numbering.

## The Move

Choose your coordination pattern based on work characteristics, not hype. Four patterns cover most production cases:

**Supervisor (controller delegates):** A single orchestrator agent routes subtasks to specialized workers. Best for dynamic task distribution where the supervisor needs to see all outputs before deciding next steps. Easiest to trace — the supervisor's trace is the full execution history. Adds latency proportional to the number of delegation rounds.

**Pipeline (sequential handoff):** Agents execute in fixed order, each consuming the previous agent's output. Like Unix pipes. Best for deterministic workflows where output quality improves through staged refinement (extract → classify → transform → validate). No coordination overhead; order is explicit. Adding parallelism is not an option — if step 3 needs step 2, it waits.

**Orchestrator-Worker (dynamic dispatch):** A central orchestrator analyzes the task, dispatches independent subtasks to workers in parallel, then synthesizes results. Best when a task decomposes into independent sub-problems (parallel research across multiple sources, multi-document analysis). Cost compounds: 4-agent orchestrator-worker workflows run $5–8 per complex task. Worth it when specialization measurably improves quality.

**Peer (handoff):** Agents pass control between peers based on task type. Cleanest for stage-based workflows (inbound → triage → research → response → customer). OpenAI's Swarm framework is built around this model. The risk: each handoff is a context switch that may lose information if the schema is underspecified.

**When to default to single-agent:** Task requires <8–10 tools, context fits in one window, failure modes are recoverable by retry. Gravity's rule: "most production multi-agent systems exist because the work has genuine boundaries — different access controls, different tools, different models — not because two LLMs are smarter than one."

## Evidence

- **Gartner research:** 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025; 57% of organizations already have agents in production. 40% of agentic AI projects are at risk of cancellation by 2027 due to failure to operationalize. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide), Nov 2025
- **Benchmark data:** ChatDev achieves 33.3% correctness on real programming tasks. AppWorld shows 86.7% failure on cross-app workflows. Logistics systems (bounded, structured work) demonstrate 27% throughput gains and 22% cost reduction. The pattern — not the model — determines whether multi-agent pays off. — [Thread Transfer](https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns), Jul 2025
- **Observability gap:** 89% of teams have observability tooling but only 52% have evaluation frameworks. Without evals, multi-agent debugging is "mostly guesswork." — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide), Nov 2025
- **Cost compounding:** Multi-agent costs 2–5× more in tokens for the same work compared to a single-agent equivalent. Orchestrator-worker with 4 agents: $5–8 per complex task. — [Gravity](https://gravity.fast/blog/ai-agent-multi-agent-coordination), May 2026; [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide), Nov 2025

## Gotchas

- **Adding a second agent to fix a broken single agent almost always makes it worse.** If the single agent fails because the task is too broad, split the task's *domain*, not its *steps*. If it fails because of context length, add RAG. If it fails because of tool count, reduce tools first.
- **Supervisor trace comprehensiveness is a false comfort.** You can see what the supervisor decided but not why the worker produced bad output. Instrument both levels independently.
- **Peer handoffs lose information silently.** Each agent's context window is its own. The receiving agent gets the message payload, not the sending agent's full reasoning. Over-communicate in the handoff schema.
- **Model the economics before you commit.** A 4-agent workflow at $6/task that runs 10,000 times/month is $60K/month. A single-agent version at $0.50/task with better retrieval is $5K/month. Quantify the quality improvement before assuming the extra cost is justified.
