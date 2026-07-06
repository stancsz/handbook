# S-213 · The Stratified Agent Stack

The agent stack is no longer a monolith — it is splitting into specialized layers, and sandboxing is becoming its own category entirely. Early agent systems bundled everything: orchestration, execution, tool access, and state management into a single service. Production teams are discovering that this coupling breaks at scale: you cannot audit a workflow if execution and reasoning share a process boundary, you cannot swap a sandbox provider if sandboxing is embedded in your orchestrator, and you cannot reason about cost if inference and execution billing are entangled. The teams winning in 2025 are designing for layer boundaries from day one.

## Forces

- Sandboxing untrusted agent code (web browsing, file writes, API calls) requires isolation from the orchestration layer — embedding it creates blast radius on failure and prevents provider swap
- Tool inventory grows from 5 to 50+ tools as agents mature — without structured routing and discovery, the orchestrator becomes a maintenance burden that scales with N²
- Multi-agent handoffs without typed contracts silently corrupt state — an agent passes a dictionary of parsed data to another agent that expects a different schema, and neither agent errors out
- Inference cost compounds multiplicatively in multi-agent systems: a 4-agent orchestrator-worker workflow costs $5–8 per complex task, making cost governance a first-class architectural concern, not an afterthought
- 40% of agentic AI projects face cancellation by 2027 (Gartner) because teams over-engineer the memory system before they have enough real interaction data to tune it

## The move

Design your agent stack as four distinct layers with clean interface boundaries:

**Layer 1 — Orchestration (the brain).** State machines, routing, multi-agent handoff logic. LangGraph for production (explicit graph semantics, replay, audit trail), CrewAI for fast prototyping (role-based agents, fastest onboarding), AutoGen for Azure-committed teams. Do not embed execution here.

**Layer 2 — Agent Runtime / Sandbox (the hands).** Isolated environments where agents execute code, browse the web, or write files. Providers: E2B (enterprise-focused, SOC 2 Type II, MCP-native), Modal (serverless compute with fast cold starts), Firecracker-based MicroVMs, Shuru, or Daytona. OpenAI's Agents SDK (April 2026) now ships with native sandbox support across 8 providers. This layer should be a drop-in swap — if sandboxing is hardcoded, you are locked in.

**Layer 3 — Tool Ecosystem (the fingers).** MCP (Model Context Protocol) is becoming the standard for agent-tool communication, replacing ad-hoc REST integrations. MCP servers expose tools with structured schemas; the agent runtime calls them through the protocol. Key insight from Shopify Sidekick: with 50+ tools, the real problem shifts from "can the agent call a tool" to "which of the 47 relevant tools should it call, in what order, with what parameters." Invest in tool discovery and routing, not just tool definitions.

**Layer 4 — Memory / Persistence (the spine).** Do not build a three-tier semantic memory system until you have real data to tune it. Start with keyword retrieval + simple context window. Graduate to hybrid retrieval (dense + sparse) with vector stores (Qdrant, Pinecone, Weaviate, pgvector) only when you have enough agent interactions to measure what "good retrieval" means for your domain.

**Typed handoffs between agents.** Define explicit schemas for every inter-agent message. Use Pydantic models or equivalent. Untyped handoffs (passing raw LLM outputs as dicts) are the leading cause of multi-agent failure — the producing agent formats data one way, the consuming agent expects another, and neither errors until the output silently degrades.

## Evidence

- **HN comment (2025):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." A practitioner writing about how these layers have different defensibility profiles and why going monolithic is the wrong call — [philippdubach.com/posts/dont-go-monolithic](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **RaftLabs production data (Nov 2025):** 1,445% surge in multi-agent inquiries (Q1 2024 → Q2 2025, Gartner); 57% of organizations already have agents in production; $5–8 per complex task for 4-agent orchestrator-worker workflows; 89% of teams have observability but only 52% have evals; untyped handoffs identified as the top killer of multi-agent workflows — [raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Shopify Engineering / ICML 2025:** Shopify Sidekick evolved from a simple tool-calling system to a sophisticated agentic platform. As tool inventory scaled past 20, the challenge shifted from "can the agent call a tool" to routing and maintenance. Indirect prompt injection (malicious content in knowledge bases) drove investment in dedicated security scanning between retrieval and agent prompts — [shopify.engineering/building-production-ready-agentic-systems](https://shopify.engineering/building-production-ready-agentic-systems)
- **Framework comparison (2026):** LangGraph is the enterprise production standard (explicit state graphs, replay, auditability); CrewAI has the fastest onboarding for prototyping but teams migrate to LangGraph as requirements mature; AutoGen is best for Microsoft/Azure-native teams. Hybrid architectures (LangGraph orchestration backbone + AutoGen research agents) are emerging as a legitimate pattern — [devops.gheware.com](https://devops.gheware.com/blog/posts/langgraph-vs-autogen-vs-crewai-comparison-2026.html)
- **OpenAI Agents SDK (April 2026):** Ships production sandbox execution with native support for E2B, Modal, Docker, Vercel, Cloudflare, Daytona, Runloop, and Blaxel — formalizing sandboxing as a pluggable infrastructure layer rather than an embedded concern — [byteiota.com](https://byteiota.com/openai-agents-sdk-sandbox-production-code-execution)

## Gotchas

- **Sandboxing is not optional for code-execution agents.** Without isolation, a single malformed code block can exfiltrate credentials or corrupt the host. Treat sandboxing like a firewall — it is not an optimization, it is a requirement.
- **CrewAI → LangGraph migrations are non-trivial.** The most labor-intensive part is refactoring CrewAI's implicit shared context into explicit LangGraph state annotations. Tool definitions transfer cleanly (both use the LangChain interface); state does not.
- **The evaluation gap is wider than the observability gap.** 89% of teams have trace-level observability. Only 52% have automated evals. Observability tells you what happened; evals tell you whether it was right. Build eval infrastructure in parallel with the agent, not after it ships.
- **Start with simple memory and upgrade only when you have data.** Three-tier hybrid retrieval with re-rankers sounds impressive but the tuning (similarity thresholds, keyword weights, merge strategies) only works when you have real agent interactions to measure against.
- **Cost compounds silently in multi-agent loops.** A 4-agent workflow that loops twice is 8x the base inference cost. Budget guards (max turns, max spend per task) belong in the orchestration layer, not the tooling.
