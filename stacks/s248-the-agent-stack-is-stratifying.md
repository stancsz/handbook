# S-248 · The Agent Stack Is Stratifying

You reached for LangChain to build your first agent. Now you're rebuilding it because the sandbox layer, the orchestration layer, the tool registry, and the evaluation pipeline all have different defensibility profiles — and bundling them was the wrong call.

## Forces

- **Agents compose multiple risky primitives.** Tool execution, code sandboxing, memory stores, and LLM calls all fail differently. Treating "the agent" as a monolith means a security breach in one layer takes down the trust boundary of the whole system.
- **The orchestration layer is not where you build moat.** LangGraph, CrewAI, and AutoGen are converging on similar APIs. The real differentiation is in tool quality, evaluation infrastructure, and domain-specific memory — not the graph structure.
- **Evaluation breaks before the agent does.** A production agent can fail silently for days — producing plausible outputs that are wrong — because the evaluation loop doesn't exist. This is the most common production failure mode and the least-discussed.
- **Sandboxing emerged as its own discipline.** Code execution for agents is no longer a solved problem. Eight providers now compete (E2B, Modal, Docker, Vercel, Cloudflare, Daytona, Runloop, Blaxel), and the choice materially affects security posture, latency, and cost.

## The move

Design the agent stack as four independent layers with clean interfaces, so each can be replaced or upgraded without touching the others:

- **Layer 1 — Orchestration:** Choose LangGraph for explicit graph-based control, CrewAI for fast role-based prototyping, or Microsoft Agent Framework 1.0 for Azure-coupled enterprise. Default to LangGraph — the steeper learning curve prevents painful rewrites 6–12 months in when graph semantics become necessary.
- **Layer 2 — Tool calling / MCP:** Use Model Context Protocol as the standard interface between agents and tools. MCP reached production-ready status in November 2025 with async operations and server discovery; within four months of launch it was adopted by OpenAI, Microsoft, Google, and Amazon (BCG, April 2025). Every custom tool integration built as a one-off is technical debt — MCP standardizes it.
- **Layer 3 — Code sandboxing:** Treat this as a separate infrastructure concern, not an agent implementation detail. The OpenAI Agents SDK (April 2026) natively supports eight sandbox providers; pick based on your security requirements (credential isolation, network egress control) and latency tolerance, not the orchestration framework.
- **Layer 4 — Evaluation / observability:** Build this before going to production. Amazon's multi-agent evaluation framework (AWS, February 2026) showed that automated metrics alone miss 40–60% of failure modes in multi-agent systems — human-in-the-loop evaluation of trace quality, inter-agent coordination, and faithfulness to retrieved context is non-negotiable for regulated domains.

## Evidence

- **AWS Blog (Feb 2026):** Amazon's real-world evaluation framework for thousands of agents built since 2025 — automated trace analysis + HITL review, four-step evaluation workflow, emphasis on decomposing failures by layer. — https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/
- **Turion.ai (May 2026):** LangGraph vs CrewAI vs Microsoft Agent Framework — three distinct philosophies: graph state machines, role-based teams, and conversational emergence. Recommendation: default LangGraph, use CrewAI for prototyping, Microsoft Agent Framework for Azure shops. — https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026
- **Gheware DevOps (Jan 2026):** Production comparison across all three frameworks — LangGraph leads on production-grade control and MIT licensing, CrewAI on time-to-prototype, Microsoft Agent Framework (ex-AutoGen) on enterprise/Azure integration. — https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html
- **FutureAGI (May 2026):** Agentic RAG patterns — agentic RAG now performs 3–8 LLM calls + 2–6 retrievals per query vs classic RAG's single pass. The failure mode shifted from under-retrieval to hallucination-on-retrieved-content; faithfulness judges (a second LLM that scores whether outputs match retrieved chunks) are now a production default. — https://futureagi.com/blog/agentic-rag-systems-2025
- **BCG AI Platforms (April 2025):** MCP adoption across major providers — Anthropic's Model Context Protocol adopted by OpenAI, Microsoft, Google, Amazon within 4 months of launch, signaling it as the de-facto standard for agent-tool communication. — https://blog.infocruncher.com/resources/agents-1-rise-and-future-of-agents/AI%20Agents%2C%20and%20the%20MCP%20%28BCG%2C%202025%29.pdf
- **HN / Reddit:** Opensoul (HN, 3 months ago) — 6-agent marketing agency on Paperclip, each running on scheduled heartbeats with a Director agent coordinating delegation. Reddit r/MachineLearning threads consistently show LangGraph + Supabase + Claude/GPT-4o as the most common production stack; embedding model swaps (Ada → Voyage/Cohere) driven by recall/precision failures, not cost.

## Gotchas

- **Don't build one agent for everything.** The Opensoul pattern — specialized agents with clear roles, isolated memory, and a coordinator — consistently outperforms single-omniscient-agent designs in multi-domain production systems.
- **The evaluation gap kills agents silently.** Faithfulness checks (does output match retrieved context?) and inter-agent trace review catch failures that automated accuracy metrics miss. Add a "faithfulness judge" LLM as a production gate — it costs ~15% more per query and catches most hallucination-on-retrieval failures.
- **Sandboxing is not optional.** Even internal agents that "only run Python for math" need credential isolation and egress control. Prompt injection via retrieved documents is a proven attack vector (NVIDIA, 2025) — the agent cannot be trusted to sandbox itself.
- **Don't retrofit evaluation.** Build the evaluation layer at the same time as the agent, not after. Retrofitting trace analysis to an existing agent system is 3–5x harder than building it in.
