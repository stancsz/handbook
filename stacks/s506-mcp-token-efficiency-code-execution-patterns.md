# S-506 · MCP Token Efficiency: Code Execution Patterns Over Direct Tool Calls

The naive way to connect agents to tools buries you in tokens. Every MCP server added, every tool definition loaded, every intermediate result threaded through the context window compounds into cost and latency that makes agents unusable at scale. The fix is not fewer tools — it is a fundamentally different calling pattern.

## Forces

- **Context window as a bottleneck:** Loading all available tool definitions for every agent invocation wastes tokens on tools that will never be called. As agent fleets scale to dozens of MCP servers and hundreds of tools, the overhead becomes the dominant cost driver.
- **Direct tool calls are chatty:** Each round-trip between agent and tool passes full schemas, full parameters, and full responses back through the context. For multi-step workflows, this compounds exponentially.
- **Standardization vs. efficiency tension:** MCP solved the "one custom integration per tool" problem — thousands of MCP servers now exist. But standardization without efficiency produces a slow, expensive agent.
- **Code execution reframes the problem:** Agents that write code to call MCP servers (instead of calling tools directly) turn a conversational problem into a batched API call. The same tool chain, dramatically fewer tokens.

## The move

Anthropic's engineering team documented the pattern in November 2025: route MCP tool calls through a code execution environment rather than direct tool invocation. The agent writes a script, the script calls the MCP server, results return as structured output — not context payload.

- **Write code instead of calling directly:** Agent produces a Python/JS script that calls the MCP server API. One LLM call produces one batched execution. Compare: direct tool calling produces a separate LLM round-trip per tool.
- **Ephemeral tool discovery:** MCP's dynamic discovery mechanism lets the code execution layer enumerate available tools at runtime without pre-loading all schemas into context.
- **Structured output over context streaming:** Results from MCP servers return as typed data (JSON, CSV, DataFrames), not token-heavy narrative. Downstream agents consume structured data.
- **Sandbox isolation:** Code execution environments (Docker, Modal, AWS Lambda) provide the security perimeter that direct tool calling lacks — a compromised agent script does not reach production systems directly.
- **Token arithmetic that speaks for itself:** Anthropic measured 150,000 tokens reduced to 2,000 tokens for equivalent work — a 98.7% reduction — by routing a Google Drive MCP server through a code execution environment instead of direct tool calls.
- **Layer the pattern with hybrid retrieval:** Combine code-execution-based MCP access with hybrid search (dense + BM25) and a reranker. The reranked retrieval feeds the agent's context; the MCP code execution handles downstream actions.

## Evidence

- **Anthropic Engineering Blog (Nov 2025):** Documented the token reduction from ~150K to ~2K tokens using code execution with MCP, with full architecture diagrams showing the execution flow vs. direct tool call flow. — [https://www.anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Omnitech Integration Review (Nov 2025):** Assessed MCP as "virtual USB-C for agents" — a universal interface reducing per-tool custom integration overhead. Confirmed rapid adoption: thousands of MCP servers built since the November 2024 launch. — [https://omnitech-inc.com/blog/model-context-protocol-mcp-for-ai-agent-integration](https://omnitech-inc.com/blog/model-context-protocol-mcp-for-ai-agent-integration)
- **Industry Benchmark (May 2026):** Agentic RAG with knowledge graphs cut hallucination by ~62% across 47 production deployments. Hybrid retrieval (dense + BM25) with a Cohere Rerank v3 reranker identified as the highest-leverage upgrade before touching more exotic patterns. — [https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns)

## Gotchas

- **Not every MCP server is suitable for code execution routing.** Stateful servers with streaming responses or WebSocket connections require a different pattern — code execution works best for REST-like MCP endpoints that return structured data.
- **Sandbox cold starts add latency.** Modal, AWS Lambda, and Docker-based execution environments introduce startup overhead. Profile this before assuming code execution is always faster — for low-latency interactive agents (sub-500ms SLA), direct tool calls may still win.
- **Debugging becomes two-layer.** When a tool fails, you need to trace whether the failure is in the agent's script logic, the MCP server, or the code execution environment. Traditional agent debugging (one stack trace) becomes three.
- **Context window management still matters upstream.** Code execution reduces per-call tokens but does not fix a poorly chunked RAG pipeline feeding the agent. Layer both.
