# S-386 · Production Hardening — What "Production-Ready" Actually Demands

Agents that demo well and agents that survive production are different species. The gap between them is everything — and teams that learn it the hard way tend to converge on the same shortlist of hardening requirements: deterministic fallbacks, observability at every tool call, cost controls, human-in-the-loop checkpoints, and idempotency. These aren't optional polish. They're what separates a system that costs $200/hour from one that costs $50,000/month.

## Forces

- **A demo works until it doesn't — and then it fails expensively.** An agent running 47 tool calls where 3 would suffice, looping until rate-limited, or returning a hallucinated refund approval will "succeed" on outcome metrics while burning cash or corrupting downstream state.
- **The stochastic mindset is non-obvious to engineers trained on deterministic systems.** AI agents are probabilistic. Input A does not always produce output B. Teams that bring web-development intuitions (it worked in staging, ship it) discover this gap in production — usually on a Friday.
- **MCP is real but the security surface is unverified by default.** 41% of surveyed software organizations are now in limited or broad production with MCP servers (Stacklok 2026 report). The ecosystem has 9,652 active public servers in the official registry. The protocol is standardized; the trust model is not.
- **Cost is the most underestimated production constraint.** Average monthly AI spending reached $85,521 in 2025 — a 36% jump from 2024 (unverified; cite as "industry survey data, 2025"). Most teams budget for inference, not for the 10x token inflation that comes from verbose tool-call loops.

## The Move

Harden agents along five axes before they hit real traffic:

- **Deterministic fallbacks for every tool call.** If a tool returns unexpected output — not an error, but malformed data — the agent should degrade gracefully, not hallucinate forward. Catch output shape mismatches at the boundary, not downstream.
- **Cost circuit breakers with hard token budgets.** Set per-task token ceilings that terminate execution and log the failure. ReAct-style loops are the primary cost inflater: an agent calling the same tool with minor variations will happily run until the API limit or the invoice.
- **Observability at every tool call boundary, not just the LLM.** LangSmith, Phoenix, or custom structured logging should trace: tool name, arguments (sanitized), response shape, latency, and cost. LLM-level traces alone miss where time and money actually go.
- **Human-in-the-loop for high-stakes actions.** Agents that modify state, approve refunds, send emails, or execute code should pause and require explicit confirmation before irreversible actions. This is not just a safety measure — it's also the most effective hallucination catch.
- **Idempotency on all agent-triggered side effects.** Every action the agent takes on external systems should be safe to retry. Use idempotency keys on API calls, check-for-existing-state before writes, and treat every retry as a fresh invocation.

## Evidence

- **Blog post (field note):** "Multi-Agent Orchestration Infrastructure: Lessons from Production" — TURION.ai, March 2026, author Balys Kriksciunas. Covers Supervisor+Specialists as the dominant production pattern, why ReAct loops inflate costs, and the "stochastic mindset" as the key cultural shift teams need. — [https://turion.ai/blog/multi-agent-orchestration-infrastructure-production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Blog post (practitioner):** "AI Agents in Production: Patterns, Pitfalls, and Best Practices for 2026" — DevStarSJ, May 2026, author SeokJoon Yun. Lists the five production requirements (deterministic fallbacks, observability, cost controls, HITL checkpoints, idempotency) as the definitional test for "production-ready." — [https://devstarsj.github.io/2026/05/07/ai-agents-in-production-patterns-pitfalls-2026](https://devstarsj.github.io/2026/05/07/ai-agents-in-production-patterns-pitfalls-2026)
- **Research report (survey):** The state of MCP adoption in 2025 — Turbostream Substack, September 2025, author Manas Mudbari. 41% of surveyed software organizations in production with MCP servers; 9,652 active public servers in official registry; major players (Anthropic, OpenAI, Google DeepMind, Microsoft) all adopted the protocol. — [https://turbostream.substack.com/p/the-state-of-mcp-adoption-in-2025](https://turbostream.substack.com/p/the-state-of-mcp-adoption-in-2025)
- **Engineering blog:** "Patterns for Building a Scalable Multi-Agent System" — Microsoft ISE Developer Blog, November 2025, authors Sushant Bhalla and Vikesh Singh Baghel. Key requirements for production multi-agent systems: accurate agent selection, optimized LLM usage, efficient orchestration, and scalability. — [https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale)

## Gotchas

- **Cost controls must be enforced at the infrastructure layer, not the prompt layer.** Telling an agent "don't exceed 10 tool calls" in a system prompt is not a circuit breaker — it is a suggestion. Token budgets and termination policies belong in the execution environment.
- **MCP server trust is the new dependency trust problem.** MCP standardizes how agents call tools, but it doesn't solve who audits the tool's behavior. A compromised MCP server can execute command injection through the agent. Vet MCP servers the same way you vet npm packages.
- **Observability tooling is immature.** LangSmith has the most production adoption for LangGraph workloads, but teams outside that ecosystem often build bespoke logging that doesn't compose. The lack of a universal trace format across frameworks is a real operational pain point in heterogeneous stacks.
