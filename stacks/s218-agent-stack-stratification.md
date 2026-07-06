# S-218 · Agent Stack Stratification

The temptation is to pick one framework — LangGraph or CrewAI — and treat it as the entire architecture. It isn't. Multiple independent sources now confirm the agent stack is decomposing into 5–7 distinct horizontal layers, and trying to span those layers with a single tool creates predictable failure modes at each boundary.

## Forces

- Early tutorials show one framework doing everything; production systems that follow this pattern hit silent failures at layer boundaries (tool calls stop resolving, context drops mid-chain, sandbox escapes)
- Sandboxing, orchestration, observability, guardrails, and model routing have fundamentally different defensibility profiles — bundling them into one "platform" optimizes for demo velocity, not production resilience
- The MCP ecosystem (10K+ servers, 97M monthly SDK downloads) proved that tool exposure is its own concern, separate from orchestration — yet most teams retrofit MCP onto orchestration-first frameworks instead of designing from the tool layer outward
- Each layer has a different cadence of change — model providers move weekly, orchestration patterns monthly, infrastructure quarterly; coupling them slows every team
- "The tutorial cliff": frameworks that promise "build an agent in 10 lines" work until you hit the first edge case, then the abstraction becomes a wall — Xpress AI rebuilt their agent framework five times before splitting it into explicit layers

## The move

Treat the agent stack as 5 distinct, independently deployable layers. Design each boundary as an explicit interface, not a shared in-process module.

**Layer 1 — Foundation model.** Route by task, not by preference. Claude 4 Opus for reasoning; GPT-4o for fast summarization; open models (Llama, Qwen) for non-sensitive data. Output tokens are 3–5× more expensive than input tokens across all providers — monitor output/input ratio per task and route accordingly.

**Layer 2 — Model routing.** Abstract the provider behind a gateway. Implement cost caps per session, latency budgets, and fallback chains (primary → secondary → graceful degradation). Tiered routing delivers 60–75% cost savings on mixed workloads.

**Layer 3 — Tool exposure (MCP).** Design MCP servers as read-only by default for production. Write actions, destructive operations, and customer data access behind explicit approval gates with audit logging. Code-execution MCP models (CE-MCP) reduce token usage by 70% and turn count by 83%, but require deep sandboxing and semantic validation of execution plans — the tradeoff is a larger attack surface.

**Layer 4 — Orchestration.** Choose based on workflow shape:
- LangGraph for stateful, multi-step processes with complex state management (used at Klarna, Replit, Elastic)
- CrewAI for sequential, role-based processes with defined handoffs (fastest path to working prototype, 34K+ GitHub stars)
- AutoGen (Microsoft Agent Framework) for conversational, dialogue-based collaboration
- Consider hybrid: LangGraph as the orchestration backbone with AutoGen for conversational sub-agents

**Layer 5 — Sandboxing.** Separate from orchestration. Options: E2B, Modal, Shuru, Firecracker. Sandboxing has a different defensibility profile than orchestration — it handles code execution, network boundary enforcement, and resource limits independently. Don't conflate "I run code" with "I orchestrate agents."

**Layer 6 — Guardrails.** Input validation, output filtering, refusal logic, audit logging. These live between orchestration and the outside world. Rate-limit tool calls per session. Set hard retry caps on retrieval reformulation (if >20% of queries need reformulation, the problem is in chunking/embeddings, not the agent logic).

**Layer 7 — Observability.** Instrument every layer from day one. Amazon's evaluation of thousands of agents found traditional LLM eval methods treat agent systems as black boxes — agents need per-component eval: planning accuracy, tool-calling success rate, hallucination detection, and cost per task. LangSmith, Phoenix, or custom tracing per layer boundary.

## Evidence

- **HN (Philipp Dubach):** The agent stack is splitting into specialized layers — sandboxing is clearly its own thing with E2B, Modal, Shuru, Firecracker each addressing different isolation needs — argued that monolithic "platform" approaches have worse defensibility profiles than layer-separated architectures — https://news.ycombinator.com/item?id=47114201
- **Internative (2026 production guide):** Defined a 7-layer agentic AI stack (Eval & QA → Observability → Guardrails → Orchestration → Tool Exposure/MCP → Model Routing → Foundation Model) as the production architecture — and explicitly states "architecture choices that worked for chatbots fail for agents, often silently and at scale" — https://internative.net/insights/blog/agentic-ai-architecture-2026
- **AWS/Amazon engineering:** Since 2025, thousands of agents built across Amazon organizations — documented that multi-agent systems require per-component evaluation frameworks separate from orchestration, covering planning, tool orchestration, and adaptive decision-making — https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon
- **Xpress AI (operational lessons 2025):** After five agent framework iterations, rebuilt around explicit layer separation — key insight: "frameworks promising build an agent in 10 lines work until the first edge case, then the abstraction becomes a wall" — https://xpress.ai/blog/2025-agent-lessons
- **Digital Applied (MCP adoption data, May 2026):** MCP has 10K+ active public servers, 97M monthly SDK downloads, 86K GitHub stars on the official servers repo — confirms tool exposure is now a standalone ecosystem, not an orchestration feature — https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol
- **Latenode framework comparison:** LangGraph used at Klarna/Replit/Elastic for production stateful workflows; CrewAI has 34K+ GitHub stars; AutoGen (Microsoft Agent Framework, GA planned Q1 2026) is the enterprise Azure choice — https://latenode.com/blog/langgraph-vs-autogen-vs-crewai

## Gotchas

- **Orchestration-first design.** Starting with LangGraph/CrewAI and adding MCP/sandboxing later produces impedance mismatches at every layer boundary. Design from the tool layer outward.
- **Context stuffing.** Agents stuffing too much context into prompts to "be safe" inflates input costs and can trigger silent truncation mid-chain. Set explicit context budgets per task type.
- **Infinite retry loops.** Without hard caps on retrieval reformulation, agents can cycle through reformulations indefinitely. Set explicit retry limits; if reformulation rate exceeds 20%, fix the retrieval layer (chunking, embedding model, stale index), not the agent.
- **Eval as afterthought.** Agents are dynamic systems that change behavior between runs. Per-component eval (not just end-to-end) is the only way to catch regressions before they hit production. Amazon's finding: traditional LLM eval methods fail to explain *why* agents fail — you need component-level signals.
- **Cost blindness.** Output tokens drive 60–80% of agent costs. Track cost per task per agent. Without per-layer cost attribution, you won't notice when a "simple" agent is generating 10x more output than expected.
