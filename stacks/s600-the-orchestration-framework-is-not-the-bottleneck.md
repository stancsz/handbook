# S-600 · The Orchestration Framework Is Not the Bottleneck

Teams spend weeks debating LangGraph vs CrewAI vs AutoGen. They ship on one, then discover the real failure modes have nothing to do with the framework. The orchestration framework is infrastructure — the bottleneck is always one layer up: evaluation, observability, and cost discipline.

## Forces

- **Framework choice is reversible but eval debt is not.** Migrating between LangGraph, CrewAI, or AutoGen is a matter of days. Rebuilding a broken evaluation harness after launch is a matter of months and requires replaying every failure you never caught.
- **89% of teams have observability; only 52% have evals.** (RaftLabs, 2025) The gap between "I can see traces" and "I can tell if the system is getting better" is the difference between debugging and guesswork.
- **Enterprise users equate speed with competence.** A slow response — even a correct one — feels broken. Tail latency (P95/P99) matters more than mean response time.
- **Naive RAG undermines agents silently.** 20–40% of agentic RAG queries require reformulation — but teams don't measure this, so they blame the model instead of the retrieval layer.
- **Typed schema mismatches kill multi-agent handoffs.** When agents pass outputs to each other without enforced schemas, cascading failures propagate before anyone notices.

## The move

Ship the simplest stack that meets the reliability bar, then invest in the three things that actually separate production agents from demos:

- **Eval harness before orchestration complexity.** Build a replay dataset of real queries and their expected outputs. Measure every code change against it. If you can't detect regression, you can't ship safely.
- **Structured state at every handoff.** Use Pydantic or Zod schemas at every agent boundary. Treat unstructured LLM output as untrusted — validate it before passing it downstream.
- **Cost budgeting with hard caps.** Set per-task token limits. Track P50/P95/P99 latency per agent. A 4-agent workflow at $5–8/complex task compounds fast — gate expensive paths behind lightweight classifiers.
- **Observability traces, not just logs.** Record full agent trajectories (tool calls, intermediate outputs, LLM inputs/outputs). Without traces, a failure in production means guessing from symptoms.
- **Start retrieval simple.** Begin with a hybrid BM25 + vector EnsembleRetriever. Add routing complexity only when metrics show a simpler approach is insufficient — not in advance.

## Evidence

- **Blog — hjLabs.in:** Field report from 18 months of production deployments — "The teams that ship reliable agents invested in observability, evaluation harnesses, prompt versioning, and human-review workflows — regardless of framework." — [hjLabs.ai-engineering-notes](https://hemangjoshi37a.github.io/hjLabs-AI-Engineering-Notes/04-crewai-vs-langgraph-vs-autogen-production-comparison/)
- **Blog — RaftLabs (Nov 2025):** "89% of teams have observability but only 52% have evals — explaining why debugging is guesswork." Multi-agent orchestration patterns breakdown. — [raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Blog — Aliac.eu:** Enterprise agentic RAG production data — Harvey AI achieved 0.2% hallucination rate across 700+ legal clients; Deutsche Telekom achieved 89% acceptable answer rate across 2M+ conversations; both attributed results to evaluation discipline and retrieval quality gates. — [aliac.eu/blog/agentic-rag-in-production](https://aliac.eu/blog/agentic-rag-in-production)
- **Blog — Lushbinary (Apr 2026):** Framework comparison — "LangGraph offers graph-based production control. CrewAI enables fastest prototyping with role-based teams. AutoGen excels at collaborative reasoning on Azure." — [lushbinary.com/blog/langgraph-vs-crewai-vs-autogen](https://lushbinary.com/blog/langgraph-vs-crewai-vs-autogen-ai-agent-framework-comparison/)
- **Blog — Technspire (Dec 2025):** "Agents work where software engineering discipline works. Bounded scope, tested behavior, scoped identity, observable runtime." Production lessons from end-of-2025 deployments. — [technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)
- **GitHub — benconally/ai-agent-framework-decision-guide:** Production checklist — "Ship a demo this week: CrewAI. Run in production next month: LangGraph. Complex multi-agent reasoning: AutoGen. Avoid a framework entirely: Raw Claude API + tool use." — [github.com/benconally/ai-agent-framework-decision-guide](https://github.com/benconally/ai-agent-framework-decision-guide)
- **Blog — 1337skills (May 2026):** "If more than 20% of queries require reformulation, the problem is in your retrieval layer — poor chunking, wrong embedding model, stale index — not in the agent logic." — [1337skills.com/blog/agentic-rag-architecture-patterns](https://1337skills.com/blog/2026-05-21-agentic-rag-architecture-patterns)
- **Blog — Netguru (Jun 2026):** "Use a reliable language model like Azure OpenAI's GPT-4o or reasoning model like o3-mini, orchestrate agents using a flexible framework like AutoGen, persist memory with structured context and vector databases, and give agents real tools." — [netguru.com/blog/ai-agent-tech-stack](https://www.netguru.com/blog/ai-agent-tech-stack)

## Gotchas

- **Traceroute is not evaluation.** Having traces does not mean you can detect if the system is improving. Build ground-truth datasets and measure hit rate, not just coverage.
- **Over-routing is a real anti-pattern.** Complex routing graphs with dozens of specialized indexes often underperform a single well-tuned hybrid retriever. Start simple; add routing only when data proves it's needed.
- **Infinite reformulation loops.** Without a hard cap on retrieval attempts, agents cycle through query reformulations indefinitely — burning tokens and adding latency. Set explicit retry limits and track reformulation rate as a first-class metric.
- **Context stuffing.** Retrieving 20 chunks and cramming them all into the prompt creates noise that degrades answer quality. Quality-gate retrieval outputs before injecting them.
- **Silent cascading failures in multi-agent.** One agent's malformed output becomes another's bad input. Typed schemas at every boundary are not optional — they are the only way to fail fast.
