# S-510 · Agent Cost Engineering: The Production Economics Nobody Talks About

Agents look cheap in demos. They are not cheap in production. The teams getting burned aren't the ones with bad prompts — they're the ones who never instrumented their cost surface before shipping.

## Forces

- **Agent workloads consume orders of magnitude more tokens than conversational AI.** A 50-step task at $3-15/Mtok on GPT-4o-class models lands at $2-10 per task before you factor in retries, re-ranking, and observability overhead.
- **Optimization is 60-85% recoverable** — but most teams discover this only after a runaway loop. Prompt caching, intelligent model routing, and hard budget enforcement can cut the bill dramatically.
- **The observability gap kills budgets before they start.** 89% of teams have tracing infrastructure; only 52% have evaluation pipelines. You can't optimize what you can't measure.
- **Gartner predicts 40% of agentic AI projects will be cancelled by end of 2027** — not because the agents fail, but because the economics don't hold at production scale.
- **Runaway loops are the dominant incident type.** The worst documented incident cost $47,000 over 11 days. Others hit $15 in ten minutes. The variance is extreme and the failure is silent — the agent produces confident text while burning tokens.

## The Move

**Build cost engineering into the agent scaffold, not as an afterthought.**

### Cache aggressively at the prompt level
Prompt caching (OpenAI's cached prompts, Anthropic's cache) can recover 60-85% of spend on repeated or long-context tasks. Cache the system prompt, cached context, and any retrieval results that repeat across requests. The key is identifying what is cacheable vs. what must recompute — static domain knowledge, schema definitions, and instruction prefixes are all strong cache candidates.

### Route cheaply, escalate surgically
Assign tasks to the cheapest capable model. A classification task that GPT-4o handles at $0.01 likely works at $0.0001 on a fine-tuned smaller model or a frontier model's faster/thinner variant. Route on task type, estimated complexity, and cost sensitivity — not on a fixed model. Segment: fast-path (cheap model, no tools), medium-path (frontier model, <3 tool calls), escalation-path (frontier + full tool suite, human-in-the-loop gate).

### Hard budget enforcement with auto-throttling
Set per-session, per-task, and daily cost ceilings. Auto-throttle or halt the agent when ceilings breach. This is a circuit breaker, not a log entry. Teams with budget enforcement survived the same token price spikes that bankrupted teams without it.

### Attribute cost per unit of work
Tag every LLM call with task type, user segment, and agent ID. Without hierarchical cost attribution you cannot identify which workflows are profitable, which are subsidized, or which are pure money pits. The goal is per-task unit economics, not just total spend.

### Plan for the runaway loop
Every agent that can call itself or loop on tool results needs a hard iteration ceiling (e.g., 20 tool calls max). Combine with a cost-per-step cap that kills the session if the agent is burning more than, say, $0.50 per step without measurable progress.

## Evidence

- **Zylos Research (2026):** Average enterprise AI monthly spend reached $85,521 in 2025. Model API spend grew from $3.5B to $8.4B between late 2024 and mid-2025. 60-85% of spend is recoverable through caching + routing + budget enforcement. Worst documented runaway incident: $47,000 over 11 days. — [Zylos Research — AI Agent Cost Engineering](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)

- **Gartner (2025):** 1,445% surge in multi-agent system inquiries (Q1 2024 → Q2 2025). 49% of organizations cite high inference cost as their top production blocker. 40% of agentic AI projects at risk of cancellation by end of 2027 due to escalating costs and unclear ROI. — [RaftLabs citing Gartner, Nov 2025](https://www.raftlabs.com/blog/multi-agent-systems-guide)

- **RaftLabs production survey (2025):** 57.3% of organizations already have agents in production. 79% of senior execs report AI agent adoption. 89% have observability tooling; only 52% have evaluation pipelines — explaining why debugging is "mostly guesswork." 4-agent orchestrator-worker workflows cost $5-8 per complex task; cost compounds across agent boundaries. — [RaftLabs — Multi-Agent Systems: Architecture Patterns](https://www.raftlabs.com/blog/multi-agent-systems-guide)

- **Harvey AI (legal):** Agentic RAG production deployment achieved 0.2% hallucination rate serving 700+ legal clients — demonstrating that rigorous evaluation and retrieval guardrails directly translate to real-world cost savings (fewer errors = fewer costly human reviews). — [aliac.eu — Agentic RAG in Production](https://aliac.eu/blog/agentic-rag-in-production)

## Gotchas

- **Caching only helps repeated contexts.** If every user request has unique context, caching hit rates collapse. Profile your actual cache hit rate before betting on caching as your primary optimization.
- **Cheap model routing introduces reliability risk.** A 7B local model that saves $0.009 per task but fails 15% of the time costs more in retry overhead and user trust than it saves. Only route down when you can measure failure rate at the new tier.
- **Budget enforcement that kills sessions mid-task creates user-facing failures.** Design the circuit breaker to gracefully degrade (fewer tools, shorter context) rather than hard-fail. Silent degradation beats angry customers.
- **Per-task cost tracking requires instrumentation at call time.** Retrofitting cost attribution into an existing agent is painful — instrument the cost surface on day one, even if you don't act on it yet.
