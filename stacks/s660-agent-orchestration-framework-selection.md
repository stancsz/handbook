# S-660 · Agent Orchestration Framework Selection

The demo uses LangChain. The production system doesn't. Choosing the wrong orchestration layer means rewriting it six months later when your agent has 12 tools, 3 memory stores, and a multi-agent handoff — all the abstractions that felt convenient at the start are now in the way.

## Forces

- **LangGraph wins on production traceability; CrewAI wins on team onboarding speed.** LangGraph's graph-based state machine gives you step-by-step execution traces that actually map to what the agent did. CrewAI's role-based team model is faster to set up for straightforward pipelines but harder to debug when things go wrong.
- **AutoGen is dead.** Microsoft moved to the Microsoft Agent Framework (MAF). The 58,500-star AutoGen repo is in maintenance mode. Building on it means inheriting an abandoned codebase.
- **The framework lock-in risk is real but misdiagnosed.** The real lock-in isn't the orchestration layer — it is the context layer (prompts, memory, tool schemas). Choosing a framework for its abstractions is the wrong trade; choosing it for its observability and failure-mode clarity is the right one.
- **Stratification is overtaking monoliths.** The enterprise AI stack now decomposes into 6 layers: Context, Inference, Orchestration, Sandboxing, Memory, and Tools. Each layer has different rebuild difficulty and different lock-in risk. Treating the stack as one monolithic choice is the most common expensive mistake.

## The move

1. **Default to LangGraph for production systems.** It has the strongest verified production record: Klarna (85M users), LinkedIn, Uber, Elastic, Replit. Its graph-based state machine maps directly to the step-by-step traces you need for debugging. Version 0.4.0 is stable and actively maintained.
2. **Use CrewAI for rapid prototyping and marketing/operations agents.** The 6-role team model (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) maps naturally to business workflows. CrewAI v1.14.6 has 52,500 stars and over 100,000 certified developers. Best for teams that need to ship a prototype in days.
3. **Never start with AutoGen.** It is in maintenance mode. If you have an existing AutoGen codebase, evaluate AG2 (the community fork) or plan a migration to MAF or LangGraph.
4. **Evaluate MAF only for greenfield Microsoft/Azure-native projects.** It is too new for production use (May 2026) but represents Microsoft's future direction for multi-agent systems.
5. **Build custom only when orchestration is the product.** If your core differentiation is the coordination logic itself (e.g., a specialized workflow engine), a custom state machine in Python is cleaner than fighting a general-purpose framework's abstractions. LangGraph is the underlying graph model you'd likely replicate anyway.
6. **Design for the 6-layer stack from the start.** Separate your context layer (prompts, retrieval), inference layer (LLM calls), orchestration layer (flow control), sandboxing layer (execution isolation), memory layer (persistence), and tools layer (external integrations). Each layer has different swap costs — know which ones are your moat.

## Evidence

- **Blog post:** LangGraph has named production deployments at Klarna (85M users), LinkedIn, Uber, Elastic, and Replit — the most verifiable production record of any current framework. CrewAI's case studies are anonymized; AutoGen has no active enterprise references. — [ODSEA — LangGraph vs CrewAI vs AutoGen Production Comparison](https://odsea.com/blog/langgraph-vs-crewai-vs-autogen-production)
- **Blog post:** "AutoGen is effectively dead — maintenance mode, replaced by Microsoft Agent Framework (MAF)." GitHub stars: AutoGen 58,500 (but stalled), CrewAI 52,500, LangGraph 33,400. The framework landscape has consolidated around two active projects. — [ODSEA — LangGraph vs CrewAI vs AutoGen Production Comparison](https://odsea.com/blog/langgraph-vs-crewai-vs-autogen-production)
- **Blog post:** "The defensible asset in enterprise AI is not the model. It's the organizational world model." 37% of enterprises now run 5+ AI models in production. The stack stratifies into Context, Inference, Orchestration, Sandboxing, Memory, and Tools layers — each with different defensibility profiles. — [Philipp Dubach — The Agent Stack Is Stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN post:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — [Hacker News — Show HN: Local-First Linux MicroVMs](https://news.ycombinator.com/item?id=47114201)

## Gotchas

- **CrewAI's "flow-first" documentation is new.** Wrapping Crews in Flows for state management was added to handle exactly the production gaps that early adopters hit. If you find Crews hard to debug, you likely skipped the Flow layer.
- **LangGraph's graph model requires upfront design work.** The flexibility that makes it powerful for production also means you cannot just describe agents in YAML and have it work. Plan your state schema before you start.
- **Stratification changes cost modeling.** With 6 layers, each with independent providers, cost doesn't just mean "LLM API spend." Sandboxing (E2B, Modal), memory (Pinecone, Qdrant), and tool hosting each add line items. A 4-agent workflow with shared memory and sandboxed tool execution can cost $5–8 per complex task — model this before committing to architecture.
- **The "over 40% of agentic AI projects cancelled by end of 2027" Gartner projection** (from a16z AI Enterprise 2025) is not because the technology fails — it is because of unclear business value and shallow context depth. The lesson: a well-scoped narrow agent beats a broad generalist every time in production.
