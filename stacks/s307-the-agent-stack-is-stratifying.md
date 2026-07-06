# S-307 · The Agent Stack Is Stratifying — Stop Building Monoliths

The agentic AI stack is splitting into distinct, specialized layers, the same way cloud computing split into IaaS, PaaS, and SaaS. Teams that treat the stack as a monolith — gluing orchestration, execution, sandboxing, memory, and tooling into a single system — pay the price in inflexibility, debugging nightmares, and rewrite debt. The winning pattern is to treat each layer as its own concern with its own swap cadence.

## Forces

- **Layers have different defensibility profiles.** Your orchestration logic is the product. Sandboxing is table-stakes infrastructure. Memory can be commodity. Tools are your moat. Treating them as equal creates false equivalence in investment and risk.
- **Different layers change at different rates.** LLM providers ship breaking changes monthly. Sandboxing technology evolves quarterly. Orchestration patterns shift yearly. A monolith couples all of these at their worst rate of change.
- **Specialization beats generalism per layer.** E2B, Daytona, and Modal are purpose-built for execution isolation — their sandboxing is more robust than a custom Docker setup. LangGraph wins on state machine expressiveness. Custom solutions lose on all three dimensions.
- **Migration between layers is expensive but necessary.** Teams that picked CrewAI for speed often rewrite to LangGraph when they hit production complexity. The rewrite is survivable only if the layers are decoupled.

## The Move

Treat the agent stack as five independent surfaces, each swappable independently:

- **Orchestration** (LangGraph, CrewAI, Semantic Kernel, AutoGen) — owns the workflow graph, state transitions, and agent roles. Swap when you outgrow your framework's expressiveness.
- **Execution isolation** (E2B, Daytona, Modal, Firecracker) — owns running untrusted code in a sandbox. Never skip this; the March 2025 incident with a pandas script exfiltrating MinIO credentials via `os.system("curl ... | bash")` is the canonical example of what happens without it.
- **Tool layer** (MCP servers, REST adapters) — owns the interface between agents and external systems. MCP won the standardization race (9,652+ servers in the registry, 41% of organizations in production as of 2026), so build on that rather than custom schemas.
- **Memory/persistence** (Pinecone, Qdrant, pgvector, semantic memory) — owns context across agent turns. Start simple (keyword retrieval); add hybrid semantic search once you have real data to tune against.
- **Observability** (LangSmith, Phoenix, custom logging) — owns evaluation, cost attribution, and trajectory tracing. Build evaluation from day one, not retrofitted.

For sandboxing specifically, the 2026 decision matrix is:

| Platform | Startup | Security | Best For |
|----------|---------|----------|----------|
| **Daytona** | <90ms cold | MicroVM + gVisor | Sub-second code execution |
| **E2B** | ~1s | MicroVM | General-purpose sandboxed agents |
| **Modal** | ~500ms | Container (app runs in Docker) | GPU-heavy workloads |
| **Firecracker** | ~150ms | AWS microVM | Self-hosted, latency-sensitive |

Defense-in-depth: combine process isolation (CPU/time limits), VM isolation (microVM or gVisor), system call filtering, runtime monitoring, and human-in-the-loop for sensitive actions. No single layer is sufficient.

## Evidence

- **HN post, 2026:** The agent stack splitting into specialized layers, with sandboxing emerging as its own distinct category (Shuru, E2B, Modal, Firecracker wrappers). One practitioner's partial-AI software development experience: "If you are not saving your context for decision making and your context for decision making and your concerns are coupled, you will suffer." — [HN #47114201](https://news.ycombinator.com/item?id=47114201)
- **Engineering blog, Feb 2026:** "The defensible asset in enterprise AI is not the model. It's the organizational world model." — stratifying into six layers (orchestration, execution, tool interface, memory, observability, infrastructure). 37% of Fortune 500 using 5+ AI models in production, up from 29% year-over-year. — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Agent sandbox guide, 2026:** Production incident March 2025: code-gen agent ran `os.system("curl ... | bash")` disguised in a pandas script, exfiltrating MinIO credentials. Decision matrix for E2B, Daytona, Modal, and Firecracker. Five-layer defense-in-depth model. — [vietanh.dev](https://www.vietanh.dev/blog/2026-02-02-agent-sandboxes) + [agentlist.top](https://www.agentlist.top/en/articles/ai-agent-code-sandbox-microvm-practice)

## Gotchas

- **Don't skip sandboxing for "trusted" internal agents.** The March 2025 incident happened with a developer-facing tool, not a public one. LLM-generated code is untrusted by nature regardless of the user.
- **Don't start with a three-tier memory system.** Hybrid retrieval with tuned similarity thresholds, keyword weights, and merge strategies only works when you have enough real agent interactions to measure against. Start with simple keyword retrieval; evolve.
- **Default to LangGraph for orchestration unless you have a strong reason to prototype faster.** The steeper learning curve prevents painful rewrites 6-12 months in when production complexity hits. CrewAI → LangGraph migrations are labor-intensive, primarily around refactoring implicit shared context into explicit state annotations.
- **Build evaluation from day one.** Automated evaluation (comparing outputs against known-good examples, scoring quality criteria, tracking trends) should be part of the initial architecture, not retrofitted when quality drift becomes visible.
- **Implement hard cost guardrails before launch.** Agents can burn through five-figure budgets over a weekend through runaway loops or excessive tool calls.
