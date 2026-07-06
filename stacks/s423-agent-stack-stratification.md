# S-423 · The Agent Stack Is Stratifying — Stop Building Monolithically

Your agent is doing too much in a single place. Routing decisions, tool execution, memory retrieval, state management, and sandbox isolation all live in one process with no layer boundaries. When it breaks — and it will — you have no idea where. The pattern emerging from production teams in 2025–2026 is clear: the agent stack is decomposing into specialized layers, and the teams treating each layer as its own concern are winning.

## Forces

- **The monolith problem** — mixing orchestration, execution, and context layers creates blast radius when any one fails; it also makes swapping components impossible without rewriting everything
- **Different defensibility profiles per layer** — model APIs are commoditizing fast; your organizational world model (context layer) is where durable competitive advantage lives
- **Sandboxing as its own discipline** — code execution and tool calls inside an agent require fundamentally different guarantees than reasoning and routing; lumping them together is the root cause of most production agent incidents
- **Enterprise AI is hitting the 40% cancellation wall** — Gartner predicts >40% of agentic AI projects will be cancelled by end of 2027; the cause is not model quality but architectural debt accumulated from monolithic early designs
- **The right answer in 2023 does not survive 2026** — what worked as a single LangChain chain is now a liability; teams that didn't stratify are rebuilding under production pressure

## The move

Treat the agent stack as six independent layers. Swap, scale, and harden each one on its own timeline.

**1. Context layer (highest defensibility)**
- Your organizational world model, process knowledge, and proprietary data
- This is where durable competitive advantage lives — not in model choice
- Guard it. Build RAG, knowledge graphs, and retrieval quality here before anything else

**2. Orchestration layer (LangGraph wins at scale)**
- State machines, routing graphs, multi-agent coordination
- LangGraph is now the production default for complex branching, durable execution, and debugging (used at Klarna, Replit, Elastic)
- AutoGen entered maintenance mode October 2025; successor is Microsoft Agent Framework
- CrewAI leads for role-based team patterns but LangGraph wins when you need inspectability

**3. Execution/sandbox layer (emerging as its own market)**
- Firecracker microVMs, per-sandbox kernel isolation, filesystem snapshots
- E2B dominates hosted sandboxing with sub-200ms cold starts from pre-warmed pools
- Daytona pivoted to agent sandboxes in 2025, now second-most-deployed open-source option
- Modal is preferred for GPU-heavy agent workloads
- OpenAI's June 2026 acquisition of Ona reshuffled this market; $4.5B TAM projected for enterprise MCP/sandbox infrastructure by 2028
- Self-hosted alternatives (microsandbox/libkrun) exist for air-gapped and data-residency requirements

**4. Tool/MCP layer**
- MCP (Model Context Protocol) is becoming the definitive standard for tool discovery and inter-agent data exchange
- A2A (Agent-to-Agent Protocol) handles inter-agent orchestration; hybrid MCP + A2A architectures deliver 40–60% faster workflow development than single-protocol approaches
- MCP for data/tool access, A2A for multi-agent collaboration — do not force one to do both

**5. Memory/persistence layer**
- For most teams under ~5–10M vectors, pgvector inside existing Postgres is sufficient
- Qdrant, Weaviate, or Pinecone when scale or metadata filtering demands it
- Semantic memory architectures (storing reasoning traces, not just documents) are gaining adoption in production

**6. Observability/evaluation layer**
- LangSmith, Phoenix, or custom structured logging
- Non-negotiable: every agent call must log input context, model reasoning, tool calls, and final output
- Without this, debugging agent failures is indistinguishable from debugging mysticism

## Evidence

- **Blog post:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing" — HN comment thread on agent stratification, citing E2B, Modal, Firecracker wrappers as the execution layer emerging separately from orchestration — [HN](https://news.ycombinator.com/item?id=47114201)
- **Blog post:** Philipp D. Dubach defines six enterprise AI agent stack layers with distinct defensibility profiles — Context (highest), Model, Orchestration, Execution, Tool, Observability — and argues "the defensible asset in enterprise AI is not the model. It's the organizational world model" — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/) (Feb 2026, updated May 2026)
- **Engineering blog:** AI Agents in Production: the production stack diagram shows orchestration → sandboxing → tool layer → memory as distinct layers with separate failure modes and hardening requirements — [devstarsj.github.io](https://devstarsj.github.io/ai/architecture/2026/04/11/ai-agents-production-architecture-patterns-memory-safety-reliability) (April 2026)
- **Comparison post:** LangGraph is production default (Klarna, Replit, Elastic), AutoGen in maintenance mode since Oct 2025, CrewAI for role-based teams — [jetthoughts.com](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)
- **Blog post:** E2B (sub-200ms cold starts, Firecracker microVMs), Daytona (pivoted to agent sandboxes 2025), Modal (GPU workloads), OpenAI Ona acquisition June 2026 — [callsphere.ai](https://callsphere.ai/blog/agentic-sandboxing-2026-e2b-daytona-modal-patterns)

## Gotchas

- **Forcing one protocol across all layers** — using MCP for inter-agent orchestration when A2A is the right tool adds unnecessary complexity; hybrid MCP + A2A wins
- **Building the monolith "now" to save time** — every team that did this in 2023–2024 is rebuilding in 2025–2026 under production pressure; the shortcut costs more later
- **Ignoring the sandbox layer until it bites** — unconstrained code execution inside your agent is not a theoretical risk; it is the primary vector for agent-related security and cost incidents
- **Treating model choice as the strategic lever** — model APIs are commoditizing; your context layer (data, retrieval quality, organizational knowledge) is what compounds over time
