# S-555 · Context Window Degradation: The Silent Agent Failure Mode

Agents fail in ways that look like bad judgment — but the root cause is usually structural: the context window is full of the wrong things, in the wrong order, at the wrong resolution. This is the silent failure mode that doesn't show up in error rates or latency metrics. Teams notice when agents start generating garbage, not when the context window silently stopped being trustworthy.

## Forces

- **Long context degrades reasoning non-linearly** — model accuracy on mid-context information drops by up to 73% regardless of window size; this is the "lost in the middle" phenomenon (Liu et al., arXiv:2307.03172)
- **Agents accumulate junk by default** — every turn adds tokens, and naive implementations append rather than distill; the context grows until it exceeds useful density
- **Memory quality and memory quantity are in tension** — adding more context windows (RAG retrieval, conversation history) increases noise faster than signal if not filtered
- **Persona bleeding is a context contamination problem** — when a "coder" persona's instructions get mixed with a "writer" persona's outputs, it's not a prompt engineering failure; it's a context boundary failure
- **Evaluation infrastructure rarely catches degradation** — standard agent evals use fresh contexts; they don't test whether agents degrade under accumulated context over time

## The move

Manage context as a first-class engineering concern. Treat the context window like memory management in a resource-constrained system — with explicit strategies for what enters, what stays, what gets compressed, and what gets evicted.

**The memory-tier architecture (production pattern):**

- **Working context (always live):** Current task, immediate tool schemas, session-specific instructions. Keep under 20% of model context budget. Explicitly curated, never auto-grown.
- **Episodic memory (retrieval on demand):** Summarized history of past interactions. Not raw conversation logs — distilled summaries with action outcomes. Stored in a vector store (Qdrant, Pinecone) or structured DB. Retrieved when the current task has overlap with a prior session.
- **Semantic memory (slow, high-value):** Learned facts, policies, world-model updates. Not session-dependent. Accessed via RAG or as system prompt constants. Only update when evidence is strong enough; treat it like a database write, not a log append.
- **Procedural memory (immutable at runtime):** Prompt instructions, tool definitions, orchestration logic. Compiled into the agent scaffold, not re-loaded from context.

**Context quality signals to instrument:**

- Track effective context density: tokens used vs. tokens that influenced the output (via attention tracing or ablation probes on recent runs)
- Set context budget alerts: warn at 60% window utilization, escalate at 80%, hard-cut at 90%
- Monitor task-to-context ratio: a 3-step task should not require 80k tokens of context; if it does, something is leaking

**Compression strategies (in order of fidelity):**

1. **Selective truncation:** Drop the oldest turns first — not the most relevant. LLM recency bias means older context has diminishing utility regardless of apparent importance.
2. **Summarization with preservation:** Summarize but preserve function call outcomes, tool responses, and any user-provided constraints. Generic pleasantries compress to nothing.
3. **Hierarchical retrieval:** Instead of dumping full history, store summaries and pull details only when a similarity search hits a relevant episode.
4. **Context window pagination:** Treat long tasks as paginated — complete phase 1, summarize results, start phase 2 with fresh context but carry forward the distilled output.

## Evidence

- **Engineering blog (Comet):** Long context windows cause 73% performance degradation on mid-context information, leading teams to architect around distributed context management rather than expanding window size — https://www.comet.com/site/blog/multi-agent-systems
- **Gartner report (cited by RaftLabs):** 1,445% surge in multi-agent inquiries Q1 2024 → Q2 2025; teams adopting multi-agent patterns are partly solving context window limits through agent decomposition — https://www.raftlabs.com/blog/multi-agent-systems-guide
- **Memori benchmark:** Agent-native memory systems that distil context to 1,294 tokens (5% of full context) achieve 81.95% accuracy vs. full-context retrieval; selective memory outperforms full-context by cost efficiency at 20× — https://www.memorilabs.ai/docs/memori-cloud/benchmark/results
- **Production post (tianpan.co):** Teams using 1M-token context windows as general-purpose RAG replacements report 40% fact miss rates and 45-second latencies — the window size does not solve the retrieval quality problem — https://tianpan.co/blog/2026-04-09-long-context-vs-rag-production-decision-framework
- **HN discussion:** The agent stack is stratifying into specialized layers — sandboxing, orchestration, memory, and tool execution are separating into distinct concerns rather than monolithic frameworks — https://news.ycombinator.com/item?id=47114201

## Gotchas

- **Naive history append** — the most common implementation mistake is `messages.append(new_turn)` without any eviction or summarization policy; this is the direct path to degraded output quality
- **RAG on conversation logs** — retrieving from raw conversation history adds noise, not signal; summaries and action-outcome pairs are the right retrieval targets
- **Expanding context window is not a fix** — Anthropic, OpenAI, and Google all show non-linear degradation inside any window size; bigger windows buy time, not quality
- **Evaluation on fresh context masks degradation** — standard evals run in clean context windows; production agents operate in accumulated context; build eval harnesses that simulate multi-session context accumulation
- **Memory tier coupling** — adding a vector store doesn't solve memory; it adds a retrieval step that introduces its own failure modes (missed queries, noisy results); memory quality requires curation, not just storage
