# S-314 · Agent Memory Layer Architecture

Agents forget everything between sessions by default. A longer context window does not fix this — it makes it worse by hiding the problem until context rot inflates latency and cost. The memory layer is the architectural component that closes the gap between "stateless model call" and "agent that actually knows you." Choosing the wrong memory architecture early is painful to unwind; choosing the right one depends on understanding what each approach actually stores.

## Forces

- **A bigger context window is not a memory strategy.** Context rot — where signal degrades under noise — gets worse as context grows. Agents that stuff everything into context spend more tokens, burn latency, and still forget across sessions.
- **"Memory" is ambiguous — three different problems hide under one name.** Episodic (what happened in this session), semantic (what does the agent know), and procedural (how does the agent act) memory require different storage and retrieval strategies. Most frameworks conflate them.
- **The memory tool you choose reshapes your entire agent design.** Mem0, Zep, and Letta each imply different agent runtimes, different retrieval semantics, and different trade-offs around latency, cost, and self-hosting.
- **LongMemEval benchmarks are self-reported in most cases.** Real-world temporal retrieval performance varies significantly from benchmark scores — validate against your actual query patterns.

## The Move

Build a tiered memory architecture that separates short-term context, cross-session facts, and knowledge graph reasoning — then pick the right tool for each tier.

**Tier 1 — Session buffer (in-context, zero infra):**
- Use the LLM's native context for the current conversation turn.
- Implement a fixed-size sliding window or priority queue for recent messages.
- No retrieval latency; evict aggressively to prevent context rot.

**Tier 2 — Cross-session memory (persistent, semantic):**
- Mem0 for fastest deployment: auto-extracts facts as key-value + vector entries, integrates with LangChain/LangGraph, AWS Agent SDK. Best for stable user preferences and personalization.
- Zep/Graphiti when temporal reasoning matters: validity windows let you query "what was true on March 1st?" — critical for finance, healthcare, and legal agents where facts change over time. Scores 63.8% on LongMemEval vs Mem0's 49.0% on temporal subtask (Particula benchmark, June 2026).
- Letta when the agent must manage its own memory like an OS: main context as RAM, recall as fast storage, archival as slow storage. The agent decides what to page in and out. Best for long-running autonomous agents (multi-day tasks).

**Tier 3 — Knowledge graph (structured, relational):**
- Cognee for typed knowledge graphs built from documents. Extract → Load into a graph DB (Neo4j, pgvector). Structural edges encode typed relationships — not just semantic similarity.
- Graphiti (Zep's open-source engine) for temporal knowledge graphs with provenance: every fact has a validity window and source trace.

**Retrieval pattern — never raw vector search alone:**
- Use hybrid search (dense vectors + sparse BM25) for recall.
- Add re-ranking (Cohere, BAAI/bge-reranker) for precision.
- Route queries to the appropriate memory tier — not everything needs a vector lookup.
- Implement memory consolidation on a schedule, not on every turn.

**MCP integration as the transport layer:**
- Mem0, Zep, Letta, and SynaBun all expose MCP tools (Mem0: 6 tools; SynaBun: 106 including memory, browser, social, loops; Zep: 5 via wrapper).
- MCP-native tools reduce custom glue code when the memory server must serve multiple agents or Claude Desktop.

## Evidence

- **Primary source — Mem0 YC W24 / $24M Series A (Oct 2025):** 14M+ downloads, 41K+ GitHub stars. Benchmarks updated April 2026 — LoCoMo: 91.6 (new algorithm), LongMemEval: 91.6 vs old 71.4. Token cost per query ~7K tokens, p50 latency 0.88s. — [https://github.com/mem0ai/mem0](https://github.com/mem0ai/mem0)
- **Ask HN — YC W23 engineering lab company (2025):** "Mem0 stores memories, but doesn't learn user patterns. We looked at Mem0, Letta/MemGPT, and similar solutions. They all solve storing facts from conversations — 'user prefers Python.' That's key-value memory with semantic search. Useful, but not what we needed. What we needed was something that learns user behavioral patterns." — [https://news.ycombinator.com/item?id=46891715](https://news.ycombinator.com/item?id=46891715)
- **Primary source — Particula Tech benchmark (June 2026):** Tested Mem0, Zep, Letta, Cognee on LongMemEval. Zep/Graphiti scores 63.8% on temporal reasoning vs Mem0's 49.0% — a 15-point gap that only matters if the agent tracks changing facts. Mem0 wins on stable preferences; Zep wins on temporal context; Letta wins on agent-self-management. — [https://particula.tech/blog/agent-memory-frameworks-tested-mem0-zep-letta-cognee-2026](https://particula.tech/blog/agent-memory-frameworks-tested-mem0-zep-letta-cognee-2026)
- **Show HN — CIPS Stack (2025):** Enterprise memory infrastructure team describes a 5-system approach: CASCADE (6-layer temporal memory with natural decay), PyTorch Memory (GPU-accelerated semantic search, 2,500+ vectors at <2ms on consumer NVIDIA), Hebbian Mind (associative graph where edges strengthen through co-activation), Soul Matrix (pre-retrieval gating at ~270 microseconds), CMM (unified cross-backend search). — [https://news.ycombinator.com/item?id=46896549](https://news.ycombinator.com/item?id=46896549)
- **Show HN — Synrix local memory (2025):** Local-first memory engine using Binary Lattice structure with fixed-size nodes and prefix-semantic addressing. O(k) lookup where k is number of results. No embeddings required — survives restarts. — [https://news.ycombinator.com/item?id=47308108](https://news.ycombinator.com/item?id=47308108)

## Gotchas

- **Do not conflate session context with persistent memory.** Stuffing conversation history into context is not memory — it is expensive, slow, and still resets on each session. Build persistence separately.
- **Mem0 does not track behavioral patterns, only extracted facts.** If your agent needs to learn "this user always abandons step 3 of a flow," Mem0's fact-extraction model will miss it. You need Hebbian/associative graph approaches or custom session analysis.
- **Neo4j is a poor choice for vector-heavy workloads.** HN community reports: slow vector operations, capped at 4K dimensions, no pre-filtering, memory overflows on small datasets. Use Qdrant, Weaviate, or pgvector for vector workloads; Neo4j only for graph traversal. — [https://news.ycombinator.com/item?id=43975423](https://news.ycombinator.com/item?id=43975423)
- **LongMemEval scores are self-reported and benchmark conditions vary.** Mem0's April 2026 self-reported 91.6 on LoCoMo is a different test condition than Particula's independently-run 49.0% for Mem0 on temporal subtask. Compare methodology, not just headline numbers.
- **Memory consolidation is expensive if you do it on every turn.** Schedule consolidation asynchronously, batch writes, and use dirty flags to avoid blocking the agent loop with graph updates.
