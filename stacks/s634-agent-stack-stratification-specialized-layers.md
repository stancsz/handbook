# S-634 · Agent Stack Stratification: Why the Monolithic Agent is Dead

When your first agent prototype works, you add features. Then tools. Then memory. Then another agent. Six months later you're debugging a tangled mess where orchestration, state, memory, and tools are all glued together with prompts — and adding one new capability means touching everything. The industry hit the same wall and started peeling the stack apart. The result: a clear set of specialized layers, each with its own best-of-breed solution, connected by well-defined interfaces.

## Forces

- **Monolithic agents hit a ceiling fast.** Tool selection accuracy drops below 90% when an agent manages 10+ tools. Context windows fill. Latency compounds. Adding a second agent to a monolith just doubles the blast radius when it fails.
- **The interface surface between layers is where multi-agent systems die.** Untyped handoffs — raw string or JSON blobs passed between agents — are the leading cause of multi-agent failure, ahead of model quality, context length, or orchestration complexity.
- **Infrastructure and orchestration have very different defensibility profiles.** A framework wrapper around an LLM API is easy to replace. A sandboxing runtime or specialized memory backend is much harder. Treating them as equivalent leads to over-investment in the wrong layer.
- **The observability gap is structural, not intentional.** 89% of teams have tracing, but only 52% have evals. This gap is why multi-agent debugging is still mostly guesswork.

## The Move

Decompose the agent stack into five independent layers. Each has a clear responsibility, a dominant tool choice, and a well-defined interface to its neighbors. Replace or upgrade one layer without touching the others.

**The five-layer model:**

- **Orchestration** — defines agent behavior, state transitions, and multi-agent coordination. LangGraph for graph-based workflows (explicit control, cyclic state, checkpointing). CrewAI for role-based teams (faster to scaffold, less granular control). Microsoft Agent Framework 1.0 (ex-AutoGen) for conversational multi-agent with emergent patterns. DSPy for declarative, optimizer-driven pipelines.
- **Tooling / connectivity** — standardizes how agents talk to external services. MCP (Model Context Protocol) has become the dominant interface: 97M+ monthly SDK downloads, 5,800+ servers, 300+ clients as of late 2025. Replaces N×M custom integrations with a single protocol. Critical caveat: 43% of MCP servers have command injection flaws; exploit probability exceeds 92% with 10 plugins installed.
- **Memory / persistence** — manages conversation state, semantic memory, and retrieval. pgvector for teams already on Postgres. Pinecone or Qdrant for cloud-native vector search at scale. Redis for low-latency session state. Custom Hebbian/associative graphs for research-grade memory with natural decay.
- **LLM** — the reasoning core. OpenAI for general-purpose with broad tool support. Anthropic Claude for complex reasoning, long contexts, and enterprise use cases. Open-source (Llama 3.x, Mistral) for cost-sensitive or data-sovereign deployments. Selection is driven by capability requirements, not convenience.
- **Execution / sandboxing** — isolates agents from the host system. E2B, Modal, Shuru, Firecracker microVMs. Docker with strict resource limits for reproducible multi-agent deployments. This layer is increasingly being unbundled as its own product category.

## Evidence

- **HN post (2025):** Opensoul — a 6-agent marketing agency stack built on Paperclip — demonstrates the multi-agent team pattern in production: Director (strategy/coordinator), Strategist, Creative, Producer, Growth Marketer, Analyst, each with autonomous task execution and inter-agent delegation. — https://news.ycombinator.com/item?id=47336615
- **HN comment (2025):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — corroborates the stratification thesis with on-the-ground production observation. — https://news.ycombinator.com/item?id=47114201
- **Engineering blog (Nov 2025):** Multi-agent systems guide with data from Gartner (1,445% surge in multi-agent inquiries Q1 2024→Q2 2025) and primary research finding: "Untyped handoffs between agents kill multi-agent workflows faster than any other issue. Every agent-to-agent boundary needs a validated schema with version numbering." — https://www.raftlabs.com/blog/multi-agent-systems-guide
- **Research (Dec 2025):** MCP ecosystem reached 97M+ monthly SDK downloads, 5,800+ servers, 300+ client apps by late 2025, with OpenAI adopting MCP in March 2025. — https://guptadeepak.com/research/mcp-enterprise-guide-2025
- **Cost benchmarks (2026):** Real production agent costs by tier: simple chatbot $23–45/month, tool-using agent $200–800/month, multi-agent workflow $500–5,000+/month, complex orchestration $2,000–15,000+/month. — https://tokenfence.dev/blog/ai-agent-cost-benchmarks-2026-real-numbers

## Gotchas

- **Don't conflate orchestration with execution.** LangGraph runs your graph; it doesn't sandbox your code execution. Teams that treat these as the same layer end up with security gaps where a malicious tool call escapes the agent boundary.
- **MCP security is an afterthought in most stacks.** 43% of servers have command injection flaws. Treat MCP servers like untrusted code: run them in isolated environments, validate all tool parameters with schema enforcement, and audit server permissions before production.
- **Typed handoffs are not optional.** Raw string handoffs between agents will cause silent failures that are nearly impossible to debug. Every inter-agent boundary needs a Pydantic schema or equivalent with version numbering — not just for type safety, but for backward compatibility as agents evolve.
- **Cost compounds multiplicatively across layers.** A 4-agent orchestrator-worker workflow at complex task complexity runs $5–8 per task in inference alone (RaftLabs, 2025). Model this before committing to architecture, not after the invoice arrives.
- **Evals are not tracing.** Tracing tells you what happened. Evals tell you whether it was right. The 37-point gap between observability adoption (89%) and eval adoption (52%) is the reason most teams can't explain why their agent failed — they just know it did.
