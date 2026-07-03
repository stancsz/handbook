# S-462 · Agentic RAG: From Static Lookup to Agent-Controlled Reasoning Loop

Naive RAG treats every query the same — embed, retrieve top-k, generate. For simple lookups this works. For anything requiring multi-step reasoning, cross-document synthesis, or adaptive retrieval, it silently fails on roughly 40% of enterprise queries. Agentic RAG embeds a planning agent inside the retrieval pipeline that decides what to retrieve, how, and when — and self-corrects when the first attempt misses.

## Forces

- **Retrieval quality sets the ceiling, not the model.** A smarter model just hallucinates more confidently from wrong context. The bottleneck is consistently at the retrieval step, not generation.
- **Naive RAG's rigidity is its fatal flaw.** Fixed top-k retrieval with no routing, no re-ranking, no self-correction means complex multi-hop questions fall through the cracks. The agent cannot recover from a bad initial retrieval.
- **Token budgets force architectural choices.** Embedding everything and stuffing it in the prompt doesn't scale. Teams hit context limits at ~50K tokens and must route intelligently — which requires an agent, not a rule.
- **Evaluating retrieval is harder than evaluating generation.** RAGAS, LLM-as-judge, and hit-rate metrics all have noise. Observability on the retrieval step specifically is where most teams are blindest.

## The move

The pattern that works in production: a **routing agent** sits at the top of the retrieval pipeline, assesses query complexity, and routes to the appropriate retrieval strategy. Below that, a **re-triever agent** executes the plan, evaluates whether results are relevant, and triggers re-retrieval or query reformulation if confidence is low.

### Concrete implementation layers

- **Query routing by complexity.** Simple factual lookups → direct vector search. Multi-hop questions → decompose into sub-queries, retrieve for each, synthesize. Ambiguous queries → HyDE (generate hypothetical document, embed that, retrieve against it).
- **Hybrid search as baseline.** Combine BM25 (keyword matching) with dense vector search. Pure vector search misses exact matches on proper nouns, codes, and domain-specific terminology. BM25 handles those; vectors handle semantic similarity.
- **Cross-encoder re-ranking.** After initial retrieval (top-20), run a cross-encoder to re-rank before feeding context to the generator. Cohere's rerank-endpoint or bge-reranker-base are common open-source choices. This alone can lift precision by 15-25% on domain-specific queries.
- **Chunk sizing: 500-1500 tokens, 10-20% overlap.** Smaller chunks (500 tokens) preserve topical coherence. Larger chunks (1500) reduce retrieval calls. Overlap prevents concept boundaries from splitting mid-idea.
- **Agentic self-correction loop.** After retrieval, the agent checks: does the retrieved context actually answer the query? If no — reformulate the query and re-retrieve (up to N attempts). If yes — proceed. This is the core differentiator from naive RAG.
- **GraphRAG for cross-document synthesis.** Microsoft open-sourced GraphRAG in July 2024. It builds a knowledge graph over documents and generates community summaries. Effective for "connect-the-dots" questions spanning multiple sources. Not worth the cost for simple lookups.

## Evidence

- **Knowledge graph RAG cuts hallucination ~62%.** Across 47 production deployments in a May 2026 MLOps Community benchmark, agentic RAG with knowledge graphs reduced hallucination rates by roughly 62% — at the cost of increased latency and orchestration complexity. — [AIThinkerLab](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns/)
- **Naive RAG fails on ~40% of enterprise queries.** Retrieval is the bottleneck, not generation. The embedding model sets the retrieval ceiling: OpenAI's text-embedding-3-large scores 64.6 on MTEB as the safe default, while Qwen3-Embedding-8B tops the multilingual leaderboard at 70.58. — [AIThinkerLab](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns/)
- **Multi-agent inference costs $5-8 per complex task.** 4-agent workflows compound quickly. Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. 57% of organizations already have agents in production, but 40% of agentic AI projects face cancellation risk by 2027 due to cost overruns. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **RAG maturity ladder.** Naive RAG (2022-2023) → Advanced RAG (pre/post retrieval optimization) → Agentic RAG (agent controls the pipeline) → GraphRAG (knowledge graph reasoning). LangGraph and LlamaIndex both support agentic RAG natively. — [aliac.eu](https://aliac.eu/blog/agentic-rag-in-production)

## Gotchas

- **GraphRAG earns its cost only on cross-document "connect-the-dots" questions.** For simple lookups, it adds latency and indexing cost with no benefit. Use it only when queries genuinely require reasoning across document relationships.
- **The embedding model is the retrieval ceiling — you can't out-engineer a bad one.** Teams spend weeks tuning chunking and retrieval parameters while the embedding model produces poor representations. Benchmark candidate models on your actual corpus before committing.
- **Token duplication in multi-agent RAG pipelines.** MetaGPT shows 72% token duplication across agents; CAMEL reaches 86%. When your RAG pipeline has a router agent, a retriever agent, and a synthesizer agent all reading the same context, costs compound fast. Cache aggressively.
- **RAG evals lag behind model evals.** 52% of teams have evaluators, but most measure generation quality, not retrieval quality. Set up retrieval metrics (hit rate, MRR, nDCG on a golden query set) independently from generation evals — they're different failure modes.
- **pgvector is sufficient until ~5-10M vectors.** Teams prematurely adopt Qdrant, Weaviate, or Pinecone. Start with pgvector inside existing Postgres; reach for dedicated vector DBs when filtering demands or scale requirements exceed what it can handle.
