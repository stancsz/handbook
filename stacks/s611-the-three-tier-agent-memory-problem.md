# S-611 · The Three-Tier Agent Memory Problem

Agents without memory start every conversation at zero. But treating all memory as a vector store is equally wrong. Real production agents need a three-tier architecture — hot, cold, and document — and conflating them is the root cause of both latency blowups and stale-context hallucinations.

## Forces

- **RAG ≠ agent memory.** RAG retrieves document chunks. Agent memory stores experiences, preferences, and learned facts about specific entities. The data model, access patterns, and eviction policies are fundamentally different.
- **Hot state needs sub-millisecond access.** Session-level checkpoints (where you are in the workflow, what the user just said) cannot round-trip to a vector store — that adds 50–200ms per retrieval and breaks streaming.
- **Cold memory without structure is useless.** Storing raw embeddings of past conversations and retrieving by similarity is not enough. You need typed records, temporal weighting, and entity scoping — who does this memory belong to?
- **The CoALA framework formalized what teams were already doing.** The Cognitive Architectures for Language Agents paper (Mendoza et al., 2024) gave practitioners a shared vocabulary for separating working memory, episodic memory, and semantic memory — and most teams discover this distinction through painful refactors.

## The Move

Build a three-tier memory architecture from the start. Each tier has different latency, different storage, and different retrieval semantics.

**Tier 1 — Hot (working memory):** Pause/resume within a session. Store in Redis or PostgreSQL as structured state (current node, pending tasks, conversation window). Sub-millisecond reads. Evict on session end or after N minutes of inactivity. Agents need this to stream responses while holding workflow state — vector round-trips break the UX.

**Tier 2 — Cold (episodic + semantic memory):** Cross-session personalization and entity state. Store in a vector database (Qdrant, Pinecone, pgvector) with typed records — not raw conversation logs. Each memory entry should have: entity ID, memory type (preference/fact/experience), timestamp, confidence score, and TTL. Retrieve by entity scope + recency + semantic similarity. This is what lets an agent know "this user prefers concise answers" without re-learning it every session.

**Tier 3 — Document (project knowledge):** Conventions, domain facts, system prompts. Store as Markdown/JSON files or in a document store. Not vector-searched — read directly by role or topic. This is the slowest-moving tier and the one most teams get right first.

**The retrieval pattern:** On each agent turn, query hot first (instant), then cold (parallel async), then document (if needed). Merge and deduplicate. Never block on a cold fetch before returning a hot-memory response.

## Evidence

- **Blog post:** The three-tier architecture (hot/Redis → cold/Qdrant → document/Markdown) is demonstrated in the "Market Analyst Agent" project, Part 2 of the "Engineering the Agentic Stack" series — [slavadubrov.github.io](https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture)
- **Blog post:** RAG and agent memory have fundamentally different requirements — RAG needs chunks and relevance scores; agent memory needs typed records, session scoping, and temporal weighting. pgvector wins for agent memory specifically because it supports SQL joins and structured metadata alongside vectors — [Kronvex](https://kronvex.io/blog-vector-database-agents)
- **Academic framework:** The CoALA (Cognitive Architectures for Language Agents) framework formalizes the working/episodic/semantic distinction as a design standard for agent memory systems — cited across multiple 2025–2026 engineering blog posts as the shared vocabulary for memory taxonomy

## Gotchas

- **Conflating cold memory with RAG is the most common mistake.** Storing agent memories as unstructured text chunks and retrieving them with similarity search produces irrelevant recalls and hallucinations. Typed, scoped, timestamped records are not optional — they are the product.
- **Blocking cold retrieval on the response path kills UX.** Fetch cold memory asynchronously and stream results as they arrive. A user waiting 300ms for "welcome back" because you did a synchronous vector search across 50k memories is a design failure, not a performance problem.
- **Memory without eviction creates a retrieval quality cliff.** As cold memory grows, semantic search degrades and stale facts override recent ones. Temporal decay functions and TTLs are not optional at scale.
- **Session scoping is overlooked.** Without entity-level scoping, one user's memories bleed into another. This is especially dangerous in multi-tenant SaaS agents. Every cold memory entry must carry a tenant or user ID as a hard filter, not just a soft signal.
