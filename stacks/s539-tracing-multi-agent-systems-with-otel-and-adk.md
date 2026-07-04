# S-539 · Tracing Multi-Agent Systems — OTEL, ADK, and the Distributed Systems Parallel

Your agent works in isolation. You connect three of them and suddenly you have a failure mode you've never seen: agent A calls B, which calls C, which fails on a tool, which causes B to retry infinitely while A waits. You have no idea where it broke. This is early distributed systems all over again — and the same solution applies.

## Forces

- **Agent calls compound invisibly.** A single user request can trigger 15+ LLM calls, 8 tool invocations, and 3 cross-agent handoffs. Standard request logging captures none of this hierarchy.
- **Failure propagation is non-obvious.** An error in a leaf agent can manifest as a hang in a supervisor, making root-cause identification impossible without causal tracing.
- **Agents break assumptions that held for single requests.** Latency budgets, token limits, and retry counts that worked for one agent fail catastrophically in multi-agent orchestration — but teams discover this in production.
- **No standard observability contract.** Unlike HTTP services (which have OTEL conventions), agent systems have no agreed-upon trace semantics for tool calls, LLM decisions, or agent-to-agent handoffs.

## The move

Treat your agent system like a distributed service mesh. Apply the full observability stack from day one — not as an afterthought.

- **Instrument at the agent boundary.** Every agent-to-agent call, every tool invocation, every LLM round-trip gets a span. Use OpenTelemetry (OTEL) as the instrumentation layer — it handles the correlation IDs and hierarchical tracing automatically.
- **Use a purpose-built agent framework for debugging.** Google's ADK (Agent Development Kit) was described on HN as "a well thought through framework by a company that leads in both agents and observability" — its tight OTEL integration makes multi-agent trace correlation first-class.
- **Add circuit breakers per agent.** Each agent should have independent timeout and retry limits so a failing leaf agent doesn't cascade into a supervisor hang. Set per-agent SLOs: e.g., "Analyst agent must respond in <8s or escalate."
- **Log at decision points, not just outputs.** Record the full tool-call reasoning chain — not just the result — so you can replay why agent B chose to call the wrong tool.
- **Mirror the LGTM stack.** Loki + Grafana + Tempo + Mimir for logs, metrics, traces, and long-term storage. The same stack that monitors your microservices monitors your agents.
- **Build an agent-specific dashboard.** Standard APM dashboards miss agent semantics. Surface: tokens/request, tool-call success rate, cross-agent handoff latency, and hallucination-flagged outputs.

## Evidence

- **HN thread (skhatter):** Multi-agent debugging parallels early distributed systems. Solutions include OTEL + LGTM, circuit breakers per agent, and per-agent SLOs. Framed as a solved problem with existing tools — the gap is adoption. — https://news.ycombinator.com/item?id=47358618
- **Gheware comparison (Jan 2026):** LangGraph offers the most control for production tracing; CrewAI for fastest prototyping; AutoGen + Semantic Kernel for Azure-native observability. All three are LLM-agnostic but differ in how traceable agent state transitions are. — https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html
- **Xcapit production cost analysis:** Observability/monitoring accounts for 10-20% of total agent production cost ($500–$2,000/month for a mid-complexity production agent handling 1,000–5,000 sessions/day). Most teams under-budget this layer until the first production incident. — https://www.xcapit.com/en/blog/real-cost-ai-agents-production

## Gotchas

- **OTEL alone doesn't help without semantic conventions.** Raw spans without agent-specific attributes (tool name, model used, handoff target) are as opaque as logs. Define your own span naming and attribute schema early.
- **LGTM is heavyweight for single-agent systems.** If you're running one or two agents, the full observability stack adds operational complexity that exceeds the debugging benefit. Start with LangSmith or Phoenix for lightweight agent-native tracing before graduating to the full ELK/Grafana stack.
- **Agent red-teaming is often missing from observability.** OWASP-aligned adversarial testing (prompt injection, approval bypass, memory poisoning) is not captured by standard trace dashboards — it's a separate concern that needs its own evaluation harness.
