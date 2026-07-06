# S-628 · Picking an Orchestration Framework: What Teams Actually Choose

You're building a multi-agent system. The decision looks simple — just pick a framework. But LangGraph, CrewAI, and AutoGen each make fundamentally different bets about what "orchestration" means, and the wrong choice early locks you into an architecture that fights your problem shape.

## Forces

- **LangGraph trades ease for control.** A directed state machine is powerful but verbose. Teams that want to ship fast reach for CrewAI — then hit walls when they need fine-grained retry logic or custom state transitions.
- **CrewAI's role metaphor is seductive but narrow.** The manager + workers model works well for pipelines where task distribution is the hard part. It collapses for anything requiring shared mutable state, conditional branching, or tight coordination between agents.
- **AutoGen's conversational paradigm is the most natural for multi-agent collaboration** but enforces the least structure — which means production reliability is almost entirely your responsibility.
- **The observability layer is the real choice.** LangGraph + LangSmith is the only combo with out-of-the-box full-trace, replay, and state inspection. Teams that skip this spend months building ad-hoc debugging infrastructure.
- **The agent stack is stratifying.** Sandboxing (E2B, Modal, Firecracker) is emerging as its own infrastructure layer, separate from orchestration — driven by the realization that running untrusted agent code requires isolation, not just orchestration.

## The Move

The 2026 production consensus: **LangGraph is the default, CrewAI is for rapid prototyping of role-based pipelines, AutoGen is for research on novel collaboration patterns.**

- Use **LangGraph** when you need: state machines, hierarchical agents, retry logic, human-in-the-loop checkpoints, full observability, or any production system where reliability debugging matters.
- Use **CrewAI** when you need: fast prototyping of manager + workers patterns, non-technical teams defining agent roles via YAML, or internal tools where "good enough" beats "correct."
- Use **AutoGen** when you are researching multi-agent conversation dynamics or need natural back-and-forth between specialized agents without enforced workflow order.
- Layer **MCP (Model Context Protocol)** on top of any choice for tool calling — it has won the tool-integration standardization battle in 2025-2026.
- Add **sandboxing** (E2B, Modal) as a separate concern from orchestration for any agent code that executes user-provided or external scripts.

## Evidence

- **Framework comparison (Internative, 2026):** LangGraph is described as "the production default for planner-executor and hierarchical agent patterns (state machines, retries, debugging)." CrewAI as "the easiest framework for role-based teams (manager + workers)." AutoGen as leading "on multi-agent collaborative patterns." The analysis recommends: "Pick LangGraph unless you have an explicit reason for the other two."
  — [Internative: LangGraph vs CrewAI vs AutoGen 2026 Comparison](https://internative.net/insights/blog/langgraph-vs-crewai-vs-autogen-2026-comparison)

- **HN thread on agent stack stratification (philippdubach, 2025):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." Argues going monolithic across these layers has poor defensibility.
  — [Hacker News: Show HN — Local-First Linux MicroVMs](https://news.ycombinator.com/item?id=47114201)

- **McKinsey production lessons (50+ agentic builds, 2025):** Found that successful deployments share an "end-to-end slice" approach: prove the full pipeline works with minimal features before adding complexity. Also emphasizes that tool reliability — not agent sophistication — is the primary failure point.
  — [McKinsey: One Year of Agentic AI — Six Lessons](https://www.mckinsey.com/capabilities/quantumblack/our-insights/one-year-of-agentic-ai-six-lessons-from-the-people-doing-the-work)

- **Real-world production agent stack (Opensoul, HN Show, 2025):** Paperclip-based deployment with 6 specialized agents (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) running on scheduled heartbeats with inter-agent delegation. Each agent checks a work queue, executes, and reports — demonstrating the hierarchical crew model at scale.
  — [Hacker News: Opensoul — Open-Source Agentic Marketing Stack](https://news.ycombinator.com/item?id=47336615)

- **Comet on multi-agent design (2025):** Models degrade up to 73% on reasoning tasks when critical information is buried in long contexts. The "Lost in the Middle" problem makes monolithic prompts fundamentally unreliable. Solution: compartmentalized agents with isolated context, then synthesis — echoing the CrewAI hierarchical model but at a lower abstraction level.
  — [Comet: Multi-Agent Systems Architecture, Patterns, and Production Design](https://www.comet.com/site/blog/multi-agent-systems)

- **Real-world coding agent workflow (Jesse Vincent / Simon Willison, Oct 2025):** Vincent uses Claude Code with a custom "Superpowers" plugin that enforces red/green TDD, structured planning steps, self-updating memory notes, and an agent "feelings journal." HN reviewers note that recent updates consolidated subagents into a single agent for self-review, simplifying the architecture. Demonstrates that even sophisticated multi-agent setups often consolidate rather than expand when teams gain experience.
  — [Simon Willison: Superpowers — Coding Agents in October 2025](https://simonwillison.net/2025/Oct/10/superpowers/)
  — [Hacker News: A Rave Review of Superpowers](https://news.ycombinator.com/item?id=47623101)

## Gotchas

- **LangGraph's verbosity is a real tax.** Simple sequential pipelines take 5-10x more code than CrewAI equivalents. Teams often switch to CrewAI for prototyping, then rewrite to LangGraph for production — budget for that migration.
- **CrewAI's autonomous delegation sounds powerful but is hard to debug.** When agents hand off tasks to each other without a defined protocol, failures cascade silently. Add explicit validation steps between agent handoffs.
- **AutoGen's group chat requires a hard `max_round` cap.** Without it, agents can loop indefinitely in conversation — a cost and reliability killer. Every AutoGen deployment needs an explicit conversation budget.
- **Sandboxing is not optional for external code execution.** If your agents run user-provided code, scripts, or query external APIs without isolation, one bad input can compromise the entire system. Treat this as a separate infrastructure concern from orchestration.
- **The "feelings journal" pattern from Superpowers is worth stealing.** Having the agent self-report confidence and emotional state ("I feel uncertain about this edge case") is a lightweight proxy for uncertainty quantification that doesn't require additional model calls.
