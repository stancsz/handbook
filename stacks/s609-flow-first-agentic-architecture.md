# S-609 · Flow-First Design: Why Agentic Systems Fail at Scale and How the Survivors Fix It

The moment your agent moves beyond a single LLM call, the architecture decisions you make determine whether you ship or stall. Teams that hit scale quickly discover that coupling the agent loop to synchronous inference collapses under load, and that stateless designs can't hold the context a multi-step workflow needs. The fix is flow-first design — starting with durable state machines, not loose agent definitions.

## Forces

- **The orchestration loop is not the LLM call.** Treating agent planning and model inference as the same synchronous operation creates head-of-line blocking. One slow LLM response stalls every pending task in the system.
- **Stateless agents fail at multi-step enterprise workflows.** Without durable state, you lose context between steps, can't recover from failures mid-graph, and can't support workflows that span days or users.
- **Framework defaults are prototype defaults.** CrewAI, LangGraph, and AutoGen all ship with synchronous, in-memory execution — fine for demos, broken in production at 200+ concurrent tasks.
- **Cost compounds through loops, not calls.** Without per-step budgets and circuit breakers, a single runaway agent can generate $15 in 10 minutes or $47,000 over 11 days.

## The move

Start with a Flow (or StateGraph), then add agents inside it. Not the reverse.

- **Isolate the agent coordinator from LLM inference.** Use an async task queue (RabbitMQ, Redis, or SQS) between the orchestration loop and model calls. This lets you scale orchestration and inference independently. One production team measured 40% reduction in p95 latency at 2,000 concurrent tasks after this split, and jumped from 920 to 3,200 tasks/minute sustained throughput.
- **Model cascading over single-model lock-in.** Route simple tasks to Haiku-class or Gemini Flash Lite models ($0.08–$1/M tokens), reserve Sonnet/4o for reasoning steps, and use Opus only for critical quality gates. Semantic caching of identical or near-identical queries recovers 34% of LLM calls.
- **Per-agent budgets and circuit breakers.** Set a default 30-second timeout per agent step and a circuit breaker on the LLM adapter. Kubernetes HPA on queue depth (target: 100 pending tasks per pod) prevents cascade failures.
- **State lives in the graph, not the call stack.** Use LangGraph's `StateGraph` with typed `Annotation` fields and explicit reducers. For message history: append semantics `(prev, next) => [...prev, ...next]`. For status fields: last-write-wins `(_, next) => next`. Getting reducers wrong is the most common early LangGraph bug.
- **Human-in-the-loop for high-stakes edges.** Build approval gates at named graph nodes for any step that writes data, sends a message, or spends money. Staged rollouts (sandbox → canary → production) validate different behavioral dimensions at each stage.
- **Observability from day one, not as an afterthought.** Instrument every graph node, tool call, and state transition with OpenTelemetry traces. LangSmith, Phoenix, or custom structured logging — pick one and wire it before you write your first agent.

## Evidence

- **Production benchmark — CrewAI async decoupling:** Splitting agent coordinator from LLM inference via async queue achieved 40% p95 latency reduction at 2,000 concurrent tasks and 3,200 tasks/minute sustained vs. 920 before the change. Redis caching of LLM responses recovered 34% of calls. Trade-off: added operational complexity (RabbitMQ, worker pools, distributed tracing).
  — *Markaicode, "CrewAI LLM Architecture: Production System Design for High-Throughput Agent Orchestration," July 2, 2026* — https://markaicode.com/architecture/crewai-llm-architecture

- **Enterprise adoption — LangGraph stateful graphs:** LinkedIn's SQL bot (LangGraph backbone) serves hundreds of employees with 95% query accuracy satisfaction rate. Uber saved 21,000+ engineering hours. Klarna's LangGraph-powered assistant handles 2.5M conversations and delivers resolution times 80% faster, equivalent to 700 full-time staff. TypeScript LangGraph now sees 42,000 npm downloads per week.
  — *AgentMarketCap, "LangGraph in Fortune 500 Production 2026," April 8, 2026* — https://agentmarketcap.ai/blog/2026/04/08/langgraph-fortune-500-production-stateful-multi-agent-workflows

- **Production cost reality:** Enterprise AI operational costs average $85,521/month (2025). Model API spend doubled from $3.5B to $8.4B (late 2024 to mid-2025). 60–85% of spend is recoverable through prompt caching, model routing, and hard budget enforcement. Runaway agent loop incidents have cost teams from $15 in 10 minutes to $47,000 over 11 days.
  — *Zylos Research, "AI Agent Cost Engineering — Production Token Economics," May 2, 2026* — https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics

## Gotchas

- **CrewAI's synchronous defaults will kill your throughput.** The framework ships with in-memory, single-threaded execution. Without async queue decoupling and per-agent timeouts, you'll hit concurrency limits at modest load.
- **LangGraph reducers silently corrupt state if wrong.** The append-vs-replace choice for each state field seems minor but causes subtle bugs — messages doubling up, status fields stuck in terminal states, partial updates disappearing on retry.
- **Conditional edges are easy to mis-wire.** The `set_entry_point` call is frequently wrong on first pass, causing graphs to skip initialization steps or loop infinitely.
- **Flow-first doesn't mean Flow-only.** Wrap agents in flows for orchestration and durability, but don't nest flows inside flows without a clear checkpoint strategy — you lose the ability to resume mid-graph on failure.
- **Cost control must be architectural, not operational.** Adding a human to watch the budget is not a solution. Hard per-step budgets, LLM adapter circuit breakers, and queue-depth autoscaling are the actual controls.
