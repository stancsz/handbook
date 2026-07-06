# S-323 · The Orchestration Framework Decision: Picking the Right Agent Runtime

You've narrowed your use case, defined your agents, and picked your models. Then the real argument starts: LangGraph, CrewAI, AutoGen/AG2, OpenAI Agents SDK, or custom? The choice isn't academic — it determines how fast you iterate, how you debug, and how your system behaves when a single agent starts behaving unexpectedly. The answer is almost entirely about the nature of your control requirements, not the frameworks themselves.

## Forces

- **LangGraph gives you graph semantics but no agent abstractions.** You get fine-grained state control but you build every role, handoff, and memory layer from scratch. Teams underestimate the bootstrap cost until they hit their first non-trivial workflow.
- **CrewAI gives you roles and processes but limits your escape hatches.** The role-based approach maps cleanly to org-chart-style multi-agent teams, but customizing the supervisor logic or injecting non-sequential flows requires fighting the framework's assumptions.
- **The framework wars settled — the runtime question didn't.** By 2026, five frameworks have distinct production footprints. The decision tree is really about control vs. speed, not features vs. features.
- **Untyped handoffs kill more multi-agent workflows than any LLM failure.** Every agent-to-agent boundary needs a validated schema with version numbering — something no framework enforces by default.
- **89% of teams have observability but only 52% have evals.** The framework you pick shapes whether "having evals" is even possible.

## The move

### Pick by control surface, not feature list

| Need | Best fit |
|------|----------|
| Complex state, custom flows, graph semantics | LangGraph |
| Fast build, role-based teams, sequential processes | CrewAI |
| Conversational agents, peer collaboration | AutoGen/AG2 |
| Single consistent vendor, OpenAI-only shop | OpenAI Agents SDK |
| Google's stack, Vertex AI integration | Google ADK |
| Full control, no abstraction, latency-critical | Custom state machine |

### Standardize on three orchestration patterns regardless of framework

1. **Supervisor pattern (most common):** Central orchestrator decomposes tasks and delegates to specialists. Best for bounded workflows with clear handoff logic.
2. **Pipeline pattern:** Sequential agents where each output feeds the next. Best for content generation, review chains, and compliance pipelines.
3. **Peer-to-peer:** Agents negotiate and collaborate without a central controller. Best for open-ended research tasks. Hardest to debug — model the cost explicitly before committing.

### Enforce typed handoffs at every boundary

Every agent-to-agent message should carry a schema: task payload, expected response shape, version number. Untyped handoffs are the top failure mode in multi-agent production systems. This is not a framework concern — it's an engineering discipline concern that applies regardless of which runtime you choose.

### Plan for the evaluation gap

Frameworks don't ship with evals. Build a 4-step eval loop from day one:
1. **Input definition** — define evaluation inputs (offline traces or online with defined inputs/outputs)
2. **Reference generation** — generate reference outputs for evaluation
3. **Metric computation** — run automated metrics against traces
4. **Human feedback** — retain human-in-the-loop (HITL) for subjective quality signals, especially for multi-agent coordination

Teams that skip step 4 pay in debugging time later.

### Treat cost as an architectural constraint

A 4-agent orchestrator-worker workflow costs $5-8 per complex task. Use prompt caching (80-90% input savings on stable system prompts) and plan caching (50% cost, 27% latency) before adding more agents. Design SLOs on P95 latency, not median — P95 inflates 1.6-3.2x over P50.

## Evidence

- **Blog post (Humaineeti):** The five frameworks (LangGraph, CrewAI, AutoGen/AG2, OpenAI Agents SDK, Google ADK) each map to a distinct control philosophy. LangGraph prioritizes graph-state expressiveness; CrewAI prioritizes speed to a working multi-agent team; OpenAI Agents SDK prioritizes tight vendor integration — [humaineeti.ai](https://www.humaineeti.ai/resources/multi-agent-orchestration-frameworks)
- **Blog post (RaftLabs):** Untyped handoffs kill multi-agent workflows faster than any other issue. 89% of teams have observability but only 52% have evals. $5-8 per complex task for 4-agent workflows — [raftlabs.com](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **AWS blog post (Amazon):** Thousands of agents built since 2025. The 4-step eval framework (input definition → reference generation → metric computation → HITL) addresses why automated eval alone is insufficient for multi-agent systems — [aws.amazon.com](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Blog post (Comet):** Context degradation: model reasoning performance drops up to 73% when critical information is buried in long contexts. Persona bleed between agent roles is a real failure mode, not just a prompt engineering concern — [comet.com](https://www.comet.com/site/blog/multi-agent-systems)
- **Blog post (GrowthEngineer.ai):** Real benchmark data across 500 runs, 5 tasks, 6 models. GPT-5-mini at $0.026/task vs Sonnet 4.5 at $0.241/task. Prompt caching delivers 80-90% savings on stable system prompts — [growthengineer.ai](https://growthengineer.ai/blog/ai-agent-cost-benchmarks)
- **HN discussion (Show HN: Opensoul):** Real production example of 6-agent marketing team (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) running on Paperclip orchestration platform with scheduled heartbeats — [news.ycombinator.com](https://news.ycombinator.com/item?id=47336615)

## Gotchas

- **LangGraph's graph semantics sound flexible but create their own complexity.** When you need to add a conditional loop or a parallel branch, you reach for the graph API. For simple sequential flows, that complexity is pure overhead. Start with the simplest pattern that covers your use case.
- **CrewAI's `allow_delegation` flag is the most misunderstood setting.** Setting it to `True` on every agent creates peer-to-peer chaos. Set it to `False` and explicitly wire the flows — you'll have more control and fewer surprise loops.
- **AutoGen is transitioning to AG2 (ag2.ai).** If you're starting a new project, evaluate AG2 directly. If you have an AutoGen codebase, plan the migration path — the Microsoft Agent Framework integration is the future direction.
- **Hybrid search + re-ranking improves retrieval quality but adds latency.** In a production RAG pipeline serving agents, a cross-encoder re-ranker adds 50-200ms. Model this cost against the retrieval accuracy gains — for some domains the latency hurt outweighs the quality improvement.
- **ACL (access control list) filtering must be applied as a pre-filter, not post-filter.** Applying it after retrieval means you pay embedding + search costs on documents the user will never see. Pre-filtering at the database query layer avoids wasted compute.
