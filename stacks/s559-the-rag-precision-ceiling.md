# S-559 · The RAG Precision Ceiling — Why Naive Retrieval Fails and Agentic Is Overkill for 60% of Queries

Naive RAG stops working. Teams either give up on retrieval quality or spend 10x to over-engineer with agentic patterns — when the right move is a lightweight router between the two.

## Forces

- Naive RAG tops out at ~70-80% precision on anything non-trivial — multi-entity questions, cross-document reasoning, ambiguous queries
- Agentic RAG reaches 90-95% precision but costs 10x per query and adds 5-15s latency — overkill for the ~60% of production queries that are single-hop
- Most teams default to one retrieval pattern for all queries, either over-paying or under-performing
- LlamaIndex leads on retrieval tooling (Self-RAG, GraphRAG, re-ranking, eval), LangGraph leads on routing/state-machine control — few teams use both together
- The 10-15% precision gap between naive and agentic RAG is often the difference between a production system and a demo

## The move

**Layer retrieval complexity: use a classifier/router to route each query to the cheapest pattern that can answer it.**

### The four retrieval paradigms, in order of cost and precision

| Paradigm | What it does | Precision | Cost/query | Latency |
|----------|-------------|-----------|-----------|---------|
| **Naive RAG** | Single vector search, top-k chunks | ~70-80% | ~$0.001 | <1s |
| **Advanced RAG** | Hybrid search + BM25 + re-ranker (Cohere Rerank) | ~85-90% | ~$0.005 | 2-3s |
| **Agentic RAG** | LLM-controlled retrieval loop, iterates until confident | ~90-95% | $0.01-0.05 | 5-15s |
| **Adaptive RAG** | Classifier routes to the cheapest capable pattern | ~varies | $0.001-0.05 | variable |

### The adaptive routing core

```
query → intent classifier → route

Single-hop, unambiguous?       → Naive RAG (dense + BM25 hybrid, top-10)
Multi-entity / complex join?  → Advanced RAG (hybrid + Cohere Rerank v3)
Ambiguous / low-confidence?   → Agentic RAG (iterate retrieval loop)
Code/data/structured query?   → specialized tool (SQL, API, code search)
```

### The cheapest upgrade that fixes most failures

Before reaching for agentic RAG, most retrieval failures are solved by two additions:

1. **Hybrid search** (dense + sparse/BM25) instead of dense-only — catches exact keyword matches dense embeddings miss
2. **Cohere Rerank v3** as a cross-encoder re-ranker — re-scores the top-20 retrieved chunks against the query, returns top-5

These two changes push naive RAG from ~70% toward ~85% precision at ~5x the cost, not 10x.

### Framework pairing: LlamaIndex for retrieval, LangGraph for orchestration

LlamaIndex has the most mature retrieval stack (chunking strategies, embedding model selection, hybrid search, re-ranking, Self-RAG, GraphRAG — all first-class). LangGraph has the most mature orchestration stack (state machines, checkpointing, conditional branching, LangSmith tracing). Production teams running agentic or adaptive RAG increasingly use both: LlamaIndex as the retrieval engine, LangGraph as the workflow controller.

## Evidence

- **Blog (Jobs By Culture):** Agentic RAG precision of 90-95% comes at 10x the cost of naive RAG — and ~60% of production queries are single-hop requiring only naive retrieval; naive RAG precision ceiling is 70-80% — [Source](https://jobsbyculture.com/blog/agentic-rag-guide-2026)
- **Blog (AiThinkerLab):** "The cheapest upgrades win most: adding hybrid retrieval (dense + BM25) and a reranker like Cohere Rerank v3 fixes the majority of retrieval failures before you touch anything exotic." GraphRAG (Microsoft, open-sourced July 2024) handles multi-hop and global questions where chunk-level retrieval fails — [Source](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns)
- **GitHub (LangGraph):** LangGraph v1.0 (Oct 2025) is "the natural fit for Adaptive RAG where the routing logic is sophisticated and you need full control over the agent loop's state transitions" — checkpointing enables time-travel debug through retrieval iterations — [Source](https://github.com/langchain-ai/langgraph)
- **HN (vers3dynamics):** A "local, multi-agent, customizable stack built for researchers" demonstrates hybrid vector + graph retrieval used in practice for academic corpus queries — [Source](https://news.ycombinator.com/item?id=47279088)
- **Framework comparison (Gheware DevOps):** LlamaIndex has "the most mature tooling for every layer of the retrieval stack: chunking strategies, embedding models, hybrid search, re-ranking, query engines, and RAG evaluation" — LangGraph is "Best for Workflows" with state machine-based agent orchestration and Adaptive RAG support — [Source](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Gotchas

- **Re-ranking before routing is a waste.** Rerankers should sit after the retrieval step, not before routing — applying Cohere Rerank on a naive RAG output is expensive and doesn't fix the root cause of bad retrieval strategy selection
- **Agentic RAG without a confidence threshold loops forever.** The agent needs a stop condition (max iterations, confidence score, or token budget) or it will re-query until it finds something plausible even when the answer isn't in the corpus
- **GraphRAG has a high index cost.** Pre-processing a corpus into entity graphs is expensive and slow — use it selectively for knowledge graphs where relationships matter, not for flat document collections
- **Embedding model selection is often the bottleneck, not the framework.** Teams spend weeks tuning LangGraph workflows when the real issue is using ada-002 embeddings on domain-specific terminology — switching to Cohere Embed v3 or a domain-fine-tuned model often yields more improvement than any architectural change
