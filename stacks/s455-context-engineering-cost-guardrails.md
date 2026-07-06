# S-455 · Context Engineering and Cost Guardrails for Production Agents

The demo works. The production bill doesn't. The gap between a compelling agent demo and a reliable production system isn't a model problem — it's an architecture problem centered on context management and cost control. Teams that treat agent engineering as prompt optimization miss the real work: engineering what the model sees at each step and building circuit breakers before runaway costs become a story.

## Forces

- **Context is a finite resource with real costs.** Models disproportionately attend to the beginning and end of context windows. Verbose tool schemas, irrelevant history, and filler content in the middle degrade reasoning while inflating token counts — a double penalty.
- **Most agent failures are invisible until they are expensive.** A single agent that loops 47 times on an ambiguous query generates 2.3 million tokens before anyone notices. Debugging requires tracing steps, not replaying sessions.
- **Prompt engineering is the wrong frame for production.** Context engineering — dynamically assembling what the model sees at each reasoning step — is the dominant paradigm for teams with agents actually running in production.
- **88% of enterprise agent projects never reach production.** The 12% that do share common architectural patterns around context pipelines, memory separation, and cost containment.

## The Move

**Build a context pipeline, not a prompt.** The production pattern is a five-layer stack assembled dynamically at inference time:

1. **System instructions** — task role and constraints, positioned at the context boundary where models attend most
2. **Retrieved knowledge** — RAG output filtered for relevance before entering the loop, not raw chunks
3. **Persistent memory** — episodic and semantic records separated by purpose (who this user is vs. what happened)
4. **Conversation history** — compressed, not full, with oldest turns summarised or dropped first
5. **Tool definitions** — only the subset relevant to the current task state, not the full schema library

**Layer cost guards on every agent before shipping.** The pattern that prevents runaway spend:

```
class AgentExecutor:
    def __init__(self, max_tokens=50000, max_iterations=5, timeout_seconds=120):
        self.token_budget = max_tokens
        self.iteration_limit = max_iterations
        self.timeout = timeout_seconds
```

Every agent gets a hard token budget, an iteration cap, and a wall-clock timeout. These are not preferences — they are production hygiene.

**Separate ephemeral and persistent memory.** Use Redis with TTL for the active conversation buffer (sub-200ms p95 recall at scale) and a vector store (Pinecone, Qdrant) for long-term semantic memory with metadata indexing. Do not mix them. The conversation buffer handles "what just happened"; the vector store handles "what has happened before with this user or topic."

**Filter at retrieval, not at model.** Relevance scoring and deduplication must happen before context enters the reasoning loop. The perception layer is where you exclude content, not inside the model.

## Evidence

- **Engineering blog (Tian Pan, Oct 2025):** 88% of enterprise AI agent projects never reach production; 95% of generative AI pilots fail or underperform. Of 7,949 shipped agents at one company, ~15% worked. Identifies the five-layer context pipeline as the differentiating pattern for working systems. — [tianpan.co/blog/2025-10-23-ai-agent-architecture-production](https://tianpan.co/blog/2025-10-23-ai-agent-architecture-production)
- **Cost engineering reference (GitHub, HimClix):** Per-action token costs for production agents: a support ticket resolution run costs ~$0.0155 (3,150 input tokens via Sonnet at $3/M + 400 output tokens at $15/M + embedding). Complex research tasks run $0.08–$0.20 per task. Documents real numbers for system design and budget estimation. — [github.com/HimClix/agentic-ai-system-design-primer](https://github.com/HimClix/agentic-ai-system-design-primer/blob/main/resources/cost-engineering/real-world-numbers.md)
- **Production case study (ToLearn Blog, Sep 2025):** A customer service agent burned $3,400 in one incident (47 minutes, 2.3M tokens) from a single ambiguous user query ("all possible product variations"). Same architecture redesigned with circuit breakers and token budgets now handles 1,000+ daily queries for under $50/day. — [tolearn.blog/blog/ai-agents-production-guide](https://tolearn.blog/blog/ai-agents-production-guide)
- **Enterprise eval framework (AWS/Amazon, Feb 2026):** HITL (human-in-the-loop) becomes mandatory for multi-agent evaluation due to emergent behaviors automated metrics miss. Validates inter-agent communication, coordination failure in edge cases, conflict resolution, and logical consistency across agents contributing to a single decision. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

## Gotchas

- **Positioning filler content in the middle of context is not neutral.** Models attend most to context boundaries (start and end). Putting verbose tool schemas or irrelevant history in the middle degrades output quality while burning tokens — the worst possible combination.
- **Conversation history is not memory.** Teams dump full chat logs as "memory" and see context window exhaustion. The correct model: compress history to summaries, maintain a structured scratchpad for working state within a task, and use the vector store for cross-session relevance.
- **Token budgets and iteration limits prevent runaway costs but also prevent legitimate long tasks.** Set budgets based on task type (simple triage: 2,000 token budget; complex research: 50,000), not a single global cap that throttles everything.
- **LangGraph reached v1.0 in October 2025** — signals API stability commitment. LangSmith adds observability cost; the framework itself is MIT-licensed. CrewAI has fastest prototyping curve but less production-grade state management. AutoGen (AG2) is strongest for multi-party conversational reasoning but has the steepest learning curve.
- **Amazon's eval findings confirm:** automated metrics alone cannot capture agent system quality in production. Build evaluation workflows with human reviewers on a sample of outputs before scaling, not after.
