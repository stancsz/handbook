# S-381 · Agent Stack Stratification

The agentic stack is not a monolith — it is stratifying into six layers, each with different defensibility profiles, tooling choices, and failure modes. Teams that treat it as one problem end up with brittle systems they cannot debug, scale, or swap out. Teams that map the layers correctly get composability, observability, and the ability to change one layer without rebuilding the rest.

## Forces

- **One framework to rule them all is a trap.** LangChain tried to own every layer; the result was tight coupling and vendor lock-in that teams now flee from.
- **Context is the moat, not the model.** Every major compute era (cloud, data stack) stratifies into specialized layers. The highest-lock-in, highest-value layer is always the one closest to the user's data and workflows — not the model.
- **Sandboxing and orchestration have different cadences.** You want to update your tool-calling policy weekly; you do not want to re-certify your sandbox environment on the same schedule. Keeping these in separate layers lets teams iterate independently.
- **Enterprise requires auditability.** Regulated industries need step-by-step replay, not just conversation logs. That requires stateful graph execution — not a stateless prompt→response wrapper.

## The move

**Map your agent system to six distinct layers and choose tooling per layer:**

1. **Context** (highest lock-in) — your embeddings, vector store, knowledge graph, session memory. This is where you win or lose. Choices: Pinecone, Qdrant, Weaviate, pgvector, or a custom knowledge graph.
2. **Orchestration** (policy layer) — how agents decide, decompose, and route. This is where your business logic lives. LangGraph for production auditability; CrewAI for fast prototyping that you'll likely migrate.
3. **Execution Runtime** — where code actually runs: Docker containers, Firecracker microVMs, E2B sandboxes, Modal, Shuru. Sandboxing is becoming its own specialized product category.
4. **Protocol Layer** — standardized tool communication. MCP (Model Context Protocol) is the emerging winner: framework-agnostic, separates "how to call" from "what credentials to use."
5. **Observability** — traces, replays, cost tracking. LangSmith for LangGraph-native shops; Phoenix (Arize) for general; custom ELK for enterprise. Without step-level traces, you cannot debug multi-hop failures.
6. **Model** (lowest defensibility) — the LLM itself. Anthropic Claude for complex reasoning; GPT-4.1 for tool-heavy tasks; open-source (Llama, Mistral) for cost-sensitive or data-private workloads.

**Key decision rules:**
- If you need audit/replay → LangGraph, not CrewAI or bare LangChain
- If you need fast team prototyping → CrewAI first, plan migration to LangGraph at scale
- If you need multi-party debate/consensus → AutoGen (Azure-native)
- If you need ambient/background agents → Temporal (workflow persistence, durable execution)
- If you need tool interoperability across frameworks → MCP everywhere
- If tokens are expensive → push deterministic work to scripts; don't let the LLM do dirty work

## Evidence

- **HN Comment (philippdubach, 2026):** The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing — Shuru, E2B, Modal, Firecracker wrappers all have very different defensibility profiles. A monolithic approach is the wrong call. — [HN thread](https://news.ycombinator.com/item?id=47114201) + [Accompanying blog](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Opensoul Show HN (iamevandrake, 2026):** Production marketing stack with 6 specialized agents (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) running on Paperclip orchestration, each with autonomous heartbeat-driven work queues. Demonstrates hierarchical multi-agent decomposition as a real pattern, not a demo. — [HN thread](https://news.ycombinator.com/item?id=47336615)
- **Enterprise Framework Comparison (Gheware, March 2026):** LangGraph wins on production auditability and cyclical workflows; CrewAI wins on onboarding speed (hours vs days); AutoGen wins on multi-party conversation patterns. Most Fortune 500 teams start with CrewAI and migrate to LangGraph. LangGraph GitHub: 12K+ stars; CrewAI: 28K+; AutoGen: 40K+. — [Gheware comparison](https://devops.gheware.com/blog/posts/langgraph-vs-autogen-vs-crewai-comparison-2026.html)
- **Production Pitfalls (Kieran Zhang, April 2026):** Four hard lessons: (1) Don't make LLM do dirty work — tokens are expensive, push deterministic tasks to scripts; (2) Skills aren't silver bullets — they're soft constraints that LLM reasoning can override; (3) Observability makes test suites actually valuable — without step-level traces you can't debug; (4) Don't just supervise — think deeply about the failure modes. — [Kieran Zhang blog](https://kieranzhang.dev/blog/agentic-4-pitfalls)

## Gotchas

- **The CrewAI→LangGraph migration is painful but necessary.** CrewAI's role-based pipeline model doesn't scale to complex stateful workflows. Budget 2-4 weeks for the migration when you hit the ceiling.
- **MCP is early.** It solves the right problem (framework-agnostic tool calling) but the ecosystem is still fragmenting. Pin to a specific MCP server version and control updates separately from your agent framework.
- **Hybrid retrieval is table stakes, not optional.** Dense vector search alone misses exact keyword matches. The winning pattern: dense + BM25 + Cohere Rerank v3. Adding this cut hallucination ~62% in a 47-deployment benchmark (AIThinkerLab, June 2026).
- **Sandboxing costs scale with agent complexity.** E2B/Firecracker-based sandboxes add 200-500ms cold start. For high-frequency tool calls, pre-warmed pools are worth the infra cost.
