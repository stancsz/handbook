# S-463 · Multi-Agent Cost & Coordination Architecture

Single-agent systems are simpler to build but become cost sinks on complex tasks — every retry, every extra tool, every step adds tokens without adding capability. Multi-agent architectures add coordination overhead, but for anything beyond straightforward RAG or triage, the per-task cost savings compound to 40–60% compared to a monolithic agent. The question is not whether to split, but when and how.

## Forces

- **Complexity vs. cost — the tradeoff is real but misread.** Multi-agent adds code, orchestration logic, and failure modes. Teams resist because of perceived complexity. The data says the break-even is lower than expected: complex tasks where one agent juggles 10+ tools or 5+ steps are the right split points.
- **Coordination overhead scales non-linearly.** A peer-to-peer network of 10 agents has 45 potential communication channels. A supervisor/worker pattern has 10. The pattern you choose determines your failure surface area more than the number of agents.
- **Token bloat is the silent cost killer.** Context loading (re-reading project files, system prompts, history) accounts for 45% of token spend per session. Multi-agent with scoped context per agent can eliminate most of this waste.
- **Tool selection accuracy degrades under load.** Single agents with 12+ tools drop below 90% tool-selection accuracy. Multi-agent architectures where each agent owns a narrow toolset preserve accuracy.

## The move

Define coordination architecture **before** building. Pick the pattern that matches your failure tolerance and latency requirements.

- **Split when:** task requires 10+ distinct tools, 5+ sequential reasoning steps, or fundamentally different context domains. The Ivern 2026 benchmark showed 40–60% cost savings for complex multi-step tasks using multi-agent vs single-agent at equivalent quality.
- **Choose hierarchical (supervisor/worker) when:** you need deterministic control flow, compliance checkpoints, or human-in-the-loop at specific stages. LangGraph's explicit edge routing makes compliance-pause failure modes impossible to skip. "Every time we've tried to bolt HIPAA-required pauses into CrewAI's hierarchical mode, the agent crew has found creative ways to skip the nurse step" — a real healthcare deployment discovered this the hard way.
- **Choose pipeline when:** tasks decompose cleanly into sequential stages (research → write → edit → publish). Each stage is a specialized agent with minimal state shared forward.
- **Choose orchestrator-worker when:** a central planner dispatches sub-tasks to specialized workers that return results. Best for parallelizable work (search 5 sources simultaneously, then synthesize).
- **Choose peer-to-peer when:** agents need to collaborate as equals, negotiate, or vote. Most complex to debug; use only when no hierarchy is natural to the problem.
- **Scope MCP servers per agent, not globally.** MCP tool definitions consume 5–10K tokens per server before the user's prompt is read. A locally-running stdio MCP runs with your user credentials — there is no per-tool sandbox. Use allow-lists per agent and lazy-load server catalogs.
- **Measure cost per task, not per model.** A $0.02–$0.47 per-task range (Ivern 2026, 200 tasks across 6 providers) means model-tier routing matters more than model choice: use cheapest model that meets quality threshold for each subtask.

## Evidence

- **Benchmark report:** Multi-agent tasks cost 40–60% less per task than single-agent at equivalent output quality. Per-task cost ranged $0.02–$0.47 across 200 benchmarked tasks (Ivern AI, April 2026, 6 providers) — https://ivern.ai/blog/ai-agent-cost-benchmark-report-2026
- **340-day production case study:** Rebuilt monolithic agent → multi-agent with scoped context. Results: 73% latency reduction (12.3s → 3.3s), 62% cost reduction ($8,400 → $3,200/month), P99 from 34s → 8s. Root cause was context bloat from a single agent carrying all state. — https://calderbuild.github.io/blog/2025/01/15/ai-agent-deep-analysis
- **Industry adoption:** Gartner tracked 1,445% surge in multi-agent system inquiries Q1 2024 → Q2 2025. 57.3% of organizations now have agents in production. 49% cite high inference costs as top blocker — https://www.raftlabs.com/blog/multi-agent-systems-guide
- **Tool selection degradation:** Tool-selection accuracy drops below 90% when single agents handle 12+ tools; most production failures are wrong tool selection, not model quality — https://www.reddit.com/r/LocalLLaMA/comments/1qwvmlk/i_got_tired_of_my_agents_randomly_failing_so_i/
- **LangGraph production users:** Used in production at Klarna, Replit, Elastic for stateful, observable workflows. Explicit graph topology prevents compliance-skip failure modes that CrewAI's delegation chain model allows — https://pub.towardsai.net/langgraph-vs-crewai-vs-autogen
- **MCP token bloat:** Each MCP server's tool definitions serialize into context. 10 servers × 15 tools = 5–10K tokens before user prompt. Tool accuracy degrades past ~30 tools in scope — https://zeroentropy.dev/concepts/mcp

## Gotchas

- **AutoGen is in maintenance mode** (October 2025). Its successor is the Microsoft Agent Framework. Do not start new projects on AutoGen — https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025
- **CrewAI's delegation chain is a compliance liability** in regulated workflows. The hierarchical mode allows agents to skip required steps when they decide (incorrectly) a case is low-urgency. Use LangGraph for anything requiring deterministic audit trails.
- **Most token waste is invisible.** 60–70% of typical AI agent spend is redundant context loading, bloated prompts, and unnecessary re-reads. Build cost visibility before optimizing — multi-trial evaluation with per-task cost tracking is the baseline.
- **Orchestration framework is not the same as workflow engine.** LangGraph, CrewAI, and AutoGen are agent orchestration frameworks — they define how agents cooperate. For long-running durable workflows with state persistence across restarts, consider Temporal or similar workflow engines as the execution substrate.
- **Peer-to-peer agent networks create exponential communication channels.** 10 agents = 45 channels. Unless the problem genuinely requires peer negotiation, use a supervisor pattern to keep channels linear.
