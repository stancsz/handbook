# S-421 · Orchestration Framework Migration: The CrewAI-to-LangGraph Pattern

You built fast with CrewAI. Agents, crews, tasks — shipped in a week. Then production hit: your agents need human-in-the-loop checkpoints, state that survives crashes, audit logs for every transition, and a workflow graph you can actually inspect. CrewAI has none of that out of the box. Now you're rewriting everything in LangGraph. You are not alone. This is the most common migration story in agentic engineering right now.

## Forces

- **Prototyping speed vs. production rigor** — CrewAI ships features in days; LangGraph ships production in weeks
- **Implicit vs. explicit state** — CrewAI hides state inside agent objects; LangGraph makes it a first-class citizen in the graph
- **Auditability in regulated industries** — Healthcare, finance, legal require traceable decision paths; CrewAI's logs are not structured for compliance
- **The sunk cost trap** — The faster you prototype, the more you have to migrate; early framework choice compounds
- **Checkpoint and resume** — Long-running agents (hours, not seconds) need state persistence; this is a hard requirement, not a nice-to-have

## The Move

The migration pattern is predictable and well-documented across enterprise teams. Know where CrewAI ends and LangGraph begins.

### What CrewAI does well (keep it)

- **Role-based agent design**: defining agents by role, goal, and backstory is more intuitive than LangGraph's node/edge model for initial brainstorming
- **Rapid multi-agent brainstorming**: when you need a Director → Strategist → Analyst pipeline in 30 minutes, CrewAI wins
- **Task delegation without ceremony**: the `Task` → `Crew` → `Kickoff` API surface is genuinely small

### Where to switch to LangGraph

- **Stateful workflows with checkpointing**: LangGraph's `save_state` / `load_state` with `Store` interface means a crash at step 7 resumes at step 7, not step 1
- **Human-in-the-loop gates**: `interrupt_before` / `interrupt_after` nodes let a human approve, redirect, or abort mid-workflow — CrewAI has no equivalent
- **Regulated audit trails**: every graph transition is an explicit edge; combined with LangSmith traces, you get structured logs that compliance teams accept
- **Complex conditional branching**: when `if state["confidence"] < 0.7: go to research_agent` needs to be visible and testable as a unit, not buried in a prompt
- **Cycles and loops**: LangGraph handles `while` semantics natively; CrewAI's looping is task-level, not graph-level

### Migration sequence

1. **Extract agents as LangGraph nodes** — each CrewAI agent becomes a node function `def research_node(state): ...`
2. **Translate task outputs to state keys** — CrewAI's `context` dict becomes typed `state` fields
3. **Add checkpointing at decision points** — wrap `store.put()` calls at every LLM call boundary
4. **Insert `interrupt_before` at human approval steps** — one decorator per gate
5. **Wire LangSmith** — `config={"tags": ["production"]}` on the compiled graph enables structured replay

## Evidence

- **Enterprise comparison (2026):** LangGraph ranked highest for production readiness, auditability, and human-in-the-loop; CrewAI ranked highest for prototyping speed; most Fortune 500 teams start with CrewAI and migrate to LangGraph — [Gheware DevOps AI Blog](https://devops.gheware.com/blog/posts/langgraph-vs-autogen-vs-crewai-comparison-2026.html), March 2026
- **Framework comparison (2026):** "LangGraph offers graph-based production control. CrewAI enables fastest prototyping with role-based teams. AutoGen excels at collaborative reasoning on Azure." — [Lushbinary](https://lushbinary.com/blog/langgraph-vs-crewai-vs-autogen-ai-agent-framework-comparison), April 2026
- **Production lessons (2025):** Four categories shipped reliably: developer tooling, internal ops automation, research/analysis, customer-facing service — but all required bounded scope, tested behavior, scoped identity, and observable runtime (what LangGraph provides structurally) — [Technspire](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons), December 2025
- **CrewAI production docs:** "We recommend starting with a Flow. Wrapping [Crews] in a Flow provides the necessary structure for a robust, scalable application" — acknowledges that standalone Crews need additional orchestration scaffolding for production — [CrewAI Production Architecture Docs](https://docs.crewai.com/en/concepts/production-architecture)

## Gotchas

- **LangGraph has a steeper initial learning curve** — graph state, typed schemas, and checkpointing APIs add upfront complexity that CrewAI hides
- **CrewAI's simplicity is a productivity trap** — teams ship fast, then discover they need LangGraph's features only after accumulating enough agent state that migration is painful
- **Checkpoint granularity matters** — saving state after every node call creates enormous storage costs; save at decision boundaries, not intermediate steps
- **LangSmith pricing** — structured traces are powerful but expensive at high-volume; budget for it before going wide
- **AutoGen is not in this migration story** — it occupies a different niche (Azure-native, collaborative code generation); if you are on Azure and building developer tooling, AutoGen may be the right starting point, not a CrewAI destination
