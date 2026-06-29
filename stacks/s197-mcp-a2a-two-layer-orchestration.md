# S-197 · MCP + A2A Two-Layer Orchestration

[S-10 MCP](s10-mcp.md) standardizes how a single agent connects to tools and data sources — the vertical axis. [S-14 A2A](s14-a2a-protocol.md) standardizes how two agents discover, delegate, and collaborate — the horizontal axis. Neither entry covers the combination: the reference architecture for 2026 production multi-agent systems. That gap closes here.

## Forces

- MCP hit 97M+ monthly SDK downloads within one year of launch; A2A v1.0 landed in early 2026 backed by Google ADK, Salesforce Agentforce, and ServiceNow — the two protocols are not competitors, they solve different layers
- Teams that pick only MCP end up with agents that access tools but can't hand off work to each other; teams that pick only A2A end up with agents that delegate but connect to everything bespoke
- The naive stack — LangGraph for orchestration, ad-hoc tool definitions per agent — works at demo scale and collapses at production scale when you have 15 agents, three vendors, and need cross-team cost attribution
- Cross-layer trust (which agent can invoke which tool on which server) and state federation (whose context gets passed at delegation) are unsolved by the specs and require architectural decisions
- Google ADK, LangChain, CrewAI, and AutoGen all implement MCP + A2A in their 2026 releases — the two-layer model is the de facto production standard

## The move

**Layer 1: MCP for tool and data access** — every agent (orchestrator, specialist, or worker) connects to its tools via MCP clients talking to MCP servers. Each server is scoped to a capability domain: a `filesystem` server, a `crm` server, a `code-execution` server. The agent never reaches outside its MCP domain.

**Layer 2: A2A for agent-to-agent coordination** — agents discover each other via an Agent Card (a JSON document at `.well-known/agent.json`), establish bidirectional sessions, and delegate tasks. The orchestrator sends a task to a specialist via A2A push or pull; the specialist reports back with results or a status update.

```
User Request
     │
     ▼
┌─────────────┐         MCP          ┌──────────────────┐
│ Orchestrator │ ──── tool access ──▶│  MCP Tool Server │  (e.g. search, calendar, code)
│  (A2A client)│                      └──────────────────┘
└──────┬──────┘
       │ A2A delegate
       ▼
┌─────────────┐         MCP          ┌──────────────────┐
│  Specialist │ ──── tool access ──▶  │  MCP Tool Server │
│  Agent      │                       └──────────────────┘
└─────────────┘
```

### Implementation pattern

```python
# Orchestrator exposes its own MCP server so specialists can use its tools
# via A2A delegation calls — the two layers compose naturally.

from mcp.client import MCPSyncClient
from a2a.client import A2AClient
from a2a.server import A2AServer, AgentCard

# --- Layer 1: MCP — agent → tools ---
orchestrator_mcp = MCPSyncClient("http://orchestrator-mcp:3000")
orchestrator_mcp.connect_tool("web_search")
orchestrator_mcp.connect_tool("document_write")

# --- Layer 2: A2A — orchestrator → specialist delegation ---
async with A2AClient("http://specialist-agent:8000") as specialist:
    # Specialist publishes its Agent Card for discovery
    card = await specialist.get_agent_card()
    print(card.name)  # "CodeReviewAgent"

    # Orchestrator delegates a sub-task, passing task context
    result = await specialist.send_task({
        "task_id": "t-42",
        "instruction": "Review the PR at commit abc123 for memory leaks",
        "context": {"pr_url": "https://github.com/org/repo/pull/42"},
    })
    print(result.status)  # "completed" | "input_required" | "failed"

    # Specialist streams back updates as it works
    async for event in specialist.stream_task(result.task_id):
        print(f"[{event.stage}] {event.message}")
```

### Key decision points

- **MCP server per capability, not per agent.** One `code-execution` MCP server shared by three agents is cheaper and easier to audit than three separate code execution stacks. Each server gets its own credentials, rate limits, and version.
- **A2A session context is not automatically forwarded to MCP.** When an orchestrator delegates to a specialist, the specialist's MCP calls run in the specialist's own context — not the orchestrator's. If the specialist needs shared state (user preferences, prior results), pass it explicitly in the A2A task payload.
- **Agent Cards are your trust registry.** Each A2A agent publishes an Agent Card listing its capabilities, security posture, and input/output schemas. Validate incoming delegation requests against the caller's card before accepting work.
- **Cost attribution across A2A delegation** requires per-call token metering — log MCP tool calls and A2A delegation token counts in your observability layer (see [S-196 OTel GenAI Telemetry](s196-otel-genai-telemetry.md)).
- **Fail gracefully at each layer.** MCP tool failures trigger fallback chains (see [S-96 Tool Fallback Chains](s96-tool-fallback-chains.md)); A2A delegation failures should return a structured error to the orchestrator so it can retry or escalate, not crash silently.

### When this doesn't fit

Single-agent applications with no delegation need only MCP. Two agents that never need to coordinate beyond direct request/response can use A2A alone. The two-layer stack adds infrastructure — Agent Card registry, MCP server fleet, session state management — that pays off only when you have three or more agents or need cross-team/cross-vendor composition.

## Receipt

> Receipt pending — 2026-06-29

## See also

- [S-10 · MCP](s10-mcp.md) — the vertical layer this entry builds on
- [S-14 · A2A Protocol](s14-a2a-protocol.md) — the horizontal layer this entry builds on
- [S-196 · LLM Telemetry via OTel GenAI Conventions](s196-otel-genai-telemetry.md) — instrumentation for cross-agent traces
