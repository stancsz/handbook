# S-305 · Multi-Agent Orchestration: Who Runs Next

Every multi-agent system has the same four problems at runtime: who should act, what should they see, how do you checkpoint state, and when do you stop. These sound trivial. They aren't. Getting them wrong creates infinite loops, cost explosions, incoherent outputs, and agents that quietly give up. Getting them right is the difference between a demo and a product.

## Forces

- **Including every agent in every request scales cost and latency linearly** — a 6-agent system that calls all agents on every request uses 4–6× more tokens than a targeted approach, and performance degrades as irrelevant context buries signal.
- **Context ordering is non-trivial.** Models pay disproportionate attention to the beginning and end of context windows; putting the wrong thing first makes the whole run go sideways.
- **Tool description quality is the bottleneck.** 89.8% of MCP tool descriptions have unstated limitations, 89.3% lack usage guidelines, and 84.3% have opaque parameters — meaning agents pick the wrong tool even when the right one exists.
- **The 88% failure rate for agent projects reaching production** means orchestration choices that seem reasonable in a notebook often fail under real load.

## The Move

Four patterns that production teams use to answer "who runs next" reliably:

**1. LLM-based agent routing (semantic routing).** Use a lightweight model (or a classification prompt against the current state) to predict which agents are relevant before invoking any. Microsoft's ISE team documented this for an e-commerce voice assistant handling order tracking, returns, recommendations, and FAQs — routing reduced unnecessary agent invocations by targeting only the relevant domain. This beats rule-based routing because new agents can be added without updating if/else chains.

**2. Hierarchical orchestration with a director agent.** Opensoul's marketing stack uses a Director agent that coordinates Strategist, Creative, Producer, Growth Marketer, and Analyst — each on scheduled heartbeats, each with a defined work queue. The director handles strategy and delegation; specialist agents handle execution. This mirrors how human organizations work and prevents the "every agent talks to every other agent" mesh problem.

**3. Context assembly pipeline at inference time.** Production systems assemble five layers dynamically: (1) system instructions, (2) retrieved knowledge (RAG output, filtered), (3) persistent memory (episodic + semantic), (4) compressed conversation history, (5) tool definitions. The order matters — system instructions and task-relevant context belong at the top, not buried in the middle where models degrade up to 73% on retrieval.

**4. Termination with budget caps and escalation paths.** Every framework handles this differently. LangGraph's `interrupts` and `commands` give explicit control; CrewAI's process modes (Sequential, Hierarchical, Consensus) encode expectations. AWS/Amazon's evaluation framework emphasizes that human-in-the-loop (HITL) remains critical for production — particularly for assessing inter-agent communication coherence and conflict resolution that automated metrics can't capture.

**Framework decision guide** (cross-referenced from Gheware, Humaineeti, LangChain docs):

| Need | Framework | Why |
|---|---|---|
| Fine-grained state, production stability | LangGraph | Explicit graph state, cycle detection, checkpointing. Uber, LinkedIn, Klarna in prod. v1.0 stable Oct 2025. |
| Fast prototype to working multi-agent | CrewAI | Role-based model is intuitive. Teams reach working prototype in hours. 60% of users are Fortune 500 exploration. |
| Azure ecosystem / enterprise Microsoft shop | AutoGen → MS Agent Framework | In maintenance mode; GA of consolidated MS Agent Framework planned Q1 2026. |
| Custom state machine, no framework overhead | OpenAI Agents SDK | Minimal abstractions. Fine-grained control at the cost of building your own checkpointing. |
| Google Cloud integration | Google ADK | Designed for Vertex AI ecosystem. Relatively new compared to others. |

## Evidence

- **HN Show HN:** Opensoul (Paperclip-based) ships 6-agent marketing agency with Director coordinating 5 specialists on scheduled heartbeats — [news.ycombinator.com/item?id=47336615](https://news.ycombinator.com/item?id=47336615)
- **Microsoft ISE:** e-commerce multi-agent case study — routing reduced unnecessary agent invocations; accurate agent selection identified as the first core requirement for production-scale systems — [devblogs.microsoft.com/ise/multi-agent-systems-at-scale](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale)
- **AWS ML Blog:** Amazon's agentic evaluation framework — HITL critical for multi-agent because automated metrics fail to capture coordination failures, conflict resolution, and inter-agent communication coherence — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Tian Pan blog:** 88% of AI agent projects never reach production; context ordering (not just context length) is the critical variable — [tianpan.co/blog/2025-10-23-ai-agent-architecture-production](https://tianpan.co/blog/2025-10-23-ai-agent-architecture-production)
- **Comet ML:** Long context degrades up to 73% on middle retrieval; distributed context management across focused agents outperforms monolithic context stuffing — [comet.com/site/blog/multi-agent-systems](https://www.comet.com/site/blog/multi-agent-systems)
- **Gheware DevOps:** LangGraph (35k stars, Uber/LinkedIn/Klarna), CrewAI (20k stars), AutoGen (30k stars, maintenance) — [devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026)
- **Humaineeti:** AutoGen consolidating into AG2; Google ADK and OpenAI Agents SDK now worth knowing alongside the older three — [humaineeti.ai/resources/multi-agent-orchestration-frameworks](https://www.humaineeti.ai/resources/multi-agent-orchestration-frameworks)

## Gotchas

- **Agent routing and context assembly are often the real bottlenecks, not the LLM choice.** Teams spend weeks evaluating Claude vs. GPT-5 when the actual production problem is that their router calls all 8 agents every time.
- **Tool description quality is invisible until it isn't.** Write MCP tool schemas like API documentation — include limitations, usage guidelines, and parameter semantics. The protocol is solid; the descriptions aren't.
- **AutoGen's maintenance mode is real.** If starting a new project, don't use AutoGen directly — use MS Agent Framework (GA Q1 2026) or LangGraph. Existing AutoGen projects need migration planning.
- **Multi-agent evaluation requires HITL for coordination, not just outputs.** You can unit-test individual agent outputs with LLM-as-judge; you cannot automatically test whether two agents produced contradictory recommendations that got silently reconciled.
