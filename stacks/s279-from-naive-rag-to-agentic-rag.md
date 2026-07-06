# S-279 · From Naive RAG to Agentic RAG

Naive RAG works for simple lookup queries — but silently fails for anything with complexity, multi-hop reasoning, or ambiguous intent. Agentic RAG replaces the single-pass retrieve-and-generate loop with an iterative reasoning cycle that self-corrects, and it's the pattern teams are standardizing on in production after watching their first-pass systems give confidently wrong answers.

## Forces

- **Naive RAG treats every query identically.** A "what's our refund policy?" gets the same pipeline as "compare indemnification clauses across all vendor contracts." The simple query gets a perfect answer. The complex one gets a superficial answer the system is equally confident in.
- **72% of enterprise RAG implementations fail or significantly underdeliver in their first year** (aliac.eu, 2026). The failure is usually not the model — it's the static, one-shot retrieval strategy that can't adapt to query complexity.
- **Chunking quality cascades.** Fixed-size chunking without semantic awareness produces retrieval results that look plausible but are contextually wrong. The generator then grounds on wrong chunks and produces wrong answers with high confidence.
- **Single-hop retrieval can't answer multi-hop questions.** "Who approved the Q3 budget and what were their key concerns?" requires two pieces of information that naive RAG retrieves independently without connecting them.

## The Move

Replace the one-shot retrieve → generate pipeline with an **iterative reasoning loop**: retrieve → evaluate → re-retrieve → validate → generate.

- **Query routing.** Classify each query type before retrieval: simple lookup, comparative, multi-hop, or ambiguous. Route simple lookups to fast vector search. Route complex queries to the agentic loop.
- **Query decomposition.** Break complex queries into sub-questions. Retrieve for each sub-question independently, then compose the answers. A "compare X across Y" query decomposes into N+1 retrievals (one per entity, one for comparison criteria).
- **Self-correction on retrieval.** After each retrieve step, evaluate whether the retrieved context actually answers the current sub-question. If similarity scores are below threshold or the content is stale, re-retrieve with a reformulated query. Use a cross-encoder reranker to reorder the top-k results by relevance to the specific question, not just vector similarity.
- **HyDE or query rewriting for ambiguous intent.** When the query is vague, generate a hypothetical ideal document and use it to guide retrieval. This surfaces results a literal keyword or embedding match would miss.
- **Hybrid search as the baseline retrieval layer.** Combine BM25 (keyword/sparse) with dense embeddings (semantic/dense). BM25 handles precise terminology; dense embeddings handle conceptual similarity. Neither alone covers both cases reliably in enterprise document stores.
- **Groundedness guardrail at generation boundary.** Before returning the final answer, run a hallucination check: does the generated answer trace back to the retrieved context? Flag and surface citations for any claim that isn't grounded.

## Evidence

- **Blog post (aliac.eu, 2026):** "Agentic RAG embeds autonomous AI agents into the RAG pipeline that plan, reason, self-correct, and dynamically adapt retrieval strategies based on query complexity." — [aliac.eu/blog/agentic-rag-in-production](https://aliac.eu/blog/agentic-rag-in-production)
- **Research / Practitioner (Andrew Ng via aliac.eu):** Agentic workflows with GPT-3.5 (iterative self-correction, tool use) jumped from 48% to 95.1% on the HumanEval coding benchmark — outperforming GPT-4 zero-shot. "The orchestration matters more than the model." — [aliac.eu/blog/agentic-rag-in-production](https://aliac.eu/blog/agentic-rag-in-production) citing Ng's 2023 paper
- **Gartner (aliac.eu):** Predicts over 40% of agentic AI projects will be canceled by end of 2027 due to escalating costs, unclear ROI, and inadequate risk controls — pointing to the cost of retrofitting production systems that weren't designed with evaluation and retrieval quality in mind from the start.
- **Production guide (futureagi.com, 2026):** "The 2026 default is no longer the 2023 retrieve-once-then-generate pattern. Production stacks combine query rewriting, hybrid search (BM25 plus dense embeddings), a cross-encoder reranker, and a generator that can re-ask the retriever (agentic RAG)." — [futureagi.com/blog/rag-architecture-llm-2025](https://futureagi.com/blog/rag-architecture-llm-2025)

## Gotchas

- **Don't agentic RAG everything from day one.** Query routing means simple lookups take the fast path. Building the full agentic loop for all queries adds latency and cost for cases that don't need it. Route first.
- **Evaluation is not optional.** Without automated groundedness checks and retrieval precision metrics, you won't know when the loop is producing better answers vs. just sounding more confident. Target retrieval precision ≥ 70%, generation groundedness ≥ 90%.
- **Stale knowledge bases are the silent killer.** Agentic RAG still retrieves from the index. If the underlying documents haven't been updated, the agentic loop will confidently compose wrong answers from outdated source material. Date-filter or freshness-score retrieved chunks.
- **Multi-hop adds significant cost.** Each decomposition step is an additional LLM call and retrieval. Budget for 3–5× the cost of naive RAG for complex queries. Set per-query cost caps.
