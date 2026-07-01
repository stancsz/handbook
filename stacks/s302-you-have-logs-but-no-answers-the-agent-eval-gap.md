# S-302 · You Have Logs, But No Answers: The Agent Eval Gap

Teams instrument their agents. They ship traces, store outputs, set up dashboards. Then a production incident hits and they realize: the logs tell them something failed, but not whether it was right. The gap between observability and evaluation is where production agent projects quietly die.

## Forces

- **Debugging multi-agent systems is not software debugging.** Tracing a 4-agent workflow across model calls, tool invocations, and handoffs requires more than log aggregation — it requires ground-truth evaluation at every decision point.
- **Eval comes last or never.** 89% of teams have observability (traces, dashboards, metrics), but only 52% have evals. The instinct is to build the agent first, measure later. That instinct produces systems that fail silently in ways logs never surface.
- **Multi-agent inference costs compound the stakes.** A 4-agent orchestrator-worker workflow costs $5–8 per task. Without evals, you're burning that budget on a system you cannot verify is improving.

## The move

Build evaluation infrastructure before the agent is done, not after. The minimum viable eval stack for a production agent system:

**1. Separate retriever and generator scoring.** Don't score the whole output. Score whether the retriever surfaced the right context (recall, MRR@K) and separately whether the generator used it correctly (groundedness, faithfulness). Naive single-index RAG fails ~40% of the time at retrieval — but a smarter model just hallucinates more confidently from the wrong context.

**2. Deterministic output validators at every agent boundary.** Every handoff between agents must have a schema-validated contract. Validators should fail loudly and deterministically. Silent failures at handoff boundaries are the primary failure mode in multi-agent pipelines.

**3. Score context assembly quality, not just output quality.** Models pay disproportionate attention to the beginning and end of context windows. System instructions and task-relevant context should anchor the boundaries. Track assembled context token count and relevance density per step — not just the final answer.

**4. Measure at every commit, not every deploy.** Eval suites that only run pre-deploy become ceremonial. Integrate scoring into the development loop so regressions surface before they reach production.

**5. Log structured metadata for every tool call.** Tool name, arguments, result, latency, cost, and whether the result was used — not just the final LLM output.

## Evidence

- **Industry survey:** 89% of teams have observability for agent systems, but only 52% have evaluation frameworks. The gap explains why multi-agent debugging remains mostly guesswork — [RaftLabs, Multi-Agent Systems Guide, Nov 2025](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Benchmarking data:** Naive single-index RAG fails to surface the right passage on ~40% of real enterprise queries. A stronger generation model doesn't fix it — it confidently hallucinates from wrong context. [Ilir Ivezaj, RAG Architecture Patterns, March 2026](https://ilirivezaj.com/ai/rag-architecture)
- **Engineering post:** Teams that built evaluation infrastructure before completing the agent consistently shipped more reliable systems. Tool-calling architecture and context assembly quality matter more than model selection. [Kalvium Labs, Building AI Agents: Architecture Tradeoffs, March 2026](https://www.kalviumlabs.ai/blog/building-ai-agents-architecture-tradeoffs/)

## Gotchas

- **Logs show you what happened; evals show you if it was right.** A trace that shows "agent called tool X with arguments Y" tells you nothing about whether Y was the correct arguments. You need ground-truth comparison at decision points.
- **Eval latency is real latency.** Full evaluation suites add 30–120s to test runs. Price this into your CI pipeline or teams will disable them.
- **Context length limits interact badly with eval tooling.** Assembling 5-agent conversation history into an eval prompt can exhaust context windows. Keep eval prompts lean — score the step, not the session.
- **Framework defaults create false confidence.** LangSmith, Phoenix, and custom logging all produce beautiful traces. Beautiful traces are not evaluation. Evaluate outputs against ground truth, not traces against expectations.
