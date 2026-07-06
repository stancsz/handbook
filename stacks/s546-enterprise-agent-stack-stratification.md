# S-546 · Enterprise Agent Stack Stratification

The agentic AI stack is no longer a linear pipeline — it's six distinct layers, each with different defensibility profiles, different winners, and different lock-in costs. Teams that treat it as one system end up over-investing in the wrong layer and leaving value on the table.

## Forces

- **37% of enterprises now run 5+ AI models in production** — single-provider lock-in is the new single-cloud risk (source: Philipp Dubach, Feb 2026)
- **40% of agentic AI projects will be canceled by end of 2027** due to unclear business value — the stack is shifting faster than teams can standardize
- Tool calling, orchestration, context management, memory, and model selection are now distinct decisions with independent trade-offs
- The highest lock-in and highest-value layer is **context** — your organizational world model — not the model itself
- The "one framework to rule them all" assumption breaks down at production scale; different layers demand different tools

## The Move

Decompose your agent stack into six independent layers. Treat each as a separate procurement decision with explicit swap criteria:

- **Sandboxing** (E2B, Modal, Shuru, Firecracker wrappers) — isolate agent code execution from your infrastructure. Swap when latency or cost thresholds are breached.
- **Orchestration** (LangGraph, CrewAI, AutoGen, Temporal, custom state machines) — controls agent flow, handoffs, and retry logic. Swap when your coordination pattern changes.
- **Context management** — prompt templates, system instructions, few-shot examples, retrieved context assembly. This is where most accuracy gains live and where lock-in is worst.
- **Memory / persistence** (Pinecone, Qdrant, Weaviate, pgvector) — stores conversation history, semantic memories, and retrieval indices. Swap on cost or compliance triggers.
- **Tool calling** (MCP, custom REST adapters, OpenAPI schemas) — MCP (Model Context Protocol, Anthropic, Nov 2024) is consolidating as the de facto standard with adoption from OpenAI, Google, Microsoft. Custom adapters remain common for proprietary internal APIs.
- **Model layer** (Claude, GPT-4o, Gemini, open-source) — route per task. Use structured routing (fast/small for classification, large/reasoning for complex tasks) over single-model defaults.

## Evidence

- **Engineering blog:** "Don't Go Monolithic; The Agent Stack Is Stratifying" — 6-layer decomposition with enterprise adoption data (37% multi-model, 40% project cancellation rate) — https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/
- **Framework comparison:** LangGraph leads enterprise production deployments in 2026; CrewAI leads proto-to-prototype ergonomics; AutoGen leads research/academic — https://presenc.ai/research/multi-agent-orchestration-frameworks-2026
- **Tool calling standard:** MCP adoption reached de facto status by late 2025 across major providers — https://cuttlesoft.com/blog/2025/11/25/anthropics-model-context-protocol-the-standard-for-ai-tool-integration
- **Real cost data:** Agentic RAG production costs $0.02–$0.31 per query depending on complexity — chunk size and embedding model choice have more accuracy impact than model tier — https://www.jahanzaib.ai/blog/agentic-rag-production-guide

## Gotchas

- **Siloing by framework** — teams pick LangGraph and then force every layer decision through its abstractions. The framework is a coordinator, not a stack.
- **Underinvesting in context** — the organizational world model (your proprietary context) compounds over time and is the hardest thing to rebuild if you switch. Treat it as the highest-value asset, not an afterthought.
- **No swap criteria** — teams rarely define exit conditions per layer. Define cost, latency, and accuracy thresholds upfront so you're not locked in by inertia.
