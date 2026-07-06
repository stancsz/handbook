# S-592 · Hybrid Search and Re-ranking: The Engineering Between Naive RAG and Agentic Retrieval

Naive RAG looks correct — it returns results, cosine scores are high, no errors surface — but answer quality is wrong 40% of the time in production. The gap between working demos and working retrieval is almost entirely in the search and ranking layer.

## Forces
- **Dense embeddings silently fail on exact-match queries.** Vector similarity handles semantic similarity but misses exact keywords, codes, IDs, and technical terms that dense models never saw enough of during training.
- **Naive chunking breaks semantic units.** Splitting at arbitrary token boundaries — sentence, paragraph, fixed window — severs code blocks, bullet lists, and cross-references that carry meaning only in context.
- **LLMs ignore the middle of long contexts.** "Lost in the middle" is not a theoretical artifact. Top-k retrieval feeds the highest-ranked chunks first, but relevant context often lives in the middle — and the model downweights it.
- **Re-rankers add latency and cost, but teams apply them blindly.** Cross-encoders improve ranking precision, but they also add a synchronous call that compounds latency and can hurt quality if the initial retrieval is poor.

## The Move
Hybrid search + calibrated re-ranking closes the gap. The pattern: fuse dense and sparse retrieval, then re-rank the fused pool with a cross-encoder before passing to the LLM.

- **Sparse: BM25 (advanced TF-IDF)** handles exact keyword matches, technical identifiers (`ISSUE-1234`), version strings, and acronyms. It ranks by term frequency × inverse document frequency without learning.
- **Dense: embedding model** (e.g., `text-embedding-3-large`, `bge-m3`, or a domain-fine-tuned variant) captures semantic similarity — synonymy, paraphrasing, conceptual overlap.
- **Fusion: Reciprocal Rank Fusion (RRF)** merges ranked lists from both methods into a single pool. Formula: `score(d) = Σ 1/(k + rank_i(d))` where k=60 is the standard damping factor. No training required; handles the geometric mismatch between BM25 and embedding scores.
- **Re-rank: cross-encoder** (e.g., `cross-encoder/ms-marco`) scores each candidate passage against the query using full attention. Takes ~20-40ms per candidate; apply to top-20 fused results, not the full corpus.
- **Context window engineering**: place the most likely answer in the first or last chunk position. Middle-position content is recalled at ~60-70% of edge positions. Use positional bias compensation or aggressive truncation of the middle.
- **Chunking with semantic awareness**: prefer overlap-based chunking with semantic boundaries (code blocks, header hierarchies, table structures) over fixed-token windows. Prepend parent document metadata to each chunk to restore cross-reference context lost by splitting.
- **Evaluate at the retrieval layer**: use RAGAS `faithfulness` and `answer_relevancy` scores, not just end-to-end accuracy. The failure is usually retrieval, not generation.

## Evidence
- **Engineering blog:** Naive RAG fails 40% of the time at retrieval in production — the dominant failure modes are vocabulary mismatch (dense embeddings miss exact keywords), lost-in-the-middle (LLMs downweight middle context), and chunking artifacts (splitting severs semantic units) — [onseok.github.io](https://onseok.github.io/posts/building-production-rag-system), March 2026
- **Technical deep-dive:** Hybrid search combines BM25 (sparse, exact-match) with dense embeddings (semantic similarity) via Reciprocal Rank Fusion, which merges ranked lists without requiring score normalization or re-training — [dasroot.net](https://dasroot.net/posts/2025/12/advanced-rag-techniques-hybrid-search), December 2025
- **Production guide:** RAGAS evaluation at the retrieval layer — not end-to-end — identifies whether failures are in retrieval or generation. Re-rankers improve ranking precision but add latency; initial retrieval quality determines ceiling — [lushbinary.com](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide), April 2026

## Gotchas
- **Re-ranking a bad initial pool makes things worse.** Cross-encoders re-score candidates — they cannot conjure relevant results from an irrelevant pool. Fix the retrieval pool first with hybrid search, then re-rank.
- **BM25's k1 and b parameters need tuning.** Default BM25 (k1=1.5, b=0.75) is rarely optimal. k1 controls term frequency saturation; b controls document length normalization. Tune on your corpus, not defaults.
- **Chunk overlap that ignores semantic boundaries introduces noise.** A 20-token overlap at the middle of a code block or table row creates fragments that confuse the LLM more than they help. Prefer semantic boundary-aware overlap (at section or code-block level) over fixed-token overlap.
- **Dense embedding model drift is invisible.** If you switch embedding models or update chunking strategy, re-index the entire corpus. Old and new vectors live in different geometric spaces — hybrid fusion of mismatched spaces degrades unpredictably.
