# S-604 · Agents Forget Everything When the Session Ends — Until You Give Them Three-Layer Memory

Stateless agents are fine for one-shot tasks. Once an agent manages ongoing relationships, projects, or workflows, session boundaries become the ceiling on everything else. Every restart discards accumulated context, forcing re-explanation and re-discovered facts. This isn't a UX annoyance — it directly drives the token bloat in S-603 (agents re-load everything each turn) and the trust surface problem in S-602 (no persistent identity means every tool call starts from zero trust).

## Forces

- **Context windows are finite and expensive.** Re-sending full conversation history scales super-linearly with session length. Agents either hit context limits or silently lose older information — both failure modes teams discover in production.
- **Episodic recall vs. structured knowledge are fundamentally different retrieval problems.** Storing everything in a vector DB and retrieving by cosine similarity ignores the difference between "what happened last time" (episodic) and "what is true about this entity" (semantic). Mixing them produces noise.
- **Memory consolidation is an unsolved operational problem.** When do you summarize? What do you delete? Who validates that the compressed memory is accurate? Teams that skip this step watch their vector stores grow without bound until retrieval latency degrades or costs spiral.
- **The tool-calling loop in S-603 is partly a memory problem.** Agents that can't retrieve relevant context from prior steps re-describe the problem on every tool call. Persistent episodic memory collapses the "explain the problem again" overhead.
- **Three databases is three operational burdens.** Episodic (vector), semantic (relational), procedural (fine-tune / few-shot cache) — teams that build all three layers independently end up with three systems to monitor, scale, and debug.

## The Move

Implement a three-layer memory architecture with a unified consolidation pipeline. Each layer handles a distinct retrieval problem; the consolidation process moves information down layers over time.

**Layer 1 — Episodic memory (vector-indexed):** Raw interaction history stored in a vector DB (Qdrant, pgvector, Weaviate). Each session turn is embedded and stored with metadata: timestamp, agent ID, task ID, outcome. Retrieval uses hybrid search (dense + keyword) with a re-ranker, not raw cosine similarity. The retrieval query is itself rewritten by the agent before hitting the vector DB — "what was the user's preference about X?" becomes a richer query than the raw question.

**Layer 2 — Semantic memory (relational):** Structured facts extracted from episodic memory and stored in Postgres/Supabase. Entity tables: user preferences, project state, established agreements, prior decisions with rationale. Semantic memory is queried with SQL or ORM, not vector search. Facts here are higher-confidence than episodic recall — they've been explicitly consolidated. The agent reads this layer when it knows what it's looking for (e.g., "get all constraints for project X") rather than when it needs to explore.

**Layer 3 — Procedural memory (compiled):** Learned patterns preserved as few-shot examples in the prompt cache or as fine-tuned adapter weights. When a task type recurs with consistent structure (e.g., "same data extraction pattern across 40 similar documents"), the agent stops deriving the approach from first principles each time. Compiled into examples or a lightweight adapter. Claude Code uses a three-tier compaction engine: deterministic tool-result clearing before every call, server-side token-threshold cleanup, and LLM summarization as last resort — before the prompt cache warms up.

**Consolidation pipeline (nightly + threshold-triggered):** Episodic memories older than N days that weren't accessed in the last M queries are candidates for summarization. An LLM summarizer extracts facts and stores them in semantic memory. Entries older than O days that weren't elevated are archived or deleted. Monitor: episodic DB size growth rate, semantic DB retrieval hit rate, layer-3 cache effectiveness.

## Evidence

- **Engineering blog:** Persistent agent memory requires three distinct layers — episodic (vector-indexed interaction history for semantic recall), semantic (structured facts and preferences in relational store), procedural (learned patterns preserved via few-shot cache or fine-tuning). LangMem (LangChain, 2025) provides a unified API over all three layers. Memory consolidation — periodically compressing episodic memories into semantic summaries — is essential for managing scale without linear context growth. — [Inductivee, AI Agent Memory Architecture, October 2025](https://inductivee.com/blog/ai-agent-memory-persistence-architecture)
- **Community post:** The two-layer approach — short-term buffer with a message window plus nightly summarization to vectors — maps closely to how production AI coding tools handle this at scale. The most interesting design choice was around cache economics: when the prompt cache is warm, they don't modify messages at all — instead they queue changes until the cache window re-negotiates. — [n8n community, Persistent Memory for AI Agents, April 2026](https://community.n8n.io/t/how-i-solved-persistent-memory-for-ai-agents-in-n8n-dual-layer-postgres-supabase-pgvector-pattern-openclaw-in-n8n/279359)
- **Benchmark/analysis:** RAG pipelines fail 40% of the time at retrieval. Naive chunk-and-embed pipelines are the culprit — splitting at fixed token boundaries breaks paragraphs and destroys document structure. Production RAG requires semantic chunking (split at meaning boundaries, not token counts), hybrid search (dense + keyword), and re-ranking. The same pattern applies to episodic memory retrieval: naive top-K cosine similarity retrieval is wrong by design. — [Lushbinary, RAG Production Guide, April 2026](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)

## Gotchas

- **Don't skip semantic memory and try to solve everything with vectors.** Teams that store structured facts as vector embeddings end up with "my entity has 40 chunks, which is the right one?" — a retrieval problem that structured storage solves by design.
- **Memory consolidation without validation creates hallucinations.** When an LLM summarizes episodic memories into semantic facts, it can introduce errors or drop important details. At minimum, flag consolidated facts as "derived — verify before acting" until confidence is established through repeated successful retrieval.
- **Layer 3 (procedural memory) is the most valuable and the most fragile.** Fine-tuning on agent traces is expensive and slow to iterate. Prompt cache with few-shot examples is cheaper but requires careful curation — bad examples compound rather than help.
- **The consolidation pipeline has a cold-start problem.** New agents have no episodic history to consolidate, so they rely entirely on semantic and procedural memory that doesn't exist yet. Seed semantic memory with explicit onboarding facts; accept that layer 3 becomes useful only after meaningful interaction volume.
