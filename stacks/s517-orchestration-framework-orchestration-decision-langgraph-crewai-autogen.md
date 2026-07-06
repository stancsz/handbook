# S-517 · The Orchestration Framework Decision: Choosing by Failure Mode, Not Feature List

When your team sits down to build a multi-agent system in 2025-2026, the choice between LangGraph, CrewAI, and AutoGen (or Microsoft Agent Framework, or OpenAI's Agents SDK) is the first architectural decision with compounding consequences. Every comparison starts with feature matrices. The teams that ship reliably start with the opposite question: **what does each framework make easy to get wrong?**

## Forces

- **LangGraph's graph paradigm is powerful but demands upfront investment** — you model the state machine before you can run anything. Teams that need to prototype fast and defer state design hit a wall. Teams that treat state as a first-class artifact ship more predictably.
- **CrewAI's role-based team abstraction collapses under complexity** — the `role + goal + backstory` pattern gets you to a working demo in hours. When you need to pass structured data between agents, add conditional branching, or handle partial failures, you're fighting the abstraction instead of using it.
- **AutoGen's conversational model is genuinely different** — it excels when agents need to negotiate, debate, or reach consensus rather than execute a known pipeline. This maps poorly to task automation and well to analysis and design tasks.
- **The "fast to demo, slow in production" trap** — CrewAI wins on time-to-first-agent; LangGraph wins on time-to-stable-production. Teams optimize for the wrong variable and pay later.
- **The framework decides what you can debug** — LangGraph exposes state at every node; CrewAI abstracts execution flow; AutoGen gives you conversation logs. When your agent does something wrong at 2am, the debugging experience is framework-dependent.
- **Model-agnosticism is now table stakes** — all three frameworks support OpenAI, Anthropic, and local via Ollama/vLLM. This has stopped being a differentiator.

## The move

Choose orchestration framework by answering three questions in order:

### 1. Who owns the control flow — you, or the agents?

- **Agents should drive** (AutoGen): multi-turn negotiation, collaborative analysis, debate tasks. The framework handles turn-taking and message routing automatically.
- **You should drive** (LangGraph): deterministic pipelines, compliance workflows, anything where a human or business rule should decide the next step. The graph IS the spec.
- **Roles should drive** (CrewAI): rapid prototyping, marketing/content pipelines, when domain experts define agent roles without engineering involvement.

### 2. What is your state model?

LangGraph forces you to define state upfront — a TypedDict with explicit fields. This is a cost at the start and a benefit at scale. If your state is simple (a few string fields), CrewAI's implicit state is faster. If your state is complex (mutable lists, partial results, branching sub-states), LangGraph's explicit model prevents an entire class of bugs.

CrewAI's state is implicit in the agent's memory and task output. LangGraph's state is explicit and versioned. For systems that need audit trails or deterministic replay, LangGraph wins without debate.

### 3. What is your observability floor?

| Framework | Debugging primitive | Trace depth |
|-----------|--------------------|--------------|
| LangGraph | Full state snapshot at every node | CheckpointStore, LangSmith |
| CrewAI | Agent-level logs, task outputs | Limited; best-effort |
| AutoGen | Conversation history | GroupChat context window |

If you have a dedicated MLOps/observability team, LangGraph + LangSmith is the only option that gives you production-grade traces without custom instrumentation. If you're a small team that needs to move fast, CrewAI's surface-level logging is faster but you'll write your own debugging tools.

### Production-ready checklist by framework

**LangGraph when:**
- You need durable, resumable agent runs (checkpoints save state to DB)
- Your workflow has conditional branching based on output content (not just tool results)
- You need to run the same graph with different models or system prompts at runtime
- Compliance or audit requires replaying a specific execution path
- You're building a customer-facing product where you need to debug failures post-hoc

**CrewAI when:**
- You're in week 1 of a greenfield project and need to validate the concept
- Non-engineers need to read and modify agent definitions (YAML)
- The workflow is linear or hierarchical with minimal conditional logic
- You want the hierarchical manager agent pattern for a pipeline
- You will rebuild in 6-12 months anyway (startup exploration, not platform)

**AutoGen when:**
- You need agents to debate, vote, or reach consensus
- Your primary use case is analysis (financial research, code review, strategy)
- You're running on Azure and want first-class Microsoft integration
- Multi-agent negotiation is the core mechanic, not a feature

## Evidence

- **Shopify Sidekick (Shopify Engineering, Aug 2025):** Evolved from a simple tool-calling system to a sophisticated agentic platform using Anthropic's agentic loop pattern. Key architectural insight: "Scaling tool inventory creates predictable failure modes — specifically, accuracy drops below 90% and latency becomes unacceptable above a certain tool count." They built tool routing and evaluation infrastructure that frameworks alone don't provide. — [Shopify Engineering](https://shopify.engineering/building-production-ready-agentic-systems)
- **RaftLabs production data (Nov 2025):** 57% of organizations already running multi-agent systems in production; inference cost compounds to $5-8 per complex task for 4-agent orchestrator-worker workflows. Typed schemas between agents are the #1 prevention for multi-agent workflow failures. 89% have observability but only 52% have evaluation pipelines. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Framework comparison (Gheware DevOps, Jan 2026):** LangGraph offers the most control and production stability via graph-based workflows; CrewAI delivers the fastest path to working prototypes but teams hit scalability limits within 6-12 months; AutoGen excels at collaborative reasoning but maps poorly to deterministic task automation. All three are model-agnostic. — [Gheware](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Gotchas

- **CrewAI's hierarchical mode creates a single point of failure** — the manager agent routes all tasks. If it misinterprets output or fails to parse a result, the whole crew stalls silently.
- **LangGraph's checkpointing is not free** — serializing state to Postgres or SQLite at every step adds latency and storage costs. Price it before committing to durable runs.
- **AutoGen's group chat has a context window ceiling** — for large teams or long conversations, messages get dropped silently. Plan for summarization or explicit truncation.
- **Framework churn is real** — LangChain (the parent project) has had significant API breaking changes across versions. Pin your dependency versions and treat upgrades as migration projects.
- **The "switch later" assumption kills projects** — teams that start in CrewAI for speed and plan to migrate to LangGraph for production underestimate the rewrite cost. The graph paradigm and YAML-based role definition lead to fundamentally different agent designs.
