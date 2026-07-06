# S-340 · The Agent Stack Is Stratifying: Six Layers, Six Different Winners

The enterprise agent stack is fragmenting into distinct horizontal layers — and teams treating it as a monolithic blob are accumulating debt they'll pay for years. Context (not models) is the deepest lock-in. MCP is the fastest-growing integration layer. Security and sandboxing are becoming their own category. The winners at each layer are different, and the teams that pick a single-framework bet at every layer are building technical debt.

## Forces

- **37% of enterprises now use five or more AI models in production** — single-provider lock-in is the new version of single-cloud risk, and teams are being explicit about avoiding it.
- **Gartner predicts 40% of enterprise apps will feature AI agents by 2026** — but over 40% of agentic AI projects will be canceled by end of 2027 due to unclear business value. The stack fragmentation compounds the evaluation problem.
- **The defensible asset is not the model — it's the organizational world model.** The context your agent holds about your business, your customers, your domain is the hardest thing to rebuild and the easiest to lose when you swap layers.
- **Sandboxing, context management, and tool integration are becoming independent layers** — Shuru, E2B, Modal, and Firecracker wrappers are carving out territory previously bundled into orchestration frameworks.
- **Most enterprise AI failures stem from shallow context, not poor models** — meaning the memory/context layer is underinvested relative to the orchestration layer.

## The Move

The agent stack is converging on six layers with distinct market dynamics. Understanding them as independent allows principled buy-vs-build decisions at each.

**Layer 1 — Inference:** Route by task. Claude Sonnet for reasoning-heavy work; GPT-4o for speed and function-calling; open-source (Qwen 3, Llama 4) for cost-sensitive or data-private workloads. 37% of enterprises already run 5+ models.

**Layer 2 — Orchestration:** LangGraph for stateful, production-grade workflows with explicit graph semantics. CrewAI for rapid prototyping and structured role-based tasks. AutoGen for conversational/brainstorming patterns. The key insight: orchestration and inference are decoupling — don't let your framework choice constrain your model choice.

**Layer 3 — Context & Memory:** The highest-lock-in, highest-value layer. pgvector for teams under ~5–10M vectors staying in Postgres. Qdrant/Pinecone/Weaviate when scale or metadata filtering demands it. Agentic RAG with knowledge graphs cuts hallucination ~62% (May 2026 MLOps Community benchmark, 47 production deployments). Embedding model selection (text-embedding-3-large vs Qwen3-Embedding-8B for multilingual) sets the retrieval ceiling.

**Layer 4 — Tool Integration & Sandboxing:** MCP (97M+ monthly SDK downloads, 5,800+ servers, 300+ client apps as of Dec 2025) is the emerging standard — OpenAI adopted it in March 2025, Microsoft invested, AWS/Azure shipped MCP tooling. But 43% of MCP servers have command injection flaws; exploit probability exceeds 92% with just 10 plugins. Sandboxing (E2B, Modal, Firecracker) is separating from orchestration as a distinct category.

**Layer 5 — Guardrails & Safety:** NeMo Guardrails NIM microservices (NVIDIA, Jan 2025) for content safety, topic control, jailbreak detection — now composable as microservices rather than framework-locked. Input/output validation, hallucination mitigation, and budget circuit breakers are table stakes for production.

**Layer 6 — Observability:** LangSmith for LangGraph-native deployments (time-travel debugging, checkpointing, full traces). Arize Phoenix for framework-agnostic tracing. Custom structured logging for cost attribution and loop detection.

## Evidence

- **Blog post (Philipp Dubach, updated May 2026):** 37% of enterprises use 5+ AI models in production; Gartner's 40% agent-app prediction; 40%+ project cancellation rate — stack stratification and context as competitive moat — https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/
- **GitHub README (benconally/ai-agent-framework-decision-guide, Apr 2026):** Production checklist for LangGraph vs CrewAI vs AutoGen; MCP first-class in LangGraph with full streaming support — https://github.com/benconally/ai-agent-framework-decision-guide
- **Research report (Deepak Gupta, Dec 2025):** MCP ecosystem metrics — 97M+ monthly downloads, 5,800+ servers, 300+ clients; 43% of servers with command injection flaws; OpenAI/Microsoft/AWS adoption timeline — https://guptadeepak.com/research/mcp-enterprise-guide-2025

## Gotchas

- **Picking one framework for every layer is a trap.** LangGraph + LangChain are great together but create coupling that constrains model routing, memory backends, and tool integration. Teams that treat the stack as vertically integrated end up rebuilding half of it when requirements change.
- **MCP security is not baked in.** 43% command injection flaw rate means adopting MCP servers at face value is a supply chain risk. Audit servers before connecting them to production agents — especially any server that executes code or writes files.
- **Context is your moat, not your model's parameters.** Teams optimize model choice obsessively and underinvest in retrieval quality, chunking strategy, and knowledge graph construction. The 62% hallucination reduction from agentic RAG with knowledge graphs is worth more than switching from GPT-4o to Claude Opus for most production use cases.
- **Sandboxing is not optional.** Code-execution agents without sandboxing have cost teams runaway-loop incidents ranging from $15 in 10 minutes to $47,000 over 11 days. The tool execution layer must be isolated from the agent reasoning layer.
