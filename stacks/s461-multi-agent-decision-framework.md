# S-461 · Multi-Agent Architecture: The Split-or-Stay Decision

Most teams either over-fragment (an agent per step) or under-fragment (one agent does everything badly). The decision of when to actually split work across agents is non-obvious, and the wrong call is expensive either way.

## Forces

- **Agents are cheap to create, expensive to coordinate.** Adding a second agent takes minutes. Managing context handoffs, shared state, and failure boundaries between them takes weeks.
- **Framework ergonomics push you toward fragmentation.** CrewAI's role-based model makes creating agents feel like a design pattern, not an engineering decision. LangGraph makes splitting a deliberate state-machine choice.
- **The "reusable specialist agent" trap.** You think you'll build a ResearchAgent that gets reused everywhere. In practice, every caller wants it slightly different, and you end up with configuration sprawl.
- **Single-agent tool bloat is equally painful.** An agent with 40 tools spends most of its token budget describing options to itself before taking action.
- **Context window limits create pressure in both directions.** Splitting agents can reduce per-agent context pressure, but shared-memory handoffs can negate the savings entirely.

## The Move

**Start with one agent. Split only when one of these conditions is true:**

- The subtask needs a **different domain of expertise** (different system prompt, different toolset, different LLM tier)
- The subtask needs **different governance rules or access controls** than the parent
- The subtask is **genuinely reusable** across multiple parent agents (a "service agent" pattern)
- The subtask needs to **run in parallel** with other work — concurrency is the clearest signal to split

**If none of those apply, use a simple inline function or a separate function within the same agent.**

### Coordination patterns — pick one per architecture:

- **Hierarchical**: Central orchestrator dispatches to specialist agents, collects results. Best when one agent "owns" the goal and others are tools. Use LangGraph's `StateGraph` with conditional edges.
- **Peer-to-peer**: Agents negotiate tasks among themselves. Best for collaborative tasks (code review + testing + deployment) where no single orchestrator makes sense. Harder to debug.
- **Hybrid**: Orchestrator handles routing; agents handle execution. The most common production pattern — it combines the clarity of hierarchy with the flexibility of specialization.

### When to use agentic RAG vs. classic RAG:

| Situation | Pattern |
|-----------|---------|
| FAQ, single-doc lookup | Classic RAG (1 retrieve, 1 generation) |
| Multi-hop questions, ambiguous queries | Agentic RAG (sub-query decomposition, re-retrieval loop) |
| Compliance / research requiring self-check | Agentic RAG with faithfulness judge gating the answer |

Agentic RAG typically runs 3–8 LLM calls + 2–6 retrieves per turn vs. classic's 1+1. Cost is justified only when question complexity demands it.

## Evidence

- **Framework comparison (2026):** LangGraph leads production adoption with 90K+ GitHub stars, durable checkpointing, and time-travel debugging. CrewAI has 47.8K stars and is favored for prototyping speed. Microsoft deprecated AutoGen in favor of a unified Agent Framework (GA planned Q1 2026). Recommendation: "Default to LangGraph unless you have strong reasons not to — the steeper learning curve prevents painful rewrites later." — [Gheware DevOps Blog, Jan 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **MCP adoption (2026):** 10K+ active public MCP servers, 15,926 GitHub repos with the `mcp-server` topic, 97M+ monthly SDK downloads cited by Anthropic. Enterprise production adoption is **41%** (verified, per Stacklok's 2026 software survey — replacing an earlier unsourced "78%" claim). The MCP registry now holds 9,652 unique server/version records. — [Digital Applied, Apr 2026](https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol)
- **When NOT to split agents:** "Don't create a separate agent for every subtask… A simple inline agent might handle the job well while also being simpler than a full connected agent. Separate agents introduce overhead. There is a slightly longer execution time due to context switching, and complexity in maintaining multiple agents. So use them judiciously." — [Microsoft Learn, Multi-Agent Orchestration Patterns](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/multi-agent-patterns)
- **Multi-agent collaboration patterns:** Three dominant models — hierarchical (central orchestrator), peer-to-peer (agents negotiate), and hybrid. Key benefits of splitting: specialization (focused prompts/tools), parallelism (independent subtasks simultaneously), modularity (agents updated independently), robustness (failure isolated). — [TURION.AI, Dec 2024](https://turion.ai/blog/multi-agent-collaboration-patterns)

## Gotchas

- **Context handoffs can negate the savings of splitting.** If you're passing full conversation history between agents, you haven't reduced context pressure — you've added serialization overhead.
- **"Reusable specialist agents" rarely stay reusable.** Every caller wants a different system prompt or toolset. Build agents for specific workflows, not generic roles.
- **Peer-to-peer is seductive but hard to debug.** Without a clear orchestration root, tracing a failure through a multi-agent conversation is painful. Default to hierarchy unless peer collaboration genuinely adds value.
- **Agentic RAG's loop behavior needs explicit budget limits.** Without token budgets or iteration caps, multi-hop retrieval can loop for 47 minutes and 2.3M tokens before hitting a stop condition — a documented $3,400 incident. — [ToLearn Blog, 2025](https://tolearn.blog/blog/ai-agents-production-guide)
