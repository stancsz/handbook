# S-391 · Multi-Agent Coordination — When the Framework Promise Meets Production Reality

You have a complex workflow that exceeds what a single LLM call can reliably handle. You've picked an orchestration framework. The demo works. Then you ship it.

## Forces

- **Frameworks sell on potential; production reveals compounding failure modes.** Multi-agent systems multiply every risk — one agent failing is noise, five agents in a broken coordination loop is an outage
- **The choice of coordination model shapes everything downstream.** A hierarchical design commits you to a manager bottleneck; a peer-to-peer design commits you to emergent chaos you can only observe, not control
- **Context window is the real memory budget.** Naive RAG fails ~40% of the time at retrieval, and LLM failures compound geometrically in multi-agent pipelines — the bottleneck is never where you think it is
- **Cost is non-linear with agent count.** Complex multi-agent tasks run $5–8 each in inference; teams that assumed linear scaling discover the real number only after the first billing cycle

## The Move

The production question is not "which framework" but "which coordination model for this task." Four patterns cover most production use cases — match the pattern to the task, then pick the framework that best implements it.

**1. Hierarchical (manager → workers)** — One agent decomposes tasks and dispatches to specialized workers. Use when: task decomposition is deterministic, you need audit trails, and failures should short-circuit early. CrewAI's default mental model. Used in Opensoul's 6-agent marketing stack (Director → Strategist/Creative/Producer/Growth Marketer/Analyst). Gotcha: the manager becomes a sequential bottleneck — parallelize the workers but keep the manager stateless.

**2. Pipeline (sequential stages)** — Each agent processes output from the previous stage. Use when: order matters, each stage is a transformation, and you need deterministic output at each checkpoint. LangGraph's linear graph mode. Good for data extraction → transformation → validation chains. Gotcha: no recovery mid-pipeline; if stage 3 fails, you restart from scratch.

**3. Orchestrator-worker (dynamic dispatch)** — Central agent decides at runtime which workers to call, in what order, with what context. Use when: task structure is not known upfront, and the orchestrator needs full flexibility. LangGraph's conditional edges implement this natively. Gotcha: orchestrator context grows with each dispatch — watch your token budget carefully.

**4. Peer-to-peer (agent-to-agent conversation)** — Agents communicate directly, negotiating roles and outputs without a central controller. Use when: you want emergent problem-solving and agents can self-organize. Microsoft Agent Framework 1.0 (ex-AutoGen GA April 2026) makes this its primary model. Gotcha: emergent behavior means unpredictable outputs — this pattern is hardest to test and debug.

**Chunking for agent memory (500–1,500 tokens, 10–20% overlap)** — Hybrid search (BM25 + dense vectors) outperforms either alone. Re-rankers help but can degrade quality if applied naively — test against your specific corpus.

**Observability is not optional.** 89% of teams with agents in production have observability; 52% have evals. The gap matters: monitoring tells you something broke, evaluation tells you why quality dropped. LangSmith dominates LangChain-adjacent stacks; Arize Phoenix for self-hosted; OpenTelemetry is the emerging cross-platform standard.

## Evidence

- **HN post (phil, 2025):** "The agent stack is splitting into specialized layers. Sandboxing is clearly becoming its thing. Shuru, E2B, Modal, Firecracker wrappers." — describes stack stratification trend in production deployments — [https://news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)

- **Opensoul Show HN (iamevandrake, 2025):** Production deployment of Paperclip agent orchestration with 6 agents as a "real marketing agency." Each agent runs autonomously on scheduled heartbeats; Director coordinates strategy, then delegates to specialized agents. Reports that the back-end architecture was the hardest part to solve. — [https://news.ycombinator.com/item?id=47336615](https://news.ycombinator.com/item?id=47336615)

- **RaftLabs production study (Nov 2025):** 57.3% of organizations have agents in production; 1,445% surge in multi-agent inquiries (Gartner, Q1 2024 → Q2 2025); 49% cite inference cost as top blocker; 40% of agentic AI projects will be cancelled by 2027 (Gartner). Four patterns cover most production use cases: hierarchical, pipeline, orchestrator-worker, peer-to-peer. — [https://www.raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)

- **Turion.ai framework comparison (2026):** LangGraph = explicit directed graph ("I build the flowchart"), CrewAI = role-based team ("I hire a team"), Microsoft Agent Framework 1.0 = conversational emergence ("I put agents in a room"). LangGraph 1.0 (Oct 2025) with 90M monthly downloads, production deployments at Uber, JP Morgan, BlackRock, Cisco, LinkedIn, Replit. — [https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)

- **1337skills RAG production guide (Jun 2026):** Naive RAG fails at retrieval on ~40% of enterprise queries. Production pipeline requires: hybrid search (BM25 + dense), re-rankers, context-aware chunking. Key insight: "retrieval is the bottleneck, not generation." — [https://1337skills.com/Blog/2026-06-12-production-rag-2026-hybrid-search-reranking-graphrag](https://1337skills.com/Blog/2026-06-12-production-rag-2026-hybrid-search-reranking-graphrag)

- **onseok production RAG (Mar 2026):** Chunking 500–1,500 tokens with 10–20% overlap, BM25 + dense hybrid search with RRF, cross-encoder reranking. Documents the "lost in the middle" problem where LLMs ignore context in the middle of long prompts. — [https://onseok.github.io/posts/building-production-rag-system](https://onseok.github.io/posts/building-production-rag-system)

- **Digits AI in Production conference (Jul 2025):** Teams from Ramp, GitHub, Adobe sharing real deployment experience. Key insight: "most AI products today are basically a chatbot on top of old software." Winning teams re-architect data and control flow, not just layer AI on legacy systems. — [https://digits.com/blog/ai-in-production-2025](https://digits.com/blog/ai-in-production-2025)

- **Imperialis Tech production analysis (Mar 2026):** 28–30% of GenAI projects successfully transition from pilot to production. Multi-agent systems introduce non-determinism, cost unpredictability, and governance gaps that demos never surface. — [https://imperialis.tech/en/blog/multi-agent-systems-langgraph-crewai-autogen-production](https://imperialis.tech/en/blog/multi-agent-systems-langgraph-crewai-autogen-production)

## Gotchas

- **Picking a framework before choosing a coordination model is backwards.** The pattern determines the framework; the framework does not determine the pattern
- **Multi-agent cost compounds non-linearly.** Each hop is an LLM call; a 5-agent hierarchical task might be 15+ LLM calls. Budget for $5–8/task on complex flows, not $0.10
- **Demos prove the happy path; production handles the failure modes.** Agent loops, context overflow, tool call failures, and hallucinated tool schemas all surface only under real traffic
- **Evaluation is where most teams underinvest.** 52% evals vs 89% observability — teams know when things break, not whether they're working correctly
- **The context window is not memory; it's compute.** Treating it as a document store (append everything) leads to degraded performance — use semantic compression, selective retrieval, and tiered memory (episodic / semantic / procedural)
