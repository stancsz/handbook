# S-562 · The Framework Is a Deployment Timeline Decision

Orchestration framework choice is rarely a technical decision — it's a timeline decision. CrewAI ships demos in a week. LangGraph ships production in a month. Raw API calls ship when you want zero dependencies. Teams that treat it as a technical purity contest waste months.

## Forces

- Open-source frameworks (LangChain, CrewAI) accelerate prototyping but accumulate hidden dependency debt that surfaces in production
- The "agent" framing sets autonomy expectations that make it psychologically harder to add the guardrails that autonomous systems actually need
- Typed schema handoffs between agents are the most underestimated integration problem — more teams fail here than on LLM selection
- The LLM is becoming a commodity; orchestration is where the defensible engineering lives
- Production inference costs compound to $5–8 per complex multi-agent task, which changes the ROI calculus on framework overhead

## The Move

Pick your framework based on when you need to ship, not what you want to build.

- **CrewAI** → ship a demo this week. Role-based, intuitive, fast onboarding. But the abstraction leaks under production load.
- **LangGraph** → ship to production next month. Graph-based, explicit control flow, full state inspection. "The boring, correct answer for production."
- **AutoGen** → complex multi-agent reasoning with conversational collaboration between agents. Steeper learning curve.
- **Raw Claude API + tool use** → when you want zero framework dependency. More code, but full control and no surprise behavior.
- **Implement your own core agent loop** → for production systems that will run long-term. Open-source frameworks are great starting points, not reliable production foundations.

Add observability and guardrails from day one. Not as features — as infrastructure. A Principal ML Engineer at AI in Production 2025 put it: the term "agent" may be doing more harm than good — he calls them "process daemons" to set the right expectations: continuous background processes, not autonomous decision-makers.

Use typed schemas (Pydantic, Zod) for every inter-agent handoff. Untyped handoffs are the #1 multi-agent integration killer.

## Evidence

- **GitHub Decision Guide:** Framework decision matrix — CrewAI for demos, LangGraph for production, AutoGen for complex reasoning, raw API to avoid dependencies — [github.com/benconally/ai-agent-framework-decision-guide](https://github.com/benconally/ai-agent-framework-decision-guide)
- **AI in Production 2025 (digits.com):** Open-source frameworks like LangChain and CrewAI are "great for prototyping but bring too many dependencies for production." Recommends implementing your own core agent loop. Also argues "process daemon" is a better term than "agent" for setting expectations. — [digits.com/blog/ai-in-production-2025-slides](https://digits.com/blog/ai-in-production-2025-slides)
- **MMNTM Research (Jan 2025):** Orchestration framework comparison — LangGraph = state machine (explicit control), AutoGen = conversations (dialogue-based), CrewAI = role-based teams. Each imposes a mental model; wrong choice means fighting the framework. — [mmntm.net/articles/orchestration-showdown](https://www.mmntm.net/articles/orchestration-showdown)
- **RaftLabs (Nov 2025):** Multi-agent production systems — 1,445% surge in inquiries. Four orchestration patterns: hierarchical, pipeline, orchestrator-worker, peer-to-peer. Untyped handoffs between agents kill workflows faster than any other issue. 57% of organizations have agents in production but only 52% have evals. — [raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- LangGraph's explicit graph model is more verbose than CrewAI's role-based approach — teams underestimate the onboarding cost
- CrewAI's role abstractions break down when you need non-role-based routing (event-driven, priority-based, load-balanced)
- Typed schema validation at agent handoffs adds latency but prevents cascade failures — skip it and you'll debug silent type-mismatch bugs for weeks
- Observability (LangSmith, Phoenix, custom) must be wired in from the start — retrofitting it into a running agent system is a rewrite
