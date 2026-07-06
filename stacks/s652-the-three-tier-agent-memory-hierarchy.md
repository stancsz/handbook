# S-652 · The Three-Tier Agent Memory Hierarchy

Most agents are chatbots with a prompt. Real agents have memory — and the production ones have three distinct tiers that handle fundamentally different concerns. Getting this wrong leads to either a stateless system that "forgets everything" or a confused one that stuffs everything into a vector store and检索 the wrong thing at the wrong time.

## Forces

- **LLMs have fixed context windows.** You cannot fit an agent's full history, user preferences, and accumulated knowledge into a prompt. You must decide what lives where.
- **Latency and cost both scale with context size.** Embedding a 100K-token history into every call is expensive and slow. The right tier for the right data type is not a nice-to-have — it's a cost control mechanism.
- **Memory is not RAG.** RAG retrieves documents for a question. Agent memory is written and read by the agent itself, across sessions, with semantic recency weighting, access frequency, and user transparency requirements that RAG pipelines don't model.
- **Agent pause/resume requires structured state.** When a human interrupts a long-running task, the agent must checkpoint its reasoning, tool-call progress, and intermediate outputs — not just its conversation history.

## The move

Split agent memory into three tiers, each with a different storage backend, TTL, and read/write pattern:

**Tier 1 — Hot Memory (session state):**
- Current conversation turns, checkpoint state, pending tool-call outputs
- Storage: PostgreSQL row or Redis hash — structured, low-latency, synchronous reads
- Write on every LLM turn; read on every LLM call
- Enables pause/resume, human-in-the-loop approval flows, and conversation summarization triggers

**Tier 2 — Cold Memory (cross-session knowledge):**
- User preferences, learned facts, accumulated context across sessions
- Storage: Vector store (pgvector, Qdrant, Pinecone) with metadata filtering — semantic similarity search
- Write: episodic summarization triggered when hot memory exceeds a threshold (~4,000 tokens)
- Read: retrieved by the agent on session start or on relevance signal
- Requires recency and access-frequency weighting to avoid stale embeddings dominating

**Tier 3 — Document Memory (project knowledge):**
- Conventions, specs, codebase facts, research notes
- Storage: File-based (Markdown, JSON) or an object store — the agent writes and queries these directly
- Agent creates and updates these files as "notes to future self"
- Human-readable and human-editable — users can inspect and correct what the agent knows
- Use case: AI coding agents that remember "this repo uses Python 3.11, not 3.12" across sessions

Each tier has an explicit read/write contract. The agent queries only the tiers it needs per call, driven by a lightweight memory manager that decides retrieval strategy.

## Evidence

- **Engineering blog:** The three-tier taxonomy (hot/cold/document) is documented by multiple independent sources as the standard production pattern for agent memory — distinguishing it sharply from RAG-first approaches that treat everything as a retrieval problem — [slavadubrov.github.io — AI Agent Memory Architecture in 2026](https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture)
- **GitHub project:** `alexpota/pg-agent-memory` implements a structured memory layer for PostgreSQL with pgvector, explicitly separating checkpoint storage from semantic memory, and adds a "memory transparency" feature so users can inspect what the agent has stored about them — [github.com/alexpota/pg-agent-memory](https://github.com/alexpota/pg-agent-memory)
- **Technical analysis:** pgvector is increasingly preferred over dedicated vector databases for agent memory specifically because agent memory needs structured metadata, SQL joins, recency weighting, and access frequency tracking — not just vector similarity — [kronvex.io — Vector Databases for AI Agents](https://kronvex.io/blog-vector-database-agents)

## Gotchas

- **Don't put everything in the vector store.** The most common mistake is skipping the hot-memory tier and embedding every conversation turn. This is slow, expensive, and produces poor retrieval results since recent context is rarely the most semantically similar to the current query.
- **Checkpoint failures silently break pause/resume.** If hot-memory writes fail (DB connection drop, Redis timeout), the agent loses its ability to resume mid-task. Wrap writes in a retry with a local file fallback.
- **Cold memory grows unbounded without a forgetting strategy.** Embeddings accumulate forever in production. Without a TTL or importance-weighted eviction policy, semantic retrieval degrades and costs rise monotonically. The agent needs a memory manager that periodically compresses or prunes cold memory.
- **Document memory needs a schema.** Agents writing free-form Markdown notes produces inconsistent, unparseable files. Define a lightweight schema (entity → attribute → value) for document memory entries so both the agent and human reviewers can read them.
