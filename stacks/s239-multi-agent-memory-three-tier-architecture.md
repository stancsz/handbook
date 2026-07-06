# S-239 · Multi-Agent Memory — Three-Tier Architecture for Shared State

When agents multiply, they stop remembering. Each one holds its own context window, makes its own decisions, and walks away with nothing durable. The result is a team of agents that can never build on each other's work, contradict each other across turns, and fail in ways that are structurally impossible to patch with better prompting alone.

## Forces

- **Context windows aren't memory** — stuffing every prior interaction into the next prompt is expensive, slow, and unreliable past ~20k tokens. You need durable, queryable state that survives beyond a single request
- **Shared memory is not the same as inter-agent messaging** — passing context between agents via messages is fine for coordination but doesn't give agents persistent, queryable access to what happened hours or sessions ago
- **Vector store ≠ memory architecture** — slapping Pinecone behind an agent doesn't make it "have memory." It makes it have a retrieval layer for documents. Real memory needs structured types, eviction policies, and consolidation
- **Scaling multiplies the problem** — two agents can coordinate with a shared in-memory dict. Ten agents with 50 tools across 200 sessions cannot. The failure surface grows faster than teams expect

## The Move

Split memory into three distinct tiers, each with its own storage, retrieval, and write semantics. Treat them like a database schema — they are different data types that happen to live near each other.

**Tier 1 — Episodic memory (what happened)**
- Stores: conversation turns, task outcomes, tool execution results, agent decisions with timestamps
- Storage: vector database (Qdrant, Pinecone) with structured metadata (agent_id, session_id, task_id, outcome, timestamp)
- Retrieval: similarity search + metadata filters. Not everything is semantic — filter by agent or session to avoid cross-contamination
- Writes: make them deliberate (explicit "remember" tool calls), not automatic. Schema-validate before inserting to prevent garbage compounding

**Tier 2 — Semantic memory (what is true)**
- Stores: ground-truth facts, entity knowledge, learned preferences, organization policies
- Storage: relational schema (PostgreSQL + pgvector, or a structured KV store) — something you can audit, query, and update without re-embedding
- Retrieval: structured query first, vector search second. If you know the entity, query by ID. Only use semantic search for open-ended discovery
- Writes: consolidation pipeline. Periodic job that reconciles episodic observations into structured facts, deduplicates contradictions, and updates the semantic store. This is not automatic — it needs a merge strategy (last-write-wins, confidence scoring, human review for high-stakes facts)

**Tier 3 — Procedural memory (how to do it)**
- Stores: agent prompts, tool definitions, workflow policies, routing rules, guardrails
- Storage: versioned documents (Git, object storage, or a policy store) the agent retrieves on-demand before executing
- Retrieval: exact match or rule-based routing. The agent fetches the relevant procedure before a class of tasks, not during
- Writes: human-authored and reviewed. This is your system prompt, your MCP tool schemas, your routing logic — treat it like infrastructure code with review gates

**Working memory (the transient layer)**
- Lives in the orchestrator's state object for the duration of a single task/session
- Includes the current plan, active tool calls, and short-term context
- Never persists — reconstruct it from episodic + semantic on session start

## Evidence

- **Blog post (AppScale, Satyam Kumar, May 2026):** "Agent Memory Architecture: Episodic, Semantic, Procedural — the Three-Tier Pattern" — establishes the canonical framework; argues context-window-plus-vector-store fails because it lacks eviction, consolidation, and typed access — [appscale.blog/en/blog/agent-memory-architecture-episodic-semantic-procedural-the-three-tier-pattern-2026](https://appscale.blog/en/blog/agent-memory-architecture-episodic-semantic-procedural-the-three-tier-pattern-2026)
- **Blog post (Mem0, Fimber Elemuwa, March 2026):** "How to Design Multi-Agent Memory Systems for Production" — reports multi-agent failure rates of 40–80%, with 36.9% attributable specifically to inter-agent misalignment (not model quality). Argues structural solutions outperform prompting fixes by 14–15 percentage points — [mem0.ai/blog/multi-agent-memory-systems](https://mem0.ai/blog/multi-agent-memory-systems)
- **Reddit discussion (r/MachineLearning):** "What is your LLM Stack in Production?" — practitioners reporting migration from single vector stores to hybrid stacks (Supabase + structured metadata, Elasticsearch for BM25 + vector for semantic). Multiple users cite recall/precision improvements from separating retrieval strategy from storage — [reddit.com/r/MachineLearning/comments/1b4sdru](https://www.reddit.com/r/MachineLearning/comments/1b4sdru/)

## Gotchas

- **Don't let episodic memory grow unbounded** — without a consolidation pipeline, the vector store becomes a noisy graveyard. Tag every episodic entry with a TTL or outcome flag and run periodic cleanup
- **Schema-drift on semantic memory** — when facts change (a customer's address, a product's price), you need a write path that updates the semantic store, not just appends to episodic. Teams forget this and end up with contradictory ground truths
- **Don't conflate message-passing with memory** — inter-agent communication (LangGraph's state updates, CrewAI's delegation) handles coordination, not persistent recall. An agent that crashed and restarted at 3 AM needs to reconstruct its context from memory stores, not from a dead message queue
- **Multi-tenant right-to-be-forgotten is non-trivial** — if agents serve multiple customers, episodic entries tagged to a user need GDPR-style deletion. This requires namespace-level isolation in the vector store and a hard-delete policy, not soft-delete
- **Procedural memory is code, not content** — treating agent prompts like configuration files without version control leads to silent regressions. A prompt that worked last week may behave differently today if an AI-assisted edit changed the routing logic subtly
