# S326 · Agent Stack Stratification

The moment you need two agents to coordinate — or one agent to run untrusted code — a monolithic "agent framework" stops being enough. You reach for this when your agent system is crossing layer boundaries: sandbox execution, tool hosting, state management, orchestration.

## Forces

- **Uniform frameworks hide non-uniform risks.** A single library claiming to do "everything" forces you to accept one-size-fits-all trade-offs in security isolation, cost, and observability — and you can't swap components when requirements change.
- **Context is the moat, not the model.** With 37% of enterprises using five or more models in production, the defensible asset is the organizational world model layered on top — not the foundation model itself.
- **Sandboxing is its own hard problem.** Running untrusted code in a containerized agent is categorically different from running it in a sandboxed subprocess — network access, filesystem boundaries, and resource limits need real engineering.
- **The 2% problem.** Only 2% of organizations report full production scale for agentic systems (Gartner, August 2025). The rest are blocked by reliability and safety — the problems that stratified stacks address.

## The move

The production agent stack is splitting into six specialized layers. Pick tools at each layer independently; avoid frameworks that entangle them.

**Layer 1 — Foundation Models**
- Route by capability, cost, and latency: Claude for reasoning, GPT-4o for function calling, Codex for code, Gemini for multimodal.
- Multi-provider via OpenRouter or unified API gateway eliminates single-provider risk.

**Layer 2 — Orchestration Engine**
- LangGraph for state-machine graphs requiring durable execution and observability (used at Klarna, Replit, Elastic).
- CrewAI for role-based crews with fast delivery on structured pipelines (v0.98+, active development).
- AutoGen in maintenance mode (Oct 2025); successor is Microsoft Agent Framework.

**Layer 3 — Sandbox / Code Execution**
- E2B for managed, cloud-hosted AI agent sandboxes (supports MCP, code interpreters, browser use).
- Daytona / Northflank for enterprise BYOC with hardware-level isolation options.
- microsandbox for self-hosted open-source isolation via libkrun — hardware-level KVM, no SaaS dependency, sub-200ms startup.
- Layer 1 complexity (Firecracker, TAP interfaces, root filesystems) is abstracted by all three into clean SDKs.

**Layer 4 — Memory / Vector Store**
- Qdrant, Pinecone, or pgvector for semantic memory with production-grade reliability.
- pgvector preferred when Postgres is already in the stack — reduces moving parts.

**Layer 5 — Tool Calling / MCP**
- MCP (Model Context Protocol) becoming the standard for agent-tool integration.
- Custom tool schemas remain viable for domain-specific APIs.

**Layer 6 — Observability / Eval**
- LangSmith for LangChain/LangGraph traces.
- Phoenix (Arize) for open-source observability.
- RAGAS for RAG evaluation.
- Custom logging where framework-native tools are insufficient.

## Evidence

- **HN Comment (stratification thesis):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — phil on HN, June 2026
  — https://news.ycombinator.com/item?id=47114201
- **Engineering Blog (6-layer model):** Production-grade agent systems require distinct layers: Orchestration Engine (planning/execution/monitoring), Memory Layer, Tool Layer, Sandbox Layer, and Observability Layer. "We're no longer asking 'can we build agents?' but 'how do we build agents that are reliable, safe, and cost-effective at scale?'" — DevStarsJ, April 2026
  — https://devstarsj.github.io/ai/architecture/2026/04/11/ai-agents-production-architecture-patterns-memory-safety-reliability
- **Framework comparison (2025):** LangGraph wins for production systems needing observability and durable execution (Klarna/Replit/Elastic); CrewAI wins for structured role-based pipelines; AutoGen entered maintenance mode. — JetThoughts, 2025
  — https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025
- **Multi-agent case study:** Opensoul ships 6 agents (Director/Strategist/Creative/Producer/Growth Marketer/Analyst) on Paperclip orchestration. Each runs on scheduled heartbeats, delegates to teammates, reports progress. Stack: Paperclip + Claude + Codex + PostgreSQL. — Evan Drake (@iamevandrake) on HN
  — https://news.ycombinator.com/item?id=47336615
- **Sandboxing comparison (2026):** E2B vs Daytona vs Modal vs microsandbox — each targets different isolation/control trade-offs. microsandbox wins for air-gapped/data-residency requirements; E2B wins for teams needing quick "code interpreter" features. — CallSphere, April 2026
  — https://callsphere.ai/blog/agentic-sandboxing-2026-e2b-daytona-modal-patterns
- **Cost breakdown (production):** 4 cost categories: API/Model (€15–60/mo), Infrastructure (€0–15/mo), Tool Integrations (€0–25/mo), Human Time (4–8 hrs setup, 1–2 hrs/wk maintenance). API costs are usually the smallest line item. — The Operator Collective, February 2025
  — https://theoperatorcollective.org/blog/ai-agent-cost-breakdown
- **Market data:** Global AI agents market $7.8B (2025) growing to $10.9B+ (2026), >45% CAGR; <5% of enterprise apps had agents in 2025, projected 40% by end 2026. — Gartner + DemandSage, cited in Thinking Inc, March 2026
  — https://thinking.inc/en/pillar-pages/agentic-ai-architecture

## Gotchas

- **AutoGen users: plan your migration.** AutoGen entered maintenance mode October 2025 with successor being Microsoft Agent Framework. If you're on AutoGen, evaluate LangGraph or CrewAI before the framework diverges further.
- **Don't underestimate Layer 3.** Sandboxing is not just "run in a container." You need network isolation, filesystem boundaries, resource limits, and audit logs. E2B/Daytona solve this for most teams; microsandbox for self-hosted requirements.
- **Naive RAG is the most common production failure.** Retrieval fails ~40% of the time in naive single-index pipelines. Hybrid search (BM25 + dense vectors) + cross-encoder reranking is the minimum viable production configuration.
- **API cost is rarely the real budget driver.** Most teams over-optimize model spend while under-investing in observability and tool reliability — the actual production blockers.
