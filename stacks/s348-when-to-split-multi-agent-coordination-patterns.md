# S-348 · When to Split: Multi-Agent Coordination Patterns

The "god prompt" antipattern kills production agents. stuffing every capability into a single prompt works in demos, but context degradation reaches 73% performance drop on reasoning tasks as prompts grow — and guardrails get buried under new messages. Splitting into multiple agents fixes this. But splitting wrong creates a different problem: coordination overhead and failure cascades that are harder to debug than the original god prompt. The decision of when to split, and how, is the central architectural question in multi-agent systems.

## Forces

- **Context is finite and degrades nonlinearly.** Critical information buried in long contexts tanks model performance by up to 73% — the model starts hallucinating because personas bleed together. A single agent handling "coder + legal + marketing" in the same session is not three agents; it's one confused agent.
- **Coordination has real cost.** Every inter-agent handoff is another LLM call, another failure point, another latency hit. The primary engineering challenge in multi-agent systems is not individual agent capability — it is the coordination mechanism between agents.
- **Framework choice shapes the coordination pattern.** LangGraph enforces explicit state-machine graphs with full control over transitions. CrewAI enforces role-based agents with built-in handoff logic. AutoGen enforces conversation-based multi-party exchanges. Each pattern is a different tradeoff between flexibility and correctness.
- **Memory architecture determines whether agents share context or remain siloed.** Agents with isolated memories diverge. Agents sharing a blackboard or vector store converge. Most teams get this wrong at first.

## The move

**Rule 1: Split on failure mode, not on task type.** If a single agent produces wrong outputs because context gets crowded, split. If it produces wrong outputs because of a bad prompt, fix the prompt first. Splitting does not fix bad prompting.

**Rule 2: Use sequential orchestration for linear dependencies.** Agent A → Agent B → Agent C. Each agent performs a distinct transformation. Output of one is input of the next. This is the multi-agent equivalent of Unix pipes. Use when: clear step ordering, each step is a distinct transformation, deterministic workflows. Opensoul's marketing stack uses this for its content pipeline: Strategist researches → Creative writes → Producer formats → Analyst measures.

**Rule 3: Use hierarchical orchestration for delegation.** A supervisor agent routes sub-tasks to specialized workers. The supervisor holds the high-level state; workers handle domain-specific execution. Cloudflare's internal stack uses three layers (platform, knowledge, enforcement) for this pattern. Use when: a director/coordinator needs to assign work to specialists, dynamic task routing, varying task complexity.

**Rule 4: Use peer-to-peer for consensus-building.** Agents communicate directly, debate, and synthesize. This is AutoGen's native model. Use when: multiple perspectives are genuinely needed, agents must review each other's work, no single correct answer exists. Cost is highest — every agent-to-agent exchange is an LLM call — so gate this pattern behind real need.

**Rule 5: Route by task complexity, not by habit.** Route simple tasks (classification, extraction, formatting) to small/fast models. Route complex tasks (reasoning, planning, creative) to frontier models. Vincent van Deth's production stack reduced costs 87% using a model-routing decision tree — not by choosing one model and using it everywhere.

**Rule 6: Use shared memory with a blackboard pattern for correlated agents.** Individual episodic memory per agent plus shared vector store. Mem0's three-tier memory architecture (episodic, semantic, procedural) is the production reference. Agents reading each other's context prevents the siloed-agent divergence problem.

## Evidence

- **Comet ML blog:** Multi-Agent Systems architecture post — context degradation hits 73% on reasoning tasks when information is buried in long contexts; three coordination patterns (sequential, hierarchical, peer-to-peer) each fit different workflow types. — https://www.comet.com/site/blog/multi-agent-systems
- **Show HN — Opensoul:** 6-agent marketing agency built on Paperclip, organized as Director → Strategist → Creative → Producer → Growth Marketer → Analyst. Each agent runs autonomously on scheduled heartbeats, checks work queue, delegates to teammates. Demonstrates hierarchical-with-sequential-elements pattern. — https://news.ycombinator.com/item?id=47336615
- **Cloudflare engineering blog:** Internal AI stack uses three-layer hierarchical architecture (platform routing, knowledge context, enforcement). Processed 241B tokens, 3,683 active users, 93% R&D adoption in 11 months. — https://blog.cloudflare.com/internal-ai-engineering-stack
- **GetMaxin:** The primary engineering challenge in multi-agent systems is coordination — communication overhead, failure dependencies, monitoring. Three critical factors: task dependencies, communication overhead, failure propagation. — https://www.getmaxim.ai/articles/best-practices-for-building-production-ready-multi-agent-systems
- **Gheware DevOps AI:** Framework comparison — LangGraph for complex stateful workflows, CrewAI for fast prototypes with role-based agents, AutoGen for multi-party debate/consensus. LangGraph's steeper learning curve prevents painful rewrites 6-12 months in. — https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html
- **Vincent van Deth (AI Architect):** 11 agents, $2,847/month → $370/month (87% reduction) using model routing decision tree — small models for simple tasks, frontier for complex. — https://vincentvandeth.nl/blog/real-cost-ai-agents-production

## Gotchas

- **Don't split for parallelism you don't need.** Parallel agents sound efficient but add coordination overhead. Split for specialization and context management, not for speed.
- **Inter-agent communication is not free.** Every handoff is an LLM call. A 4-agent pipeline where each agent calls the orchestrator plus 2-3 tools can mean 100+ LLM calls per "task." Audit the call graph before you ship.
- **Failure cascades are the silent killer.** If Agent C depends on Agent B which depends on Agent A, a failure in A propagates. Build explicit retry logic and circuit breakers at each handoff boundary.
- **Framework lock-in is real.** LangGraph's state-machine model is explicit but verbose. CrewAI's role-based model is fast to prototype but opinionated. Choose based on where you expect to change, not where you are today.
