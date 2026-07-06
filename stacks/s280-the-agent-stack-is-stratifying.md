# S-280 · The Agent Stack Is Stratifying

The agent stack is fragmenting into six specialized layers — sandboxing, orchestration, memory, tools, context, and guardrails — and treating it as a monolith is the mistake that kills production systems. Each layer has different defensibility profiles, different failure modes, and different switching costs, and the teams that understand this are outcompeting those that buy a single orchestration framework and call it done.

## Forces

- **One framework can't own every layer.** LangGraph handles graph orchestration well; it doesn't own sandboxing, memory, or tool protocol. Teams that bolt everything onto one framework accumulate coupling debt that surfaces as brittleness at scale.
- **Specialization winners are already emerging at each layer.** Sandboxing: E2B, Modal, Firecracker wrappers. Tool protocol: MCP (15,926 GitHub repos, 9,652 public servers, 41% enterprise production adoption per Stacklok 2026). Memory: Pinecone, Qdrant, pgvector. Each is winning on its specific problem, not the full stack.
- **40%+ of agentic AI projects will be canceled by end of 2027** (Gartner-style projections cited by Philipp Dubach, 2026) — the dominant cause is shallow context: agents retrieve the right documents but can't reconstruct the organizational reasoning processes that make them actionable.
- **Agent inference generates up to 100x more tokens than conversational AI** (Zylos Research, 2026) because of multi-step reasoning, tool calls, and context accumulation — costs that a monolithic stack doesn't surface until the first runaway loop.
- **37% of enterprises now run 5+ AI models in production** (Dubach, 2026) — multi-provider routing across a stratified stack is now the norm, not the exception.

## The move

Treat the agent stack as six distinct layers. Design interfaces between them. Own exactly one or two; use specialists for the rest.

**The six layers, bottom to top:**

- **Sandboxing / execution.** Isolate untrusted code execution (code agents, file system access). E2B, Modal, Firecracker microVMs. This layer is its own product category now — don't roll your own.
- **Orchestration.** Define agent workflow, state transitions, and multi-agent coordination. LangGraph (explicit graph/state machine), CrewAI (role-based team hierarchy), Microsoft Agent Framework 1.0 / AutoGen v0.4 (conversational multi-agent). Pick based on coordination model needed, not feature count.
- **Memory / persistence.** Short-term conversation context, long-term semantic memory, episodic storage. Pinecone, Qdrant, Weaviate, pgvector. pgvector wins for teams already on Postgres; vector-native stores win at scale.
- **Tool calling / protocol.** MCP (Model Context Protocol) has become the USB of agent tool integration — 15,926 GitHub topic repos, 97M+ monthly SDK downloads, 41% enterprise production adoption. Standardize tool interfaces on MCP; custom schemas are legacy.
- **Context / knowledge.** RAG pipelines, chunking strategies, re-rankers, organizational world model. This is where defensibility lives — not in the model, but in the quality and specificity of the context you feed it.
- **Guardrails / safety.** Input validation, output filtering, hallucination mitigation, cost circuit breakers, rate limiting. Must be layer-independent so a failing model call doesn't cascade.

## Evidence

- **HN post / engineering blog:** The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. E2B, Modal, Firecracker wrappers each targeting isolation differently. — [philippdubach.com — Don't Go Monolithic; The Agent Stack Is Stratifying (Feb 2026)](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Primary research / blog:** Turion.ai's 2026 comparison of LangGraph (explicit graph nodes), CrewAI (role-based team hierarchy), and Microsoft Agent Framework 1.0/autoGen v0.4 (conversational emergent) — three fundamentally different coordination philosophies with distinct production readiness profiles. — [turion.ai — LangGraph vs CrewAI vs AutoGen: 2026 Comparison (May 2026)](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)
- **Research report:** 41% of enterprises in limited or broad production with MCP servers (Stacklok 2026 software report). 37% of enterprises run 5+ AI models in production. Average enterprise AI operational cost: $85,521/month. — [Digital Applied — MCP Adoption Statistics 2026 (May 2026)](https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol)
- **Cost analysis:** Production AI agent costs: enterprises averaging $85,521/month; 60–85% recoverable through caching, routing, and budget enforcement; runaway loops cost $15 in 10 minutes to $47,000 over 11 days. — [Zylos Research — AI Agent Cost Engineering (May 2026)](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)
- **Production lessons:** Four categories shipped to production in 2025: developer tooling (tightest feedback loop), internal operations automation (clear success criteria), customer-facing interaction (strictest requirements), data pipelines (strongest ROI). — [Technspire — State of Agentic AI 2025 (Dec 2025)](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Buying a full-stack platform to avoid the stratification decision defers the problem, not solving it.** When the platform hits a layer boundary (e.g., your orchestration framework doesn't natively support your vector store's filtering semantics), you're back to custom integration — just with more lock-in.
- **MCP is not a silver bullet for tool calling.** It standardizes the protocol, not the tool quality. A standardized interface over poorly-scoped, hallucination-prone tools still fails in production. Invest in tool design (clear schemas, explicit preconditions, result validation) before protocol standardization.
- **Cost surfaces in the guardrails and memory layers, not where you'd expect.** The orchestration layer doesn't show you that your agent ran 47 tool calls in a single session — that's a memory accumulation and cost circuit-breaker problem, which belongs in layers 1 and 6, not layer 2.
