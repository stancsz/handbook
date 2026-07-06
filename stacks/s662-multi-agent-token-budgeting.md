# S-662 · Multi-Agent Token Budgeting: Controlling the Cost Explosion in Production Agent Systems

[You have five agents. Each reads the same 8,000-token context. Each calls the same 20-tool schema definitions. Each produces intermediate output that the supervisor re-reads. What should cost $0.02/query is costing $1.40. Nobody on the team can explain where the tokens went, and the quarterly API bill is 40× what the PM estimated. This is the default state of multi-agent systems in production — uncontrolled token proliferation across agent boundaries.]

## Forces

- **Every multi-agent framework duplicates context by default.** MetaGPT has a 72% token duplication rate; CAMEL reaches 86%; even optimized frameworks like AgentVerse still show 53%. The orchestrator re-sends shared schemas, system prompts, and context windows to every agent on every turn — and production teams rarely audit this.
- **Token cost is non-linear with agent count.** Adding a second agent doesn't double cost — it multiplies it across the number of handoff points, shared context reads, and re-iteration loops. A 6-agent DeepSearch system was reported at $2.00/query on HN, compared to sub-$0.10 for equivalent single-agent approaches.
- **Observability is the #1 barrier to production multi-agent adoption** (Zylos Research, Jan 2026) — not capability, not reliability, but the inability to trace where tokens and money go.
- **The "more agents = better results" assumption breaks at cost thresholds.** Anthropic's own research confirms that orchestration complexity (multiple agents iterating) beats single-model zero-shot only when the workflow complexity justifies it — not as a general principle.

## The Move

Control token proliferation through three compounding strategies:

- **Context segmentation and per-agent memory scoping.** Define exactly what each agent can read. A research agent gets document chunks and search results; it never gets the UI state. A writing agent gets drafts and brand guidelines; it never gets raw API payloads. Gate context at the agent level, not the session level.
- **Supervisor-first routing with hard budget guards.** Route every request through a lightweight supervisor that decides whether a full multi-agent dispatch is warranted. Simple lookups → single agent. Multi-source synthesis → multi-agent with explicit sub-task limits. This alone cuts unnecessary dispatches by 60-80% in reported deployments.
- **Tool schema memoization.** Register tool definitions once and share a reference. Don't re-send full OpenAPI schemas or JSON tool descriptions on every turn. Cache and version schemas; agents reference schema IDs, not full payloads.
- **Streaming intermediate outputs.** Don't accumulate full agent outputs in context — stream them to a shared artifact store (S3, Redis) and have dependent agents read summaries, not raw outputs.
- **Per-agent model tiering.** Assign smaller, cheaper models to narrow-task agents (routing, extraction, validation) and reserve frontier models only for synthesis and judgment. A CLAUDE-3-5-HAULK/$3/M for a classification agent is waste.
- **Budget-per-turn with graceful degradation.** Set a max-token budget per agent per task. If exceeded, return a structured "incomplete" signal instead of retrying, and have the supervisor decide whether to retry with a different strategy or surface a partial result.

## Evidence

- **HN discussion (June 2025):** A practitioner running a 6-agent DeepSearch system for stock research reported ~$2.00/query and noted "running multiple agents is expensive, decreasing RoI." The thread surfaced that "the more capable the model, the lower the need for multi-agents" — suggesting that frontier-model upgrades can sometimes replace multi-agent complexity entirely.
  — [Hacker News: Building Effective AI Agents](https://news.ycombinator.com/item?id=44301809)
- **Zylos Research (Jan 2026):** Multi-agent token duplication benchmarks across MetaGPT (72%), CAMEL (86%), AgentVerse (53%). 72% of enterprise AI projects now involve multi-agent systems (up from 23% in 2024).  Observability ranked #1 production barrier. Real-world results cited: 80% reduction in insurance claims processing, $18.7M annual savings in banking fraud — achievable only with controlled token budgets enabling consistent multi-agent orchestration at scale.
  — [Zylos Research: Multi-Agent Orchestration Patterns 2025](https://zylos.ai/research/multi-agent-orchestration-2025)
- **Anthropic Engineering (Dec 2024):** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." Their case studies showed that multi-agent workflow gains over single-model prompting disappear when the complexity overhead isn't justified by the task — which directly maps to token budget: if the extra 80,000 tokens per query don't demonstrably improve output quality, the budget was wasted.
  — [Anthropic: Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)

## Gotchas

- **Token counting in framework dashboards is usually wrong.** LangChain, CrewAI, and custom Python orchestrators all report token counts that include framework overhead — not just model I/O. Log at the raw API call level to get actual costs.
- **Context window limits create invisible truncation silently.** If you don't monitor truncation explicitly, agents silently drop the oldest context — and you get degraded results with no error signal. Budget guards must measure effective context utilization, not just raw token counts.
- **Cached tool schemas still cost on first load.** If you're memoizing tool definitions, the first call still sends the full schema. Budget the cold-start cost across the expected number of unique tool configurations, not just per-request.
