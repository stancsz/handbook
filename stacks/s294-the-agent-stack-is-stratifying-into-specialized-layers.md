# S-294 · The Agent Stack Is Stratifying into Specialized Layers

Agent demos run on a monolith. Production runs on layers. The enterprise AI agent stack is following the same decomposition pattern as cloud infrastructure and the modern data stack — and teams that go monolithic are building technical debt that compounds faster than they realize.

## Forces

- **Monolithic stacks prototype fast and scale painfully.** Tutorial- cliff frameworks that let you "build an agent in 5 lines" collapse at production scale. The "fifth agent framework" problem — Xpress AI tried 5 before shipping — is the symptom of picking a monolith that couldn't be upgraded without a rewrite.
- **Each stack layer has a different rate of change and defensibility.** Model layers commoditize every 6 months. Context layers (organizational knowledge, process graphs, relationships) compound over years. Treating them the same leads to over-investment in the wrong place.
- **37% of enterprises now run 5+ models in production.** Single-provider lock-in is the new single-cloud risk. The HN-comment from 7777777phil on the agent stack splitting HN post: "these layers have very different defensibility profiles and why going monolithic is the wrong call."
- **Sandboxing is becoming its own infrastructure category.** Shuru, E2B, Modal, Firecracker wrappers — execution isolation has different requirements than orchestration or context, and teams are buying/building dedicated solutions rather than bolting it on.

## The move

Decompose the agent stack into specialized layers. Pick the right tool at each layer rather than defaulting to one vendor's opinion of the full stack.

- **Context layer** — your organizational world model is the highest-lock-in, hardest-to-rebuild asset. Invest here. This is not RAG alone; it's process knowledge, relationship graphs, institutional memory.
- **Model layer** — route tasks to the right model. Claude for coding/cognition, GPT for reasoning, smaller open-source models for high-volume low-stakes tasks. Multi-model is the norm, not the exception.
- **Orchestration layer** — LangGraph for stateful workflows requiring auditability (regulated industries); CrewAI for rapid prototyping and role-based pipelines; custom state machines for unique coordination patterns.
- **Tool/sandboxing layer** — MCP (Model Context Protocol) as the standard interface for LLM-to-tool connections. Dedicated sandboxing (E2B, Modal, Firecracker) for code execution isolation, separate from orchestration.
- **Security layer** — permissions, compliance, access control, output validation. Treat as a distinct infrastructure concern with its own blast radius.
- **Observability layer** — LangSmith for LangGraph-deep tracing; Arize Phoenix for OpenTelemetry-native; Langfuse for self-hosted. Non-negotiable at multi-step workflow scale.

## Evidence

- **Blog post:** Philipp D. Dubach analyzed the 6-layer stack and found context (organizational world model) has the highest lock-in while models have the lowest. 37% of enterprises run 5+ models in production. Gartner predicts 40% of agentic AI projects will be cancelled by end of 2027 due to unclear business value. — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN comment (primary source):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — [HN #47114201](https://news.ycombinator.com/item?id=47114201)
- **Engineering blog:** Xpress AI's "Digital Workforce" team shipped their fifth agent framework in 2025 after abandoning earlier monoliths. The lesson: "frameworks promising 'build in 5 lines' collapse at production scale." — [xpress.ai](https://xpress.ai/blog/2025-agent-lessons)

## Gotchas

- **Going monolithic is the locally-optimal, globally-disastrous choice.** Fast to start, expensive to evolve. By the time you hit the wall, your organizational context is tangled with the framework.
- **Underestimating context as the defensible layer.** Agents that retrieve documents but cannot reconstruct human reasoning processes (why a decision was made, who escalated it, what the informal process actually is) will fail at enterprise adoption. Invest in context graphs, not just retrieval.
- **Treating MCP as optional rather than foundational.** MCP (open-sourced by Anthropic, November 2024) is rapidly becoming the N×M solution for LLM-to-tool connectivity. Build vs. buy decisions on MCP servers should be an architectural decision, not a feature add.
