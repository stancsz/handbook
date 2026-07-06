# S-648 · The Three-Layer Agentic Stack

[Most "AI agents" in production are a single LLM with a while loop. Systems that actually hold up under load decompose reasoning, planning, and execution into distinct layers with different failure modes and optimization targets.]

## Forces
- **LLMs are general-purpose but not specialized.** A model good at reasoning is not the same as one optimized for fast tool execution or coherent long-horizon planning. Treating a single model for all three creates a ceiling on each.
- **Debugging is nearly impossible without layer separation.** When a "agent" fails, you can't tell if it planned wrong, reasoned poorly, or executed the tool call incorrectly. A flat loop hides all three failure modes in one output.
- **Latency, cost, and reliability trade-offs conflict across layers.** Fast, cheap models for execution drag on planning quality. Large frontier models for reasoning introduce latency unacceptable for high-frequency tool calls. These tensions only resolve with explicit layer boundaries.
- **The single-loop mental model is the default trap.** It maps intuitively to "the AI thinks, then acts, then repeats." It is also the architecture that burns $3,400/month in API calls with nothing to show.

## The move
Split the agent into three functionally distinct layers, each with its own model, interface contract, and failure mode:

- **Reasoning layer** — slow, capable model (Claude Opus, GPT-4o). Decomposes the high-level goal into sub-steps. Emits a structured plan. This layer runs infrequently (once per task or human interrupt).
- **Planning layer** — medium model (Claude Haiku, GPT-4o-mini). Takes the reasoning layer's plan and decides *which tools to call next* and *with what arguments*. Maintains short-horizon state. This is the hot loop — optimized for latency and cost.
- **Execution layer** — fast model or deterministic function (GPT-4o-mini, or pure code for stateless tools). Actually calls external APIs, reads files, sends webhooks. Returns structured results to the planning layer. This layer must be fast because it is called many times per task.

Each layer communicates via a typed schema contract — not natural language. The reasoning layer outputs JSON plans. The planning layer outputs tool-call descriptors. The execution layer returns structured results. This makes every layer independently testable and debuggable.

Additional patterns that separate shipped systems from pilots:

- **Circuit breakers on the execution layer.** If a tool call fails three times, halt and escalate to a human. Do not let the planning layer retry indefinitely.
- **Streaming at the reasoning layer only.** Show the user the model's thinking in real time from the reasoning layer. Execution layer calls happen silently in the background.
- **Token budgets per layer.** Assign a per-task token allowance to the reasoning layer, a per-step allowance to the planning layer. When budget is exhausted, fail deterministically rather than drifting.

## Evidence
- **Blog (Technspire, Dec 2025):** "The core lesson: agents work where software engineering discipline works." Four categories consistently shipped to production: developer tooling, internal ops automation, research synthesis, and customer-facing Q&A — all with explicit layer boundaries and feedback loops. Systems that failed did so because they treated the LLM as both planner and executor with no separation. — https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons
- **Blog (Essa Mamdani, May 2026):** "The difference between a monolithic LLM wrapper and a distributed agentic architecture: 40% latency drop, automatic failure recovery, and stopping the 'API lottery.'" Documents the three-layer stack (Reasoning / Planning / Execution) as the 2026 production standard, with MCP as the execution-layer protocol. — https://essamamdani.com/blog/production-grade-agentic-ai-mcp-multi-agent-2026
- **Blog (AIThinkerLab, Jun 2026):** RAG systems follow an 8-pattern complexity ladder. The highest two rungs — agentic RAG and multimodal RAG — require the three-layer decomposition to work. Teams that skip to "agentic RAG" without layer separation see hallucination rates stay flat. Teams that add a planning layer between retrieval and generation see ~62% hallucination reduction across 47 production deployments (MLOps Community benchmark, May 2026). — https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns
- **Blog (Alphabold, 2026):** LangGraph production deployments at Uber, JP Morgan, BlackRock, Cisco, LinkedIn, and Klarna all use graph-based state machines to enforce layer separation. The graph structure encodes which layer handles which transitions. — https://www.alphabold.com/langgraph-agents-in-production

## Gotchas
- **The reasoning layer becomes a bottleneck if called too often.** If your "reasoning" model is invoked on every step, you have not actually separated layers — you have just renamed them. Gate the reasoning layer to task-start and human interrupt only.
- **Typed contracts between layers are not optional.** Without explicit schemas, the planning layer leaks context to the reasoning layer and you get emergent circular dependencies that are nearly impossible to untangle.
- **Not every agent needs all three layers.** A simple cron-based report generator probably only needs a planning + execution layer. The reasoning layer adds overhead that only pays off on tasks with genuine goal decomposition complexity. Size the stack to the task.
- **Multi-agent is not the same as multi-layer.** Having five agents that all do reasoning + planning + execution in parallel is not the three-layer pattern — it is five monolithic agents. The layers are vertical slices, not a horizontal team structure.
