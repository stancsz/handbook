# S-234 · The Stratified Agent Stack — Sandboxing Is Now Its Own Layer

The agent stack is no longer a linear pipeline. It is stratifying into specialized layers — orchestration, execution, sandboxing, tool protocol — and sandboxing has emerged as its own distinct discipline. Teams that treat it as an afterthought are paying for it in production.

## Forces

- **Monolithic agent stacks hide blast radius.** When the LLM, tools, file system, and network access all live in one process, a prompt injection or tool misuse can propagate silently across every capability the agent controls
- **Agent-to-agent handoffs compound risk.** Multi-agent systems route work between agents; each handoff is a context boundary where one agent's assumptions about the next agent's state are wrong more often than right
- **Sandboxing was an afterthought in 2023-2024.** Teams used containers orVMs for dev/test and dropped them in production. The 2025 wave of production incidents (runaway loops, tool call cascades, data exfiltration via prompt injection) forced a reckoning
- **The MCP ecosystem explosion made the problem worse and then better.** 6,400+ MCP servers means 6,400+ trust boundaries that each agent operates across — without isolation, a compromised tool connector exposes the entire agent graph
- **Specialized players emerged.** E2B, Modal, Shuru, Firecracker wrappers — the market recognized that sandboxing is a distinct engineering problem with distinct solutions, not a checkbox in the Dockerfile

## The move

Three-layer separation that holds at production scale:

- **Execution layer isolated per agent.** Each agent runs in its own sandboxed environment (microVM, container, or WASM runtime). An agent that goes into a loop or gets prompt-injected is contained — it cannot escalate to other agents or the host system. E2B's sandbox API and Modal's containerized function execution are the most referenced production choices for this
- **Tool boundaries enforced by MCP, not trust.** MCP servers are the only bridge between the execution sandbox and external systems. The protocol provides typed input/output contracts — tools can only return what the schema defines, so a compromised tool cannot inject arbitrary code or data back into the agent graph
- **Orchestration layer stateless where possible.** The orchestration graph (LangGraph, custom state machine) tracks workflow state but delegates execution to isolated agents. When an agent fails or drifts, the orchestrator can re-spawn a fresh sandbox without losing workflow state — making failure recovery a restart, not a rollback
- **Cost and latency controls at the sandbox boundary.** Budget circuit breakers, token limits, and timeout enforcement belong at the sandbox level, not inside the agent prompt. A misbehaving agent hits the wall before it burns budget. Zylos.ai documented runaway loops costing $15 in ten minutes to $47,000 over eleven days — all preventable with hard enforcement at the execution boundary
- **Filesystem access scoped and auditable.** Agents that need file system access should operate against a virtualFS or a bind-mounted directory with explicit read/writeAllowlists. The host filesystem is never in play

## Evidence

- **HN thread (philzhang, June 2026):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." Referenced alongside a post arguing against monolithic agent stacks on defensibility grounds — [https://news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)
- **RaftLabs (Nov 2025):** Of organizations running agents in production (57%), the most common failure mode was not model quality — it was the observability gap and uncontained tool call cascades. Recommended explicit typed contracts between agent layers as a first-order concern — [https://www.raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Lushbinary framework comparison (Apr 2026):** Migration from CrewAI to LangGraph explicitly calls out that CrewAI's implicit shared context between agents makes sandboxing harder — the state must be refactored into explicit boundaries. LangGraph's graph model makes each node a natural isolation boundary — [https://lushbinary.com/blog/langgraph-vs-crewai-vs-autogen-ai-agent-framework-comparison/](https://lushbinary.com/blog/langgraph-vs-crewai-vs-autogen-ai-agent-framework-comparison/)
- **Zylos.ai token economics research (May 2026):** Runaway agent loops cost teams $15 to $47,000 depending on scale. 60–85% of inference spend is recoverable through disciplined controls, most of which sit at sandbox or orchestration boundaries — [https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/)

## Gotchas

- **Containers are not enough.** A Docker container shares the kernel with the host — a container escape is a host compromise. MicroVMs (Firecracker, gVisor) provide stronger isolation at lower overhead than full VMs. E2B's cloud runtime uses microVMs specifically for this reason
- **MCP servers are not inherently sandboxed.** The protocol defines the interface; the server still runs in the host environment. Each MCP server should live in its own sandbox with minimal privileges — don't give every tool root access to your infrastructure just because it's behind an MCP wrapper
- **Stateless orchestration is harder than it sounds.** LangGraph's checkpointing API helps, but resumability across sandbox boundaries requires serialization of agent state (tool call results, intermediate outputs) that your orchestration layer must own. Without it, a mid-workflow failure forces the agent to restart from scratch
- **Cold start latency kills user-facing agents.** MicroVM-based sandboxing adds 500ms–2s cold start overhead. For background agents (batch processing, scheduled tasks), this is acceptable. For synchronous user-facing flows, pre-warmed sandbox pools are required
