# S-585 · Agent Stack Stratification — Sandboxing as a First-Class Layer

The agent stack is fracturing into six distinct specialization layers, and the teams treating it as a monolith are paying for it. Sandboxing — once an afterthought — has emerged as its own architectural tier with dedicated tooling, distinct failure modes, and a measurable gap between teams that have it and teams that don't.

## Forces

- **AI-generated code breaks traditional container assumptions.** Containers assume reviewed, tested code. Agents generate and execute code at runtime that has never been reviewed. This collapses the threat model that Docker-based isolation depends on.
- **The 85%-to-5% gap is a sandboxing gap.** Cisco RSA 2026 identified 85% of enterprises experimenting with AI agents but only 5% confident in production deployment. The delta is isolation boundaries — not model quality.
- **Sandboxing is not interchangeable with orchestration or memory.** Teams retrofit sandboxing into existing layers instead of treating it as its own tier. This creates blast-radius failures where a compromised agent can escape into shared infrastructure.
- **Layer specialization enables different defensibility profiles.** Each layer (sandbox, orchestration, memory, tools, observability, evaluation) has different switching costs and competitive moats. Monolithic designs collapse these into a single point of failure.

## The move

Treat sandboxing as an independent architectural layer, matched to threat model — not to developer convenience.

- **Map threat level to isolation technology.** Low-risk internal tools: Docker containers with network restrictions. Medium-risk multi-tenant SaaS: gVisor. High-risk untrusted code execution: Firecracker MicroVMs or Kata Containers. There is no universal answer — only the answer matched to your threat model.
- **Use purpose-built agent sandboxing platforms for code execution.** E2B grew 375x in 12 months (40,000 to 15M executions/month, Mar 2024→Mar 2025), with 88% of Fortune 100 on the platform. Modal and Shuru serve adjacent niches. These platforms handle the runtime isolation that Docker doesn't.
- **Enforce skill sandboxing at the subprocess level.** Subprocess isolation with declared network whitelists, filesystem restrictions, resource limits, and audit logging. For higher-risk skills, add AST scanning before install to catch injection attempts.
- **Let orchestration and sandboxing evolve independently.** LangGraph and CrewAI own orchestration; E2B/Firecracker own isolation. Conflating them into one layer creates a rebuild obligation when one matures faster than the other.
- **Design for blast-radius containment, not prevention.** Assume agents will attempt unexpected actions. Network isolation, filesystem restrictions, and resource limits should contain the damage — not stop the attempt.
- **Audit sandbox boundaries like network boundaries.** Log every sandbox escape attempt, resource limit hit, and permission escalation. These are your most valuable failure signals.

## Evidence

- **Blog post:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing" — HN comment by 7777777phil linking to philippdubach.com analysis showing 37% of enterprises now use 5+ AI models in production, with the stack stratifying into six distinct layers each with different defensibility profiles — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Blog post:** E2B sandbox growth data (375x YoY), Fortune 100 adoption (88%), and the documented 5% confident production deployment rate vs 85% experimenting — [Fordel Studios](https://fordelstudios.com/research/ai-agent-sandboxing-isolation-production-2026)
- **HN post:** Local research multi-agent stack using SQLite+FTS5 for memory (zero infra overhead) with subprocess isolation and network whitelists per skill — [HN #47279088](https://news.ycombinator.com/item?id=47279088)
- **Blog post:** 65% of agent teams hit a wall within 12 months and face a rewrite — architecture choice in week one determines ceiling in year one — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/11/langgraph-autogen-crewai-dspy-multi-agent-orchestration-2026)
- **Blog post:** MCP reached 97M+ monthly SDK downloads (Jan 2026), becoming the de-facto standard for tool integration; E2B, Modal, and Firecracker wrappers each serving different isolation use cases — [Ajentik](https://www.ajentik.com/insights/multi-agent-systems-production-guide) + [Generation Digital](https://www.gend.co/blog/model-context-protocol-mcp)

## Gotchas

- **Docker is not a sandbox for AI agents.** Docker assumes reviewed code. Agents generate and execute unreviewed code at runtime. The shared kernel alone disqualifies it for high-risk execution environments.
- **Conflating orchestration with isolation is the most expensive mistake.** LangGraph and CrewAI excel at workflow state management. Neither is a sandbox. Using them as both creates a single point of failure when requirements diverge.
- **Defaulting to "just containers" delays the problem, not solves it.** Teams that skip isolation early pay compound interest later: the agent grows in capability, the blast radius grows with it, and retrofitting isolation into a running system is harder than building it in.
- **Skill-level isolation is not the same as agent-level isolation.** Even within a sandboxed agent, individual skills (code execution, file access, API calls) need their own restrictions. A compromised skill inside an otherwise sandboxed agent can still escalate.
