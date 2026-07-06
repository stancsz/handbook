# S-258 · PydanticAI vs LangGraph: Two Production Bets

You need to ship an agent to production and your team argues about whether to use PydanticAI or LangGraph. Both are credible. Both have defenders. The decision reshapes how you handle type safety, state, observability, and the path from prototype to prod.

## Forces

- **Type safety vs execution visibility — you can't have both by default.** PydanticAI makes contracts explicit through runtime validation. LangGraph makes execution paths visible through graph-based tracing. Each catches a different class of production failure.
- **Prototype velocity vs production robustness — they optimize for opposite phases.** CrewAI wins on "ship a demo this week." But once you need production-grade state management, LangGraph earns its complexity. PydanticAI occupies the middle ground — fast to prototype, strong at production, if your problem fits its mental model.
- **The ecosystem vs the contract — this is the real trade-off.** LangChain/LangGraph has 38,200+ dependents, 70+ LLM providers, and LangSmith for enterprise tracing. PydanticAI has type safety and dependency injection that makes testing trivial. You pay the ecosystem tax or you pay the type-contract tax.

## The move

**Choose based on where your failure modes live, not on feature lists.**

- **Use PydanticAI when:** your agent has well-defined inputs/outputs, you want full Pydantic v2 validation catching malformed LLM outputs before they reach application code, your team is Python-first, and structured outputs are a priority. WebSocket streaming is ~40 lines vs LangGraph's ~80. Dependency injection lets you mock dependencies without changing agent code.
  - Best for: medical triage agents, structured data extraction, form-handling workflows, anything where a wrong output shape is worse than a slow one.
  - Dependency injection pattern: inject `TriageDependencies(patient_id, db_connection)` into the agent; swap mocks for testing without touching agent logic.

- **Use LangGraph when:** you have multi-step, iterative workflows where execution paths branch conditionally, you need time-travel debugging and checkpointing, or you're building multi-agent orchestration where agents are graph nodes and transitions are edges.
  - Best for: research pipelines, coding agents that loop, anything with conditional retry logic or human-in-the-loop checkpoints.
  - LangSmith gives you full traces across every node firing — critical for debugging why a 47-step workflow took the wrong branch.

- **Consider CrewAI for rapid prototyping** of role-based multi-agent systems (Director → Strategist → Creative → Producer). Ships fast. Refactor to LangGraph when you hit the walls — which you will at scale.

- **Consider AutoGen / Microsoft Agent Framework** for multi-party conversations where agents debate, build consensus, or review each other's work. Zero framework cost. The Microsoft→AG2 transition created confusion; be aware tutorials may be stale.

- **Model cascading as a cost lever:** Teams building with either framework are reporting 40-70% token cost reduction by routing simple queries to smaller models (e.g., GPT-4o-mini) and reserving larger models (Claude Opus, GPT-4.1) only for steps that genuinely need them.

## Evidence

- **GitHub decision guide (updated April 2026):** Decision matrix: "Ship a demo this week → CrewAI. Run in production next month → LangGraph. Complex multi-agent reasoning → AutoGen. Avoid a framework entirely → Raw Claude API + tool use." MCP support rated 5/5 for LangGraph as first-class graph nodes with full streaming.
  - *GitHub: benconally/ai-agent-framework-decision-guide* — [URL](https://github.com/benconally/ai-agent-framework-decision-guide)
- **Production comparison (Vstorm OSS, February 2026):** After building 30+ production AI agent systems with both: Pydantic AI wins on type safety (compile-time validation of structured outputs, ~40 lines for WebSocket streaming vs ~80 in LangChain), developer experience, and dependency injection. LangChain wins on ecosystem breadth (70+ LLM providers, LangSmith enterprise tracing). Key metric: WebSocket streaming in Pydantic AI is ~40 lines vs ~80 in LangChain.
  - *Vstorm OSS: Pydantic AI vs LangChain for Production AI Agents (2026)* — [URL](https://oss.vstorm.co/blog/pydantic-ai-vs-langchain)
- **HN discussion (13-agent system, PAI Family):** Running a 13-agent system for months with specialized agents for research, finance, content, strategy, critique, and psychology. Key learning: "The arrangement of checks between agents matters more than which model you pick for any one step." Multi-agent collaboration and prediction-market-style disagreement between agents.
  - *Hacker News Ask: How are you using multi-agent AI systems in daily workflow?* — [URL](https://news.ycombinator.com/item?id=47270020)
- **Turion.ai comparison (May 2026):** LangGraph: graph nodes + edges, best for stateful workflows with conditional branching. CrewAI: role-based team hierarchy, best for rapid prototyping. AutoGen: conversation chains between agents, best for multi-party debate and consensus-building.
  - *Turion.ai: LangGraph vs CrewAI vs AutoGen: 2026 Comparison* — [URL](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)

## Gotchas

- **PydanticAI v1.0 landed September 2025 — verify you're reading current docs.** The framework has moved fast; pre-v1 patterns may not apply.
- **LangGraph's graph mental model has a real learning curve.** Budget 1-2 days to internalize nodes-as-agents, edges-as-transitions before it clicks.
- **Multi-agent coordination amplifies errors: research shows 17x error rate for independent agents vs 4x with central coordination.** Never just throw more agents at a problem.
- **Production cost surprise: AI agent costs typically run 5-15x higher than prototype.** Token/API spend is 30-50% of total; infrastructure is 20-35%; observability is 10-20%. Model cascading is the highest-leverage cost lever.
