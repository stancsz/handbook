# S-440 · The Agent Stack Is Stratifying

You picked an orchestration framework and assumed the rest was implementation detail. Six months later your agent is running untrusted code, leaking state between sessions, and you have no idea which layer is causing the 3-second latency spike. The agent stack is splitting into four distinct disciplines — and treating it as one monolithic choice is how teams end up with systems they can't debug, secure, or swap.

## Forces

- **One framework to rule them all doesn't work.** LangChain, CrewAI, and AutoGen all started as monolithic orchestration tools. They all accumulated sandboxing, memory, and observability — and none of them do all four well
- **Sandboxing is its own hard problem.** Running untrusted LLM-generated code, files, or tool calls in production requires isolation at a level orchestration frameworks weren't designed for. Modal, E2B, and Firecracker-based microVMs are filling this gap
- **State persistence is not optional at scale.** LangGraph's checkpointing and CrewAI's memory are naive compared to purpose-built solutions. Teams hit the ceiling when they try to scale from 100 to 100,000 conversations
- **The evaluation layer is where teams give up.** LangSmith, Phoenix, and custom logging all exist, but 89% of teams have observability while only 52% have structured evals — leaving debugging as "mostly guesswork" (RaftLabs, 2025)

## The move

The agent stack is separating into four specialized layers. Each layer has its own best-in-class tool, and the teams that ship reliable agents are choosing deliberately per layer rather than locking into one framework:

- **Orchestration:** LangGraph for production-grade state machines (LinkedIn, Uber, Klarna); CrewAI for fast prototyping and role-based workflows; custom state machines when you need zero dependency overhead
- **Sandboxing/execution isolation:** Modal for Python-native serverless compute; E2B for sandboxed code execution; Firecracker-based microVMs (Shuru) when you need kernel-level isolation
- **Memory/persistence:** Postgres + pgvector for structured relational memory; Qdrant or Weaviate for high-dimensional vector search; Redis for ephemeral session state
- **Observability/evals:** Phoenix (Tracelength) for open-source LLM tracing; LangSmith for LangChain-native observability; custom eval pipelines with structured scoring

The rule: start with one tool per layer. Add the second only when you have concrete evidence the first has hit its ceiling.

## Evidence

- **HN discussion (16 days ago):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — 7777777phil, HN comment on Show HN: Local-First Linux MicroVMs — https://news.ycombinator.com/item?id=47114201
- **RaftLabs production data:** 89% of teams have observability but only 52% have structured evals — the observability/eval gap explains why multi-agent debugging is "mostly guesswork" — https://www.raftlabs.com/blog/multi-agent-systems-guide
- **LangChain production users:** LinkedIn (hierarchical recruiter agent), Uber (customer support), Klarna (80% resolution time reduction) all use LangGraph specifically for its state management — not the full LangChain ecosystem — https://www.langchain.com/blog/is-langgraph-used-in-production
- **Atlan engineering data:** Over 60% of production agent incidents trace back to state management failures — agents losing context mid-workflow, repeating steps, or crashing without recovery — https://atlan.com/know/ai-agent/ai-agent-memory/what-is-langgraph

## Gotchas

- **Don't choose an orchestration framework and assume its bundled memory/sandboxing is production-grade.** CrewAI's built-in memory degrades at scale; LangChain's tool calling is fine for prototypes but too many deps for production
- **Sandboxing without observability is invisible risk.** Running untrusted LLM code in an E2B sandbox means nothing if you can't trace what executed and why
- **The "build your own core agent loop" advice applies to orchestration, not all four layers.** Implement your own state machine; don't reinvent sandboxing or observability from scratch
- **Multi-agent adds a latency tax at every layer.** Each agent boundary is a network hop, a serialization, and a potential failure mode — measure before splitting
