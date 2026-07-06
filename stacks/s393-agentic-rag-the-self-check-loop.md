# S-393 · Agentic RAG — The Self-Check Loop That Classic RAG Forgot to Include

You built a retrieval pipeline, added an LLM, and shipped it. The demo looked great. Then the model invented facts from thin air, nobody caught it, and a customer caught it for you.

## Forces

- **Classic RAG treats every query identically.** A one-shot retrieve-and-generate pipeline has no decision point between "retrieved bad context" and "shipped hallucinated answer"
- **The agentic layer adds latency but also adds a gate.** Each LLM call in a retrieval loop costs tokens — the tradeoff is real but often justified for high-stakes outputs
- **Grader precision drift is silent.** Hallucination rates on real-world RAG are low (0.2% at Harvey AI with 700+ legal clients) but catastrophic in regulated industries — one fabricated legal clause can undo a firm's credibility
- **Production teams confuse "it works in testing" with "it works on hard questions."** Classic RAG handles FAQs well; agentic RAG handles the 20% of queries that are multi-hop, ambiguous, or edge cases

## The Move

Agentic RAG converts the linear retrieve-generate pipeline into a **control loop** with a mandatory self-check gate before output. The canonical five-component loop:

- **Router** — Classify query type. Route simple FAQs to classic retrieval (no overhead). Route multi-hop or ambiguous queries to the full agentic loop
- **Retriever** — Initial retrieval. Use hybrid search (dense + sparse vectors) for recall coverage
- **Grader** — Binary relevance filter: "does this chunk actually support answering the query?" Reject false positives before they reach the generator
- **Generator** — Draft the answer using graded chunks
- **Faithfulness Judge** — The critical gate. Check: does every claim in the generated answer trace back to a retrieved passage? If not, loop back to retrieval or flag for human review

The self-check loop is not optional in production. A research agent retrieved 8 chunks, used 6, and invented a seventh fact entirely — no span scored faithfulness, no judge gated the answer. The agent had every framework feature except the one that would have caught the hallucination.

Production targets: retrieval precision ≥ 70%, generation groundedness ≥ 90%, end-to-end task success ≥ 85%.

## Evidence

- **Blog (Tian Pan, tianpan.co):** 90% of agentic RAG projects failed in production in 2024 — root cause was treating RAG as a "set and forget" embed pipeline rather than a monitored control loop. Every failure traced to a missing evaluation or self-check step
- **Blog (futureagi.com, updated May 2026):** Real production case: a legal research agent retrieved 8 chunks, generated a draft, and shipped. A customer flagged one fabricated paragraph. The trace showed no faithfulness span scored. Fix: add a faithfulness judge that loops back to retrieval or escalates when claims lack source grounding
- **AWS ML Blog (Yunfei Bai et al., Feb 2026):** Amazon built thousands of agents since 2025. Their core lesson: automated metrics alone are insufficient for multi-agent evaluation. HITL (human-in-the-loop) evaluation is critical for assessing inter-agent communication, agent specialization alignment, conflict resolution, and logical consistency — dimensions that automated metrics miss

## Gotchas

- **Over-retrieval is as dangerous as under-retrieval.** More chunks = more noise = more surface area for the model to hallucinate from. The grader is there to filter, not pass everything through
- **Judge drift silently degrades your system.** Grader precision (calibration of the relevance classifier) drifts over time as model versions change. Monitor it with a labeled test set of 100 representative queries run nightly
- **The async message bus is the hidden bottleneck.** In multi-agent CrewAI/LangGraph setups, the retrieval loop can queue messages faster than agents can consume them — p95 latency jumps from 800ms to 12s. Decouple orchestration from execution with a task queue (Celery, Redis, etc.)
- **Context-enforced RAG is the stronger variant** — require the model to cite specific source passages for each claim during generation. Claims without citations get dropped or flagged, rather than evaluated after the fact
- **Semantic caching reduces cost 20–35% on high-repetition workloads** — worthwhile once the system is stable and query patterns are understood, but don't add it before you have the self-check loop working
