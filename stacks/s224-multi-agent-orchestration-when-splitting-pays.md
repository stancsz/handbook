# S-224 · Multi-Agent Orchestration — When Splitting Actually Pays

Multi-agent systems get sold as the natural evolution of AI agents. The pitch: decompose a complex task into specialized agents, coordinate them, get superlinear gains. The reality: 40% of multi-agent pilots fail within six months of production deployment. Single agents match or outperform multi-agent setups in 64% of benchmarks. The accuracy delta is +2.1 percentage points — for roughly 2x the cost. Before you split an agent into three, you need to know what the split actually buys you.

## Forces

- Multi-agent inquiry volume grew 1,445% from Q1 2024 to Q2 2025 (Gartner) — the hype outpaced the evidence, and teams are paying for it with failed pilots
- The coordination overhead is non-linear: each additional agent adds not just cost but failure modes (coordination failure, contradictory outputs, deadlocks, cascading errors)
- Single-agent performance is underrated — a well-prompted Claude 4 Opus or GPT-4.5 with tool access handles most "multi-agent" use cases without coordination overhead
- The 40% failure rate isn't because multi-agent systems don't work — it's because teams pick the wrong orchestration pattern for their problem or don't have a clear stopping condition
- Average organizations deploy 12 agents; projected growth is 67% in two years — the sprawl is real and operational costs compound faster than teams expect
- Migration between orchestration frameworks (CrewAI → LangGraph, for example) is the most expensive hidden cost — implicit shared state in one framework becomes explicit refactoring debt in another

## The Move

Before splitting, apply the **split test**: does this task require (a) genuinely different domain expertise, (b) independent execution that can happen in parallel, or (c) adversarial viewpoints that should produce contradictory outputs for a judge to resolve? If none of the three apply, keep it single-agent.

When splitting is justified, match the orchestration pattern to the coordination requirement:

- **Orchestrator-Worker** (one central agent decomposes, delegates, assembles): use when task decomposition is clear and the orchestrator is clearly smarter than the workers — customer service routing, report generation from independent sections, multi-document research synthesis
- **Hierarchical Supervisor** (supervisor above, specialists below, explicit handoff gates): use when agents need approval before proceeding to the next stage — compliance checking, content moderation pipelines, multi-stage approvals
- **Pipeline** (agents process sequentially, output of one feeds the next): use when order matters intrinsically — drafting → editing → fact-checking → publishing
- **Swarm / Peer** (agents coordinate loosely, may communicate with multiple peers): use when the problem is exploratory and you want emergent synthesis — early-stage research, brainstorming, competitive analysis

Implement explicit stopping conditions. Without them, agentic loops run until they hit a token or time budget — which means they fail expensively, not gracefully. A hard max-iterations cap combined with a quality threshold gate prevents runaway loops.

## Evidence

- **Gartner data (Q1 2024 → Q2 2025):** Multi-agent system inquiries grew 1,445%; average organization uses 12 agents; 67% growth projected within two years. Multi-agent pilots fail within 6 months at 40% rate. Single-agent matches/outperforms multi-agent in 64% of benchmarks; multi-agent accuracy gain averages +2.1 percentage points vs ~2x cost increase — [Beam.ai synthesis of Gartner data](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- **Opensoul (HN Show):** Built a 6-agent marketing agency stack — Director (strategy/coordinator), Strategist, Creative, Producer, Growth Marketer, Analyst — running on Paperclip with scheduled heartbeat loops. The creator explicitly notes this is "productizing what I learned" after a year of autonomous agent systems, not a greenfield experiment. Each agent checks a work queue, executes, delegates, and reports — [HN Show HN, June 2025](https://news.ycombinator.com/item?id=47336615)
- **Cordum production analysis (2026):** Framework behavior differs sharply in failure modes. CrewAI's `Process.sequential` default suits structured pipelines; AutoGen v0.4's layered Core + AgentChat model suits low-level control at higher engineering cost. The expensive mistake in 2026: teams ignore migration and governance tests while comparing demos. Tool schemas (CrewAI → LangChain) transfer directly; implicit shared state is the expensive refactor — [Cordum.io, June 2026](https://cordum.io/blog/crewai-vs-autogen-2026)
- **Google Vertex AI (Patrick Marlow, Staff Engineer):** 12+ years in conversational AI; delivered hundreds of models to production. Key finding: multi-agent evaluation requires HITL (human-in-the-loop) because automated metrics fail to capture coordination failures, inter-agent communication breakdowns, and emergent behaviors that only appear in complete-system runs. The evaluation challenge scales superlinearly with agent count — [ZenML LLMOps Database / YouTube, 2024](https://www.zenml.io/llmops-database/lessons-learned-from-production-ai-agent-deployments)

## Gotchas

- **Naive decomposition is the #1 failure mode**: splitting an agent because "it feels like separate concerns" without clear coordination boundaries creates agents that fight over state or duplicate work — the coordination overhead exceeds the parallelism gain
- **State management is the hidden migration trap**: CrewAI's implicit shared context must be refactored into explicit LangGraph state annotations for a clean migration; this is the most labor-intensive part and teams consistently underestimate it
- **Framework comparison demos lie**: CrewAI vs LangGraph vs AutoGen demos run on friendly, well-defined inputs. Production inputs are messy, adversarial, or ambiguous. Compare failure behavior, not happy paths
- **The cost of coordination is not in the LLM calls**: it's in the serialization, state transfer, retry logic, and observability gaps between agent boundaries — those costs don't appear in demo budgets
