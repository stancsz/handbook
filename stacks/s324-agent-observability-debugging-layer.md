# S-324 · Agent Observability: The Missing Debugging Layer

A LangGraph prototype produces wrong answers. A production multi-agent system produces wrong answers and you have no idea why. The agent decided to call the wrong tool, the LLM drifted on a subtle instruction, the retrieval returned a mismatched chunk — and there's no structured trace. The prototype-to-production gap in agentic systems is not primarily a model problem or an orchestration problem. It is an observability problem: you cannot debug what you cannot see.

## Forces

- **Agent decisions compound.** A single agentic workflow might involve 5-15 LLM calls, multiple tool invocations, and state transitions — each of which can introduce or propagate error. Without structured logging at every step, failure modes are opaque.
- **PostHog learned this the hard way.** After launching and iterating on PostHog AI, their team found that the observability layer — logging inputs, reasoning traces, tool results, outputs — was non-negotiable for production. Debugging agent failures without it is described as "like debugging a production outage without logs."
- **LangGraph + LangSmith is the dominant production stack for this layer.** Typed state schemas with checkpointing (PostgreSQL, Redis) combined with LangSmith tracing gives teams durable state recovery plus full execution visibility. The alternative — custom logging — works but requires significant engineering investment.
- **The MCP server insight: expose your product before you build an agent.** PostHog found that 34% of AI-created dashboards used their MCP server without any custom agent. Validating product-as-tool before committing to product-as-agent is an observability-positive decision: MCP calls are inherently structured and traceable.

## The move

Build observability into the agent from the first prototype, not after the first incident:

- **Log the full execution trace at every step:** input context, model reasoning (if available via provider), which tools were called, their results, the final output. Treat this as schema, not prose — structured logs are queryable in a way free-text is not.
- **Use typed state schemas + checkpointing as your state observability layer.** LangGraph's typed state means every state transition is a typed event you can replay. PostgreSQL checkpointing lets you resume from any checkpoint. Redis checkpointing gives low-latency recovery. Choose based on consistency vs. throughput needs, not on developer preference.
- **Combine LangGraph's interrupt-and-resume with human-in-the-loop approval.** For regulated industries or high-stakes decisions, pause the graph, surface state to a human, and resume on approval. This is both a safety control and a debugging mechanism — you can inspect agent state mid-execution.
- **LangSmith or equivalent is the minimum viable observability stack for LangGraph users.** It provides trace-level visibility across the graph with minimal instrumentation. For non-LangGraph stacks, instrument custom spans around each LLM call, tool call, and state transition.
- **Fan-out/fan-in subgraphs provide both performance and observability gains.** Parallel subgraph execution cuts research agent latency 60-70% while keeping each branch independently traceable — a better observability signal than sequential chains.

## Evidence

- **Graebener.tech (primary blog):** "Observability is non-negotiable. When an agent makes a decision, you need to know why. Every agent call should log: the input context, the model's reasoning, which tools were called and their results, the final output." — March 2025 — https://graebener.tech/blog/building-with-ai-agents
- **PostHog engineering newsletter:** "34% of dashboards created by AI were done through their MCP server. Building MCP first validated demand before committing to a full agent." — Ian Vanagas, March 2026 — https://newsletter.posthog.com/p/what-we-wish-we-knew-before-building
- **Gheware DevOps blog (primary):** "LangGraph production failures are almost always state management failures. Typed state + checkpointing is the only reliable way to build multi-agent systems that survive pod restarts and production failures. Interrupt-and-resume enables human-in-the-loop approval flows without blocking threads." — Rajesh Gheware, March 2026 — https://devops.gheware.com/blog/posts/langgraph-production-state-management-enterprise-2026.html
- **SkillGen (framework comparison):** "LangGraph provides production-tested observability through LangSmith integration. State persistence across sessions — agents can resume interrupted workflows." — 2026 — https://skillgen.io/multi-agent-frameworks-compared-2026

## Gotchas

- **Structured logging without queryability is not observability.** Dumping JSON to stdout is not the same as having trace IDs you can correlate across LLM calls, tool calls, and downstream services. Instrument with correlation IDs from the start.
- **LangSmith pricing bites at scale.** It is excellent for development and low-volume production, but costs scale with trace volume. Budget for it or have a migration plan to self-hosted alternatives (OpenTelemetry + Jaeger, Phoenix by Arize) before you hit the pricing cliff.
- **Checkpointing without schema evolution strategy breaks at version boundaries.** When you change your state schema, old checkpoints become unreadable. Version your state schemas and have a migration path — this is the stateful equivalent of database migrations.
- **Human-in-the-loop looks good on paper but breaks at scale.** Interrupt-and-resume works for 10 approvals per day. At 1,000 approvals per day, you need either automated confidence thresholds (auto-approve low-risk paths) or a dedicated human review queue. Design for the scale you'll actually hit, not the scale you're targeting.
