# S528 · From Pipeline to Control Loop: Agentic RAG Architecture

You reach for this when naive RAG surfaces confidently wrong answers, or when a single retrieval pass isn't good enough for production-grade accuracy.

## Forces

- Naive retrieval keeps surfacing loosely relevant documents, and the model confidently generates answers grounded in the wrong context
- Adding more retrieved chunks doesn't help past a certain point — you just dilute signal with noise
- Static chunking strategies fail across diverse query types (factual lookup vs. comparative analysis vs. reasoning chains)
- The feedback loop is missing: nothing checks whether retrieved content actually answered the question before generation starts
- Chunking and embedding quality are upstream problems whose failures cascade silently into generation

## The move

Treat RAG as a **feedback control loop**, not a one-shot pipeline. The key move is inserting a relevance grader between retrieval and generation as a hard gate.

- **Insert a relevance grader** between retriever and synthesizer. Score each chunk against the query; only proceed to generation if score exceeds threshold (typically 0.7). This alone cuts hallucination-inducing retrievals by 60–70%.
- **Route by query complexity.** Simple factual queries (under 15 words) route to fast vector search. Complex multi-concept queries route to hybrid retrieval (vector + BM25 keyword) with optional graph traversal.
- **Retry with strategy shift on low relevance.** If the grader scores below threshold, loop back to the retriever with a modified query strategy — expanded synonyms, different embedding model, or BM25 fallback — rather than generating from bad context.
- **Allocate token budgets per agent role.** Planner: 30%, Retriever: 20%, Synthesizer: 50% of the per-query budget. This forces the system to stop retrieving and start synthesizing, rather than infinite retrieval loops.
- **Validate output against retrieved context.** After generation, run a lightweight faithfulness check: does the answer stay grounded in the top-ranked chunks? Flag mismatches for review or retry.
- **Use query classification upstream.** Classify the query type (factual, comparative, procedural, opinion) before retrieval starts. Route to domain-specific chunking strategies and retrieval pipelines accordingly.

## Evidence

- **Engineering blog (ふぁるこんLABO, 2026):** Naive retrieval kept surfacing loosely relevant documents. Adding a relevance grader between retrieval and generation dropped hallucination-inducing retrievals by 60–70%. Treating RAG as a control loop — routing based on query complexity and retrying on low relevance — became the production default. — [Agentic RAG & Multi-Agent Orchestration in Production](https://iwajunnews.com/2026/05/19/agentic-rag-multi-agent-orchestration-in-production-what-we-actually-learned-in-2026)
- **Industry analysis (RaftLabs, Nov 2025):** 1,445% surge in multi-agent system inquiries (Gartner Q1 2024 → Q2 2025). 57% of organizations already have agents in production (LangChain survey, 1,300+ professionals). The shift from naive RAG to agentic RAG tracks the broader move from linear pipelines to graph-based control loops. — [Multi-Agent Systems: Architecture Patterns for Production AI](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Research signal (Comet, Jan 2026):** When critical information gets buried in the middle of long contexts, model reasoning performance degrades by as much as 73%. Relevance grading + selective retrieval solves this by surfacing only high-signal chunks rather than flooding the context window. — [Multi-Agent Systems: Architecture, Patterns, and Production Design](https://www.comet.com/site/blog/multi-agent-systems/)

## Gotchas

- Relevance grading itself uses an LLM call — it adds latency and cost. Budget it in: a cheap grader model (e.g., a small classifier) often beats a frontier model for pass/fail decisions.
- Token budgets per agent role are easy to misconfigure. Set them too tight and the synthesizer truncates answers; too loose and the retriever loops forever.
- Query classification models drift — re-evaluate routing accuracy quarterly or when your query distribution changes.
- Faithfulness checks post-generation catch problems but don't fix root causes upstream. Invest in chunk quality before you invest in downstream validation.
- The retry-with-strategy-shift loop can theoretically run forever. Hard-cap retries (3 is common) and fall back to "I couldn't find enough relevant context" rather than generating.
