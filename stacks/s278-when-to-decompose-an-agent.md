# S-278 · When to Decompose an Agent

A single monolithic agent with a fat system prompt and a pile of tools feels like the pragmatic starting point. It usually is — until it isn't. The decomposition decision is not about complexity tolerance; it's about failure modes that emerge predictably past specific thresholds.

## Forces

- **Context burial is not a soft problem.** When critical information lands in the middle of a long context, model reasoning degrades by up to 73% — regardless of context window size. Safety guardrails get displaced. Personas bleed. Hallucinations spike.
- **More tools per agent = worse tool selection.** Each additional tool dilutes the signal-to-noise ratio in the prompt. An agent managing 15 tools makes more tool-calling errors than three agents managing five each.
- **Non-determinism compounds exponentially in single-agent loops.** Every LLM call introduces variance. A 5-step single-agent pipeline multiplies that variance five times over — versus compartmentalized agents where failures stay contained.
- **Cost and latency scale linearly in single-agent loops.** Total latency = sum of all steps. Multi-agent architectures allow concurrency where tasks are independent.
- **The right reason to split is not "it's complex."** Complexity alone is managed with better prompting. The right reason is **domain boundary** — different knowledge, different tools, different governance, or different reuse potential.

## The move

Decompose when at least one of these conditions is true:

- **The agent needs fundamentally different knowledge bases.** A coding agent and a legal-review agent sharing one context is an information-interference problem, not a prompting problem.
- **Tool sets don't share a domain.** If half the tools are for filesystem operations and half are for CRM queries, split them. Ambiguous tool routing is the primary source of silent failures in production.
- **Different governance applies.** Access controls, audit requirements, and compliance rules vary by domain. An agent handling PII data should not share the same execution context as one querying public APIs.
- **The workflow has reusable subtasks.** If the same subtask appears across multiple parent agents, it should be its own agent — not copied into each parent's prompt.
- **Context exceeds ~30K tokens of working memory.** Not the hard limit — the working-memory threshold where performance on the primary task measurably degrades.

**The decomposition framework (from Microsoft Copilot Studio guidance, verified against multiple practitioner sources):**

```
Split into a separate agent IF the subtask:
  1. Is complex enough to need its own suite of tools OR knowledge
  2. Requires different governance rules or access controls
  3. Can be reused across multiple parent agents

Otherwise: use an inline agent (simpler, less overhead)
```

**Practical split heuristic (from multi-agent practitioners, 2025-2026):**

| Signal | Action |
|--------|--------|
| >10 tools in one agent | Consider splitting by domain |
| >30K tokens intermediate context | Compartmentalize the longest branch |
| Agent does "everything" | Identify the 2-3 distinct domains, split first |
| Tool-calling error rate >5% | Likely too many tools — split and route |
| Two personas in one system prompt | Split immediately — persona bleed is structural |

## Evidence

- **Google internal benchmarks:** Distributed multi-agent architecture cut processing time from 1 hour to 10 minutes — a **6× speedup** — on tasks that previously required a single monolithic agent. Orchestration topology was more impactful than model selection. — [macgpu.com multi-agent production guide](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html), June 2026
- **Comet.ml research synthesis:** Performance on reasoning tasks degrades by up to **73%** when critical information is buried in the middle of long contexts. Safety guardrails get displaced, and persona bleeding causes cross-domain hallucinations (e.g., hallucinating libraries that don't exist because a "coder" persona inherits instructions from a "creative writer" persona). — [Comet multi-agent systems blog](https://www.comet.com/site/blog/multi-agent-systems), 2026
- **Microsoft Copilot Studio guidance:** "Don't create a separate agent for every subtask." Separate agents introduce overhead — use them only when the subtask needs its own tools, governance, or reuse potential. Inline agents handle most cases. — [Microsoft Learn multi-agent patterns](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/multi-agent-patterns), 2025
- **AdaptOrch (2026):** Orchestration topology delivers **12–23% gains** on SWE-bench independent of model choice, confirming that how agents are wired matters more than which model powers each one. — [macgpu.com](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html)

## Gotchas

- **Splitting too early adds coordination overhead before you understand the actual boundaries.** Start monolithic, identify the natural fracture lines from production failures, then split.
- **Agents that don't share state cleanly are the #1 source of multi-agent bugs.** Decomposition only helps if inter-agent communication is explicit and typed. Implicit shared context (a la CrewAI) needs refactoring into explicit state annotations.
- **Each new agent boundary is a new failure surface.** More agents means more network calls, more latency, more observability gaps. Decomposition trades one class of failure (context burial) for another (coordination failure). Budget observability investment proportional to agent count.
- **CrewAI → LangGraph migration is non-trivial.** Each CrewAI agent becomes a node; the most labor-intensive part is refactoring implicit shared context into explicit LangGraph state annotations. Plan for this if you're migrating production systems.
