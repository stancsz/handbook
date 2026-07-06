# S-557 · The Agent Stack Is Stratifying Into Six Layers

Single-monolithic agent stacks don't survive production. The infrastructure is fragmenting into distinct specialized layers — and the wrong move at any layer kills the whole system.

## Forces

- A single "agent" couples too many concerns: routing, reasoning, tool execution, memory, state, cost control
- Choosing one vendor for everything is single-cloud risk — 37% of enterprises now run 5+ models in production
- Context and data are the real defensible assets; models are interchangeable
- 40% of agentic AI projects will be canceled by end of 2027 due to unclear business value (Gartner)
- Over 40% of agentic AI projects face cancellation due to unclear ROI — cost visibility is a survival requirement, not an optimization

## The move

The enterprise agent stack is stratifying into **six layers**, each with different requirements, different tooling winners, and different defensibility profiles:

### Layer 1 — Sandbox / Execution Environment
Isolates agent code and tool calls from the host system. This is its own specialized problem.
- Tools: E2B, Modal, Shuru, Firecracker-based microVMs, AWS Lambda containers
- This layer has "very different defensibility profiles" from the rest — sandboxing failures are systemic
- Choosing a monolithic agent framework ignores this layer entirely

### Layer 2 — Orchestration / State Machine
Controls agent flow, branching, memory state, and multi-step execution.
- **LangGraph** (by LangChain): graph-based workflows, best production control, steepest learning curve — recommended as default for serious work
- **CrewAI**: role-based agent teams, fastest prototyping, hits scalability limits in 6–12 months
- **AutoGen** (Microsoft): collaborative multi-agent reasoning, best Azure integration, Semantic Kernel merger coming Q1 2026
- **n8n**: full-stack agent guide for non-engineers, workflow automation backbone
- **Custom / Temporal**: for teams with specific workflow durability requirements

### Layer 3 — Language Model Routing
Determines which model handles which task — the biggest cost lever.
- OpenAI (GPT-4o, o3): general purpose, highest cost
- Anthropic (Claude 3.5/3.7): best reasoning, strong for coding and analysis
- Google (Gemini 2.5 Flash): cheapest option, viable free tier for small-scale production (solo dev on $0/month LLM cost)
- Open-source (Llama 3.2, Mistral): local inference, privacy-sensitive workloads; 7B models handle RAG well; recursive agent workflows work on mistral-small

### Layer 4 — Tool Calling / Integration
How agents interact with the outside world.
- MCP (Model Context Protocol): rapidly becoming standard for tool registry
- Custom REST tool schemas: still common; CrewAI/LangGraph have first-class support
- Pattern: agents start with zero access, request tools with justification, human approves once (AgentKey pattern) — avoids the "paste API keys into .env" trap

### Layer 5 — Memory / Retrieval
Persistent state beyond single turns.
- **pgvector** (PostgreSQL): handles <5M vectors, 100–200ms latency acceptable — SQL + vector in one atomic query
- **Pinecone / Qdrant / Weaviate**: for scale or sub-50ms latency requirements
- **Hybrid search**: BM25 + dense retrieval (Reciprocal Rank Fusion) beats either alone — confirmed in every production postmortem
- **Rerankers**: Cross-encoders improve precision but can actually hurt quality depending on corpus — test empirically
- **Query transformation**: HyDE, multi-query decomposition, query expansion address the semantic gap between short queries and long documents

### Layer 6 — Observability / Governance
Cost, trace, eval, access control.
- **LangSmith**: primary tracing/eval for LangChain/LangGraph stacks
- **Arize Phoenix**: open-source observability for any LLM application
- **Custom logging**: common for teams that hit LangSmith pricing
- **Cost controls**: circuit breakers, per-agent budgets, hard limits on agentic loops — non-negotiable at production scale

## Evidence

- **HN Show HN post:** Solo dev runs 4 AI agents (content, engagement, leads, security) on Gemini 2.5 Flash free tier — $0/month LLM, ~$5/month infra (Vercel + Firebase). Uses OpenClaw orchestration, WSL2 runtime, 25 systemd timers. Hit a $127 Gemini bill in 7 days by creating a key from the wrong GCP project — always use AI Studio directly. — [https://news.ycombinator.com/item?id=47296664](https://news.ycombinator.com/item?id=47296664)
- **Blog post (Dubach):** The agent stack is stratifying into 6 layers with different defensibility profiles. 37% of enterprises use 5+ models in production. Single-provider lock-in is the new single-cloud risk. Most enterprise AI failures stem from shallow context, not poor models. — [https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Blog post (TrueFoundry):** Multi-agent orchestration has 4 patterns: sequential, parallel, hierarchical (supervisor), dynamic. Demos break on context limits, error propagation, runaway cost, and weak cross-agent observability. Gateway control plane gives per-agent observability and full audit trails. — [https://www.truefoundry.com/blog/multi-agent-architecture](https://www.truefoundry.com/blog/multi-agent-architecture)
- **NVIDIA Technical Blog:** Deployed AI-Q research agent (LangGraph-based) to 100s of concurrent users. Key lesson: "Every agentic application is different — generic rules like 'one GPU per 100 users' don't apply." Used NeMo Agent Toolkit to profile and estimate hardware needs during phased rollout. — [https://developer.nvidia.com/blog/how-to-scale-your-langgraph-agents-in-production-from-a-single-user-to-1000-coworkers](https://developer.nvidia.com/blog/how-to-scale-your-langgraph-agents-in-production-from-a-single-user-to-1000-coworkers)
- **RaftLabs analysis:** 4 patterns cover most production multi-agent designs. 57% of organizations already running agents. Inference costs compound to $5–8 per complex task in 4-agent workflows. 89% have tracing but only 52% have evals — debugging is guesswork. — [https://www.raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Enterprise RAG practitioner post:** Hybrid search beats pure semantic. Rerankers essential but must be tested empirically. pgvector handles more production workloads than vendors acknowledge for <5M vectors. Query transformation (HyDE, decomposition) closes the semantic gap. — [https://www.applied-ai.com/briefings/enterprise-rag-architecture/](https://www.applied-ai.com/briefings/enterprise-rag-architecture/)

## Gotchas

- **Going monolithic** — picking one framework to own the whole stack ignores that each layer has different innovation velocity and different defensibility. The sandbox layer especially is being reinvented independently.
- **No cost circuit breakers** — without per-agent budgets and hard loop limits, one runaway agent can exhaust a month's budget in hours. Gemini free tier misuse is the canonical example.
- **Skipping evals** — 89% have tracing but only 52% have evals. You can see what happened but not whether it was right.
- **Reranker over-reliance** — rerankers can degrade quality on certain corpora. The NVIDIA finding holds: test empirically, not theoretically.
- **Scaling with generic rules** — "one GPU per 100 users" doesn't apply to agents. Profile your specific application's token throughput, tool call frequency, and context window refill rate before capacity planning.
