# S-428 · Orchestration Framework Choice in Production

Your agent prototype works. Now you're choosing an orchestration framework for production — and the three leading options have sharply diverged in ways that only surface under real load. LangGraph, CrewAI, and AutoGen each make a different bet about where complexity belongs. Picking the wrong one means rewriting at month three.

## Forces

- **LangGraph trades dev speed for production control.** Explicit graph topology, checkpointing, and conditional edges mean more upfront code — but failures are reproducible and audit paths are explicit.
- **CrewAI bets on team mental models over engineering precision.** Role-based agents with delegation chains map cleanly to how non-engineers think about workflows — and that's a real advantage when product owns the prompt iteration.
- **AutoGen bets on conversation as the primitive.** Multi-agent message passing feels natural for chatty systems but becomes a liability when you need deterministic sequencing or compliance checkpoints.
- **The "right" framework depends on your failure mode.** Compliance workflows need LangGraph's edge explicitness. Rapid iteration on marketing/research pipelines suits CrewAI. Microsoft/Azure shops with conversational agents reach for AutoGen.

## The move

Match framework to workflow type, not to hype:

- **Use LangGraph when** compliance or human-in-the-loop checkpoints are non-negotiable. Explicit state machine edges make skipped steps structurally impossible — CrewAI's delegation chain has been shown to skip nurse-review steps when agents "decide" cases are low-urgency. LangGraph's graph logic makes that failure mode impossible.
- **Use CrewAI when** the team thinks in "agents with jobs" and ships fast. CrewAI benchmarks at 40% faster shipping than AutoGen for equivalent pipelines — at the cost of observability and compliance tooling.
- **Use AutoGen when** you are deep in the Microsoft ecosystem and need multi-agent conversational loops. Azure OpenAI integration is first-class. Async v0.4 architecture is powerful but the standalone project has uncertain long-term Microsoft commitment.
- **Prefer Plan-and-Execute over ReAct** for cost-sensitive pipelines: separate planning (expensive model) from execution (cheaper model) reduces API spend 30-40% with no quality degradation on structured tasks.
- **Cap tool sets at 30-40 tools per agent.** Tool selection accuracy drops from 95%+ at 5 tools to 80-85% at 50+ tools due to semantic similarity between options.
- **Instrument before optimizing.** Multi-agent pipelines generate 6-9x more API calls than single-agent equivalents — measure before assuming parallelism pays off.

## Evidence

- **Healthcare triage pipeline (LangGraph):** 12 engineer-days from first PoC to production. 40% reduction in triage time. Explicit graph edges made HIPAA-required pauses structurally enforced rather than prompt-dependent. — [Towards AI: LangGraph vs CrewAI vs AutoGen Production Guide 2026](https://pub.towardsai.net/langgraph-vs-crewai-vs-autogen-which-ai-agent-framework-should-your-enterprise-use-in-2026-3a9ebb407b09)
- **Competitive intel pipeline (CrewAI):** 5-agent crew replaced 20 analyst-hours/week manual process. 40% faster shipping versus equivalent AutoGen pipeline in benchmarks. — [Towards AI: LangGraph vs CrewAI vs AutoGen Production Guide 2026](https://pub.towardsai.net/langgraph-vs-crewai-vs-autogen-which-ai-agent-framework-should-your-enterprise-use-in-2026-3a9ebb407b09)
- **Agent stack fragmentation:** Engineering teams report the stack is splitting into specialized layers — sandboxing, orchestration, memory, tool execution, evaluation, context management — with different winners at each layer. Going monolithic across all layers is increasingly seen as a wrong call. — [HN: Agent stack splitting into specialized layers](https://news.ycombinator.com/item?id=47114201) + [Philipp Dubach: Don't Go Monolithic; The Agent Stack Is Stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying)
- **Production performance metrics:** ReAct covers ~70% of agent use cases. Plan-and-Execute cuts costs 30-40%. Tool selection degrades above 50 options (95%→80% accuracy). RAG metadata pre-filtering cuts retrieval latency 40-60%. — [Pharos Production: AI Agent Architecture Patterns 2026](https://pharosproduction.com/insights/engineering/ai-agent-architecture-patterns-2026)
- **LangGraph vs competition benchmarks:** 47M+ PyPI downloads with LangChain. LangGraph leads on production reliability, observability, human-in-the-loop, cost predictability, and ecosystem longevity. CrewAI leads on dev speed. — [AgentMarketCap: Multi-Agent Framework Decision Guide 2026](https://agentmarketcap.ai/blog/2026/04/11/langgraph-autogen-crewai-dspy-multi-agent-orchestration-2026)

## Gotchas

- **CrewAI's delegation chain is prompt-dependent, not structurally enforced.** For compliance-critical workflows, this is a blocker — agents can and do skip steps they deem unnecessary.
- **AutoGen's Microsoft commitment is uncertain.** v0.4 async architecture is powerful but the standalone project's long-term trajectory is unclear; Azure shops face less risk.
- **Multi-agent parallelism doesn't always pay off.** 6-9x more API calls means 6-9x more cost — measure the actual speedup before assuming parallelism justifies the overhead.
- **Context window isn't free performance.** Prefill latency at 1M tokens can exceed 2 minutes before first output token. Anthropic's pricing reflects this ($10/$37.50 per million tokens above 200K).
