# S-654 · The Stratifying Stack

The agent stack is no longer a monolith — it has fractured into six specialized layers with independent rates of change, different defensibility profiles, and incompatible selection criteria. Teams that treat it as one decision (pick a framework, done) end up with brittle systems they can't debug, extend, or swap.

## Forces

- **One integration layer collapses under scale.** Before MCP, connecting N models to M tools meant N×M bespoke connectors. At 3 models × 10 tools = 30 integrations. At 5 models × 30 tools = 150. The math collapses.
- **Context is the moat; models are commoditizing.** Foundation model prices have dropped 95%+ in 18 months. The defensible asset is the organizational world model and process knowledge — not the model underneath.
- **Orchestration choices have long tails.** Picking CrewAI for speed and migrating to LangGraph at scale means rewriting agent definitions, tool schemas, and state management. The framework is not swappable without surgery.
- **Execution isolation is its own problem.** Agents need sandboxed tool execution. Running that in-process with the orchestrator couples security policy to workflow logic.

## The move

Split the stack into six layers and treat each as an independent procurement decision:

1. **Context Layer** — The organizational world model: what the agent knows about your processes, data, and business rules. This is where lock-in and defensibility live. Invest here most heavily.
2. **Orchestration Layer** — LangGraph for production systems needing deterministic routing, checkpointing, and human-in-the-loop; CrewAI for fast prototyping; OpenAI Agents SDK if you're all-in on the OpenAI ecosystem; avoid going multi-framework.
3. **Execution Layer** — Sandboxed tool runtime (E2B, Modal, Shuru, or custom Firecracker wrappers). Decouple from orchestration — the workflow engine should call an execution host, not execute tools directly.
4. **Tool Integration Layer** — MCP (Model Context Protocol). Adopt it now. One implementation per tool, universal compatibility across all MCP-compliant models. Stop building custom REST wrappers per model per tool.
5. **Retrieval Layer** — RAG is not a toggle. Chunk on structure (headings, paragraphs), not fixed character counts. Use hybrid search (vector + keyword). Re-rank over-fetched candidates with a cross-encoder. Query decomposition for multi-hop questions.
6. **Infra Layer** — Containerize agent logic separately from the LLM runtime. Budget circuit breakers at the API gateway level. Prompt caching and intelligent model routing as defaults, not optimization.

## Evidence

- **Blog post:** Philipp D. Dubach's "Don't Go Monolithic; The Agent Stack Is Stratifying" maps the six-layer decomposition and argues the context layer (organizational world model) carries the highest defensibility — while the model layer is commoditizing fastest. — [https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Framework comparison:** Boolean and Beyond's multi-agent framework comparison notes LangGraph's advantage is checkpointing and deterministic routing (write `if confidence < 0.7: return "human_help"`) versus CrewAI's higher velocity at the cost of production reliability — agents can only be "asked to be careful" rather than programmatically enforced. — [https://www.booleanbeyond.com/en/insights/langgraph-vs-crewai-vs-autogen-multi-agent-frameworks](https://www.booleanbeyond.com/en/insights/langgraph-vs-crewai-vs-autogen-multi-agent-frameworks)
- **MCP adoption data:** As of March 2026, MCP has 97 million monthly SDK downloads, 10,000+ public servers, and adoption from OpenAI, Google DeepMind, Microsoft, and AWS. Anthropic donated it to the Linux Foundation's Agentic AI Foundation in December 2025. — [https://clarion.ai/insights-model-context-protocol-enterprise-interoperable-ai-agent-infrastructure](https://clarion.ai/insights-model-context-protocol-enterprise-interoperable-ai-agent-infrastructure)
- **RAG production gap:** AgentEngineering's production RAG analysis finds naive chunking (fixed character counts) is the single largest determinant of retrieval quality failure. Semantic chunking on structural boundaries + hybrid search + re-ranking closes the gap that plateaus most "demo-quality" RAG systems. — [https://www.agentengineering.io/topics/articles/rag-for-agents](https://www.agentengineering.io/topics/articles/rag-for-agents)
- **Cost data:** Zylos Research reports average enterprise AI spend at $85,521/month (2025). Runaway agent loops have cost teams from $15 in ten minutes to $47,000 over eleven days. 60–85% of AI spend is recoverable through prompt caching, model routing, and budget circuit breakers. — [https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)
- **Framework landscape 2026:** Humaineeti's orchestration survey finds LangGraph favored for production control (deterministic routing, time-travel debugging via checkpoint loading), CrewAI for prototyping velocity, AutoGen consolidating into AG2, and OpenAI Agents SDK and Google ADK as newer entrants. — [https://www.humaineeti.ai/resources/multi-agent-orchestration-frameworks](https://www.humaineeti.ai/resources/multi-agent-orchestration-frameworks)

## Gotchas

- **MCP servers vary wildly in quality.** MCP registries allow dynamic capability discovery — but unverified servers can inject vulnerabilities or misuse private data. Governance: private registries, server whitelisting, capability scoping per session.
- **LangGraph's "time travel" debugging requires checkpoint discipline.** You must persist checkpoints at meaningful decision points — not just at the end. Teams that skip this lose the ability to replay and fork executions.
- **Naive RAG silently degrades.** "Silent embedding drift" — gradual degradation of retrieval quality — goes unnoticed until it significantly impacts output. Set up automated retrieval eval (RAGAS or custom) and re-index triggers, not just manual refreshes.
- **Budget circuit breakers must live outside the agent loop.** Putting cost limits in the prompt or orchestration layer doesn't stop a runaway loop from burning tokens before the check fires. Place hard caps at the API gateway.
