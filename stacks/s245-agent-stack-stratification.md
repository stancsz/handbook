# S-245 · Agent Stack Stratification

The agent stack is not a monolith. It is splitting into six specialized layers — and teams that treat it as one thing pay for it in debuggability, cost, and lock-in. Understanding which layer owns which concern lets you upgrade, swap, and harden each independently.

## Forces

- **The monolithic agent assumption creates tight coupling.** When you bundle orchestration, tool execution, memory, and sandboxing into a single abstraction, a change in any one concern forces a change in all of them — and failures propagate invisibly across layer boundaries.
- **Different layers have fundamentally different defensibility profiles.** The model layer is commoditizing fast (OpenAI → Anthropic → open-source within months). The organizational world model — your data, your tools, your access patterns — is the durable asset. Treating them symmetrically means investing engineering effort in the wrong place.
- **Sandboxing is its own discipline.** Agent code execution is not the same as a web request handler. The failure modes (infinite loops, data exfiltration, privilege escalation) require isolation primitives that general-purpose orchestration frameworks do not provide.
- **Typed schemas are where multi-agent workflows break, not in the agents themselves.** Data passed between agents is unstructured by default. The boundary between two agents is where pipelines silently fail — not because either agent is unreliable, but because the interface contract is undefined.
- **Error rates compound multiplicatively in multi-agent pipelines.** Five steps at 95% accuracy each yields 77% end-to-end accuracy. This is not a prompting problem — it is an architectural problem.

## The move

Decompose the agentic stack into independent layers, each with a clear interface to its neighbors. The six-layer model from production teams:

1. **Model routing** — picks which model handles which task. 37% of enterprises now run 5+ models in production, routing by cost, capability, and latency. Keeps the model layer swappable without rewriting orchestration.
2. **Orchestration** — defines agent behavior, state transitions, and workflow. LangGraph for graph-based state machines with audit trails; CrewAI for fast role-based prototyping; custom FSM for fully deterministic pipelines. Critically, this layer should not own tool execution.
3. **Memory and persistence** — thread-level context (Redis), session-level (PostgreSQL), long-term knowledge (Pinecone, Qdrant). Separate the cache hierarchy from the orchestration layer with a well-defined read/write interface.
4. **Tool execution / sandboxing** — the actual runtime for agent code and tool calls. E2B, Modal, Firecracker-based isolation. This is increasingly a separate purchase decision from orchestration. Voice AI agents handle only 3–4 concurrent users per instance (persistent WebSocket connections, not request/response), making container-per-session a real infrastructure concern.
5. **Observability and evals** — LangSmith, Phoenix, or custom distributed tracing. 89% of teams with agents in production have observability; only 52% have structured evals. You cannot improve what you cannot measure — and raw traces are not measurement.
6. **Governance and guardrails** — input/output validation, hallucination detection, cost controls, PII redaction. Must be enforced at the orchestration layer boundary, not retrofitted inside agents.

## Evidence

- **HN post / Philipp Dubach:** The agent stack is splitting into specialized layers, with sandboxing emerging as its own category (Shuru, E2B, Modal, Firecracker wrappers). Argues each layer has a different defensibility profile and that monolithic stacks are the wrong call. — [Don't Go Monolithic: The Agent Stack Is Stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **RaftLabs (Gartner data):** 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. 57% of organizations already running agents in production. Four orchestration patterns cover most use cases: hierarchical, pipeline, orchestrator-worker, and peer-to-peer. Inference costs compound to $5–8 per complex 4-agent task. — [Multi-Agent Systems: Architecture Patterns for Production AI](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Gheware DevOps Blog:** LangGraph is the enterprise production standard (stateful graphs, audit trails, HITL for regulated industries). AutoGen entered maintenance in October 2025 with Microsoft Agent Framework as successor. Most Fortune 500 teams start with CrewAI and migrate to LangGraph. — [LangGraph vs AutoGen vs CrewAI: Enterprise Comparison 2026](https://devops.gheware.com/blog/posts/langgraph-vs-autogen-vs-crewai-comparison-2026.html)

## Gotchas

- **Do not conflate orchestration flexibility with capability.** A LangGraph workflow that routes between ten agent types is not inherently more capable than a well-scoped CrewAI crew — it is more auditable and durable under production load. Choose based on audit requirements, not perceived sophistication.
- **Typed schemas at agent boundaries are not optional in production.** Unstructured JSON passed between agents silently degrades. Define Pydantic or equivalent schemas at every inter-agent interface — this is the most reliable single improvement to multi-agent reliability.
- **Semantic caching lives at the memory layer, not orchestration.** Teams that implement vector similarity caching inside the orchestration loop end up with cache coherence bugs. Cache at the retrieval layer with a clear invalidation policy.
- **Load balancers do not work for voice/session-based agents.** Traditional round-robin or least-connections routing cannot route start/stop requests to the same session-aware instance. Session affinity is required — this is ainfra, not orchestration.
- **Observability without evals is theater.** Logging every LLM call is not the same as measuring whether outputs are correct, safe, and on-brand. Define eval datasets and run them in CI before calling the system production-ready.
