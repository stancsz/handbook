# S-542 · Agent Memory Architecture — The Three-Tier Model

Your agent is helpful in a single conversation but useless across sessions. It forgets what it learned yesterday, re-asks the same clarification questions, and starts every interaction from scratch. This is the three-tier memory problem: short-term (context window), session (episodic), and long-term (persistent). Production teams that get this right build agents that improve over time. Those that don't build systems that reset to zero every session.

## Forces

- **Context windows are finite and expensive.** A 200K-token context window sounds large until you're paying for it on every call. Teams routinely burn 60–70% of their context budget on retrieved chunks, leaving little room for working memory, system prompts, and conversation history.
- **Retrieval is not memory.** Vector similarity search finds documents; it doesn't model what the agent has learned, decided, or concluded across interactions. A semantic recall system and a memory system serve different purposes and require different architectures.
- **Memory architecture determines defensibility.** The model is commoditized. The organizational world model — accumulated context, learned preferences, domain-specific reasoning patterns — is what stays. Teams that treat memory as an afterthought cannot compound learning across sessions.
- **Multi-agent memory has coordination costs.** When multiple agents share a memory store, write conflicts, staleness, and inconsistent world views become real failure modes that don't exist in single-agent systems.

## The Move

The three-tier memory model separates concerns by access frequency, latency, and persistence:

### Tier 1 — Short-Term Memory (Working Context)
- Lives in the context window. Zero persistence — erased when the session ends.
- Holds the current task state, active tool outputs, the system prompt, and recent conversation turns.
- **Key move:** Budget your context window explicitly. Reserve 30–40% for the LLM's own reasoning, 30–40% for retrieved context, and the remainder for working memory. If you exceed these ratios, compress or offload before the next call.
- Use structured logging of intermediate steps (tool calls, decisions, tool results) — not just final outputs — so the agent can self-correct mid-loop.

### Tier 2 — Session Memory (Episodic)
- Persists across a conversation thread but resets between sessions.
- Records what the user asked, what the agent concluded, what actions were taken, and the outcome.
- **Key move:** Store episodes as structured JSON events, not raw transcripts. An event log `[{"action": "web_search", "query": "...", "result": "...", "agent_decision": "..."}]` is far more actionable for future sessions than a raw conversation dump.
- Implement session summarization: after every 10–15 turns, compress the thread into a brief summary and discard the full transcript. This caps memory growth without losing signal.

### Tier 3 — Long-Term Memory (Persistent Knowledge Store)
- Accumulates across all sessions, users, and interactions. The organizational world model.
- Powers personalization, domain knowledge, learned user preferences, and cross-session reasoning.
- **Key move:** Use a dual-store architecture. Vector database (Qdrant, Pinecone, Weaviate, or pgvector for smaller deployments) for semantic recall. Structured store (PostgreSQL, SQLite) for facts, user profiles, and learned preferences that require transactional consistency.
- Implement **memory gating**: not every interaction should write to LTM. Flag interactions that contain novel information, user corrections, or failed predictions. Write selectively; retrieve broadly.
- Cross-reference agentic RAG patterns: the long-term memory store is the knowledge base that agentic RAG queries. Design the chunking schema with future retrieval intent — organize by concepts, not documents.

### Memory in Multi-Agent Systems
- Each agent maintains its own STM, but shared session/LTM is accessed through a **memory router** — a lightweight service that routes memory read/write requests to the appropriate store.
- Use vector similarity for knowledge retrieval across agents, but implement a **consistency layer** (e.g., a lightweight validation step before writes) to prevent divergent world models between agents.
- Periodically run a **memory reconciliation pass**: one agent (or a dedicated archivist agent) reviews recent LTM writes and flags contradictions or staleness.

### Memory Eviction and Forgetting
- **Time-based eviction:** Archive memories older than 90 days to cold storage unless explicitly flagged as high-value.
- **Importance-based eviction:** Use the LLM or a lightweight classifier to score each memory event for relevance. Prune the bottom 20% quarterly.
- **Context compression:** Before each session, retrieve top-K relevant memories and inject them as a "briefing" — do not inject the entire memory store.

## Evidence

- **Enterprise AI Blog — Modularity:** "Memory systems allow agents to learn from experience. Short-Term Memory (STM) maintains coherence during a single task or session, while Long-Term Memory (LTM) accumulates knowledge across interactions." — [Modularity, Agentic AI Architecture: Patterns That Hold Up in Production](https://www.modgility.com/blog/agentic-ai-architecture), September 2025
- **Aaliac / Enterprise Survey — Production Metrics:** Harvey AI achieves a 0.2% hallucination rate across 700+ legal clients in 45 countries by combining structured legal memory with agentic RAG. Deutsche Telekom handles 2M+ conversations per month at an 89% acceptable answer rate using a tiered memory architecture for customer support. — [Aaliac, Agentic RAG in Production: Patterns & Enterprise Guide](https://aliac.eu/blog/agentic-rag-in-production), 2025
- **Amazon ML Blog — Multi-Agent Memory Evaluation:** "Since 2025, there have been thousands of agents built across Amazon organizations. In multi-agent systems evaluation, HITL becomes critical because of the increased complexity and potential for unexpected emergent behaviors." Memory consistency across agents is cited as a primary evaluation challenge requiring human oversight. — [AWS Machine Learning Blog, Evaluating AI Agents: Real-World Lessons from Building Agentic Systems at Amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon), 2025
- **Deployment Guide — Cost Context:** VPS/Docker deployments ($10–30/month) support a full three-tier memory architecture with local vector DB and PostgreSQL. Serverless (Lambda/Cloud Run, $1–50/month) can run stateless agents but struggles with persistent LTM due to cold starts and ephemeral storage. — [Paxrel, How to Deploy an AI Agent to Production](https://paxrel.com/blog-ai-agent-deployment), March 2026

## Gotchas

- **Don't store everything.** The most common mistake is writing every interaction to long-term memory. This creates a bloated, expensive-to-query store that degrades retrieval quality. Gate writes with a relevance filter.
- **Vector DB ≠ memory system.** A vector store answers "what documents are semantically similar?" A memory system answers "what has this agent learned about this user, domain, or problem?" They serve different queries and should be queried differently.
- **Context compression is not free.** Compressing a 15-turn conversation into a useful summary requires the LLM to make judgment calls about what matters. Test compression quality — summaries that lose critical context are worse than no summaries.
- **Multi-agent memory consistency is hard.** If Agent A writes a user preference to LTM and Agent B reads a stale version, the user experiences the agent as forgetful or contradictory. Implement write timestamps and lightweight invalidation for shared memory reads.
- **Memory GDPR and the right to erasure.** Long-term memory stores that contain user data must support deletion. Architect for it from day one — a memory store that can't forget is a liability under GDPR Article 17 and EU AI Act Article 12.
