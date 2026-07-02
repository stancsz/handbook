# S-382 · The Multi-Agent Handoff Problem

Multi-agent systems are surging — Gartner tracked a 1,445% increase in multi-agent inquiries from Q1 2024 to Q2 2025, and 57% of organizations already have agents in production per a LangChain survey of 1,300+ professionals. But the same data shows that 40% of agentic AI projects will be canceled by end of 2027, driven by escalating costs and unclear ROI. The root cause is almost always the same: handoffs between agents are treated as implementation details when they are actually the load-bearing architecture.

## Forces

- **Token duplication kills economics.** Token overhead across multi-agent workflows compounds to $5–8 per complex task. MetaGPT wastes 72% of tokens on duplication; CAMEL wastes 86%. Teams underestimate this until the first bill arrives.
- **Untyped handoffs are the #1 failure mode.** RaftLabs (100+ AI products shipped) identifies untyped handoffs between agents as the single fastest way to kill a multi-agent workflow — above model quality, above context length, above everything else.
- **Pattern choice is irreversible at scale.** Once a team commits to a hierarchical or peer-to-peer structure, refactoring is expensive. The pattern must match the task topology, not the other way around.
- **89% have observability; only 52% have evals.** Most teams can see what agents are doing but cannot tell if they're doing it correctly. Handoff quality is invisible without structured evaluation.
- **Inference costs compound in multi-agent.** Enterprise AI inference spending grew 3.2x in 2025 even as per-token costs fell. Volume growth outran unit economics improvements. Multi-agent amplifies this because every agent runs inference independently.

## The move

The architectural decision that determines whether a multi-agent system survives contact with production is how agents pass state to each other. Treat handoffs as typed contracts, not implicit context concatenations.

- **Define structured output schemas for every handoff.** Not just "the output of agent A is the input to agent B" — define the exact shape, required fields, and validation rules. This is the antidote to the "agents agree with each other without real verification" failure mode. LangChain's structured output APIs and Pydantic schemas are the standard implementation.
- **Match orchestration pattern to task topology, not preference.** Supervisor pattern: best for single-turn delegation with governance requirements (e.g., customer support escalation). Hierarchical: for enterprise-scale systems with 20+ agents and clear chain of command. Orchestrator-worker: for fan-out tasks where a central planner dispatches to specialized nodes (e.g., research → write → review). Peer-to-peer: for fault-tolerant distributed tasks where no single point of failure is acceptable. Swarm: only for robotics or optimization problems requiring 50+ agents.
- **Instrument handoffs, not just traces.** A span in Langfuse tells you agent A called agent B. What it does not tell you is whether agent B received the right context to act correctly. Tag handoffs with semantic metadata: task type, urgency, context completeness score, and downstream success signal.
- **Budget inference per agent, not just per workflow.** Semantic caching deflects ~30% of queries entirely. Model routing handles another ~50% with cheaper models. Prefix caching reduces remaining costs. These compose — together they achieve 80%+ reduction from naive baseline. Route simple classification tasks to small models; reserve expensive reasoning models for complex synthesis only.
- **Enforce evaluator checks after each major step.** After each handoff, run a lightweight evaluator: did agent B receive everything it needed? Did agent A produce structured output that matches the schema? If not, retry or escalate — do not continue. This is the structured equivalent of the "shared state, trace IDs, deterministic routing" discipline that production teams cite.

## Evidence

- **Survey:** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025, with 57% of organizations already running agents in production. — [RaftLabs / Gartner](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Framework comparison:** GitHub adoption as of January 2026: AutoGen 28,400 stars, CrewAI 15,200 stars. LangGraph leads on observability and production control; CrewAI leads on prototyping speed (5.76x faster than LangGraph in QA tasks per a CrewAI benchmark); AutoGen leads on multi-agent conversation patterns and Azure integration. — [Second Talent](https://www.secondtalent.com/resources/crewai-vs-autogen-usage-performance-features-and-popularity-in/)
- **Production failure pattern:** "Untyped handoffs between agents kill multi-agent workflows faster than any other issue." The top risks of hierarchical multi-agent: manager agent delegates incorrectly, workers duplicate effort, context becomes inconsistent across agents, agents agree without verification, system becomes hard to debug. Mitigations: structured outputs, shared state, trace IDs, deterministic routing, evaluator checks after each major step. — [AI Engineering Insider / AutoGen comparison](https://aiengineeringinsider.substack.com/p/autogen-crewai-and-multi-agent-orchestration)
- **Cost compounding:** Inference costs in multi-agent workflows compound to $5–8 per complex task. Enterprise AI inference spending grew 3.2x in 2025 while per-token costs fell by 1,000x — volume growth outran unit economics. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide) and [Axe Compute](https://axecompute.com/ai-inference-costs-at-scale)

## Gotchas

- **Choosing CrewAI for prototyping then migrating to LangGraph for production works — but budget the migration.** The frameworks have fundamentally different mental models (role-based teams vs graph state machines). The migration is not just syntax; it is rethinking how you represent workflow state.
- **Token cost audits lag deployment by months.** Most teams discover the cost problem only on the first billing cycle. Build cost visibility into the observability layer from day one — track tokens per agent, per handoff, per workflow.
- **"Observability without evals" is a false sense of security.** You can see what happened. You cannot tell if it was right. The 37-point gap between teams with observability (89%) and teams with evals (52%) is where silent failures live.
- **DeepSeek-R1 proved inference-time compute scaling works, but overthinking is real.** A 7B model with 100x inference compute can match a 70B model with standard inference — but accuracy follows an inverted-U beyond a threshold. Budget-aware agents that know when to stop reasoning are more cost-effective than agents that always think harder.
