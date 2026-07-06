# S-519 · Production Agent Cost Engineering and Observability: The Three Things Nobody Instruments Until They Burn Money

When a single support ticket resolution costs $1.10 and a runaway agent loop costs $47,000 over eleven days, the gap between "it works in demos" and "it runs in production" is measured in dollars. The teams that stay operational have three things locked down before they deploy: a cost model, an observability pipeline, and an eval harness. Most teams retrofit all three after their first incident.

## Forces

- **Enterprise AI spend doubled from $3.5B to $8.4B between late 2024 and mid-2025** — the compounding nature of agentic workflows (5-20 LLM calls per task) makes token costs non-linear and easy to underestimate until the monthly bill arrives.
- **Retrofitting observability costs 10x more than instrumenting on day one** — agent reasoning traces, tool call sequences, and per-turn quality signals are invisible to standard APM (Datadog, New Relic) and require purpose-built instrumentation.
- **Final-answer eval is insufficient for agents** — a correct answer reached through a policy-violating tool call is a failing trajectory. The metric that matters is not the output but the path, and most teams only score the output.
- **Cost circuit breakers are not optional** — agent loops, context overflow, and reasoning drift can compound costs at 10x+ rate within minutes, and teams have reported incidents ranging from $15 in ten minutes to $47,000 over eleven days.

## The Move

The production agent stack requires three instrumentation layers that must be built in from the start:

**1. Cost model as a first-class concern**
- Model token cost per call (input + output + context window), not just LLM API price. A single support ticket resolution involves: classify ($0.01) + analyze context ($0.18) + generate draft ($0.22) + refine ($0.31) + summarize ($0.08) = $0.80 in LLM calls alone. Tool calls add $0.05-$0.17 on top. External API calls (Serper, Pinecone, email) add further cost.
- Route models by task complexity: small/fast models for classification and routing ($0.001/call), frontier models only for generation and reasoning.
- Use prompt caching to recover 60-85% of recoverable spend — cache system prompts and stable context across agent turns.
- Implement hard budget enforcement with per-task cost limits and circuit breakers. Cap maximum turns and tokens per workflow before deployment.

**2. Observability: distributed tracing + eval + debugging**
- Use OpenTelemetry as the backbone, extended with custom LLM span attributes (tokens, model, temperature, tool calls). Standard APM cannot interpret agent intent or reasoning chains.
- Log every agent call with: input context, model reasoning, tool calls and results, final output. Without this, debugging agent failures is debugging a black box.
- Implement tiered sampling (importance-based) to reduce storage costs by 80% while retaining full traces for failures and high-value interactions.
- LangSmith processes traces from 400+ companies in production. LangFuse offers self-hosted tracing for data-sensitive workloads. Arize Phoenix excels at embedding-level observability for RAG-heavy agents.

**3. Eval harness: trajectory-level, not just final-answer**
- Three layers of evaluation: final-answer (score the last message), trajectory (score the sequence of steps, tool calls, retries, recovery), and per-turn (detect jailbreaks, leaked prompts, policy violations in production).
- LLM-as-judge requires structured rubrics, multi-model cross-validation, and human calibration to be reliable — unguided LLM judging has systematic failure modes.
- Key production eval metrics: tool-call accuracy, trajectory coherence, memory retrieval efficiency, task completion rate, cost-per-task, and loop rate.
- Automated eval workflows (LangSmith, Braintrust, DeepEval, RAGAS) handle regression; human-in-the-loop (HITL) remains critical for multi-agent systems where emergent behaviors are difficult to quantify through metrics alone.
- Amazon's agentic evaluation framework uses two components: automated evaluation for standardized regression, and human judgment for inter-agent communication quality, coordination failure, and logical consistency across agents contributing to a single decision.

## Evidence

- **Production cost breakdown:** A real support ticket resolution workflow costs $1.10 total — $0.80 LLM (5 calls), $0.17 tool calls (MCP + API), $0.13 external APIs. Most teams cannot answer "what does one task cost" until they instrument for it. — [AgentMeter](https://www.grislabs.com/blog/agentmeter/how-much-do-ai-agents-cost)
- **Enterprise spend and recovery potential:** Enterprises averaged $85,521/month in AI operational costs as of 2025. 60-85% of spend is recoverable through prompt caching, model routing, and budget enforcement. Runaway agent loops have cost teams $15 in 10 minutes to $47,000 over 11 days. — [Zylos Research](https://zylos.ai/en/research/2026-05-02-ai-agent-cost-engineering-token-economics/)
- **Observability stack:** LangSmith processes traces from 400+ companies. 89% of multi-agent teams have observability but only 52% have evals — the gap means debugging is largely guesswork. The three-pillar architecture (traces + eval + debugging) is the standard pattern from Amazon, Salesforce, and enterprise teams. — [QubitTool](https://qubittool.com/blog/agent-observability-engineering), [OPTIN AMP OUT](https://www.optinampout.com/blogs/agent-observability-transforms-production-ai.html)
- **Eval failure modes:** A correct final answer reached in 20 steps with two policy-violating calls is a failing trajectory. Offline evals miss 90% of production failure patterns (infinite loops, tool misuse, hallucinated actions, context overflow, reasoning drift). Per-turn classifiers detect jailbreaks and prompt leakage that are invisible to trace-level logging. — [MorphLLM](https://www.morphllm.com/ai-agent-evaluation)

## Gotchas

- **Standard APM (Datadog, New Relic) cannot observe agents** — they track latency and error rates but not agent reasoning chains, tool-call intent, or trajectory quality. Purpose-built LLM observability is required.
- **LLM-as-judge without structured rubrics is unreliable** — unguided judging produces high variance scores. Use multi-model cross-validation and calibrate against human judgments at least quarterly.
- **Prompt caching requires stable, repeated context** — it helps for system prompts and recurring workflows but provides minimal benefit for highly dynamic, single-pass tasks. Assess caching eligibility per workflow type.
- **Per-turn eval requires instrumentation at call time** — you cannot reconstruct per-turn quality signals from final-answer logs. Instrument from day one; retroactive extraction is lossy and incomplete.
- **Cost circuit breakers must be enforced at the orchestration layer** — relying on monitoring dashboards to catch runaway agents is too slow. Budget limits and turn caps should halt execution automatically.
