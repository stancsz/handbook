# S-620 · From Monolithic "God Prompt" to Agent Stack Stratification

[The single-agent prompt is maxed out. Context windows fill, persona bleeds through guardrails, and the model becomes a confident Yes-Man doubling down on its own hallucinations. The architectural response is not a bigger model — it's splitting the stack into specialized layers and connecting them through open protocols.]

## Forces

- **Monolithic agents hit a hard ceiling at complexity ~8-10 tools.** Tool selection accuracy drops below 90%, response latency compounds, and persona bleed becomes unavoidable. You cannot prompt-engineer your way out of this.
- **Integration debt is the N×M problem.** Every new model × every new tool requires a custom integration. Without a shared protocol, this compounds faster than teams can keep up.
- **Sandboxing is its own layer now.** Agents that execute code, browse the web, or call external APIs need isolation — but this was bolted on ad hoc. It's becoming a first-class infrastructure concern.
- **The observability gap is real.** 89% of teams building multi-agent systems have monitoring; only 52% have evals. This explains why debugging is still mostly guesswork.

## The Move

Break the agent into specialized layers connected by open, standardized protocols:

**1. Orchestration layer — choose your mental model.**
- LangGraph for explicit state machines: durable execution, graph visualization, strong for production systems needing observability (Klarna, Replit, Elastic confirmed users)
- CrewAI for role-based crews: fast to wire up, good for content pipelines and support workflows where role handoffs map naturally
- AutoGen for conversational agents: strong for multi-turn negotiation patterns; now in maintenance mode (Oct 2025), successor is Microsoft Agent Framework
- OpenAI Agents SDK for minimal primitives: teams that want low abstraction overhead and full control
- Custom state machines for simple, well-bounded tasks: don't reach for a framework if a loop + switch statement covers it

**2. Tool-calling layer — standardize on MCP.**
- The Anthropic-led Model Context Protocol (MCP, launched Nov 2024, donated to Linux Foundation Dec 2025) won the protocol war. Microsoft, PayPal, Twilio, Box, Asana, and ElevenLabs have shipped MCP servers.
- November 2025 update added server discovery via `.well-known` URLs, async operations, and scalability improvements — signaling production graduation.
- MCP solves the N×M integration problem: implement the protocol once per model host and once per tool, gain universal interoperability instead of custom wiring per pair.

**3. Execution/sandboxing layer — isolate untrusted or dangerous tool execution.**
- E2B, Modal, Firecracker wrappers, and Shuru are all converging on lightweight sandboxing as a distinct primitive.
- The stack is stratifying: orchestration ≠ execution ≠ tool hosting. Treating these as separate concerns makes each independently replaceable.

**4. Memory layer — vector DB is necessary but not sufficient.**
- Vector databases (Pinecone, Qdrant, pgvector, Weaviate) handle semantic retrieval. They are not memory systems.
- A production memory system additionally needs: query decomposition for multi-part questions, hybrid retrieval (semantic + keyword with configurable fusion), memory triage (what gets promoted from session to long-term), and forgetting policies.
- Storage choice tracks team context: pgvector lives inside existing Postgres, costs 3-8× less than Pinecone at equivalent scale, handles ~2M vectors without special tuning. Pinecone for zero-ops at scale. Qdrant for maximum throughput on self-hosted.

**5. Evaluation layer — non-negotiable at multi-agent scale.**
- LangSmith, Phoenix (Tracelens), or custom structured logging with schema-verified agent traces.
- Without evals, multi-agent debugging is archaeology. The observability gap (89% monitoring vs 52% evals) is the primary reason teams can't explain failures.

## Evidence

- **Engineering blog:** The agent stack stratifying into orchestration, sandbox, and tool-hosting layers — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/) — confirmed in HN discussion citing E2B, Modal, Firecracker wrappers as distinct sandboxing options
- **Industry analysis:** "The protocol war is over. MCP won." — [byteiota.com](https://byteiota.com/mcp-protocol-november-25-update-production-ready-ai-agent-standard) covering Anthropic's Nov 2025 MCP update and Linux Foundation donation
- **Enterprise blog:** MCP adoption by PayPal, Microsoft, Twilio, Box, Asana, ElevenLabs — [clarion.ai](https://clarion.ai/insights-model-context-protocol-enterprise-interoperable-ai-agent-infrastructure)
- **Framework comparison:** LangGraph favored for production systems needing durable execution and observability; CrewAI for fast role-mapping pipelines; AutoGen in maintenance — [getbeam.dev](https://getbeam.dev/blog/agent-orchestration-frameworks-compared-2026.html)
- **Memory architecture:** "Pinecone, Weaviate, Qdrant, and pgvector give you basic semantic search. Here is everything else a production memory system requires" — [exabase.io](https://exabase.io/blog/why-a-vector-database-is-not-a-memory-system)
- **Vector DB comparison:** pgvector sufficient to ~2M vectors, Pinecone for zero-ops at scale, Qdrant for maximum throughput; Weaviate dropped due to schema-first friction — [kalviumlabs.ai](https://www.kalviumlabs.ai/blog/vector-databases-compared-pgvector-pinecone-qdrant-weaviate)
- **Multi-agent stats:** 89% of teams have observability, only 52% have evals; 1,445% surge in multi-agent system inquiries Q1 2024 → Q2 2025 (Gartner) — [raftlabs.com](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Production patterns:** Four categories consistently shipped in 2025: developer tooling, internal ops automation, research/analysis, customer service — [technspire.com](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Don't reach for a framework before you need one.** A well-bounded single-agent task with 3-5 steps and clear success criteria doesn't need LangGraph. The framework imposes a mental model; fight it only when the problem requires it.
- **MCP is not a magic interoperability wand.** MCP standardizes the *interface* but not the *implementation quality*. A poorly implemented MCP server will still cost you weeks. Evaluate servers, not just the protocol.
- **Vector search ≠ memory.** Adding Pinecone and calling it "memory" is a common and expensive mistake. Memory requires query decomposition, triage, and forgetting — none of which a vector DB provides out of the box.
- **Inference cost compounds across agents.** A 4-agent orchestrator-worker workflow can cost $5-8 per complex task. Model the economics before committing to architecture, not after.
- **AutoGen is in maintenance.** If starting a new project today, the AutoGen → Microsoft Agent Framework migration path needs to be on your radar.
