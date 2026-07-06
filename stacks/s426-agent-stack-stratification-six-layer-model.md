# S-426 · The Six-Layer Agent Stack — Stratification as the Production Pattern

Every AI demo is monolithic: one prompt, one model, one outcome. Every production system eventually splits into layers. The agent stack is following the same trajectory as the web stack (app → framework → server → OS → metal → power grid) — and the layer boundaries are now legible enough to design around.

## Situation

You're building an AI agent for customer support. You start with LangChain + OpenAI + one Python file. Six months later, you have five different models, a vector database with retrieval drift, MCP tools that don't compose, a sandbox escaping to the network, and no way to audit which agent touched what. The system didn't grow organically — it was never designed for layering. The six-layer model gives you the vocabulary to avoid this.

## Forces

- **Layer boundaries aren't obvious in demos.** What looks like one decision (which framework?) spans at least six distinct concerns with different defensibility, different lock-in, and different replacement costs
- **Vertical integration feels faster short-term.** Using one vendor's model + orchestration + hosting + tools reduces integration overhead — but creates a dependency that compounds as the system grows
- **The "model" layer is a commodity trap.** Model capability gaps close in 6-12 months. The layer with the highest defensibility — organizational context, process knowledge, accumulated tool chains — lives at the bottom of the stack, not the top
- **Security and sandboxing are their own discipline.** Sandboxing started as an afterthought in agent frameworks. It is now a standalone category (E2B, Modal, Firecracker wrappers) with different defensibility than orchestration
- **Multi-agent memory is the unsolved middle layer.** 36.9% of multi-agent failures stem from inter-agent misalignment — agents ignoring, duplicating, or contradicting each other's work (Mem0 research, 2026). No single framework solves this

## The Move

Design your agent architecture as six horizontal layers. Know which layer each decision lives in, and resist the pull to conflate them.

**Layer 1 — Context (Highest Defensibility)**
Organizational world model: your documents, processes, customer history, product knowledge, and accumulated tool results. This is the hardest to rebuild and the most durable competitive moat. Architect it as a retrieval system (RAG, vector DB) with explicit ownership — every piece of context knows when it was updated and by which agent.

**Layer 2 — Orchestration**
Agent coordination: LangGraph, CrewAI, Temporal, or custom state machines. This is where workflow logic lives. It is increasingly commoditizing — the difference between frameworks is ergonomic, not architectural. Choose for debugging clarity, not feature count.

**Layer 3 — Tool Integration**
MCP (Model Context Protocol) is now the dominant standard. MCP server downloads grew from ~100K (Nov 2024) to 8M+ (Apr 2025) (Gupta, 2025). The protocol is under Linux Foundation governance (Agentic AI Foundation, Dec 2025). Build tool interfaces as MCP servers. Keep MCP servers narrow and single-purpose — 43% of published MCP servers have command injection flaws (Gupta, 2025). The attack surface grows with server complexity.

**Layer 4 — Sandboxing (Fastest Growing Category)**
Agents execute. Execution requires isolation. This layer has fragmented into E2B, Modal, Shuru, Firecracker wrappers — all solving the same problem with different trade-offs. Treat sandboxing as a separate deployment concern from orchestration. Do not conflate "I have a container" with "I have a secure execution environment." The threat model is different: agents are probabilistic, can be prompted to behave unexpectedly, and may chain tool calls in ways you didn't anticipate.

**Layer 5 — Inference**
Model calls: Claude, GPT-4o, Gemini, or self-hosted. This is the most commoditized layer. Multi-model routing is table stakes — 37% of enterprises use 5+ models in production (a16z AI Enterprise 2025). Route on cost/quality trade-offs per task class, not globally. A research agent gets Opus. A classification agent gets Haiku.

**Layer 6 — Infrastructure**
Compute, networking, storage. Kubernetes, Docker, serverless, or bare metal. The production question is not "where" but "how fast can you revoke." Agents that can act autonomously need infrastructure that can be killed instantly.

## Evidence

- **Engineering blog:** Philipp Dubach's "Don't Go Monolithic; The Agent Stack Is Stratifying" (Feb 2026, updated May 2026) documents the six-layer decomposition with defensibility analysis — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN thread:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing" — camkego confirms: "doing partial-AI software development, these layers have very different defensibility profiles" — [HN #47114201](https://news.ycombinator.com/item?id=47114201)
- **Market research:** MCP adoption data — 8M+ downloads, 5,800+ servers, Linux Foundation governance, 90% projected adoption by end of 2025 — [Gupta Research](https://guptadeepak.com/research/mcp-enterprise-guide-2025/)
- **Multi-agent failure analysis:** 36.9% of multi-agent failures from inter-agent misalignment (Mem0, 2026) — [mem0.ai blog](https://mem0.ai/blog/multi-agent-memory-systems)

## Gotchas

- **Conflating orchestration with inference.** LangChain/LangGraph are orchestration tools. Do not let the framework's model abstraction leak into your architecture decisions about where models live or how they are routed.
- **MCP server proliferation without audit.** 43% of published MCP servers have command injection flaws. Never deploy a third-party MCP server to production without reviewing its tool schemas. Prefer narrow, purpose-built servers over broad ones.
- **Treating sandboxing as solved by containers.** Docker containers and cloud sandboxes have different threat models. An agent that can call a file-write tool and a shell tool in the same turn needs something stronger than a container boundary.
- **Building context before you know what you're retrieving.** The organizational world model (Layer 1) is expensive to build and maintain. Start with the retrieval paths you actually need, not an exhaustive index.
