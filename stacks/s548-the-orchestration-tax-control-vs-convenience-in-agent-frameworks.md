# S-548 · The Orchestration Tax — Control vs. Convenience in Agent Frameworks

You want to ship a multi-agent workflow. You have four reasonable options. Each one bakes in a different set of constraints — and the choice you make on day one is painful to reverse six months later. This is the orchestration tax: the upfront cost you pay in flexibility, lock-in, or complexity in exchange for not building everything from scratch.

## Forces

- **Prototype speed vs. production stability** — CrewAI gets you a working multi-agent demo in hours; LangGraph gets you a state machine you can actually reason about at 3am when something breaks
- **LangChain coupling vs. custom code** — CrewAI ships on LangChain. If LangChain has a bad week, your agents feel it. Reddit users report copying CrewAI's API concepts and reimplementing without LangChain for serious workloads
- **Graph expressiveness vs. operational simplicity** — LangGraph's StateGraph lets you model any control flow, but the mental model takes 1-2 days to internalize. Role-based crews (CrewAI) are immediately intuitive but constrain you to hierarchical task delegation
- **Observability vs. black boxes** — LangSmith's time-travel debugging and checkpointing are purpose-built for LangGraph. Other stacks require rolling your own tracing
- **Sandboxing is its own problem now** — agent code execution needs isolation. E2B, Modal, Firecracker wrappers are becoming a separate infrastructure layer, not an afterthought

## The move

The consensus from 2025-2026 practitioner discussions: **default to LangGraph for production**, and build the simplest thing that could work for prototypes — or go framework-free with raw tool-calling if the workflow is simple enough.

- **CrewAI**: Use only for demos and internal tooling where you control the environment and can tolerate LangChain updates. The role-based mental model (Director, Strategist, Producer) maps cleanly to business workflows. Decouple from LangChain if you ship it to users.
- **LangGraph**: The graph-based approach models state explicitly. Nodes are agents or functions, edges define transitions, state flows through the graph. Best MCP support of any framework — MCP tools are first-class graph nodes with full streaming. LangSmith provides time-travel debugging and checkpointing that other stacks lack.
- **Raw API (Claude/OpenAI tool use)**: If your workflow is a single agent with tools, just use the API directly. Prompt engineering and simple orchestration are achievable with string formatting. "Most of it is just simple prompt engineering" — r/LocalLLaMA practitioner who rebuilt their stack this way.
- **OpenAI Agents SDK**: Emerging as a fourth contender in 2026, worth evaluating alongside the others.
- **CrewAI production architecture**: Decouple the agent planning loop from LLM inference via an async task queue. This prevents head-of-line blocking and allows independent scaling of orchestration and model serving — reduces p95 latency by ~40% at 2,000 concurrent tasks. Plan for 16 GB vRAM minimum per GPU-backed worker.

The five-layer model for production agents (keneland.com practitioner guide):
1. **Human layer** — approval gates, tenant config, monitoring dashboards
2. **Orchestration layer** — task routing, state management, workflow definition
3. **LLM layer** — model selection, prompt management, cost/caching
4. **Tools layer** — MCP servers, REST integrations, code execution
5. **Data layer** — vector store, RAG pipeline, context assembly

Build the event bus as durable from day one (Kafka/Redpanda-backed), not in-process first. In-process is faster to prototype but events are lost on crash — retrofitting durability is expensive.

## Evidence

- **Framework decision guide (GitHub):** Production checklist for LangGraph vs. CrewAI vs. AutoGen vs. raw API. Verdict: "LangGraph — the boring, correct answer for production." — [benconally/ai-agent-framework-decision-guide](https://github.com/benconally/ai-agent-framework-decision-guide)
- **HN discussion on agent stack stratification:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." Multi-layer defensibility profiles analysis — [HN #47114201](https://news.ycombinator.com/item?id=47114201)
- **Practitioner architecture guide:** "Build the event bus as in-process first" is the wrong default — durable (Kafka/Redpanda) should be the starting point. Investment in agent output evaluation should be day-one, not retrofitted. Memory system tuning (thresholds, weights, merge strategies) only works when you have real agent interactions to measure against — [keneland.com](https://keneland.com/blog/building-production-agentic-ai-systems-a-practitioner-s-architecture-guide)
- **Opensoul HN launch:** 6-agent marketing agency stack (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) running autonomously on scheduled heartbeats — [HN #47336615](https://news.ycombinator.com/item?id=47336615)
- **CrewAI production architecture:** Async task queue decoupling reduces p95 latency ~40% at 2,000 concurrent tasks. 16 GB vRAM per GPU worker minimum. Kubernetes HPA on queue depth — [markaicode.com](https://markaicode.com/architecture/crewai-llm-architecture)
- **AI in Production 2025 (Ramp, GitHub, Adobe, Digits):** "Test model outputs directly with customers." Embedding drift degrades RAG silently over time — reindexing is prohibitively expensive so teams let it degrade — [digits.com](https://digits.com/blog/ai-in-production-2025)

## Gotchas

- **CrewAI without decoupling hits scaling limits fast** — the agent planning loop blocking on LLM inference is the #1 cause of production incidents in CrewAI systems
- **LangGraph's steeper learning curve pays off** — practitioners who started with CrewAI for prototypes report painful rewrites 6-12 months in when they need stateful, conditional workflows
- **Memory system tuning before you have data is wasted effort** — three-tier hybrid retrieval sounds impressive but the thresholds and weights only get tuned with real interaction volume
- **Naive RAG fails ~40% of enterprise queries** — vector similarity alone misses exact keyword matches; hybrid search (dense + sparse/BM25) is the production minimum, not an optimization
