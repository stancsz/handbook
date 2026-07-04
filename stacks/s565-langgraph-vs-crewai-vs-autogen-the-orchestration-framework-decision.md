# S-565 · LangGraph vs CrewAI vs AutoGen: The Orchestration Framework Decision

Teams don't choose an orchestration framework — they choose a mental model, a scaling ceiling, and a debugging surface area. The three dominant options make different bets on all three.

## Forces

- LangGraph, CrewAI, and AutoGen solve the same problem with fundamentally different abstractions — a state machine, a role-based team, and an async group chat — and the wrong abstraction creates compounding debt as complexity grows
- No framework wins on all axes: LangGraph has the highest production ceiling but slowest initial velocity; CrewAI ships fastest but hits a wall on partial failures and custom control flows; AutoGen 0.4+ is event-driven and powerful on Azure but has the steepest learning curve
- The 52% evals gap (RaftLabs: 89% observability coverage but only 52% running actual evals) means teams ship without measuring — and framework choice determines whether "we'll add eval later" is survivable

## The move

Match the framework to the production trajectory, not the prototype:

- **CrewAI** if the use case is a bounded, linear pipeline of specialist steps and the team needs to ship in days. Its Agent/Task/Crew abstraction reads cleanly to non-specialists. Accept the wall: partial failures, custom branching, and anything requiring per-node retry logic will fight you.
- **LangGraph** if the workflow has multiple paths, requires breakpoints, human-in-the-loop approval steps, or will need per-node retry policies. The graph mental model maps directly to production requirements. Pay the upfront cost: LangGraph has a steeper initial learning curve and more boilerplate but a higher ceiling.
- **AutoGen 0.4+** if the team is on Azure, needs deep native OpenAI integration, or wants collaborative multi-agent reasoning. Its async message-passing model handles complex group dynamics well. Avoid if the team needs fast onboarding or plans to migrate off Azure.
- **Custom state machine** (Temporal, or raw Python with explicit transitions) when the agent logic is secondary to workflow reliability — Temporal's built-in durability, retries, and saga patterns handle what no LLM framework can: guaranteed execution under infrastructure failures.

## Evidence

- **Framework comparison — 18 months production:** HjLabs shipped on all three frameworks; verdict: CrewAI ~70% of use cases (linear pipelines), LangGraph when retry control and breakpoints are needed, AutoGen when Azure and group chat patterns fit. Source-specific weaknesses: CrewAI struggles with partial failures and malformed JSON from tool calls; LangGraph requires significant upfront state design; AutoGen is "opinionated about model choice" and steep learning curve. — [hjLabs.in — CrewAI vs LangGraph vs AutoGen](https://hemangjoshi37a.github.io/hjLabs-AI-Engineering-Notes/04-crewai-vs-langgraph-vs-autogen-production-comparison/)
- **Production AI agent lessons — observability:** Every agent call should log input context, model reasoning, tool calls with results, and final output. "Without this, debugging agent failures is like debugging a program with no stack trace." — [Graebener.tech — Building Production AI Agents](https://graebener.tech/blog/building-with-ai-agents)
- **Multi-agent cost data:** Gartner tracked 1,445% surge in multi-agent inquiries Q1 2024–Q2 2025. Inference costs compound to $5–8 per complex task in 4-agent workflows. Untyped handoffs between agents are the most common killer of multi-agent systems. — [RaftLabs — Multi-Agent Systems Guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Eval gap:** 89% of teams have observability coverage but only 52% run actual evals — meaning most teams can see what their agents did but not whether it was right. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- CrewAI's hierarchical process (manager agent delegates to workers) sounds like real delegation but is still a single LLM routing tokens — under load it becomes a bottleneck, not a team
- LangGraph's "breakpoints" for human-in-the-loop sound great until you realize they're synchronous by default and require a dedicated UI or polling loop to be useful in production
- AutoGen 0.4's async event-driven architecture is the most powerful model for complex group dynamics but is a completely different programming paradigm — "it requires a mindset shift from prompt-and-respond to subscribe-and-react"
- Framework choice is sticky: migrating from CrewAI's implicit control flow to LangGraph's explicit graph is a rewrite, not a refactor. Pilot with the framework you'll keep.
