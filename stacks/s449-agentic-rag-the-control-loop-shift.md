# S-449 · Agentic RAG: The Control Loop Shift

Naive RAG works fine in demos. Six weeks into production, a user asks a multi-hop question and the system returns a technically correct but contextually wrong answer. Nobody notices for days. The problem isn't the retrieval — it's treating RAG as a pipeline when it should be a control loop.

## Forces

- **Naive RAG fails silently on retrieval** — embedding-based similarity search returns documents that are technically relevant but contextually wrong. Studies from production teams report 40% retrieval failure rates on naive pipelines
- **The LLM-as-orchestrator shift** — once you accept the LLM can decide *when and how* to retrieve, not just *what* to retrieve, the architecture transforms from linear pipeline to adaptive loop
- **Token budgets force specialization** — treating every agent as having a token budget (Planner gets 30%, Retriever 40%, Synthesizer 30%) forces architectural decomposition instead of the single-god-agent antipattern
- **Correction beats retrieval** — adding a relevance grader between retrieval and generation cut hallucination-inducing retrievals by 60–70% in production systems

## The move

The architecture that emerged in 2025–2026 from teams running RAG in production:

- **Split retrieval from generation** — use a separate agent to evaluate relevance scores on retrieved chunks before passing them to the synthesis model. Discard below threshold, re-query with adjusted strategy
- **Planner → Retriever → Grader → Synthesizer** — four distinct agents with explicit token budgets and failure modes at each transition
- **Query analysis before embedding** — route queries to the right retrieval strategy: keyword for short fact lookups, semantic for conceptual questions, hybrid for multi-hop
- **Hybrid search as baseline** — dense (embedding) + sparse (BM25) combined outperforms either alone; cross-encoder reranking at retrieval boundary catches the top-10-but-should-be-top-3 problem
- **Retry with strategy shift** — if relevance score < 0.7 after first retrieval, re-query with modified embedding or different chunk strategy (up to 3 retries)
- **Production evaluation targets** — faithfulness ≥ 0.9, answer relevancy ≥ 0.85, context precision ≥ 0.8 (measured via RAGAS or custom graders)

## Evidence

- **Engineering blog (Falcon LABO, 2026):** Agentic RAG team added a relevance grader as a gate between retrieval and generation, observing 60–70% reduction in hallucination-inducing retrievals. Key insight: "It's not a pipeline, it's a control loop" — each failed retrieval becomes data for the next iteration
  — https://iwajunnews.com/2026/05/19/agentic-rag-multi-agent-orchestration-in-production-what-we-actually-learned-in-2026

- **Data science blog (DevStarsJ, 2026):** Production-grade agentic RAG pipeline using LangGraph orchestration + LlamaIndex Workflows + Docling for document extraction. Notes hybrid chunking (semantic boundary detection) and dual embeddings (BGE-M3 for dense + sparse) as the combination that closes the "silent failure" gap
  — https://datascientists.info/index.php/2026/02/18/building-production-grade-agentic-rag-part-1

- **AI engineering guide (MarsDevs, 2026):** Documents the naive RAG → Corrective RAG → Agentic RAG maturity curve. Reports that 40% of naive RAG pipelines fail at retrieval in production, primarily due to embedding similarity returning contextually wrong documents. Production build cost: $8K–$50K, 3–16 weeks. Also notes MCP becoming the standard retrieval tool interface
  — https://www.marsdevs.com/guides/agentic-rag-2026-guide

## Gotchas

- **Top-k cutoff excludes the right answer** — a document at position 11 in results is lost despite being the correct match; reranking before synthesis is the fix, not expanding k
- **Embedding mismatch destroys retrieval** — if your chunking strategy doesn't respect semantic boundaries (e.g., splitting a HR benefits clause across two chunks), embeddings lose coherence; use semantic-aware chunking, not fixed token windows
- **No evaluation = silent degradation** — without RAGAS or equivalent metrics on faithfulness/answer_relevancy/context_precision, you won't know the system drifted until a user complains
- **Token budgets require enforcement** — letting agents decide their own context windows leads to runaway token costs; assign budgets architecturally, not via system prompts
