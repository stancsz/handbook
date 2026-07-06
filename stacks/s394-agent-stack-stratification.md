# S-394 · Agent Stack Stratification

The moment you need two agents to share a tool, handle a failure, and coordinate state — the "one framework to rule them all" approach collapses. The stack fractures into layers whether you planned it or not. Teams that embrace stratification from day one ship faster and debug cleaner than those who fight it.

## Forces

- **Monolithic frameworks promise simplicity but create coupling.** When orchestration, tool execution, sandboxing, memory, and observability are all inside one abstraction, a change in any layer ripples unpredictably through the rest
- **The failure modes of agents are inherently layer-specific.** A token budget blowout is an orchestration concern. A tool returning malformed JSON is a tool-layer concern. A silent semantic failure is a verification concern. These require different mitigations
- **The ecosystem is converging on specialized tools per layer.** The days of building everything in CrewAI or LangGraph are giving way to composing: LangGraph for orchestration, MCP for tools, Temporal or Modal for sandboxed execution, LangSmith for traces — each layer independently swappable
- **Teams that stratify too late pay twice.** Retrofitting separation of concerns into a tightly coupled agent monolith is harder than building it in from the start

## The move

Accept that an agent system has at least four distinct layers. Design for their independence from day one.

**Layer 1 — Orchestration.** The brain: decides what to do, in what order, with what context. LangGraph when you need graph-based state machines and checkpointing. CrewAI for fast prototyping of role-based agent teams. AutoGen when multi-agent conversation dynamics are the core value. Raw LLM API when the workflow is simple enough that the framework adds more complexity than it removes.

**Layer 2 — Tool calling.** The hands: executes actions against external systems. MCP (Model Context Protocol) is emerging as the standard interface layer — it solves the "one agent, N tools" wiring problem cleanly and has 16.6k GitHub stars on Microsoft's reference implementation. Custom tool schemas via function calling remain valid for internal systems where the MCP overhead isn't worth it.

**Layer 3 — Sandboxed execution.** The isolation layer: runs untrusted code, browser automation, shell commands. E2B, Modal, Shuru, and Firecracker wrappers are each carving out territory here. Firecracker-based microVMs win on cold-start latency for short-lived tool execution. E2B wins on the browser-automation use case. Pick based on your threat model and latency budget, not on framework compatibility.

**Layer 4 — Observability and memory.** The spine: traces every decision, stores state across runs. LangSmith for LangGraph-native traces with time-travel debugging. Phoenix (by Arize) for framework-agnostic observability. For memory: hybrid of vector DB (Qdrant, Weaviate, or pgvector for sub-5M-vector scale) plus a structured session store. Don't conflate retrieval memory with conversation state — they have different access patterns.

## Evidence

- **HN post on stack stratification:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." A practitioner's direct account of hitting the monolithic ceiling and reaching for layer separation — [https://news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)
- **DevOps comparison guide (2026):** "Default to LangGraph unless you have strong reasons not to — while the learning curve is steeper, you won't hit a ceiling 6 months in and face a painful rewrite." Documents why orchestration-layer decisions are load-bearing — [https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **RaftLabs production survey (2025):** 1,445% surge in multi-agent system inquiries (Q1 2024 → Q2 2025 per Gartner); 57% of organizations already have agents in production; four orchestration patterns cover most production use cases: hierarchical, pipeline, orchestrator-worker, and peer-to-peer — [https://www.raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **GitHub decision guide (2026):** MCP achieves 5-star support in LangGraph with first-class graph nodes and full streaming; LangSmith provides time-travel debugging and checkpointing — [https://github.com/benconally/ai-agent-framework-decision-guide](https://github.com/benconally/ai-agent-framework-decision-guide)
- **RAG architecture analysis (2026):** pgvector is sufficient for most teams under ~5-10M vectors; embedding model sets the ceiling for retrieval quality before vector DB choice matters — [https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns)

## Gotchas

- **Untyped handoffs kill multi-agent workflows faster than any other issue.** When one agent passes context to another, the schema must be explicit and enforced. LangGraph's typed state channels handle this well; CrewAI's implicit role-based passing does not by default
- **Sandboxing is not optional if agents touch the network or filesystem.** Running tool execution in the same process as orchestration is a category error — it couples a high-trust concern (LLM decisions) with a high-risk concern (arbitrary code/network). Teams skip this in prototypes and pay in production incidents
- **Cost compounds non-linearly in multi-agent systems.** A 4-agent orchestrator-worker workflow typically runs $5–8 per complex task (RaftLabs, 2025). Budget for inference cost management as a first-class concern, not an afterthought — circuit breakers, token budgets, and model routing all belong in layer 1
