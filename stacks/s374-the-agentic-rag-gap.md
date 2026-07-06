# S-374 · The Agentic RAG Gap — Why Multi-Hop Retrieval Breaks Without Self-Check Loops

Your research agent answers a multi-hop legal question. It retrieves 8 chunks, generates a draft, ships the answer. Two days later a customer flags one paragraph as fabricated. The trace shows the agent retrieved 8 chunks, used 6 of them, and invented the seventh fact entirely. No span scored faithfulness. No judge gated the answer. The agent had every framework feature it needed, except the one that would have caught the hallucination: a self-check loop. This is what agentic RAG looks like when the agent layer is bolted onto a classic pipeline without the trace and eval back-end that makes dynamic retrieval trustworthy.

## Forces

- **Agentic RAG multiplies failure modes, not just capability.** Classic RAG has one failure mode: retrieves the wrong chunk. Agentic RAG has failure modes at every hop — wrong query rewrite, wrong routing, wrong synthesis — and each one can compound before the next retrieval corrects it
- **The agent framework provides execution primitives, not correctness guarantees.** LangGraph and CrewAI give you loops, state machines, and tool orchestration. None of them tell you whether the retrieved content actually supports the claim you're about to generate
- **Naive RAG pipelines fail ~40% of retrievals.** Industry benchmarks consistently show single-hop retrieval accuracy well below production thresholds. Agentic RAG compounds this with multi-step reasoning that propagates errors silently
- **The research-to-answer gap is the hardest part.** Agents are great at following chains of reasoning. They are not great at knowing when to stop, when to re-retrieve, and when a synthesis claim isn't backed by any retrieved chunk

## The move

The core technique: treat every agentic RAG pipeline as a **retrieval-verify-generate** loop, not a retrieve-generate loop. The verification step is non-negotiable.

- **Add a faithfulness judge between retrieval and synthesis.** Gate the answer behind a binary: does the retrieved context actually support the key claim? Use a lightweight judge model (not the same model that generated the claim) — this breaks the self-reference loop
- **Implement re-retrieval on failure, not just on initialization.** If the judge fails, rewrite the query and retrieve again. Classic RAG retrieves once. Agentic RAG should retrieve up to N times with different query rewrites before giving up and surfacing uncertainty
- **Use query decomposition as the default for multi-hop questions.** Don't trust a single rewritten query to surface all relevant chunks. Decompose into sub-questions, retrieve independently, then synthesize — this is the strongest structural safeguard against under-retrieval
- **Log every retrieval-to-claim mapping.** The fabricated fact that slips through is always one where the agent used retrieved context to set up the answer but invented the claim from thin air. Annotate which chunks support which generated sentences — this makes post-hoc audit tractable
- **Set step budgets, not just token budgets.** Agentic RAG loops can spin. Define a max-retrieve threshold per query (e.g., 3 rounds) and surface a "could not verify" response rather than a hallucinated one when the budget is exhausted
- **Validate over-retrieval as aggressively as under-retrieval.** More chunks do not mean better answers. Retrieval of 20 chunks that dilute the signal with noise is worse than 5 highly relevant ones. Use a relevance filter or reranker before passing context to the synthesis model

## Evidence

- **Future of AGI blog (2026):** Documented the specific failure scenario — a research agent that retrieves 8 chunks, generates a draft, and ships without a self-check loop. Demonstrated the architectural contrast between classic RAG (1 retrieve → answer) and agentic RAG (dynamic query rewriting, multi-hop reasoning, self-check, re-retrieval on failure). Found that naive pipelines fail ~40% of retrieval attempts without any agentic layer — the agent compounds the error — https://futureagi.com/blog/agentic-rag-systems-2025
- **Lushbinary comparison (2026):** Found that hybrid search (BM25 + dense vectors) is now the retrieval baseline for production RAG, with rerankers (Cohere Rerank, BGE-Reranker) used to filter over-retrieved chunks before synthesis. Also confirmed that agentic RAG typically requires 3–8 LLM calls per query versus 1–2 for classic RAG, making the faithfulness check a cost-justified guardrail — https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide
- **AWS ML Blog / Amazon engineering (Feb 2026):** Reported that traditional LLM eval (black-box outcome testing) is insufficient for agentic systems — Amazon's own evaluation framework for agents built across the organization requires separate assessment of tool selection accuracy, reasoning coherence, memory retrieval quality, and task completion rate. Specifically identified that multi-hop RAG chains need human-in-the-loop evaluation for inter-step consistency because automated metrics fail to catch propagated errors — https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/

## Gotchas

- **Using the same model as judge and synthesizer creates self-referential validation.** The model that generated the claim will rationalize why the claim is correct. Always use a separate judge — either a different model or a structured extraction prompt that forces chunk citation, not synthesis
- **Re-retrieval without query decomposition just re-runs the same bad query.** Teams implement "retry on failure" loops but only re-run the same query. The fix is to decompose the query into multiple sub-queries on retry, not to retrieve more of the same
- **The faithfulness gate adds latency that will be bypassed under deadline pressure.** Bake it as a hard gate in the pipeline, not an optional step. An unchecked answer is worse than a slow one
- **Chunk-level attribution is only useful if chunks are small enough to cite precisely.** Large chunk sizes (1024+ tokens) make it impossible to isolate which specific passage supports a claim. Use 256–512 token chunks with overlap as the practical sweet spot for agentic RAG
