# S-343 · Multi-Agent Coordination as Distributed Systems

When you split one agent into five, the hard problem isn't the individual agents — it's the coordination. Conversations between agents are messages, shared artifacts are state, and failed agents are crashed nodes. The teams that have learned this the hard way are converging on a single conclusion: treat your agentic pipeline like a distributed system, or it will fail like a monolithic one.

## Forces

- **Shared state lives in artifacts.** When a planner agent outputs a spec and a coding agent writes code from it, those artifacts are your distributed state. Intent drift between them — the spec says one thing, the code does another — is your equivalent of state inconsistency.
- **Agents fail non-deterministically.** Unlike a crashed microservice you can restart, an agent that produces plausible-but-wrong output doesn't signal failure. Your fault tolerance must detect semantic failure, not just crashes.
- **Orchestration frameworks abstract away the hard parts.** LangGraph, CrewAI, and AutoGen handle the easy coordination — they choke on the hard parts: intent preservation across agent boundaries, consensus on shared artifacts, and graceful degradation when one agent goes off-task.
- **Verification gates are mandatory, not optional.** Without deterministic checks between agent stages (compile, lint, schema validation), misinterpretation compounds silently until the output is garbage.

## The move

Multi-agent software pipelines should be architected and operated like distributed systems. The key practices:

- **Sequential stages with verification gates.** Break work into stages (plan → design → code → test) with deterministic checkpoints between each. Each gate runs compile, lint, schema checks, or structured tests — things that detect failure objectively. Agentic review handles qualitative assessment; deterministic checks catch regressions.
- **Artifacts are shared state — version them.** Treat the plan document, design spec, and generated code as committed state in a shared store. Agents read from and write to this store; the pipeline between stages is a commit, not a handoff.
- **Intent preservation via explicit contracts.** Before agent A calls agent B, define the schema of the artifact B will consume. A plan isn't "write a Python module" — it's "write a Python module conforming to this interface spec." Schema drift between stages is the distributed systems equivalent of an API contract break.
- **LLM-as-judge for semantic checkpoints.** Deterministic checks catch code that doesn't compile; they don't catch code that does compile but doesn't solve the problem. Use a separate LLM call — or a smaller/faster model — to evaluate output quality against the upstream artifact's intent before proceeding.
- **Orchestrator = service mesh, not monolith.** A central orchestrator routes tasks to specialized agents, but agents shouldn't all be reachable from everywhere. Think north-south vs east-west traffic. A Director agent in Opensoul's marketing stack delegates to specialists; it doesn't do their work.
- **Fallback to human-in-the-loop at escalation boundaries.** Fully autonomous multi-agent pipelines remain rare in enterprise. The practical pattern: agents run autonomously within defined boundaries; outcomes that require judgment, approval, or fall outside policy escalate to a human.

## Evidence

- **HN Discussion (mrothroc):** Multi-agentic software development is a distributed systems problem — breaks work into sequential stages (plan, design, code) with verification gates; deterministic checks handle compile/lint, agentic reviewer handles qualitative assessment. External validation converts misinterpretations into detectable failures. — https://news.ycombinator.com/item?id=47761625
- **MMC / HN Interview Survey:** Interviewed 30+ startup founders and 40+ enterprise practitioners. Found that over half of surveyed startups build their own agentic stacks from scratch, citing limited flexibility in existing frameworks. Main blockers are workflow integration, employee trust, and data privacy — not technical model performance. — https://news.ycombinator.com/item?id=45808308
- **Microsoft Multi-Agent Reference Architecture:** Documents 10 patterns including Semantic Router with LLM Fallback (classify intent with lightweight SLM, escalate to expensive LLM only on low confidence) and Dynamic Agent Registry (agents register capabilities, orchestrator discovers by capability). — https://microsoft.github.io/multi-agent-reference-architecture/docs/reference-architecture/Patterns.html
- **Netguru Production Case Study:** Built "Omega," a Slack-native sales agent, using AutoGen + AgentChat after evaluating LangChain, CrewAI, and Google ADK. Key lesson: framework choice matters less than retaining control over the system's evolution. Chose AutoGen for lower abstraction level and transparency. — https://www.netguru.com/blog/ai-agent-tech-stack
- **Opensoul (HN Show):** Open-source agentic marketing stack with 6 agents (Director, Strategist, Creative, Producer, Growth Marketer, Analyst). Each agent runs autonomously on scheduled heartbeats, checking work queues, delegating to teammates, reporting progress. Built on Paperclip orchestration platform. — https://news.ycombinator.com/item?id=47336615

## Gotchas

- **Don't skip the deterministic gate.** Adding a code review agent doesn't replace a linter — it complements it. Agents catch qualitative problems; deterministic checks catch the easy ones without spending LLM budget.
- **Framework lock-in is real.** Over half of production teams eventually rewrite their orchestration layer. LangGraph's graph-based model is more explicit about state transitions than CrewAI's role-based teams, making it easier to debug — but steeper to learn. Default to LangGraph unless you have a specific reason not to.
- **Intent drift compounds across stages.** A 5% misinterpretation rate per agent stage becomes a 30% failure rate across 7 stages. Mitigate this by tightening the contract schema at each handoff, not by trusting agents to preserve intent without scaffolding.
- **Cost control is harder in multi-agent systems.** Each agent call is a separate API call. Parallel agents multiply cost. Budget controls must be per-agent and per-pipeline, not global.
