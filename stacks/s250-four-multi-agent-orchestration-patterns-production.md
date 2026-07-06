# S-250 · Four Multi-Agent Orchestration Patterns in Production

The single agent works in the demo. The multi-agent pipeline fails in production — not because the models are wrong, but because the coordination topology was never designed for failure, cost, or scale.

## Forces

- **Single agents plateau fast.** Beyond 15–20 tool calls or 5–6 reasoning steps, performance degrades — hallucinations increase, instructions are forgotten, outputs become inconsistent. Complex real-world tasks demand adaptive, resilient execution that a single agent cannot provide.
- **Every coordination topology trades latency for reliability.** A fully peer mesh gives agents maximum autonomy but makes failure modes unpredictable. A strict supervisor hierarchy gives you auditability but creates a bottleneck at the top.
- **Market pressure is real.** The multi-agent AI market is valued at $5.4B (2024) → projected $236B (2034) at ~46% CAGR. Gartner: 40% of enterprise applications will embed AI agents by end of 2026. This is not a research curiosity — it is an infrastructure bet.
- **The orchestration pattern is a deployment decision, not a code preference.** Supervisor, Swarm, Pipeline, and Router patterns each encode different assumptions about trust, latency tolerance, and failure recovery — and picking the wrong one is expensive to undo.

## The Move

Four production-proven topologies for multi-agent coordination. Choose based on your latency budget, failure tolerance, and whether agents are homogeneous or domain-specialized.

### 1. Supervisor Pattern — One Agent, Many Workers
A central supervisor decomposes a task and delegates sub-tasks to specialized workers, then aggregates results.

- Use when: Tasks decompose cleanly into independent sub-tasks with a clear aggregation step
- Best for: Research → analysis → synthesis pipelines, document processing (extract → transform → validate)
- Implementation: LangGraph `send` primitive or CrewAI hierarchical `ManagerAgent`
- Failure mode: Supervisor becomes the bottleneck; if it mis-decomposes, all workers produce wrong outputs
- Production signal: Used at Klarna and Elastic for customer support ticket routing

### 2. Swarm Pattern — Peer-to-Peer with Shared Context
Agents advertise capabilities and dynamically discover and delegate to peers based on task requirements.

- Use when: Task boundaries are unknown at design time; agents must self-organize
- Best for: Open-ended research, competitive analysis (many sources, unknown structure), marketing content (Strategy → Creative → SEO → Analyst)
- Implementation: Agent registry with capability metadata, broadcast-and-respond message bus
- Failure mode: Circular delegation loops; agents waiting indefinitely for responses from peers that never respond
- Production signal: Opensoul's 6-agent marketing agency uses a peer mesh — Director coordinates, but agents check work queues and delegate to peers autonomously
- Market stat: 46% CAGR — driven primarily by swarm-style use cases where task structure is discovered, not prescribed

### 3. Pipeline Pattern — Sequential Stage with Quality Gates
Tasks flow through a fixed sequence of specialized stages, each producing an output consumed by the next.

- Use when: Tasks have a known sequence; you need auditability and deterministic retry points
- Best for: Contract review (extract → validate → compare → draft), compliance audits, code review (lint → test → security scan → merge)
- Implementation: LangGraph state machine with conditional edges between stages, or CrewAI sequential `Crew` with task dependencies
- Failure mode: Stage N failure blocks all downstream stages; long pipelines amplify latency
- Production signal: Harvey AI (legal, 700+ clients) runs contract review through a pipeline: extract → clause match → risk flag → draft response
- Cost note: Multi-agent pipelines in production run $5–8 per complex task in LLM inference alone

### 4. Router Pattern — Agent Selection Based on Query Classification
A classifier agent routes incoming requests to the most appropriate specialist agent(s), without a fixed workflow.

- Use when: Input types are diverse and require different handling strategies
- Best for: Customer support triage, multi-format document ingestion (invoice vs. contract vs. email), hybrid RAG (structured query → SQL agent; unstructured → vector agent)
- Implementation: Small classifier model (e.g., `gpt-4o-mini`) routes to specialist; specialists use OpenAI Agents SDK `run` with routing logic
- Failure mode: Misclassification routes to the wrong agent; cascading failure if the router itself degrades
- Production signal: Deutsche Telekom's 100M-customer support system routes across 10 countries using a classification layer before agent dispatch

## Evidence

- **Blog post (Lushbinary, May 2026):** Four production-proven patterns (Supervisor, Swarm, Pipeline, Router) with market data — $5.4B (2024) → $236B (2034), ~46% CAGR, Gartner 40% enterprise embed rate — [Lushbinary multi-agent orchestration guide](https://lushbinary.com/blog/multi-agent-orchestration-patterns-supervisor-swarm-pipeline-router-guide)
- **Blog post (Gennoor, Jan 2026):** Beyond 15–20 tool calls or 5–6 reasoning steps, single-agent performance degrades; LangGraph for fine-grained stateful control, CrewAI for rapid manager+worker+reviewer prototyping, AutoGen entering maintenance mode Oct 2025 — [Gennoor multi-agent systems comparison](https://gennoor.com/resources/blog/multi-agent-systems-langgraph-crewai)
- **Blog post (Imperialis Tech, Mar 2026):** Multi-agent production gaps — no built-in determinism, unpredictable costs, enterprise integration challenges; Gartner projects 70% of multi-LLM orgs will use orchestration platforms by 2028 — [Imperialis multi-agent in production](https://imperialis.tech/en/blog/multi-agent-systems-langgraph-crewai-autogen-production)
- **Show HN (Opensoul, ~3 months ago):** 6-agent marketing agency using peer mesh — Director, Strategist, Creative, Producer, Growth Marketer, Analyst — running autonomously on scheduled heartbeats, delegating to teammates — [Opensoul on HN](https://news.ycombinator.com/item?id=47336615)

## Gotchas

- **Don't default to multi-agent.** Many "multi-agent" needs are single-agent-with-tools. If the task has a known sequence, use a pipeline. If a single model with better tools solves it, use one agent.
- **AutoGen is in maintenance mode.** As of October 2025, Microsoft recommends Microsoft Agent Framework as the successor. Do not start new projects on AutoGen.
- **Swarm patterns need explicit loop prevention.** Without TTL counters or acknowledgment timeouts, agents in a peer mesh can delegate to each other indefinitely, running up costs with no output.
- **Pipeline failure cascades.** If stage 3 of a 5-stage pipeline fails, stages 4 and 5 never run — but you still pay for stages 1–3. Design retry budgets per stage, not per pipeline.
- **Router misclassification is a silent failure.** Unlike a pipeline that visibly breaks, a bad router silently sends requests to the wrong agent. Build classifier accuracy into your eval suite.
