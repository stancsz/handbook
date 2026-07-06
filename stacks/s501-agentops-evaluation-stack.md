# S-501 · AgentOps: Evaluating and Observing Production Agent Systems

The demo works. The pilot works. The production deployment is a different system — and you will not understand it without tracing. Agents in production fail silently, cost unpredictably, and degrade gradually. The teams winning with agentic AI in 2026 are not the ones with the best prompts. They are the ones who can see inside the loop.

## Forces

- **Reliability gap:** The best current AI agent solutions achieve goal completion rates below 55% when working with CRM systems — a fundamental gap between demo and production reliability. ([Maxim AI](https://www.getmaxim.ai/articles/ensuring-ai-agent-reliability-in-production))
- **Invisible failures:** Action hallucination (agent claims it succeeded when the tool call failed) produces confident, plausible text that passes every toxicity and PII filter. The failure mode is invisible to traditional guardrails.
- **Cost compounding:** Multi-agent systems compound inference costs to $5–8 per complex task. Without per-trace attribution, you cannot know which workflows are profitable.
- **Evaluation lag:** Teams ship prompts fast and evaluate slowly. By the time a regression is noticed, days of bad outputs have been generated.
- **The observability paradox:** You need to instrument agents before you know what matters. But you cannot retroactively add tracing to a system you do not understand.

## The move

Build AgentOps before you need it. Instrument every agent boundary, every tool call, every state transition, and every LLM call. Then use that trace data to drive three closed loops: evaluation (is the output right?), cost control (is this workflow profitable?), and reliability (did the action actually happen?).

### Instrument at every boundary

- **Trace root tagging:** Tag every trace at its entry point with user ID, tenant ID, task type, and agent version. Propagate those tags through all child spans. Cost attribution is impossible without it.
- **Tool call wrapping:** Wrap every tool call (MCP, REST, function) with a span that records the input, the actual response code, latency, and whether the error was surfaced to the agent or silently discarded.
- **State transition logging:** Log every agent state change (planning → executing → reviewing → done) with a timestamp and the deltas. This is what you need when a workflow silently loops or dead-ends.

### Evaluate continuously, not retrospectively

- **Faithfulness scoring:** After generation, run a lightweight judge model that checks: does the output actually claim only what the retrieved documents support? A research agent retrieving 8 chunks but generating a fact from outside them is a documented production failure pattern. ([FutureAGI](https://futureagi.com/blog/agentic-rag-systems-2026))
- **Per-step assertions:** Treat each agent step as a unit test. If the agent calls a SQL tool, assert the query syntax is valid before execution. If it retrieves documents, assert non-empty results before proceeding.
- **Regression suites on production traces:** Take every failed trace from production and turn it into an eval case. Score the agent against it automatically on every deploy.
- **Self-check loops over one-shot generation:** The gap between retrieval and generation must include a faithfulness gate — not just retrieval quality, but whether the agent actually used what it retrieved. ([FutureAGI](https://futureagi.com/blog/agentic-rag-systems-2026))

### Use tail-based sampling, not head-based

- **Keep every anomalous trace:** Failed traces, expensive traces (>3x median cost), and timeout traces must be retained in full. Head-based (random) sampling at high volume drops exactly the traces you need when an incident hits.
- **Sample the happy path aggressively:** Happy-path traces at full fidelity are storage waste. 1% of successful traces retained is sufficient for regression suites.
- **Drift is a first-class signal:** Model updates, prompt changes, and retrieval corpus changes all cause behavioral drift. Track trace-to-trace variance in output length, tool call count, and error rate as a separate metric from success rate. ([Extency](https://extency.com/blog/agentops-observability-evals-agentic-ai-2026))

### Make cost visible at the workflow level

- **Per-workflow cost:** Compute token cost per workflow execution end-to-end. A 6-agent DeepSearch query costing ~$2 USD per query is only viable if the output value justifies it. ([HN user jsemrau](https://news.ycombinator.com/item?id=44301809))
- **Model cascading:** Route simple queries to cheaper models; reserve expensive models for steps that genuinely need them. Semantic caching reduces redundant calls on repeated queries by 30–60%.
- **Iteration budgets:** Set maximum loop counts per workflow. A planning agent that loops 50 times is a runaway cost center. ([FRE|Nxt Labs](https://www.frenxt.com/research/multi-agent-architecture-guide))

## Evidence

- **Multi-agent reliability data:** Research from Maxim AI (2025) documents that the best AI agent solutions achieve goal completion rates below 55% on CRM operations, confirming that the reliability gap is structural, not a tuning problem — [URL](https://www.getmaxim.ai/articles/ensuring-ai-agent-reliability-in-production)
- **Gartner adoption surge:** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025, with 57% of organizations already running agents in production — [Microsoft ISE Blog](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale)
- **Production cost data:** Simple production agents run $500–$2,000/month; mid-market task-execution agents $1,500–$5,000/month; enterprise multi-agent stacks $4,000–$12,000+/month. Build costs: $8K–$25K for single-task, $40K–$120K for task-execution, $80K–$200K+ for complex multi-agent — [AI Agents First](https://aiagentsfirst.com/ai-agent-deployment-cost-2026)
- **Tail-based sampling pattern:** Teams must keep every failed, expensive, or anomalous trace and sample happy paths aggressively; head-based sampling at volume drops the traces needed during incidents — [Extency](https://extency.com/blog/agentops-observability-evals-agentic-ai-2026)
- **Agent decomposition timing:** Add agents only when you hit a genuine boundary (audience, timing, trust); premature decomposition creates debugging complexity that outweighs the specialization benefit — [FRE|Nxt Labs](https://www.frenxt.com/research/multi-agent-architecture-guide)
- **Agentic RAG failure pattern:** A production research agent retrieved 8 chunks, used 6, and fabricated a fact from none of them. No span scored faithfulness. No judge gated the answer. The self-check loop was the missing component — [FutureAGI](https://futureagi.com/blog/agentic-rag-systems-2026)

## Gotchas

- **Tracing overhead is real but worth it:** Adding full instrumentation adds 5–15ms per span. Batch writes to your trace store and async flush. The cost is a fraction of the cost of not knowing why your agent failed at 2am.
- **Eval quality depends on eval set quality:** If your eval cases don't cover the failure modes you actually see in production, you will pass evals and fail in the field. Build eval cases from production traces, not from synthetic scenarios.
- **Tool call success is not agent success:** The agent may call the right tool with the right parameters and still produce wrong output. Instrument the tool response, not just the call.
- **Cost attribution breaks at agent handoffs:** If you do not propagate cost tags through agent-to-agent handoffs, you will only see the orchestrator's cost, not the specialist's.
- **The 55% completion rate is your baseline, not your ceiling:** That number is a floor for what current systems achieve without structured AgentOps. Structured evaluation and closed-loop feedback consistently push completion rates above 80% in documented deployments.
