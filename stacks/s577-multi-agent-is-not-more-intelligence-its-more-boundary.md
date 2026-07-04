# S-577 · Multi-Agent Is Not More Intelligence — It's More Boundary

You have six tools and a coherent task. Someone suggests splitting into two agents. The pitch: "Two specialized agents working together will be smarter." This is the wrong mental model, and it leads most teams into expensive, debugging-hostile systems they didn't need.

Multi-agent architectures don't multiply intelligence. They multiply boundaries. The only valid reasons to split are genuine separation requirements — different access scopes, different tool sets, different models, different rate limits. Everything else is complexity you added for no gain.

## Forces

- **The complexity wall is real but often misdiagnosed.** Single agents degrade predictably: tool selection accuracy drops below 90% with 12+ tools, prompt conflicts emerge when you fix one behavior and break another, and context extension doubles latency. Teams see this and reach for multi-agent as the fix — but the wall often signals a need for better tool design or a simpler task scope, not another agent.
- **Inference costs compound super-linearly.** A 4-agent orchestrator-worker workflow costs $5–8 per complex task vs $0.10–0.50 for a single-agent equivalent. Each agent-to-agent handoff adds another LLM call and another latency tick. The economics only work when the boundaries are real and the parallelization pays off.
- **Untyped handoffs kill more multi-agent projects than the LLM.** Every agent-to-agent boundary is a potential silent failure mode. If the output schema isn't versioned, enforced, and validated, agents pass corrupted or mis-typed data downstream and the whole system fails in a way that's nearly impossible to trace.
- **89% of teams have observability but only 52% have evals.** The observability gap is why multi-agent debugging is guesswork. You can see what agents returned but not whether they were right.
- **Gartner tracked 1,445% surge in multi-agent inquiries** from Q1 2024 to Q2 2025. Adoption is exploding. The failure rate is exploding too — Gartner projects 40% of agentic AI projects at risk of cancellation by 2027.

## The Move

Before splitting, apply the **boundary test**: do you have at least one of these genuine separations?

| Boundary Type | Example | Why It Justifies Split |
|---|---|---|
| **Access scope** | Billing agent needs PCI data; support agent must not | Splits enforce separation at the access layer instead of hoping the model stays restricted |
| **Tool sets** | Code interpreter vs. CRM tools vs. document retrieval | Loading all tools into one agent causes tool selection noise |
| **Model choice** | Claude for reasoning; smaller model for extraction | Different models have different costs and latency profiles |
| **Rate limits** | Third-party API with 100 req/min cap | Dedicated agent can enforce throttling that shared agents can't |
| **Latency budget** | Sub-500ms response required | Parallel agents can shave total wall time |

If none of these apply, build one agent. If you have one genuine boundary, split. If you have three+, you have a real multi-agent system worth the complexity.

**Four coordination patterns cover almost all production cases:**

1. **Supervisor (hierarchical):** One orchestrator delegates to specialized workers. Clean for task decomposition where the supervisor owns the outcome. Bottleneck risk if the supervisor becomes the failure point.

2. **Peer (debate):** Agents work in parallel on the same problem, critique each other, and a judge picks the best output. Best for code review, creative work, and any domain where iteration from disagreement improves quality. Expensive — you're running multiple full workflows.

3. **Market (auction):** A task enters a pool, agents bid on it, one claims it. Best for task queues where work has natural boundaries and agents compete for available tasks. Forces you to build the bidding schema, which is a forced march toward typed handoffs.

4. **Shared-state:** Agents read from and write to a common datastore (vector DB, KV store, Postgres). Best for multi-agent research pipelines where agents find, extract, and accumulate information over time. The risk: state corruption if writes aren't transactional.

**The non-negotiable: typed, versioned handoffs at every boundary.** Define the schema. Version it. Enforce it with a validator before the downstream agent receives it. Silent failures at handoff boundaries are the #1 cause of multi-agent debugging nightmares.

## Evidence

- **Blog (Gravity):** "The intuition that 'more agents will do better than one agent' is wrong more often than it is right. Most production multi-agent systems exist because work has genuine boundaries, not because two LLMs are smarter than one." — [Gravity Fast Blog, 2026-05-21](https://gravity.fast/blog/ai-agent-multi-agent-coordination/)
- **Blog (RaftLabs):** 1,445% surge in multi-agent system inquiries tracked by Gartner (Q1 2024 → Q2 2025); 57% of organizations already running agents in production; 89% have observability but only 52% have evals; inference costs compound to $5–8 per complex task for 4-agent workflows; untyped handoffs identified as the #1 killer of multi-agent projects. — [RaftLabs, 2025-11-20](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Engineering post (onseok):** Documented production RAG + multi-agent system serving results via MCP across thousands of internal documents. Key lesson: hybrid search with Reciprocal Rank Fusion (RRF) handles both keyword precision and semantic breadth, but re-rankers can *hurt* quality if the training distribution doesn't match the retrieval domain. Confirmed MCP as the standard tool-calling interface for agent-to-tool integration. — [onseok, 2026-03-31](https://onseok.github.io/posts/building-production-rag-system)
- **Blog (Netguru):** Recommended Azure OpenAI GPT-4o or o3-mini (reasoning model) for the LLM layer, flexible orchestration via AutoGen, structured context + vector databases for memory. Key finding: most organizations underestimate what it takes to build agents that work in production — the gap between "it works in demo" and "it works under load with bad inputs" is where teams get burned. — [Netguru, 2025](https://www.netguru.com/blog/ai-agent-tech-stack)

## Gotchas

- **Adding agents to fix a bad prompt is the most expensive form of debt.** If a single agent with good prompting can do the task, that's always the right answer. Multi-agent adds debugging surface area proportional to the number of agents times the number of handoffs.
- **The "supervisor sees everything" problem.** In hierarchical patterns, the orchestrator passes the full conversation context to each sub-agent. This means your context costs multiply — not just at the final output but at every delegation. A 5-agent pipeline where the supervisor broadcasts context to each worker can use 5–10x more tokens than the equivalent single-agent approach.
- **Evaluation in multi-agent is under-invested and it shows.** With 89% observability but only 52% evals, most teams can see what happened but can't tell if it was right. Build evals into the pipeline, not as an afterthought — treat every handoff as a point where you could automatically validate the output before passing it downstream.
- **Parallelism is the only thing that makes multi-agent cheaper than sequential single-agent.** If your agents wait on each other, you're paying for the overhead of coordination with no throughput gain. Peer and market patterns only make economic sense when tasks genuinely overlap in time.
