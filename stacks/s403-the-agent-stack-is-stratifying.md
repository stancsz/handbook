# S-403 · The Agent Stack Is Stratifying Into Six Layers

The "AI agent stack" is not a stack — it's a landscape of distinct layers with different defensibility profiles, different lock-in trajectories, and different competitive dynamics. Treating it as a monolith leads to over-investment in commoditizing layers and under-investment in the one zone that compounds: your organizational context.

## Forces

- **Model providers are racing to the bottom.** OpenAI, Anthropic, Google, Meta, Mistral, DeepSeek all compete aggressively on capability and price. Being "built on GPT-5" is not a moat — the model layer is becoming as undifferentiated as cloud compute.
- **37% of enterprises now run five or more models in production.** Single-provider lock-in is the new single-cloud risk. Polyglot inference is the default, not the exception.
- **Context is the highest-lock-in, hardest-to-rebuild asset.** The knowledge that makes your agent useful — your company's decisions, relationships, reasoning patterns, and institutional memory — cannot be replicated by downloading a new model.
- **Gartner predicts 40% of agentic AI projects will be canceled by end of 2027** due to unclear business value. The failure mode is building infrastructure without building the thing that actually matters: domain-specific context.
- **Sandboxing and execution environments are becoming their own product category.** E2B, Modal, Shuru, Firecracker wrappers are separating from the orchestration layer entirely.

## The move

Recognize the six layers and invest proportionally. The commoditizing layers (models, orchestration) should be abstracted and swappable. The compounding layers (context, workflow) are where to build defensibility.

**Layer 1 — Foundation Models.** The base reasoning engine. Commodity by 2026. Strategy: abstract behind a model router. Don't hard-code GPT-4o or Claude-3.5. Swap freely based on cost, latency, and capability at the task level.

**Layer 2 — Orchestration / Agent Framework.** LangGraph, CrewAI, AutoGen, or custom state machines. This layer determines how agents decompose tasks, coordinate, and recover from errors. Strategy: choose based on team familiarity and complexity ceiling — LangGraph for production-grade graph workflows, CrewAI for fast prototyping toward team-based agents.

**Layer 3 — Tooling and Integration.** MCP servers, REST tool schemas, code execution environments. This layer connects agents to your actual systems. Strategy: MCP is emerging as the standard interface. Invest in tool design quality, not tool quantity.

**Layer 4 — Context and Memory.** Semantic memory (vector stores: Pinecone, Qdrant, pgvector), episodic memory (session state), and organizational memory (your specific decisions and reasoning). Strategy: this is the compounding layer. Protect it. Make it portable. Build retrieval quality as a core competency.

**Layer 5 — Sandboxing and Execution.** The environment where agent actions run. CloudVMs, containerized code execution, browser automation. Strategy: treat as a separate infrastructure concern. Platforms like E2B, Modal, and Firecracker-based wrappers are solving this independently from orchestration.

**Layer 6 — Governance and Evaluation.** Observability, cost control, safety rails, human-in-the-loop checkpoints. Strategy: evaluate not just model outputs but agent behavior end-to-end. Amazon's research notes that multi-agent systems require HITL (human-in-the-loop) evaluation because automated metrics fail to capture coordination failures, inter-agent communication breakdowns, and emergent edge cases.

## Evidence

- **Blog post:** "Don't Go Monolithic; The Agent Stack Is Stratifying" — documents the six-layer model with lock-in risk analysis, finding 37% of enterprises use 5+ models in production and context is the highest-risk lock-in layer — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Engineering blog:** LangGraph vs CrewAI vs AutoGen comparison with production guidance — recommends defaulting to LangGraph due to graph-based state management, notes 90k+ GitHub stars vs CrewAI's 20k+ — [devops.gheware.com](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Engineering blog:** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025, with 57% of organizations already running agents in production; 89% have observability but only 52% have evals — [raftlabs.com](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- **Building on a model's capabilities rather than your own context is a trap.** When the model improves, your "moat" disappears. The defensible asset is how your agent reasons about your specific domain, not the base model.
- **Orchestration frameworks create hidden coupling.** A CrewAI prototype that works well for 3 agents often requires a painful rewrite to LangGraph when you need graph-state recovery, conditional branching, and long-running workflow persistence. Default to the more expressive framework for production.
- **Observability without evaluation is theater.** Teams instrument their agents (89%) but fewer than half run evals (52%). You can see what your agents did but not whether they were right.
- **Sandboxing is still immature.** Code execution environments for agents vary wildly in isolation guarantees, timeout behavior, and cost. Treat this as an unsolved problem and plan for migration.
