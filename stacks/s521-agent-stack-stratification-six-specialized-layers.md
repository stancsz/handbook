# S-521 · The Stratifying Agent Stack: Six Layers, Six Different Games

The agentic stack is fragmenting. What looked like a single category in 2024 — "AI agent framework" — is actually six independent layers with different winners, different defensibility profiles, and different rates of change. Teams that treat it as one problem end up with the wrong build/buy decisions at every layer.

## Forces

- **The M×N integration problem is finally being solved** — MCP (Model Context Protocol) reached 17,000+ public servers and broad vendor adoption (Anthropic, OpenAI, Google, Microsoft) by late 2025, making tool integration a solved layer rather than a custom engineering project.
- **Sandboxing is its own product category now** — E2B, Daytona, Modal, Firecracker, and the CNCF agent-sandbox project all target code-execution isolation as a distinct capability, not a feature inside an orchestration framework.
- **Orchestration frameworks are converging on a production winner** — LangGraph dominates enterprise production; CrewAI dominates prototyping; AutoGen entered maintenance in late 2025 with Microsoft recommending migration.
- **Governance costs 2–5× inference in production** — teams budget for the LLM API bill, then discover observability, compliance, and integration overhead dominates the TCO.
- **Context is the moat, not the model** — the highest-defensibility layer in the enterprise agent stack is organizational knowledge and process state, not the foundation model itself.

## The Move

The 2025–2026 production agent stack stratifies into six layers. Treat each as an independent build/buy decision:

### Layer 1 — Foundation Model
Pick based on capability requirements, context window, and cost. OpenAI/Anthropic for general enterprise; open-source (Llama, Mistral, Qwen) for privacy-sensitive or cost-sensitive workloads. This layer commoditizes fastest — do not build your defensibility here.

### Layer 2 — Orchestration
- **LangGraph** for production systems requiring graph-based state, audit trails, and complex branching — the enterprise standard as of 2026. Qodo uses it for their coding agent specifically because graph density controls how structured vs. flexible the agent is.
- **CrewAI** for rapid prototyping and role-based pipelines — teams can ship a working multi-agent system in under an hour. Most successful teams migrate to LangGraph for production scale.
- **AutoGen** — entered maintenance in late 2025; Microsoft now recommends migration to Semantic Kernel for Azure shops.
- PydanticAI is gaining traction as a middle path: structured validation + dependency injection without LangChain's complexity tax.

### Layer 3 — Tool Integration (MCP)
The Model Context Protocol is the "USB-C for AI" — a vendor-neutral standard replacing bespoke point-to-point integrations. With 17,000+ public MCP servers and adoption across all major vendors, it is the default choice for new projects. Security (72% of teams cite it as the top concern) and access control at scale remain open problems.

### Layer 4 — Sandbox / Code Execution
Agents that write and run code need isolated execution environments. The stack here:
- **Modal** — serverless Python with ~100ms cold starts, good for short-lived compute
- **E2B** — agent-native sandboxes, fastest time-to-sandbox for AI workloads
- **Daytona** — open-source, Kubernetes-native, hardware-level isolation
- **Firecracker / CNCF agent-sandbox** — microVM-level isolation with warm pool pre-provisioning (sub-second cold starts on Kubernetes); backed by Google and a CNCF project
- Docker with hardening (`--network=none`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`) is reasonable for non-adversarial internal workloads.

### Layer 5 — Memory / State
Production agents need persistent state beyond a single context window. Choices:
- **Vector stores** (Pinecone, Qdrant, Weaviate, pgvector) for semantic memory and RAG
- **Structured state** (PostgreSQL, Redis) for typed, checkpointed agent state
- The most successful pattern: typed + scoped shared state with checkpointing — each agent knows what it can and cannot read/write.

### Layer 6 — Observability / Governance
This is where production costs actually live. LangSmith processes traces from 400+ companies; Arize Phoenix serves teams wanting open-source tracing. A 2026 AgentMarketCap analysis found governance + monitoring costs 2–5× inference spend. Teams that skip this layer discover it when they cannot explain why their agent made a bad decision.

## Evidence

- **HN Discussion:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." A practitioner with partial-AI software development experience confirmed: context persistence and decision logging are table-stakes, not features. — [HN #47114201](https://news.ycombinator.com/item?id=47114201)
- **Enterprise Analysis:** Philipp D. Dubach maps the stack into six layers with distinct defensibility profiles: Context (highest), Orchestration (medium-high), Security, Model, Infrastructure, Observability. Key insight: "The defensible asset in enterprise AI is not the model. It's the organizational world model." — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Framework Comparison:** LangGraph dominates regulated-industry production; CrewAI dominates prototyping velocity; AutoGen entered maintenance late 2025. Qodo's engineering team chose LangGraph for their coding agent specifically because graph edge density directly maps to how structured or flexible the agent behavior should be. — [Gheware DevOps Blog](https://devops.gheware.com/blog/posts/langgraph-vs-autogen-vs-crewai-comparison-2026.html), [Qodo Blog](https://www.qodo.ai/blog/why-we-chose-langgraph-to-build-our-coding-agent/)
- **MCP State of Adoption:** 72% of technical professionals expect MCP usage to increase in the next 12 months (survey of 92 practitioners, Nov–Dec 2025). Security is the #1 blocker for production MCP deployments. — [Zuplo State of MCP Report 2025](https://zuplo.com/mcp-report)
- **TCO Analysis:** Enterprise AI agent spending projected at $47B by end of 2026. Over 40% of agentic AI projects expected to be canceled by end of 2027, with escalating costs cited as the primary driver. Governance/monitoring costs 2–5× inference spend. — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/12/enterprise-agent-tco-hidden-costs-governance-monitoring-2026)

## Gotchas

- **CrewAI → LangGraph migrations are common** — CrewAI's English-like API is great for demos and prototypes, but production requirements (audit trails, typed state, complex branching) push teams to LangGraph. Build the prototype in the right framework for production, not the fastest one.
- **MCP is not production-grade security by default** — the protocol is mature enough to standardize on, but access control, rate limiting, and audit logging for MCP servers require explicit engineering.
- **Sandbox cold starts destroy user experience** — if your agent runs code, pre-provision a warm pool of sandboxes. Firecracker/CNCF agent-sandbox and Daytona both offer warm pools; raw Docker does not.
- **Context window is not memory** — giving an agent a long context window does not solve the memory problem. Typed, scoped state with checkpointing is the production pattern, not "stuff more into the prompt."
