# S-415 · The Three-Layer Agentic Stack

When agentic systems fail in production, the failure looks like a single problem — but it lives at one of three distinct layers. Most teams treat the stack as monolithic. The teams that ship stable agents have learned to separate: reasoning, protocol, and orchestration. Each layer has different failure modes, different replacement costs, and different competitive implications.

## Forces

- **The stack looks like one thing; it behaves like three.** Before MCP, tool schemas were tangled into orchestration code. Swapping an LLM meant rewriting tool definitions. Adding a new tool meant touching agent code. Teams that built "integrated" systems built systems where every change cascaded.
- **The protocol layer was always the weak link — now it's the solved link.** MCP has 97M+ monthly SDK downloads and adoption from Anthropic, OpenAI, Google, and Microsoft. The tool-integration problem that consumed most agent engineering time is now a solved problem. But solved problems create new strategic pressures: if tool integration is commoditized, where is the moat?
- **Orchestration is the new competitive layer.** LangGraph owns durable state, checkpointing, and time-travel debugging — features that make agents recoverable and auditable in production. CrewAI owns rapid multi-agent prototyping for business teams. These are fundamentally different value propositions, and the production/prototyping fork is widening into a genuine architectural choice.
- **Reasoning models are becoming layer-2, not layer-1.** The emergence of extended-thinking models (Claude 3.7, o3, Gemini 3) means the reasoning layer can now be swapped independently. You no longer need to choose your planning model and your execution model from the same family.

## The move

Architect your agentic system as three independently deployable layers:

**Layer 1 — Reasoning.** Planning, task decomposition, decision-making. LLM-native. Swap models without touching anything else. Extended-thinking models (Claude 3.7, o3) are appropriate for complex planning; fast models (GPT-4.1-mini, Gemini Flash) for routine decisions.

**Layer 2 — Protocol.** Standardized tool communication. MCP is the current winner. Every tool is an MCP server; every agent is an MCP client. This layer is now commodity — choose it based on ecosystem, not custom integration work.

**Layer 3 — Orchestration.** State management, multi-agent coordination, error recovery, human-in-the-loop. LangGraph for durable production workflows. CrewAI for rapid multi-agent prototyping. OpenAI Agents SDK for OpenAI-only stacks. The choice here determines your recovery model, your observability surface, and your ability to run agents for extended periods.

Test each layer in isolation. Replace each layer independently. The stack only becomes brittle when these layers blur.

## Evidence

- **Framework comparison (Jobs By Culture, 2026):** LangGraph recommended for production workloads for durable state/checkpointing/time-travel debug. CrewAI for rapid prototyping. AutoGen moved to maintenance — Microsoft consolidating around Agent Framework (GA Q1 2026). — [jobsbyculture.com/blog/ai-agent-frameworks-compared-2026](https://jobsbyculture.com/blog/ai-agent-frameworks-compared-2026)
- **MCP adoption metrics (VantagePoint, 2025):** 97M+ monthly MCP SDK downloads (TypeScript + Python combined). Supported by Anthropic, OpenAI, DeepMind, Microsoft. Adopted by 5M+ GitHub users. Called "USB-C for AI" — the standard eliminates custom tool-integration code per model. — [vantagepoint.io/blog/anthropic/what-is-model-context-protocol-mcp-business-data](https://vantagepoint.io/blog/anthropic/what-is-model-context-protocol-mcp-business-data)
- **Production lessons (Technspire, Dec 2025):** Agents that shipped to production in 2025 did so in three categories: developer tooling (tight feedback loop), internal ops automation (clear success criteria), research/analysis (tool-augmented LLMs). Key pattern: agents work where software engineering discipline works. — [technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Don't entangle protocol into orchestration.** If your MCP tool definitions live inside your LangGraph agent code, you can't test the tool schema independently and you can't swap orchestration frameworks without rewriting tools.
- **The prototyping/production fork is real.** CrewAI's role-based agent model is excellent for demos and proof-of-concept multi-agent workflows. It is not appropriate for long-running agents with failure recovery requirements. Choose CrewAI to prove the workflow; migrate to LangGraph to harden it.
- **Checkpoint everything in orchestration.** The production cases that shipped (Klarna, Uber, LinkedIn on LangGraph) all use durable state. Without checkpointing, agent failures require full restart from scratch — which makes the agent brittle under load and opaque under failure.
