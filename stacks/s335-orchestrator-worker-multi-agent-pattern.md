# S-335 · The Orchestrator-Worker Pattern: Why Single-Agent Systems Collapse at Scale

Your agent works great until it doesn't — until the task grows, the context window shrinks, the model starts skipping steps, and the single agent becomes a single point of failure. The orchestrator-worker pattern solves this by splitting cognitive load across a coordinating brain and specialized hands, but the implementation details determine whether you get resilience or chaos.

## Forces

- **A single agent's context is a finite resource.** As task complexity grows, the model wastes tokens on managing state instead of executing work. A 3,000-token task inside a 200,000-token context might be fine; a 50,000-token task is not.
- **Specialized agents outperform generalists on domain tasks.** A coding agent fine-tuned or prompted for code review consistently beats a general-purposes LLM acting as a "developer." Division of labor is a capability multiplier.
- **Orchestrator-worker is the highest-leverage pattern for 3–6 agents, but untyped handoffs kill it.** The moment agents start passing unstructured outputs to each other, you have silent failures, schema drift, and cascading errors that are near-impossible to debug.
- **Cost compounds per agent turn.** A 4-agent orchestrator-worker workflow on GPT-4o runs $5–8 per complex task. Teams that don't model this early are surprised by production bills.

## The move

Split your agent system into a central orchestrator and domain-specific workers, with versioned Pydantic schemas governing every handoff:

- **Orchestrator** owns task decomposition, delegation, result synthesis, and retry logic. It does not execute domain work — it decides who does what and when. Keep it lightweight; its job is coordination, not completion.
- **Workers** are narrow, stateless, single-purpose. Each worker receives a typed input, produces a typed output, and returns. No shared state between workers.
- **Handoff contracts are versioned schemas.** Every agent-to-agent boundary uses a Pydantic model with explicit field types and version numbers. This is the non-negotiable part — untyped handoffs are the #1 cause of multi-agent production failures.
- **Error recovery is explicit graph edges, not implicit loops.** In LangGraph, model this with conditional edges: if worker returns error → orchestrator retries with backoff or escalates. In CrewAI, the manager agent explicitly delegates tasks and handles exceptions.
- **Checkpoint intermediate state.** Long-running orchestrator-worker flows need resumability. LangGraph's built-in checkpointing handles this; custom implementations need Redis + task state serialization.
- **Cost-budget the orchestrator.** Set per-task token and dollar limits on orchestrator-level. A runaway worker loop is a runaway bill.

## Evidence

- **Engineering blog (RaftLabs, Nov 2025):** A 4-agent orchestrator-worker workflow costs $5–8 per complex task in production. Teams that model economics upfront pick which tasks deserve full orchestration vs. simple sequential flows. — [https://www.raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **HN discussion (May 2026):** Practitioners report that stateless, single-agent pipelines break immediately when a user references prior context. Solutions: thread-scoped agent memory with importance scoring, not just conversation history. — [https://news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **Production post (Technspire, Dec 2025):** Developer tooling agents graduated first because the tight compile-test-human-review loop provides natural checkpoints and error boundaries. Internal ops automation (ticket triage, access routing) shipped second — both are natural fits for orchestrator-worker decomposition. — [https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Over-decomposition is a real failure mode.** Splitting a 5-step task into 5 workers creates more coordination overhead than the specialization gain is worth. The sweet spot is 3–6 agents where each handles a genuinely distinct capability.
- **Orchestrator becomes a bottleneck.** If the orchestrator is doing real work (not just delegating), it will hit context limits just like a single agent. Treat the orchestrator as pure coordination.
- **CrewAI's manager delegation vs. LangGraph's explicit graph are two implementations of the same pattern.** CrewAI's `Manager` agent is faster to set up; LangGraph's directed graph gives you checkpointing, streaming, and explicit error recovery out of the box.
- **Multi-agent eval is still mostly guesswork.** 89% of teams have observability but only 52% have evals for agent outputs. You will ship blind on quality until you invest in output validation — plan for this in your first production deployment.
