# S-336 · Agentic RAG: When Retrieval Becomes Reasoning

Traditional RAG treats every query the same — chunk, embed, retrieve top-k, generate. It works fine for "what's our refund policy?" and catastrophically for "compare indemnification clauses across all three vendor contracts and flag inconsistencies." Agentic RAG embeds autonomous agents inside the retrieval pipeline itself: the system plans the retrieval strategy, reasons over the results, self-corrects when context is insufficient, and dynamically adapts — making retrieval a reasoning loop, not a lookup.

## Forces

- **Naive RAG is brittle by design.** A fixed retrieve-then-generate pipeline has no mechanism to detect when retrieval fails, when the query requires multi-hop reasoning, or when the retrieved context contradicts itself. It just generates.
- **Query complexity is not uniform.** Simple factual lookups cost 1 retrieval pass. Comparative analysis, synthesis across sources, and ambiguous queries can require 5–10 iterations. A static pipeline over-provisions for simple queries and under-delivers for complex ones.
- **Context quality determines output quality more than model choice.** A European bank's audit system saved EUR 20M+ over 3 years not by switching models but by fixing what it fed the model. Context is where the leverage is.
- **Hallucination is a retrieval problem, not a model problem.** The 0.2% hallucination rate Harvey AI achieves across 700+ legal clients comes from grounding generation in verified retrieved context — not from prompting harder.

## The Move

Embed an agentic loop inside the retrieval pipeline:

- **Query analysis → routing.** Before retrieval, classify the query type: factual lookup, comparison, causal reasoning, or open-ended synthesis. Route each type to a different retrieval strategy (dense vector search, BM25 keyword, hybrid, or graph traversal).
- **Plan-and-decompose.** For multi-hop questions ("compare X across Y and flag Z"), the agent decomposes into sub-queries, retrieves for each independently, then synthesizes. A contract comparison query becomes: retrieve contract A, retrieve contract B, extract indemnification clauses from each, compare, flag inconsistencies.
- **Self-correction loop.** After retrieval, the agent evaluates whether context is sufficient and hallucination risk is low. If not (low relevance score, contradictions, gaps), trigger a second-pass retrieval with modified query or expanded search space.
- **Re-ranking.** After initial vector retrieval, a cross-encoder re-ranker re-scores candidates against the full query intent — not just semantic similarity — pulling the most relevant results to the top before generation.
- **Grounded generation with citation.** Generate with explicit citations to retrieved chunks. Citation enforcement reduces hallucination by forcing the model to anchor output to retrieved evidence.
- **Feedback from generation back to retrieval.** Use generation-side signals (uncertainty markers, citation failures) to refine the next retrieval cycle in long-running workflows.

## Evidence

- **Engineering blog:** Agentic RAG achieves 89% acceptable answer rate at Deutsche Telekom handling 2M+ annual conversations, versus 72% for standard enterprise RAG. — [aliac.eu — Agentic RAG in Production](https://aliac.eu/blog/agentic-rag-in-production)
- **Research study:** Andrew Ng's agentic workflow study shows coding accuracy jumps from 48% (single retrieve-then-generate) to 95.1% when the agent iterates: retrieves, generates partial solution, self-evaluates, re-retrieves missing context. — [aliac.eu — Agentic RAG in Production](https://aliac.eu/blog/agentic-rag-in-production)
- **Legal production:** Harvey AI serves 700+ legal clients with a 0.2% hallucination rate using retrieval-grounded generation. — [aliac.eu — Agentic RAG in Production](https://aliac.eu/blog/agentic-rag-in-production)
- **Comet blog:** Model performance on reasoning tasks degrades up to 73% when critical information is buried in the middle of long contexts — the "Lost in the Middle" problem that agentic RAG mitigates through targeted, multi-pass retrieval. — [Comet — Multi-Agent Systems: Architecture, Patterns, and Production Design](https://www.comet.com/site/blog/multi-agent-systems)

## Gotchas

- **Self-correction loops inflate latency and cost.** A 3-pass agentic RAG pipeline costs 3x more per query than naive RAG. Budget for this in cost engineering; set a hard cap on passes to prevent runaway loops.
- **Re-ranking adds a non-trivial latency step.** Cross-encoder re-ranking is slower than vector similarity search. Use it selectively — only for queries where initial retrieval precision matters (comparative, causal, verification tasks), not for simple lookups.
- **Citation enforcement is not free.** Forcing the model to cite requires prompt engineering and often degrades fluency. Test with your specific model family; Claude and GPT-o3 handle citation constraints better than older models.
- **Hybrid retrieval is table stakes, not optional.** Pure dense vector search misses keyword-exact matches and proper nouns. Production agentic RAG stacks combine dense (semantic) + sparse (BM25) retrieval — Qdrant, Weaviate, and Pinecone all support hybrid modes natively.
