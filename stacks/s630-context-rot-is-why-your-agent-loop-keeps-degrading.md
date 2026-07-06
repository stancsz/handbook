# S-630 · Context Rot Is Why Your Agent Loop Keeps Degrading

Your agent works fine with 10 tool calls. Then 20. Then it starts making wild mistakes — wrong tools, hallucinated functions, corrupted reasoning chains. You assume it's the model. It's not. It's context rot: the progressive accuracy degradation LLMs experience as context length grows. And in agentic systems where each step feeds the next, it compounds catastrophically.

## Forces

- **Long contexts ≠ better reasoning.** Expanding context windows past ~4K tokens causes accuracy to drop, not rise. The model isn't forgetting — it's deprioritizing. Relevant information in the middle of a context gets almost completely ignored.
- **Agent loops amplify the problem.** Each tool result appended to context widens the window. By step 15, your agent is reasoning through a haystack of its own outputs, each a potential hallucination seed.
- **Adding tokens is the team's first instinct, but it's the wrong fix.** RAG over retrieval. More system prompt. Longer instructions. All address symptoms. The real fix is architectural: don't put everything in the context.
- **Single-agent architectures hit a hard ceiling.** A monolithic agent managing 5+ tools or multi-step reasoning over long sessions will eventually degrade to unreliable. This is a fundamental property of transformer attention, not a tuning problem.

## The move

Split the monolithic agent into specialized, context-bounded agents — and use a router or supervisor to coordinate them. Each agent gets a narrow context window and a single responsibility.

- **Bounding context is the core act.** Cap each agent's working context to what it can reliably attend to. For most models, that's 3-5K tokens of active reasoning content. Use semantic memory layers (episodic, procedural, declarative) to externalize what doesn't need to be in the immediate loop.
- **Route before reasoning.** Classify query complexity before deciding whether to invoke a full multi-agent workflow. Simple factual queries bypass the agent loop entirely — direct retrieval only.
- **Design for context eviction, not context accumulation.** Externalize conversation history, intermediate reasoning states, and retrieved documents into a memory store. Agents pull what they need per-step rather than carrying everything.
- **Use hierarchical agents to cap depth.** A supervisor agent decomposes tasks and delegates to specialist agents. Each specialist operates in a bounded context. Only the supervisor holds the cross-agent state.
- **Implement context-aware chunking in RAG layers.** When retrieval is part of the loop, use small overlapping windows with reranking — not large document dumps. The "Lost in the Middle" effect means the position of a retrieved chunk matters as much as its relevance score.
- **Profile your specific model.** The 20-document drop from 75% to 55% is a 2023 Stanford baseline. Model families vary significantly. Run a simple probe: place the same key fact at position 1, 10, and 20 of your context window and measure recall. Use that to set your context cap, not the theoretical window size.

## Evidence

- **Research paper (arXiv/Stanford, 2023):** LLM accuracy drops from 70-75% to 55-60% with just 20 retrieved documents (~4K tokens) — the "Lost in the Middle" effect. Information at positions 1 and 20 is recalled at near-baseline; information at positions 8-14 is nearly invisible. — [arXiv:2307.03172](https://arxiv.org/abs/2307.03172)
- **Engineering blog (Comet, Jan 2026):** 73% performance degradation on reasoning tasks when critical information is buried in long contexts. Industry is responding by shifting from monolithic LLMs to multi-agent systems as a direct architectural counter. — [Comet Blog — Multi-Agent Systems](https://www.comet.com/site/blog/multi-agent-systems)
- **Redis engineering guide (Dec 2025, updated May 2026):** Documents context rot empirically — position 1 yields 75% accuracy, position 10 drops to 55% for the same content. Argues for external memory architecture as the production solution, not context window engineering. — [Redis Blog — Context Rot](https://redis.io/blog/context-rot)
- **Enterprise RAG case studies (aliac.eu, Feb 2026):** Harvey AI achieves 0.2% hallucination rate across 700+ legal clients. Deutsche Telekom handles 2M+ conversations at 89% acceptable answers. Both use bounded-context agent architectures with aggressive retrieval filtering — not monolithic context windows. — [aliac.eu — Agentic RAG in Production](https://aliac.eu/blog/agentic-rag-in-production)

## Gotchas

- **Naive RAG makes context rot worse.** Dumping retrieved chunks into the context window without reranking or size-gating adds noise exactly where the model is most sensitive. Always rank-then-truncate.
- **Memory != context.** Storing conversation history in a vector DB and retrieving it per-step is not the same as having it in the context window. The model still needs selective in-context inclusion — not indiscriminate retrieval.
- **Agent persona bleeding is a context rot symptom.** When your "coder" agent starts generating marketing copy mid-task, it often means earlier context has diluted the task framing. Bounding the context or resetting between task boundaries fixes it.
- **You can't tune your way out of this.** No prompt engineering, temperature setting, or model swap eliminates the attention degradation at scale. The fix is structural — externalize context, specialize agents, cap loop depth.
