# S-573 · The Stack Is Not a Stack — It's Six Layers, and Only Two Are Defensible

Your agent runs on LangGraph, talks to a Claude model, stores embeddings in Pinecone, and deploys on Modal. You feel like you have a "stack." You don't. You have six loosely glued layers, and four of them have more defensibility than a commodity — meaning someone else will build a cheaper, faster version and you'll have to switch. The two layers that actually compound are the ones most teams neglect.

## Forces

- **Model commoditization is near-complete.** OpenAI, Anthropic, Google, and open-source (Llama, Mistral, Qwen) have converged enough that the model is table stakes, not moat — corroborated by the fact 37% of enterprises now run 5+ models in production without competitive differentiation from the choice.
- **Infrastructure is rented, not built.** Modal, Modal, Modal, AWS Bedrock, and vLLM all do the same job. The layer changes fastest and offers the least durable advantage.
- **Orchestration frameworks are evaporating.** LangGraph, CrewAI, and AutoGen are converging on similar primitives. The framework you pick today will be replaced or subsumed within 18 months.
- **Context and organizational world models compound.** The data you feed the agent, the retrieval architecture, and the institutional knowledge encoded in prompts and tools — these are what get better over time and cannot be replicated by a competitor buying the same SaaS.
- **Security is the least glamorous and most underestimated layer.** Credential leakage through context windows, prompt injection via tool results, and lack of per-boundary schema validation are causing real production incidents — not theoretical risks.

## The move

Treat the agent stack as six independent layers. Invest disproportionately in the top two. Do not mistake renting infrastructure for building capability.

### The six-layer stack (ranked by defensibility)

1. **Security** — Access controls, permissions, compliance guards. This layer is underestimated until it isn't. The context window is a credential aggregation point in most agentic systems. Every tool-result boundary needs a validated schema contract.
2. **Context** — Memory, retrieval, RAG, knowledge graphs, session state. This is the organizational world model. It compounds. It is the hardest to rebuild if you switch everything else. Embedding model choice sets the retrieval ceiling; a reranker (Cohere Rerank v3, bge-reranker) with hybrid retrieval (dense + BM25) is the cheapest upgrade that fixes most retrieval failures.
3. **Agent Logic** — The reasoning, planning, and decision-making layer. Prompting strategy, tool selection accuracy, error recovery paths. This lives in your prompts and tool schemas.
4. **Tooling** — MCP servers, REST integrations, code interpreters, browser automation. The tool surface area. Tool selection accuracy drops below 90% once you exceed 12 tools — split into sub-agents before you hit this wall.
5. **Orchestration** — LangGraph, CrewAI, AutoGen, Temporal. These define how agents coordinate. All three are converging; pick for team familiarity and debugging ergonomics, not long-term lock-in.
6. **Infrastructure** — Modal, Modal, Docker, Kubernetes, serverless functions, GPU scheduling. Rented. Commodity. Swappable. Do not build unique capability here.

### Layer-specific decisions

- **RAG complexity ladder:** Naive chunk → hybrid retrieval + reranker → parent-document retrieval → query decomposition → GraphRAG → agentic RAG. Most teams start at level 3 when they should start at level 2. The jump to agentic RAG with knowledge graphs cut hallucination ~62% across 47 production deployments.
- **Multi-agent triggers:** Split when tool selection accuracy drops below 90% with 12+ tools, when response latency exceeds acceptable thresholds, or when context window utilization doubles costs. Four orchestration patterns cover most cases: hierarchical, pipeline, orchestrator-worker, peer-to-peer. Use validated schema contracts with version numbering at every agent-to-agent handoff — untyped handoffs are the leading cause of multi-agent workflow failures.
- **Framework selection:** LangGraph for complex, stateful, production-grade workflows with detailed control. CrewAI for fastest path to working prototypes (teams hit scaling limits within 6-12 months). Microsoft Agent Framework for Azure-ecosystem enterprise (GA Q1 2026). All three are model-agnostic.
- **CrewAI async bottleneck:** Coupling the agent orchestration loop directly to synchronous LLM inference creates a single-threaded chokepoint. Fix: split the agent coordinator from LLM inference via an async task queue (RabbitMQ, Redis + Celery). Stateless, replicated coordinator nodes dequeue, compose prompts, push to a GPU worker pool.

## Evidence

- **HN discussion + blog post:** The enterprise AI agent stack is decomposing into six specialized layers with different defensibility profiles. "The defensible asset is not the model. It's the organizational world model." 37% of enterprises run 5+ models in production, confirming model is not the differentiator. — [HN thread](https://news.ycombinator.com/item?id=47114201), [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Multi-agent survey:** 57% of organizations have agents in production, but only 2% are at full production scale. 89% have observability; only 52% have evals. 1,445% surge in multi-agent inquiries (Gartner Q1 2024 → Q2 2025). 40% of agentic AI projects at risk of cancellation by 2027. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide), citing LangChain survey (1,300+ professionals) and Gartner
- **Production cost case study:** Ed-tech agent hit 92% success in test, 55% in production. Monthly cost: $200 budgeted → $847 actual (4.2x overrun). 47 different data format issues. 3 catastrophic failures totaling $18,700 in losses across ~$103K invested over 18 months. — [Calder's Lab](https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/)
- **Cost engineering:** Enterprise AI operational cost averages $85,521/month (2025). 60–85% of spend is recoverable through prompt caching, model routing, and budget enforcement. Runaway agent loops cost $15 in 10 minutes to $47,000 over 11 days. 4-agent orchestrator-worker workflow: $5–8 per complex task. — [Zylos Research](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/)
- **RAG benchmark:** Agentic RAG with knowledge graphs cut hallucination ~62% across 47 production deployments. Hybrid retrieval + reranker is the highest-ROI first upgrade. Embedding model sets the retrieval ceiling: OpenAI text-embedding-3-large (64.6 MTEB) is safe default; Qwen3-Embedding-8B tops multilingual at 70.58. — [AIThinkerLab](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns)

## Gotchas

- **Building on orchestration framework primitives is not the same as building capability.** If your competitive logic lives in LangGraph graph definitions, you're one framework migration away from rewriting it.
- **The test/production gap is not a model quality issue — it's a data distribution issue.** Agents are tested against clean, predictable inputs. Production data has 47 different formats, implicit assumptions, and edge cases. Budget 3–4x the expected cost and test against adversarial inputs before launch.
- **Credential propagation through context windows is the #1 unaddressed security risk.** Every tool result that flows back through the LLM before the next tool call is a potential credential leak. Schema-validate tool result boundaries, never pass raw API responses into context.
- **Observability without evals is theater.** 89% of teams have logging; only 52% have evaluation suites. You cannot improve what you cannot measure, and measuring tool-call accuracy and task completion rates requires intentional eval infrastructure — it does not come with LangSmith out of the box.
