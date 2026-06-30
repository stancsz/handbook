# S-247 · Context Engineering — Controlling What the Agent Sees

The agent loop fails not because the model is wrong, but because the wrong things are in the context window. Context engineering is the discipline of treating context as a first-class engineering artifact — not an afterthought, not a prompt tweak, but a deliberate, measured system for controlling what information the LLM has at every step.

## Forces

- **Token cost and latency scale with context size.** A naive multi-turn agent consuming full conversation history, all retrieved chunks, and expanded system prompts can burn $200+ in API calls before producing a single useful output. The model is rarely the bottleneck — the context is.
- **Context quality compounds faster than model quality.** IBM documented a workflow that consumed 20M tokens and failed. Switching to compressed memory pointers reduced it to 1,234 tokens and succeeded. The orchestration was the only variable.
- **Prompt engineering hit a ceiling; context engineering is what comes next.** Anthropic's engineering blog (Sep 2025) explicitly framed the shift: prompt engineering asks "what words do I use?", context engineering asks "what configuration of context generates the desired behavior?" — a fundamentally different question.
- **Framework abstractions hide context in ways that are hard to debug.** LangGraph, CrewAI, and AutoGen all bundle context construction inside opaque abstractions. The moment you need to audit exactly what the model saw, or inject a human approval gate, or switch embedding models, you're fighting the framework.

## The Move

Context engineering has four concrete levers, validated across Anthropic, Mem0, the 12-Factor Agent practitioner community, and production teams:

- **Scope ruthlessly at retrieval time.** Don't retrieve 20 chunks and stuff them all in. Retrieve 3-5 highly relevant ones, then let the agent request more if needed. Over-retrieval is the dominant cause of context bloat. Teams building agentic RAG now measure reformulation rate — if more than 20% of queries require query reformulation, the retrieval layer is broken, not the agent logic.
- **Structure context as typed layers, not a flat message array.** Anthropic recommends separating system instructions, relevant domain knowledge, past tool call history, current session memory, and output format constraints into distinct, labeled sections. This lets the model reason about each layer independently and lets you version, swap, and audit each independently.
- **Treat memory as a compression problem, not a storage problem.** The goal is not to remember everything — it's to retain the signal and discard the noise. IBM's 20M → 1,234 token case used memory pointers rather than full document summaries. Mem0's framework models this as episodic memory (what happened), semantic memory (what was learned), and working memory (what's active now).
- **Own your prompts as code, not framework config.** Frameworks like LangChain and CrewAI generate system prompts behind the scenes from role/goal descriptors. Production teams that ship reliably write system prompts as versioned strings, write regression tests against them, and audit the exact token count at every LLM call boundary. This is the "own your prompts" principle from the 12-Factor Agent framework — it's the one factor that separates agents that survive production incidents from ones that don't.

## Evidence

- **Anthropic Engineering:** "Effective Context Engineering for AI Agents" (Sep 29, 2025) defines the discipline explicitly, distinguishing it from prompt engineering through four concrete strategies: selective context inclusion, structured context architecture, iterative refinement, and context compression. — [URL](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- **IBM production case:** A workflow consuming 20M tokens that repeatedly failed was fixed by switching to compressed memory pointers, reducing token consumption to 1,234 tokens — the sole variable. Documented in the "12 Factor Agent" framework analysis. — [URL](https://tianpan.co/zh/blog/2026-01-26-12-factor-agents-production-ai)
- **Mem0 practitioner survey:** "Most agent failures aren't model failures — they're context failures. The underlying LLM often works fine; the problem lies in the information being fed to it." Corroborated by HN discussion on "The new skill in AI is not prompting, it's context engineering" (Mar 2025, ~300 comments). — [URL](https://mem0.ai/blog/context-engineering-ai-agents-guide)
- **Community validation:** The r/LocalLLaMA "AI Developer Tools Map 2026 Edition" (5 months ago) explicitly calls out context management as a distinct layer requiring dedicated tooling, separating it from orchestration and model selection. — [URL](https://www.reddit.com/r/LocalLLaMA/comments/1r47a79)

## Gotchas

- **The 80% ceiling is a context ceiling, not a model ceiling.** If your agent works 80% of the time in testing and fails in production, the gap is almost always unmeasured context — distribution shift, growing history, stale retrieved documents, or unversioned system prompts.
- **Framework-level context hiding makes auditing impossible.** Before debugging a bad agent output, log exactly what the model received at the API level — not what the framework says it sent. They often differ.
- **Context compression must preserve semantic signal.** Naive truncation of old conversation turns removes the causal chain the model needs for multi-step reasoning. Pointer-based approaches (reference IDs + summaries) preserve signal at lower token cost.
- **Measuring reformulation rate is the fastest diagnostic.** Instrument how often the agent re-queries the retrieval layer or asks for clarification. A rate above 20% points to retrieval, not to the agent's reasoning.
