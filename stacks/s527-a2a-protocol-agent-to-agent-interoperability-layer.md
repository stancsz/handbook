# S-527 · The A2A Protocol: Agent-to-Agent Interoperability at Production Scale

S-526 covers Agent Cards — the self-describing JSON document that lets agents discover each other's capabilities. But discovery without a transport mechanism is a phone book without a phone. The **A2A (Agent-to-Agent) Protocol** is the interoperability layer that makes capability discovery actionable: a standard way for agents to negotiate tasks, delegate work, stream results, and handle multi-turn conversations across service boundaries.

## Forces

- **Multi-agent systems are bottlenecked on integration, not intelligence.** Gartner reported 1,445% growth in multi-agent system inquiries (Q1 2024 → Q2 2025), yet 40% of pilots fail within six months. The failure mode is rarely the agents themselves — it's the plumbing: hardcoded URLs, bespoke authentication, and one-off integration code that makes every new agent a three-week project.
- **MCP and A2A solve different layers, but teams keep conflating them.** MCP (Model Context Protocol) handles *agent → tool* communication: how an agent calls a web search, a database, or a Slack webhook. A2A handles *agent → agent* communication: how one agent delegates a task to another, streams progress, and receives structured results. Using MCP for agent-to-agent patterns produces awkward, hard-to-maintain systems. Using A2A for tool-calling is overengineering.
- **The ecosystem is consolidating around layered standards.** A2A was introduced by Google Cloud in April 2025 with enterprise partners including Salesforce, SAP, and Accenture. It is now governed by the Agentic AI Foundation under the Linux Foundation alongside MCP. The signal: two formerly competing protocol layers (capability discovery, transport) are being standardized in parallel, and production systems built on this layered model are outpacing those built on bespoke integration.
- **Vendor lock-in is the silent tax on bespoke agent integration.** Every hardcoded agent-to-agent integration is technical debt. When one team changes their API, every downstream consumer breaks. A standard protocol with an Agent Card registry means agents can be swapped, upgraded, or substituted without cascading changes across the system.

## The move

**Use A2A as your agent-to-agent transport when you have more than one agent that needs to delegate, request, or report to another.** Treat MCP as the tool-calling layer underneath, not a replacement for it.

- **Implement the Agent Card first.** Before any A2A communication, publish a JSON Agent Card at `https://<base_url>/.well-known/agent-card.json`. This is the discovery mechanism that makes A2A dynamic rather than hardcoded. The card includes: agent name, version, capabilities (skills/endpoints), authentication requirements, and streaming support flags.
- **Use A2A's task delegation for cross-domain handoffs.** When Agent A needs Agent B to perform work, A2A provides a structured `tasks/send` endpoint. Agent B can process asynchronously, stream updates back via Server-Sent Events, and return a `Task` object with status, output, and artifacts. This is cleaner than polling a REST endpoint or managing a shared queue.
- **Rely on A2A for multi-turn conversations, not webhooks.** MCP is stateless per call. A2A maintains a `taskId` across turns, enabling agents to have extended back-and-forth without re-establishing context. This is the right abstraction for a supervisor agent coordinating a multi-step workflow.
- **Run A2A alongside MCP, not instead of it.** A typical production agent uses MCP to call tools (search, database, code execution) and A2A to communicate with sibling or subordinate agents. The protocols are complementary; conflating them is the most common mistake.
- **Apply the same security model to agent-to-agent calls as to user-to-agent calls.** A2A supports authentication headers and Bearer tokens. Treat inter-agent calls as potentially untrusted — validate inputs at every boundary. Camunda's Project Orchestr-AI-te found that inline prevention (real-time blocking of malicious actions) was critical in multi-agent workflows where one agent's output becomes another's input.
- **Prefer A2A over shared-database coordination for state.** Passing a `taskId` and letting the protocol manage state transitions (submitted → working → completed → failed) is cleaner than having agents poll a shared Postgres table. The protocol encodes the state machine.

## Evidence

- **A2A ecosystem formation:** Google Cloud launched A2A in April 2025 with enterprise partners Salesforce, SAP, and Accenture. Governed by the Agentic AI Foundation (Linux Foundation) alongside MCP. — [A2A Protocol Official Site](https://a2a-protocol.org/latest/topics/agent-discovery/), [Codefinity A2A Blog](https://codefinity.com/blog/A2A-Protocol)
- **Multi-agent adoption and failure rates:** 1,445% growth in multi-agent inquiries (Gartner), average 12 agents/organization, 40% pilot failure rate within 6 months. Production success correlates with adopting layered standards rather than bespoke integration. — [Beam.ai Multi-Agent Orchestration Patterns](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- **Layered protocol adoption signal:** The teams shipping production multi-agent systems in 2026 are those who internalized the layered model (A2A for inter-agent, MCP for tool-calling) early. — [Codefinity A2A Blog](https://codefinity.com/blog/A2A-Protocol)
- **Security and inline prevention in multi-agent workflows:** Camunda's analysis across 50+ enterprise customers found that real-time blocking of inter-agent actions (inline prevention) was essential as one agent's output increasingly becomes another's input. — [Camunda: Hype to Impact](https://camunda.com/blog/2025/10/hype-to-impact-lessons-learned-making-agentic-orchestration-work)

## Gotchas

- **Don't build A2A-like patterns on top of MCP.** It can technically be done, but the abstraction leaks. MCP is designed for stateless tool calls; forcing it into multi-turn agent conversations produces awkward request/response threading that the protocol wasn't designed to handle.
- **A2A doesn't solve trust — it standardizes communication.** Two adversarial or misconfigured agents can still produce garbage at scale. Agent Cards describe capabilities, not guarantees. Treat inter-agent outputs as untrusted input until validated.
- **Streaming adds complexity to debugging.** A2A's Server-Sent Events streaming is powerful for real-time feedback but makes trace reconstruction harder. Instrument your observability layer to capture the full task lifecycle — from delegation to completion — before enabling streaming.
- **Not all agents need A2A.** A single-agent application with tool-calling (MCP) doesn't need A2A. The protocol overhead is only justified when you have meaningful agent-to-agent handoffs or coordination. If your "multi-agent" system is really a single agent with multiple tools, you're not ready for A2A.
