# S-583 · The Agent Protocol Stack — MCP, A2A, and Where the Boundary Lives

You've got agents that can call tools. Now you want agents that can call each other. The ecosystem has converged on two distinct protocol layers — Model Context Protocol (MCP) for tool/resource access and Agent-to-Agent (A2A) for inter-agent collaboration — but teams keep conflating them, which creates fragile architectures that are hard to debug and impossible to swap.

## Forces

- **MCP and A2A solve different problems but look similar on the wire.** Both involve agents sending structured messages. The conceptual boundary is not obvious from implementation, so teams implement one when they need the other, then rebuild six months later.
- **Protocol abstraction feels premature until it isn't.** Writing a tool-calling interface directly into your agent feels faster. Then you need a second agent, then a third, and suddenly you have N×M integration points with no discoverability.
- **Framework coupling is the hidden cost of protocol adoption.** If you build directly against MCP server implementations or A2A agent cards, you inherit the provider's versioning, behavior, and failure modes. The protocol is standardized; the SDKs are not.
- **HITL requirements cut across both layers.** Human-in-the-loop checkpoints happen at the tool level (MCP: should this email send?) and at the agent level (A2A: should this task hand off?). Most architectures implement these inconsistently across layers.

## The move

The agent protocol stack operates in two distinct layers that should be designed, evaluated, and versioned independently.

**Layer 1 — MCP (Model Context Protocol, Anthropic): tools and resources.**
This is the agent-to-data-plane. MCP defines how a single agent connects to external tools, data sources, and compute resources. Think of it as the USB-C of tool integration: you describe what your tool does via a schema, and any MCP-compatible agent can discover and call it.

- Use MCP for: database queries, API calls, file I/O, web searches, code execution, email sending, external service integrations
- MCP does NOT handle: task delegation, agent discovery, result passing between agents, workflow orchestration
- The MCP server registry pattern (Anthropic's approach) lets you publish a tool catalog independently of any single agent framework

**Layer 2 — A2A (Agent-to-Agent, Google + Linux Foundation): agent collaboration.**
A2A defines how agents discover each other, negotiate task delegation, pass context, and report status. Google donated A2A to the Linux Foundation in June 2025 with 50+ partners (AWS, Microsoft, Salesforce, SAP). It competes with IBM's ACP and community ANP but has the broadest enterprise backing.

- Use A2A for: task handoff between agents, agent capability discovery, inter-team coordination, result streaming between agent processes
- A2A does NOT handle: tool execution, prompt management, model routing
- The A2A agent card (a JSON manifest of capabilities) enables dynamic agent discovery without hard-coded integration points

**The boundary rule:** MCP = agent-to-resource. A2A = agent-to-agent. If the entity on the other end of the call is a tool (persists no state, performs one operation, returns a result), use MCP. If the entity is an agent (has goals, can decide, can delegate further), use A2A.

**Implement HITL at the right layer.** Human approval for a database query belongs in MCP (via a confirmation tool wrapper). Human approval for whether an analysis agent should hand off to an escalation agent belongs in A2A (via a task-state checkpoint).

**Design both layers to be swappable.** Define your own thin interface abstractions over MCP clients and A2A connectors. The protocols are stable; SDK implementations (langchain-mcp, crewai-tools, Microsoft's A2A SDK) are not.

## Evidence

- **Engineering blog:** MCP connects agents to tools and data sources; A2A connects agents to other agents. Google's A2A donated to Linux Foundation June 2025 with 50+ partners — A2A has emerged as the leading inter-agent standard while MCP remains the dominant tool-integration protocol — [AIMadeTools](https://www.aimadetools.com/blog/agent-to-agent-communication/)
- **Framework comparison:** LangGraph, CrewAI, and AutoGen each handle MCP tool integration natively but differ in A2A support — LangGraph's graph-based model maps cleanly to A2A task handoffs, while CrewAI's role-based teams implement A2A-like delegation internally — [Iterathon](https://iterathon.tech/blog/ai-agent-orchestration-frameworks-2026)
- **Enterprise research:** Google's A2A (donated to Linux Foundation June 2025 with 50+ partners including AWS, Microsoft, Salesforce, SAP) has 150+ organizations using agent communication standards, with market projecting $8.5B agent framework spend by end of 2026 — [Zylos Research](https://zylos.ai/research/2026-01-12-ai-agent-orchestration-frameworks), [Zylos Research](https://zylos.ai/research/2026-02-15-agent-to-agent-communication-protocols/)
- **HN field report:** Teams building multi-agent systems ask "has anyone successfully mixed different frameworks?" — mixing LangGraph, CrewAI, and custom agents requires protocol-level abstraction to avoid N×M integration coupling — [Hacker News](https://news.ycombinator.com/item?id=45721705)

## Gotchas

- **Conflating the layers is the most common mistake.** Implementing A2A to call a tool, or MCP to delegate a task, works until you need to scale or debug — then the abstraction leaks everywhere.
- **MCP servers are not agentic.** A server that implements MCP can still be a stateless function. The protocol tells you how to call it; it does not tell you what to do when the call fails, times out, or returns ambiguous results.
- **A2A agent cards are only as good as their maintenance.** A stale agent card (wrong capability, outdated endpoint) creates silent failures — agents attempt handoffs to agents that cannot handle them.
- **Framework-native abstractions leak.** Building on langchain-mcp or crewai-mcp integrations is fast but couples you to the framework's MCP client behavior. Abstract the MCP layer behind your own interface before adding business logic.
