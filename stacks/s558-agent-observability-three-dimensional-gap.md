# S-558 · Agentic Observability — The Three-Dimensional Gap

Traditional APM assumes agents are deterministic functions with observable failure modes (HTTP codes, latency spikes, error rates). AI agents are probabilistic reasoning loops with failure modes that APM cannot see. Teams shipping to production discover this the hard way.

## Forces

- Traditional APM answers "did it return 200 or 500?" — agents return plausible nonsense with 200 OK
- Agent failures are emergent: a 6-step reasoning chain where step 3 drifts slightly produces an answer that looks correct but is wrong
- Multi-agent systems compound this: failure may live in agent interaction logic, not individual agent behavior
- 57% of companies now deploy agents in production, but observability tooling maturity lags by 12-18 months
- Hallucination and reasoning drift have no HTTP status code — they require purpose-built evaluation
- Budget overruns from runaway agent loops are the #1 production incident type, yet most teams have no automated detection

## The move

Build a **three-pillar observability stack** that covers the full agent lifecycle — not just "was it up?" but "was it right?"

- **Trace**: Capture every decision hop — tool call, LLM call, state transition, tool result. OpenTelemetry is the standard transport; extend Semantic Conventions with custom span attributes for LLM-specific data (model, temperature, token counts, tool name). LangSmith processes 1T+ spans monthly from 400+ companies in production. For multi-framework environments (LangGraph + LlamaIndex + custom), Phoenix auto-instruments LangGraph, CrewAI, AutoGen, DSPy, and Haystack — and is self-hostable with full data ownership.
- **Eval**: Quantify output quality, not just delivery. LLM-as-Judge is the dominant production pattern — use a stronger model to evaluate responses against golden sets and real traffic. Gate deployments on hallucination scores and win-rate against baseline. The Elysiate RAG production guide recommends: "log every hop (rewrite → retrieve → rerank → assemble → generate) with cost/latency attribution and cache hits" and gate deployments by win-rate and hallucination scores.
- **Debug**: Reconstruct failures after the fact. Time-travel replay (replay agent execution from any checkpoint), loop detection (flag when the same tool is called N times with similar inputs — a primary runaway agent signal), and chain-of-thought auditing. Budget circuit breakers belong here too: alert when spend exceeds threshold within a sliding window, and hard-kill agents that exceed cost limits.

**Staging guide by team maturity:**

| Stage | Priority | Toolset |
|-------|----------|---------|
| Prototyping | Low friction, fast feedback | LangFuse (self-hosted, generous free tier) |
| Production | Full observability, trace quality | LangSmith (LangChain ecosystem) or Phoenix (multi-framework, self-hosted) |
| Enterprise | Compliance, audit trails, governance | Datadog LLM Observability or IBM Watsonx (governance focus, enterprise pricing) |

**Platform-specific signals observed:**
- LangSmith: 400+ companies, 1T+ spans/month, 85% GPT-4o tool-calling accuracy measured. Best integration with LangChain/LangGraph.
- Arize Phoenix: OpenTelemetry-native, 12+ LLM providers, 10+ frameworks auto-instrumented. Best for teams needing data ownership and multi-vendor model routing.
- LangFuse: Self-hostable, generous free tier, good for teams iterating fast without committing to a single framework.

## Evidence

- **Engineering blog (Microsoft ISE):** Multi-agent systems require four fundamental requirements: accurate agent selection, optimized LLM usage, efficient orchestration, and scalability — observability is what proves these are met in production, not just in tests. — [devblogs.microsoft.com/ise/multi-agent-systems-at-scale](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale)
- **Research article (Zylos AI):** Enterprise AI operational cost averages $85,521/month (2025). Agentic loops have cost teams $15 in 10 minutes to $47,000 over 11 days. 60-85% of spend is recoverable through caching, routing, and budget enforcement — all of which require observability as prerequisite. — [zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)
- **Primary production account (Calder's Lab):** MeetSpot v1 showed 92% test success, 55% production success — a 37-point gap invisible without per-hop tracing. Cost ran $847/month vs. $200 budgeted. Optimized to $312/month after instrumenting and identifying redundant calls and bad caching. — [calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough](https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough)

## Gotchas

- Logging every LLM call generates massive volume (1T+ spans/month for LangSmith users) — budget storage costs and implement intelligent sampling before shipping everything to your observability backend
- LLM-as-Judge evaluation introduces circularity risk (evaluator model has same failure modes as agent model) — cross-validate with human-labeled golden sets, especially for high-stakes outputs
- Loop detection thresholds are workload-specific: a 5-call limit works for a web research agent but breaks a code generation agent that legitimately calls the same tool multiple times with different arguments — tune per agent type
- Without budget circuit breakers, a single misconfigured agent prompt can generate thousands of dollars in charges before a human notices — this is not a hardening step, it is a prerequisite for production
- Agent observability is not a one-time setup — evaluation criteria drift as requirements evolve; build evaluation as a continuous process gated into deployment, not a one-time baseline
