# S-376 · Agent Stack Stratification: The Layers Exist, Use Them

The promise of a monolithic agent framework that does everything collapses the moment you hit production. Teams building with a single framework discover that orchestration, sandboxing, memory, tool access, and observability have fundamentally different defensibility profiles — and that conflating them creates hidden fragility. The agent stack is stratifying into distinct layers, and the teams shipping reliably in 2025-2026 have already adapted.

## Forces

- **Inference cost compounds non-linearly across agents.** A 4-agent orchestrator-worker workflow costs $5–8 per complex task — 40x more than a single-agent equivalent. Budgeting for Layer 1 (compute) while ignoring Layer 2 (LLM APIs) and Layer 3 (operational overhead) is the most common budget failure mode
- **Sandboxing, orchestration, and memory have different update cadences.** Coupling them in one framework means you inherit breaking changes across all three whenever any one layer evolves — and they evolve at different speeds
- **The observability gap is wider than teams expect.** 89% of organizations have agent observability in place, but only 52% have structured evals. Multi-agent debugging without evals is guesswork
- **Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025.** The shift from single-agent prototypes to multi-agent production is real and happening now

## The move

The architecture that holds up in production separates concerns into distinct, swappable layers:

- **Foundation models** (OpenAI, Anthropic, open-source) — chosen per task complexity, not globally. Claude for reasoning, GPT-4o for function-calling, smaller open models for extraction
- **Orchestration** (LangGraph for graph-based workflows, CrewAI for fast role-based prototyping, Temporal for stateful long-running workflows) — not a single framework, the right tool per workflow type
- **Sandboxing** (E2B, Modal, Shuru, Firecracker microVMs) — isolation is now its own discipline with dedicated tooling, not something you bolt on
- **Memory/persistence** (Pinecone, Qdrant, pgvector, semantic memory) — externalized and queryable, not kept in prompt context
- **Tool calling** (MCP as the emerging standard, custom REST schemas for internal systems) — MCP adoption reached 90% projection by end of 2025 with 5,800+ servers and Linux Foundation governance
- **Observability** (LangSmith, Arize Phoenix, custom structured logging) — traces across agent boundaries, not just per-agent metrics

Single agents are the right default: 3x faster task completion, 60% better accuracy on bounded tasks (3-5 steps). Split to multi-agent only when you hit the ceiling — parallel sub-tasks, distinct domain expertise required, or context window exhaustion.

## Evidence

- **Shopify Sidekick (2025):** Evolved from simple tool-calling to sophisticated agentic platform. Key lesson: tool count scaling creates logarithmic complexity growth — at 10+ tools, accuracy degrades without careful prompt design and evaluation frameworks. Published evaluation approach using GRPO training at ICML 2025 — [Shopify Engineering Blog](https://shopify.engineering/building-production-ready-agentic-systems)
- **Multi-agent production economics:** A team running 4 LangChain agents with A2A communication saw costs escalate from $127/week to $891 to $4,200 over three weeks — a 33x cost increase driven by inference compounding across agents. Key breakdown: lack of per-agent cost caps, no budget-aware routing, no eval-driven early termination — [Towards AI, $47K post](https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-broke-5f845848de33)
- **MCP ecosystem maturation:** 8M+ server downloads by April 2025 (from ~100K in November 2024). OpenAI adopted MCP in March 2025, Google DeepMind in April 2025, Linux Foundation governance under Agentic AI Foundation by December 2025. 43% of MCP servers have command injection flaws — security scrutiny is now essential for any production deployment — [Deepak Gupta Research, MCP Enterprise Guide](https://guptadeepak.com/research/mcp-enterprise-guide-2025/)

## Gotchas

- **The eval gap kills debugging.** Without structured evals at agent boundaries, multi-agent failures are invisible until users report them. Add evals before you add agents
- **MCP server proliferation creates attack surface.** With 5,800+ servers available, each plugin is a potential CVE. The 92% exploit probability threshold with 10 plugins means you must vet MCP servers the same way you vet npm packages
- **Orchestration framework lock-in is real.** LangChain is widely criticized as "bloated" in local deployment communities (r/LocalLLaMA, 2025) — teams building production systems copy the API patterns and implement their own minimal framework rather than accepting the abstraction overhead
- **Budget at Layer 2, not Layer 1.** Infrastructure costs dropped 70% since 2020 ($50-60/month baseline), but LLM API costs at scale are 3-5x what teams budget. Model the full token consumption across all agent hops before committing to architecture
