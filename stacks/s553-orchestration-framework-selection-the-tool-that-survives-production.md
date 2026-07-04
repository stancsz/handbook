# S-553 · Orchestration Framework Selection: The Tool That Survives Production

Choosing an orchestration framework is easy. Choosing one that survives a year of production with shifting requirements, rotating engineers, and cost audits is not. Teams that pick for the demo pay later — rewriting the orchestration layer while the rest of the system depends on it.

## Forces

- **LangGraph, CrewAI, and AutoGen look similar in demos** — the real differentiation surfaces only under production pressure: branching logic, state management, cost observability, and team familiarity
- **The fastest prototyping choice is often the slowest long-term** — CrewAI's role-based abstractions are welcoming but fight back when workflows become non-linear
- **Framework coupling is expensive to undo** — orchestration choices become load-bearing as the rest of the system hooks into their abstractions
- **Vendor alignment matters** — AutoGen v0.4's group chat model pairs tightly with Azure; LangGraph is model-agnostic; CrewAI is LLM-agnostic but uses LangChain under the hood

## The Move

Match the framework to the workflow topology, not the feature list.

**Use LangGraph when:**
- Workflows require conditional branching, loops, and stateful graphs (the graph IS the program)
- You need explicit control over every edge and node in the execution flow
- You are building multi-agent systems where agent boundaries map to graph nodes
- Production debugging and step-level tracing are non-negotiable
- You want to stay model-agnostic and avoid vendor lock-in

**Use CrewAI when:**
- The workflow is a linear or fan-out/fan-in pipeline of specialist agents (research → write → review → publish)
- Team members are less technical and need abstractions that read like roles and responsibilities
- Prototyping speed is the hard constraint — onboarding takes an afternoon
- The use case fits the hierarchical process (manager delegates to workers)

**Use AutoGen v0.4+ when:**
- Collaborative multi-agent reasoning is the core (agents debate, critique, and revise)
- You are already on Azure and want tight OpenAI/Azure AI Studio integration
- The workload benefits from async group chat rather than structured pipelines

**Build custom (minimal orchestration) when:**
- The workflow is simple enough that a loop + tool calls + a state dict does the job — most agent code is better as 200 lines of Python than 20,000 lines of framework
- You need to avoid LangChain's overhead (CrewAI bundles it) — fork the API surface you need and implement it against your stack directly

## Evidence

- **Framework comparison (production experience):** CrewAI handles ~70% of use cases well (linear pipelines); LangGraph wins on branching and stateful workflows; AutoGen dominates on collaborative reasoning tasks. CrewAI's main friction point is meta-orchestration around the framework when workflows require conditional loops — the framework wasn't designed for it. — [hjLabs AI Engineering Notes: CrewAI vs LangGraph vs AutoGen](https://hemangjoshi37a.github.io/hjLabs-AI-Engineering-Notes/04-crewai-vs-langgraph-vs-autogen-production-comparison/)
- **Stack stratification:** The agent stack is splitting into specialized layers — sandboxing (E2B, Modal, Firecracker wrappers), orchestration, memory, and tool calling are converging as distinct categories. Going monolithic (one framework for everything) is increasingly the wrong call as the layers have different defensibility profiles. — [Hacker News on agent stack stratification](https://news.ycombinator.com/item?id=47114201)
- **Multi-agent orchestration patterns:** Four patterns cover most production use cases — hierarchical (supervisor delegates), pipeline (sequential), orchestrator-worker (router assigns tasks), and peer-to-peer (agents collaborate as equals). Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025, with 57% of organizations already running agents in production. — [RaftLabs: Multi-Agent Systems Architecture Patterns](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- **CrewAI uses LangChain under the hood** — teams that thought they were avoiding LangChain by choosing CrewAI are still coupled to its abstractions, bugs, and upgrade cadence
- **AutoGen v0.4 is a significant rewrite** from v0.2 — many blog posts and comparisons reference the old API; verify the version before trusting code samples
- **Framework choice propagates** — once you build tool definitions, state schemas, and agent prompts on a framework, migrating is a full rewrite; choose based on where you'll be in 18 months, not where you are today
- **The simplest production-grade orchestration is often a while loop + structured state + explicit tool definitions** — framework overhead pays off only when the workflow complexity genuinely justifies it
- **Multi-agent orchestration compounds costs** — $5–8 per complex multi-agent task is typical; cost controls must be per-agent and per-task, not global
