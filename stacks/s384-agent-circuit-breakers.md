# S-384 · Agent Circuit Breakers

Agents in production fail loud, fast, and expensively — and the most dangerous failures aren't the ones that break loudly. They are the ones that run perfectly and cost you $200 while looping on nothing, or return garbage that your downstream system accepts silently. The answer is circuit breakers: explicit, tunable runtime policies that cut the loop before it becomes a line item.

## Forces

- **Loops don't announce themselves.** An agent calling the same tool with minor variations will happily run until you hit the API rate limit or the bill arrives.
- **Output validation is downstream's job, but downstream trusts you.** When an agent returns `{"status": "refunded"}` and your system acts on it, the cost of that hallucination is yours.
- **MCP's security surface is unverified by default.** 43% of published MCP servers have command injection flaws — a tool your agent calls freely may be executing attacker-controlled input.
- **Frameworks abstract away the failure mode, not the failure.** LangGraph, CrewAI, and AutoGen all give you loops. None of them give you a cost ceiling unless you build it.
- **Retry and loop detection require different policies.** A transient API error deserves a retry. A 14th consecutive attempt to call the same tool does not.

## The move

Build explicit circuit breakers into every agent loop — not as afterthoughts but as first-class runtime policy.

**1. Loop detection with call-fingerprinting.** Track not just call count but call *signature* — the tool name + argument hash. A 3-call loop on the same tool with different args is sometimes valid (e.g., paginated fetch). A 10-call loop with identical signatures is always a bug. Set per-tool call budgets and break with a typed exception.

**2. Cost circuit breakers.** Set a hard cost ceiling per task session in cents. Track cumulative cost in real-time — input tokens × model price + output tokens × model price — and interrupt before exceeding the ceiling. One HN builder reported losing $200+ on a single runaway run before adding this.

**3. Output schema enforcement at the boundary.** Never pass agent raw output to downstream systems. Use Pydantic or Zod validation at the agent-to-system boundary — reject and retry if the output doesn't match the expected schema. This catches hallucinated JSON fields, missing required keys, and type coercion errors before they propagate.

**4. MCP tool allowlisting.** Don't grant agents access to all available MCP tools. Define an explicit per-task allowlist. For tools with filesystem or shell access, add a secondary confirmation gate — either human-in-the-loop or a separate signing step. The 43% command-injection flaw rate in published MCP servers makes this non-optional for any external-facing deployment.

**5. Escalation paths, not just stops.** A circuit breaker that just logs and halts creates a support ticket. A good circuit breaker: (a) stops the run, (b) emits a structured failure state with the last valid checkpoint, (c) routes to a human reviewer or fallback agent. The agent can resume from the checkpoint rather than restart.

**6. Temporal persistence for long runs.** For workflows spanning minutes to hours, checkpoint state at each step. If a circuit breaker trips, resume from the last checkpoint — not from scratch. Temporal's workflow durable execution pattern applies directly here: the run survives process restarts, and retry policies are explicit rather than implicit.

## Evidence

- **Show HN (AgentCircuit):** Built specifically to address the "agent stuck calling the same function over and over" problem, with circuit breakers for both loop detection and output type validation. Reports $200+ lost on a single runaway run before the tool was built. — [HN #46899775](https://news.ycombinator.com/item?id=46899775)
- **Deepak Gupta Research (MCP Enterprise Guide):** Found that 43% of published MCP servers have command injection vulnerabilities — compounding the risk when agents are given broad tool access. Recommends explicit allowlisting and input sanitization as baseline. — [guptadeepak.com/research/mcp-enterprise-guide-2025](https://guptadeepak.com/research/mcp-enterprise-guide-2025)
- **Sumvid (Building Production-Grade AI Agents):** Documents the production failure mode: "an agent calls the same API in an infinite loop and racks up $12,000 in charges overnight" alongside hallucinated outputs that propagate to downstream financial systems. Recommends output schema validation as the primary defense. — [sumvid.ai/articles/production-ai-agents-architecture](https://sumvid.ai/articles/production-ai-agents-architecture)
- **GrowthEngineer.ai (Production AI Agent Stack):** Identifies six non-negotiable production layers, with guardrails and cost controls as distinct from orchestration. Notes that 78% of enterprise teams run MCP-backed agents in production as of April 2026, making the MCP security surface a mainstream concern. — [growthengineer.ai/blog/production-ai-agent-stack](https://growthengineer.ai/blog/production-ai-agent-stack)

## Gotchas

- **Call-count budgets aren't enough.** An agent can appear to make progress while each call is actually a no-op (tool returns empty, agent reformulates the same question). Track meaningful progress — whether the tool's output changed the agent's state — not just call count.
- **Hard cost ceilings kill valid long tasks.** A $0.50 ceiling will abort a legitimate multi-step research task. Calibrate per task type: simple FAQ = $0.05, complex research = $5.00. Use task classification to select the budget tier.
- **Allowlisting MCP tools breaks the "just add a tool" developer workflow.** Teams resist friction during development. Gate it: allowlist is off in dev (with logging), required in staging and production. Add a pre-deploy checklist item.
- **Checkpoint size grows with task length.** If you checkpoint the full conversation history at every step, you pay storage costs and slow resume. Checkpoint only the durable state — the work product, not the full context window.
