# S-228 · LLM Selection for Agents — The Real Decision Factors

Choosing an LLM for an agent is not the same as choosing one for a chatbot. The decision changes once the model is running in a loop — calling tools, maintaining state across steps, and making downstream API calls that cost real money. Production teams that made the wrong call didn't pick a "worse" model. They used the wrong criteria.

## Forces

- **Benchmarks don't predict agent performance** — the factors that matter for agents (tool-call reliability, instruction adherence under load, JSON schema correctness, prompt-cache hit rates) are not on leaderboard scores
- **The "best model" flips by task type** — Claude wins for long-running agents with 5+ tool calls; GPT wins for high-volume, latency-sensitive pipelines with simple prompts; the split is operational, not capability-based
- **Context caching changes the economics** — an agent re-sending 100K tokens per step across dozens of steps benefits from cache reads that can cut LLM cost by 60–70%, but only if the model and prompt structure support high cache hit rates
- **Tool-call reliability under pressure is non-negotiable** — a 5% tool-call failure rate sounds acceptable; in a 20-step agent it compounds to near-certain failure by step 20
- **Failure modes differ** — GPT degrades gracefully under long context (token throughput stays high); Claude degrades in quality but stays reliable; the right choice depends on which failure mode your use case can absorb

## The Move

Frame LLM selection for agents around these five operational criteria, not benchmark rankings:

- **Tool-call reliability at depth** — test the model with 5+ sequential tool calls using your actual schema, not a toy example. Look at: does it produce valid JSON on every call? Does it follow the argument schema? Does it stop calling tools prematurely?
- **Cost per successful task, not cost per million tokens** — a model that costs 2× more per token but completes 40% more tasks has better economics. Track this metric, not raw token price
- **Prompt-cache hit rate at your context size** — Claude's cache read pricing is ~10× cheaper than full input pricing. At agent scale (100K+ tokens per run), a 60% cache hit rate cuts LLM costs by ~35%. Model the cache hit rate before deciding
- **Instruction adherence under concurrent load** — production agents share contexts and system prompts across concurrent requests. Test whether the model maintains guardrail adherence when handling multiple simultaneous tasks
- **Failure mode mapping** — decide whether you can tolerate slower degraded output (GPT) or need the agent to fail explicitly and loudly (Claude). For customer-facing agents, explicit failure is almost always better

## Evidence

- **Engineering blog:** ClawPulse monitored ~12M production requests across agentic AI systems and found Claude's advantage in tool-call reliability and prompt-cache economics compounds to lower cost-per-successful-task for long-running agents, while GPT wins for high-volume, simple task pipelines where latency is the primary constraint — [ClawPulse](https://www.clawpulse.org/blog/anthropic-claude-vs-openai-gpt-in-production-a-2026-engineering-comparison)
- **Comparison analysis:** Gheware's 2026 framework comparison found LangGraph (Python/TypeScript) with 90K+ GitHub stars is the production orchestration standard at Uber/LinkedIn/Klarna, noting the orchestration framework choice matters as much as the model choice — [Gheware](https://devops.gheware.com/blog/posts/langgraph-vs-autogen-vs-crewai-comparison-2026.html)
- **Cost data:** Inventiple tracked 4 production agentic systems over 6 months and found per-task costs ranging from $0.023 (simple triage, LangGraph, 2.4 avg steps) to $0.41 (multi-agent crew, CrewAI, 8.2 avg steps), with cost-per-task being the metric teams should optimize, not token price — [Inventiple](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)

## Gotchas

- **Testing with toy examples masks real failures** — tool-call reliability tests must use your actual schema, your actual error handling, and your actual context length. A model that works on a 3-step demo may fail at step 12 in production
- **Route by task complexity, not by static config** — a single model for all agent tasks is a cost overpay for simple tasks and a capability underrun for complex ones. Implement dynamic routing: cheap fast models for triage steps, capable models for reasoning steps
- **Anthropic's agent features are moving fast** — Claude 4's Programmatic Tool Calling, Advisor Strategy, Tool Search, and MCP Connector are in public beta with 1M-token context. These materially change the tool-use loop economics and should be re-evaluated if you evaluated Claude on earlier versions
- **Cache invalidation is a silent cost** — prompt cache hits depend on prefix matching. If your system prompts or context structures vary per request, your cache hit rate will be far lower than the theoretical maximum
