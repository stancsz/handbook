# S-364 · Agent Stack Stratification and MCP Convergence

The temptation is to treat the AI agent stack as a monolith — one framework, one model, one retrieval store, tightly coupled. That works until you need to upgrade one piece, harden security, or route traffic across providers. The field is splitting, and the teams winning are the ones who decomposed early.

## Forces

- **The model layer commoditizes faster than your organizational context.** Foundation models improve on 6-month cycles and swap out quarterly. Your process knowledge, permission structures, and domain memory do not. Treating them as equally upgradeable leads to fragile, tightly-coupled stacks that break on every model release.
- **Different layers have fundamentally different defensibility profiles.** The context layer (organizational world model, process knowledge) is your moat. The model layer is a commodity you rent. The tool layer is increasingly standardized. Conflating them into one stack means you're defending everything equally — and defending nothing well.
- **MCP is becoming the connective tissue between layers.** Model Context Protocol emerged as a standard for tool discovery and invocation, but it's evolving into the interface layer between agents and the external world. Teams that hardcode tool schemas are rebuilding every time a tool changes; teams using MCP-adapter layers are not.

## The move

The agent stack decomposes into six layers with distinct update frequencies, defensibility, and selection criteria:

- **Security** (permissions, compliance, PII redaction, audit logging) — enforce at the perimeter, not per-agent
- **Context** (organizational world model, process knowledge, domain memory) — this is your moat; invest here, not in the model
- **Models** (foundation LLMs, embeddings, multimodal) — commodity layer; route intelligently, switch vendors painlessly
- **Tools** (tool schemas, REST integrations, MCP servers) — standardize on MCP for tool discovery and invocation
- **Memory** (vector stores, semantic memory, session state) — separate retrieval from generation concerns
- **Orchestration** (workflow graphs, agent coordination, state machines) — keep it dumb enough to be replaceable

**Three practical implications:**

- Route model calls through an **AI Gateway / proxy layer** that handles routing, caching, budget enforcement, and observability before calls reach the model. Cloudflare's AI Gateway processed 20.18M requests/month across 295 teams with this pattern — the gateway is where you enforce cost controls that prevent runaway loops.
- Use MCP as the **standardized tool interface** between your agent and external systems. MCP servers expose JSON-Schema tool specs; agents discover and invoke them dynamically rather than through hardcoded schemas. This decouples your agent from individual tool implementations.
- **Instrument at every layer boundary**, not just at the orchestration level. Token counts, retrieval similarity scores, tool call success rates, and latency per span are the minimum viable observability stack for multi-agent production systems.

## Evidence

- **Blog post (Philipp Dubach, 2026):** The enterprise AI agent stack is following the same decomposition pattern as the modern data stack — six layers with different defensibility profiles. Context (organizational world model) is the highest-defensibility layer; the model layer is commodity. — https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/
- **Engineering blog (Cloudflare, 2026):** Cloudflare's iMARS team built a three-layer system — AI Gateway (proxy/routing), Workers AI (inference), MCP servers (tool interface) — processing 241.37B tokens with 3,683 active internal users across 295 teams. 93% R&D adoption in 11 months. Key architectural decision: decoupling the routing layer (AI Gateway) from the inference layer (Workers AI) so each can evolve independently. — https://blog.cloudflare.com/internal-ai-engineering-stack
- **Engineering blog (Agentic RAG production, 2026):** Multi-agent production deployments with dedicated retrieval agents, re-ranking layers, and hybrid search (BM25 + dense embeddings) consistently outperform monolithic RAG. Harvey AI achieved 0.2% hallucination rate across 700+ legal clients; Deutsche Telekom hit 89% acceptable answer rate on 2M+ conversations. The key architectural choice: agents that plan retrieval strategy dynamically, not a fixed retrieve-then-generate pipeline. — https://aliac.eu/blog/agentic-rag-in-production

## Gotchas

- **Over-stratifying too early creates coordination debt.** Six layers is a target, not a starting point. Teams that decompose into microservices from day one spend more time managing interfaces than building capability. Start with a monolith that works, identify the first genuine tension (can't upgrade the model without breaking the workflow, can't add a new tool without a full release), and decompose along that seam.
- **MCP is not yet ubiquitous.** Support varies by framework and platform. LangChain/LangGraph have native MCP integration; CrewAI has an enterprise MCP server but limited self-hosted support. Bet on MCP as the standard but hedge with abstraction adapters so you're not locked in if the protocol landscape shifts.
- **Cost control must be architectural, not operational.** Manual budget reviews do not catch runaway agent loops in time. Budget circuit breakers at the gateway layer, token-count budgets per agent, and hard limits with automated rollback are the baseline. One team reported a $47,000 runaway loop over 11 days before detection — the cost was entirely preventable with proper gateway-level enforcement.
