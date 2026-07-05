# S-632 · When to Split an Agent (and When Not To)

Your multi-agent demo impressed everyone. Six months in, you've got context-passing bugs, inter-agent hallucination, $9,800/month bills, and no idea which agent produced the wrong answer. The problem isn't that multi-agent is wrong — it's that most teams split agents too early, for the wrong reasons, with the wrong communication patterns. The decision to go multi-agent has concrete triggers. Most teams hit none of them.

## Forces

- **The multi-agent frame is pushed hard by every framework vendor.** LangGraph, CrewAI, and AutoGen all make spawning agents trivial. Easy spawning creates a gravitational pull toward complexity that isn't earned by the problem.
- **Context window pressure is the wrong reason to split.** Teams see their agent's context growing and reflexively reach for agent splitting. But context window overflow is usually a chunking, compression, or retrieval problem — not a staffing problem.
- **Orchestration overhead compounds.** Each management layer adds LLM calls. Each inter-agent handoff is a potential hallucination surface. Debugging a chain of five agents is an order of magnitude harder than debugging one.
- **Structured communication is the hard part nobody budgets for.** Agents communicating through free-form text require each downstream agent to interpret the upstream output. Schema-validated message passing dramatically reduces miscommunication — but it requires upfront design work.

## The Move

### Split only when you have at least one of these triggers

- **Trigger 1 — Specialized knowledge domains.** A single agent needs deep, conflicting expertise to handle a workflow (e.g., legal compliance + financial modeling + code generation). Separate agents with focused system prompts and tool sets consistently outperform generalists on domain-specific tasks. The domain boundary is the agent boundary.
- **Trigger 2 — Parallel execution on independent sub-tasks.** Multiple sub-tasks that don't depend on each other's output should run simultaneously, not sequentially. A research phase that fetches competitor data, internal metrics, and market signals in parallel is a natural fit for a multi-agent dispatcher.
- **Trigger 3 — Strict isolation requirements.** Some tasks must not bleed context or state into others — financial calculations that shouldn't be influenced by prior conversation context, security-sensitive operations that need a separate trust boundary. Agent isolation enforces this structurally.

### Use orchestrator-worker as your default pattern

```
Lead Agent (Orchestrator)
  → dispatches tasks to specialized agents
  → aggregates results
  → makes final decisions
```

Anthropic's own multi-agent research system uses this pattern. The lead agent coordinates research sub-agents, each responsible for a different angle. The orchestrator never does the research itself — it manages the process. This keeps the lead agent lightweight and predictable.

### Use structured message schemas for every inter-agent communication

Define TypeScript interfaces or JSON schemas for every message type. An agent's output must be machine-parseable by the receiving agent — not just human-readable prose that requires interpretation. A legal-review agent outputting `{ "violations": [], "risk_level": "low" }` is vastly more reliable than a prose paragraph.

### Use a shared-memory (blackboard) pattern for decoupled coordination

Agents that don't need to know about each other — only about shared state — are easier to add and debug. Implementation: a structured JSON document in a database or in-memory store. Each agent reads its relevant sections, writes results to its designated section. The orchestrator reads all sections and assembles the final output.

### Start single-agent. Add agents only when you have evidence.

Add a second agent only when you have measurable evidence that a single agent is failing — not when the codebase makes it easy. If your single agent with good prompting and tools handles 90% of cases correctly, invest in the remaining 10% with better prompting, retrieval, or tools before adding a second agent.

## Evidence

- **HN Ask: Scaling AI agents in production:** An AI e-commerce analyst practitioner using LangGraph reported that LangGraph's checkpointing was critical for state persistence across agent steps — particularly for resuming long-running report generation jobs after failures. They emphasized that their biggest win was treating agent state as a first-class database concern, not an in-memory concern. — [HN thread #44909029](https://news.ycombinator.com/item?id=44909029)
- **Cleanlab: AI Agents in Production 2025:** Surveyed 1,837 engineering leaders; only 95 (5%) had AI agents live in production. Of those, 70% of regulated enterprises rebuild their AI stack every 3 months or faster, and fewer than 1 in 3 teams are satisfied with their observability and guardrail solutions. The report notes that the gap between experimentation and production is fundamentally an engineering challenge, not a model capability challenge. — [Cleanlab](https://cleanlab.ai/ai-agents-in-production-2025)
- **CoreSysLab: Multi-Agent AI Systems in Production:** Detailed analysis of inter-agent communication patterns: "structured message passing — where agents communicate through well-defined schemas rather than free-form text — dramatically reduces miscommunication." Cites the shared-memory (blackboard) pattern as the most decoupled approach for adding agents without cascading changes. Notes that cost and latency overhead from each management layer compounds quickly. — [CoreSysLab](https://www.coresyslab.com/blog/multi-agent-ai-systems-production)
- **Engineering.fyi: Anthropic multi-agent research system:** Anthropic's own engineering blog describes their transition from prototype to production multi-agent system. Key lessons: checkpointing every agent step, using structured output schemas to prevent inter-agent miscommunication, and building an orchestration layer that handles failures and retries at the system level rather than inside individual agents. — [Engineering.fyi/Anthropic](https://www.engineering.fyi/article/how-we-built-our-multi-agent-research-system)

## Gotchas

- **Inter-agent hallucination is real.** A downstream agent treats an upstream agent's prose output as ground truth. Schema-validated structured outputs are the mitigation — not prompting the downstream agent to "be careful about the previous agent's output."
- **Runaway agent loops are expensive.** Teams report costs from $15 in ten minutes to $47,000 over eleven days from uncontrolled agent loops. Hard budget enforcement and step-count limits are non-negotiable in production.
- **Stack churn is the hidden enemy.** 70% of regulated enterprises rebuild their AI stack every 3 months. Choosing an orchestration framework is a commitment — the churn cost is real. LangGraph's checkpointing model and broad ecosystem adoption make it the most defensible choice for teams that need production-grade state management.
- **Observability is always underinvested.** Fewer than 1 in 3 production teams are satisfied with their observability. Without trace-level logging of every agent step and tool call, debugging a multi-agent system in production is archaeology.
