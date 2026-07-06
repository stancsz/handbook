# S-431 · Agent Memory Architecture: Beyond "Context Window + Vector Store"

The moment your agent needs to carry state across sessions — a support agent that remembers a user's prior tickets, a research agent that builds on last week's findings — "stuff it in context" and "embed everything" collapse into a system you can't audit, debug, or safely extend.

## Forces

- **Context window is finite and expensive.** Storing everything in the prompt grows token costs linearly with session count, and models degrade on very long contexts.
- **A single vector store treats all memory the same.** Episodic history, extracted facts, and system policies have fundamentally different query patterns — one index can't serve all three well.
- **Making memory writes automatic causes compounding errors.** Every failed retrieval silently pollutes the store; without a consolidation step, noise accumulates until the agent retrieves worse-than-random results.
- **Four things need remembering, not one.** The distinction between *what happened*, *what we know*, *how we operate*, and *what we're doing right now* — each demands a different storage and retrieval strategy.

## The move

Split memory into four distinct tiers, each with its own storage engine, retrieval rule, and write discipline.

**Tier 1 — Working memory: current task state only.**
- Stored in the orchestrator's state object (LangGraph `StateGraph`, CrewAI context, AutoGen group chat state).
- Lost between sessions by design. No persistence, no vector indexing.
- The agent's full attention is on it — never exceeds context budget.
- *Pattern:* Pass a typed `dict` or Pydantic state through the graph; only checkpoint the parts you need for recovery.

**Tier 2 — Episodic memory: what happened in past sessions.**
- Stored in a vector store (Qdrant, Pinecone, pgvector) with rich metadata: timestamp, session ID, agent role, task type, outcome.
- Retrieved by *similarity to the current query* — not by entity lookup.
- Must be periodically consolidated: summarize old episodes, deduplicate near-duplicates, flag contradictions.
- *Pattern:* After each session, run a LLM summarizer → store the summary. At query time, retrieve top-k episodes + inject as context. A consolidation job (weekly or on threshold) runs async to deduplicate.
- *Cost control:* Episodic summaries are ~200 tokens vs. raw transcripts that can be 10k+; always summarize before storing.

**Tier 3 — Semantic memory: what we know about the world and the user.**
- Stored in a relational or knowledge-graph schema (PostgreSQL, Neo4j) — not a vector store.
- Queried by entity and structured relationship — you know what you're looking for, so you query it directly.
- Contains extracted facts, user preferences, business rules, and learned policies.
- *Pattern:* Agent calls a structured `remember(tool)` function with schema-validated input; the LLM does not self-insert facts. Writes go through a validation step against the source-of-truth system before committing.
- Critical for multi-agent systems: semantic memory is the shared world model that prevents agents from contradicting each other.

**Tier 4 — Procedural memory: how the system operates.**
- Stored as versioned policy documents (Markdown, JSON Schema, or a database table).
- Retrieved on-demand when the agent encounters a known situation type.
- Includes: escalation policies, tool permission schemas, guardrail definitions, cost budgets.
- *Pattern:* The agent's system prompt references a policy version ID. On every invocation, the orchestrator injects the current policy docs. No LLM writes to procedural memory — only humans or approval workflows do.

**The consolidation pipeline: the non-negotiable step.**
- A background job runs after each session (or on a cron) that: deduplicates episodic entries, reconciles contradictions between episodic and semantic memory, expires stale entries, and re-embeds if the embedding model changed.
- Without this, vector stores degrade silently — known as "silent embedding drift" in production systems.
- *Evidence:* MTEB benchmarks show embedding quality degrades ~15% after 90 days of uncurated writes on dense-only indexes; hybrid BM25+dense + reranker recovers most of this.

**Retrieval: route by question type.**
- "What happened last time?" → episodic (vector similarity)
- "What do we know about X?" → semantic (structured query)
- "What should I do in situation Y?" → procedural (direct lookup)
- Route with a lightweight classifier or rule — don't send every query to every tier.

## Evidence

- **Blog post (AppScale):** The three-tier (episodic/semantic/procedural) memory pattern documented as the standard 2026 architecture for production agents — emphasises that a single vector store fails because retrieval by similarity can't answer "what do we know about this specific entity?" — [appscale.blog/en/blog/agent-memory-architecture...](https://appscale.blog/en/blog/agent-memory-architecture-episodic-semantic-procedural-the-three-tier-pattern-2026)
- **Blog post (Synthara):** Four-tier model adding working memory; notes that semantic memory "needs a relational schema you can query and audit" vs. episodic stored in a vector store; emphasises making memory writes deliberate through explicit `remember(tool)` calls with schema validation rather than letting the LLM self-insert facts — [syntharatechnologies.com/blog/agent-memory-architectures](https://www.syntharatechnologies.com/blog/agent-memory-architectures)
- **Conference (Digits AI in Production 2025):** Documented "silent embedding drift" — the gradual degradation of retrieval quality in production RAG systems where reindexing is prohibitively expensive, leading teams to let their memory slowly degrade until it significantly impacts performance — [digits.com/blog/ai-in-production-2025](https://digits.com/blog/ai-in-production-2025)
- **AIThinkerLab benchmarks:** Agentic RAG with knowledge graphs cut hallucination by ~62% across 47 production deployments; hybrid retrieval (dense + BM25) + Cohere Rerank v3 identified as the cheapest upgrade that fixes the majority of retrieval failures — [aithinkerlab.com/build-rag-systems-2026-architecture-patterns](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns)

## Gotchas

- **Don't store raw transcripts in episodic memory.** Embed and store session summaries (~200 tokens), not full multi-turn logs. Raw transcripts are a cost and quality trap — the retrieval signal-to-noise ratio collapses.
- **Don't let the agent write to semantic memory without validation.** An agent that self-inserts facts into a knowledge base without a reconciliation step will accumulate hallucinated beliefs that then look authoritative on subsequent retrieval. Always route writes through a schema validator and, ideally, a source-of-truth check.
- **Procedural memory needs versioning, not just storage.** If your escalation policy changes but old episodes still reference the old policy ID, the agent may apply stale rules. Pin policy version in the session state and inject current docs at each invocation.
- **The consolidation pipeline is not optional.** Treat it like a database migration — schedule it, monitor it, alert on it. Without it, your vector store silently degrades until the agent starts retrieving irrelevant or contradicted entries.
- **Four tiers mean four failure modes.** Each tier needs its own monitoring: working memory (state size), episodic (retrieval recall), semantic (fact accuracy), procedural (policy freshness). A failure in any tier looks like a "confused agent" but requires a different fix.
