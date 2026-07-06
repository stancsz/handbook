# S-231 · The Simplicity Principle — When Frameworks Cost More Than They Save

Agents demo beautifully. Production breaks quietly. The field is converging on a counterintuitive lesson: strip the framework, keep the pattern.

## Forces

- **Frameworks add indirection that hurts debugging.** LangChain's abstraction layers have been cited in HN threads and Reddit posts as making tracebacks opaque — when an agent loops infinitely or calls the wrong tool, the framework's state management obscures which line caused it
- **The N×M MCP problem is real.** Without a standard protocol, every new model–tool pair required a custom connector; the explosion of agent-to-tool integrations made this unsustainable
- **YC 2025 signals infrastructure maturity.** The Fall 2025 YC batch was ~50% AI agents — but early deployments surfaced "operational constraints" and "workflow ownership issues" that lean teams without infrastructure backgrounds struggled to debug
- **Microsoft unified AutoGen + Semantic Kernel.** The April 2026 GA of Agent Framework 1.0 was partly a response to ecosystem fragmentation, consolidating two Microsoft-backed frameworks into one production SDK

## The move

**Start with LLM API calls directly. Add orchestration only when you can name the specific complexity it's solving.**

- **Start minimal.** Anthropic's engineering guide explicitly recommends beginning with direct API calls — many agent patterns fit in a few lines of code without LangChain, CrewAI, or any framework
- **Reach for LangGraph when you need explicit control flow.** Its directed-graph model shines for complex branching, parallel nodes, and cyclical workflows where you need to inspect or replay execution paths — but it's a tool, not a foundation
- **Reach for CrewAI when team roles are clear.** Role-based agent composition (researcher → writer → reviewer) maps well to business workflows with defined handoffs, not to arbitrary computational graphs
- **MCP is now the standard connector layer.** Adopted by OpenAI (March 2025), Google (April–May 2025), Microsoft, and AWS; donated to the Linux Foundation's Agentic AI Foundation (December 2025). Treat it as USB-C for AI — it eliminates per-model tool rewrites
- **Instrument before you optimize.** The number one lesson from multi-agent production deployments: you cannot fix what you cannot see. Structured logging and trace IDs across agent hops are not optional — they're the only way to find where a plan derailed

## Evidence

- **Anthropic engineering guide (primary source, June 2025):** "We suggest that developers start by using LLM APIs directly: many patterns can be implemented in a few lines of code." Their most successful implementations used "simple, composable patterns" rather than complex frameworks — [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **HN thread on same guide (543 points, June 2025):** Multiple practitioners confirmed the pattern — one commenter with Durable Objects noted the actor model maps well onto agents, where each agent instance = one actor, and agent-to-agent communication = tool calling via MCP or RPC. A recurring theme: frameworks that abstract too early make debugging harder than the original problem — [HN Discussion: Building Effective AI Agents](https://news.ycombinator.com/item?id=44301809)
- **Turion.ai framework comparison (2026):** Built production systems on all three (LangGraph, CrewAI, Microsoft Agent Framework). Their decision framework: LangGraph for explicit flowchart control, CrewAI for role-based team workflows, Microsoft Agent Framework when emergent conversational patterns between agents are the primary value — [LangGraph vs CrewAI vs AutoGen 2026 Comparison](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)
- **MCP adoption trajectory:** MCP server downloads grew from ~100K (November 2024) to 8M+ (April 2025). Enterprise deployments at Block, Bloomberg, Amazon, and hundreds of Fortune 500 companies. By end of 2025, an estimated 90% of organizations will use MCP — [Guptadeepak.com: MCP Enterprise Adoption 2025](https://guptadeepak.com/research/mcp-enterprise-guide-2025/)
- **YC batch data:** 67 of 144 startups in YC Spring 2025 batch were AI agents (up from 58/163 in Winter 2025). The Fall 2025 batch was ~50% agents. Key constraint cited: "operational constraints and workflow ownership issues" in early deployments — [PitchBook: YC going all-in on AI agents](https://pitchbook.com/news/articles/y-combinator-is-going-all-in-on-ai-agents-making-up-nearly-50-of-latest-batch)
- **Madrona infrastructure analysis (February 2025):** Neon reported AI agents creating databases at 4× the rate of human developers; Create.xyz created 20,000 databases in 36 hours on Neon. Three-layer framework emerging: Tools (MCP), Data (vector stores, pgvector), Orchestration — [Madrona: AI Agent Infrastructure Three Defining Layers](https://www.madrona.com/ai-agent-infrastructure-three-layers-tools-data-orchestration/)

## Gotchas

- **LangChain is not LangGraph.** LangChain (the high-level framework) has significant abstraction overhead; LangGraph (the lower-level graph library) is leaner and more transparent. Choosing LangChain "because it has LangGraph" conflates two very different tools
- **MCP adoption does not equal MCP security.** The rapid growth outpaced security tooling. Common failure modes: tool poisoning attacks (malicious context injection via MCP tool responses), misconfigured permission scoping, and compliance gaps across EU AI Act / HIPAA. Sandboxed execution environments and explicit context declarations are not yet universal
- **Multi-agent coordination overhead grows non-linearly.** Three agents coordinating in a chain is manageable. Twelve agents in a peer network with shared state produces failure modes (message storms, conflicting tool calls, deadlock) that are genuinely hard to debug. Split agents by audience or trust boundary, not by workflow step
- **Cost observability lags feature development.** Most teams have no idea what their agents cost per task until the API bill arrives. Token counting, per-agent cost attribution, and budget alerts are still afterthoughts in most stacks
