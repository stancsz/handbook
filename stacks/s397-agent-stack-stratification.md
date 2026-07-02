# S-397 · The Agent Stack Is Stratifying Into Specialized Layers

The monolith is dead. The agent stack that started as "one model, one prompt, one output" has fractured into six distinct layers — each with its own tooling, its own lock-in profile, and its own defensibility. If you're still building a flat, single-tier agent, you're making decisions in the wrong order.

## Forces

- **Monolithic agents hide compounding failure.** When everything lives in one process, a single model outage, a context overflow, or a runaway tool loop takes down the whole system. Teams discover this the hard way at 2 AM
- **37% of enterprises now run five or more models in production** — not by design, but because the problem decomposed itself. Sandboxing, routing, and model diversity are now first-class concerns, not afterthoughts
- **Context is the highest-lock-in, hardest-to-rebuild layer** — and it's buried under every other decision. Get the model right, then realize your vector DB schema is wrong, then realize you can't change it without retraining everything
- **Gartner predicts 40% of agentic AI projects will be canceled by end of 2027** due to unclear business value — the tooling sprawl is a symptom of a deeper uncertainty about where the value actually lives

## The Move

The six-layer stack is becoming the de facto architecture for production agent systems. Treat each layer as independently deployable, with clear interfaces between them:

- **Application Layer** — Your product UI, user interaction logic, session management. Defensively weak: easy to replicate, easy to swap
- **Orchestration Layer** — LangGraph, CrewAI, Microsoft Agent Framework 1.0 (ex-AutoGen). Determines how agents coordinate, how state flows, how failures propagate. Pick based on coordination model needed (graph-based vs role-based vs conversational)
- **Agent/Skills Layer** — Tool definitions, prompt templates, system instructions. Moderate defensibility: the skills you teach an agent are hard to replicate if trained on domain-specific data
- **Data/RAG Layer** — Vector databases, retrieval pipelines, knowledge graphs. This is where agents get domain grounding. Neo4j and pgvector are common choices; hybrid retrieval (dense + sparse) improves faithfulness by 42% over traditional RAG
- **Model/Routing Layer** — LLM calls, model selection, fallbacks. Anthropic for reasoning-heavy tasks, OpenAI for tool-calling, open-source (Qwen, Llama) for cost-sensitive or on-prem scenarios. 37% of enterprises use 5+ models specifically to route by capability and cost
- **Sandbox/Execution Layer** — E2B, Modal, Shuru, Firecracker wrappers. Sandboxing is becoming its own discipline as agents execute untrusted code or hit third-party APIs. Isolated execution prevents cascading failures from a single bad tool call

The key architectural principle: **treat each layer as swappable**. The model you use today will be replaced. The orchestration framework you pick today will have a better competitor in 18 months. The vector DB you choose is the hardest to change — invest in schema design and abstraction early.

## Evidence

- **Blog post (Philipp Dubach, 2026):** The enterprise AI stack is stratifying into six layers with different defensibility profiles. Context — not models — is the highest lock-in layer. 37% of enterprises now use five or more models in production. — https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/
- **Engineering blog (Turion.ai, 2026):** LangGraph (graph-based orchestration), CrewAI (role-based teams), and Microsoft Agent Framework 1.0 (conversational/ex-emergent) each represent a distinct coordination philosophy. Microsoft unified AutoGen + Semantic Kernel into Agent Framework 1.0 GA on April 3, 2026. — https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026
- **Industry analysis (Neo4j, 2026):** Agents fail in production not because of model limitations but because they lack the right context at the right time. Agentic RAG improves faithfulness by 42% compared to traditional RAG in multi-step enterprise knowledge Q&A. — https://neo4j.com/blog/agentic-ai/ai-agent-useful-case-studies

## Gotchas

- **Don't build vertically integrated.** The temptation to lock into one vendor's full stack (e.g., OpenAI + Assistants API + Pinecone) is real — it works today and is faster to ship. But it creates single-provider risk that compounds as the stack ages. Layer your abstractions from day one
- **Sandboxing is not optional.** If your agent calls third-party APIs or executes code, a failure in the execution layer should not crash your orchestration layer. Treat them as separate processes with explicit IPC, not shared memory
- **Context window size is a false comfort.** Ultra-long context windows (200K+ tokens) have an "attention blind spot" — LLMs pay significantly more attention to the beginning and end than the middle, causing up to 30% information loss in the middle of the context
- **Cost control must be architectural, not a feature.** Tool-using agents multiply costs 5–10x over simple chatbots. Design in hard cost guards (max iterations, token budgets, circuit breakers) before launch, not after a surprise bill
