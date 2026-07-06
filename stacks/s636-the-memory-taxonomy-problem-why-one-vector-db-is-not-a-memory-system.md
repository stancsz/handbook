# S-636 · The Memory Taxonomy Problem: Why "Add a Vector DB" Is Not a Memory System

Every agent demo starts with one: a vector database. Chunk some documents, embed them, retrieve on query. It works. Then you ship, and after a few sessions you notice the agent keeps forgetting things it just learned, re-discovers the same facts across sessions, and occasionally retrieves memories that were contextually wrong but semantically close. The issue isn't the vector database — it's treating it as the answer to a question it doesn't answer: what does it mean for an agent to *remember*?

## Forces

- **"Memory" in AI agents is four orthogonal problems pretending to be one.** Working state, session progress, cross-session facts, and semantic recall each need different storage primitives, retrieval patterns, and update semantics. A single vector DB solves at most one of them well.
- **Context window pressure forces the problem you think you don't have.** Agents forget mid-task, not just between sessions. The model bleeds relevant context around the middle of long histories — degrading as much as 73% on reasoning tasks at 128K context.
- **Fuzzy retrieval and structured facts are in tension.** Vector search excels at semantic similarity; it fails at "update the user's shipping address to 42 Elm St." You need both, and they conflict on the same storage layer.
- **Memory consolidation has a cost you don't model until it burns you.** Without periodic compression, episodic memory grows unbounded. With aggressive compression, you lose detail. The right cadence depends on use case, and teams discover this only after either running out of context or silently losing institutional knowledge.

## The move

Build a tiered memory architecture aligned to the CoALA model — four layers, each with the right storage primitive and update semantics.

**Tier 1 — Working memory (in-process).** Holds the current step's state: tool call arguments, partial LLM response, current plan. Never persists — reconstructed from the checkpoint on resume. Use: Python dict or dataclass, scoped to the current call stack.

**Tier 2 — Short-term / checkpoint memory (Redis or PostgreSQL).** Holds session-level progress: conversation history so far, plan steps completed, current task state. Enables pause-and-resume without losing work. Redis for latency-critical resume paths (sub-millisecond); PostgreSQL for durable checkpoints that must survive restarts. Key insight: the checkpoint is the unit of recovery, not the message.

**Tier 3 — Episodic memory (pgvector or Qdrant).** Holds cross-session events: "User asked about NVDA earnings last week," "Customer complained about shipping on March 3rd." Stored as embedded vectors with metadata. Retrieve by semantic similarity with a time decay filter — recent episodes rank higher. Store raw text alongside the vector for human review and debugging.

**Tier 4 — Semantic / factual memory (PostgreSQL or Redis hash).** Holds permanent structured facts: user preferences, business rules, product constraints. Updated deterministically, not retrieved by similarity. Wrong address → update the row, don't search for "address near Elm Street." Treat this as a write-through cache of ground truth, not a search surface.

**Bonus — Consolidation worker (background job).** On a rolling schedule (e.g., nightly or after N sessions), compress episodic memory summaries into semantic memory. Raw events age out after 30-90 days depending on retention needs. This is the step teams skip, and it silently produces unbounded storage growth.

## Evidence

- **Blog post:** Slava Dubrov, "AI Agent Memory Architecture in 2026," documents the CoALA taxonomy and the four-layer pattern with Redis for transient state, PostgreSQL/pgvector for semantic recall, and consolidation workers. Notes 40% storage reduction from compression — [slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture](https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture)
- **Engineering blog:** Shopify Sidekick (Aug 2025) hit the checkpoint failure mode in production — tools scaled from 20 to 50+ and the system lost track of session state without explicit checkpoint boundaries. Their fix: per-capability-group checkpointing before handoff — [shopify.engineering/building-production-ready-agentic-systems](https://shopify.engineering/building-production-ready-agentic-systems)
- **Engineering blog:** Chadana Bhagat's production memory series (2025) built the full stack — episodic with Qdrant, semantic with PostgreSQL, consolidation worker, multi-agent Redis-backed shared memory, and PII scrubbing — reporting 40% storage reduction post-consolidation — [chandanbhagat.com.np/ai-agents-memory-production-architecture-complete](https://chandanbhagat.com.np/ai-agents-memory-production-architecture-complete)

## Gotchas

- **Semantic memory needs write-through semantics, not search semantics.** The most common mistake: trying to retrieve "what's the user's plan tier?" via vector similarity. It finds the closest topic match instead. Use structured storage with deterministic key lookups for facts; reserve vector search for open-ended recall.
- **Episodic without a consolidation worker is a time bomb.** Without compression, episodic storage grows indefinitely and retrieval quality degrades. Without a defined retention policy (e.g., compress to summary after 30 days, delete raw after 90), you inherit unbounded cost and stale context.
- **Cross-agent memory requires a shared store, not per-agent stores.** In multi-agent systems, two agents working on the same task need a shared memory layer — not copies of the same episodic store. Use Redis with workspace-key namespacing or a shared PostgreSQL schema. RaftLabs found untyped handoffs kill multi-agent workflows faster than any other failure mode (2025) — typed semantic memory is part of the solution.
