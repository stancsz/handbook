# S-400 · The Orchestrator-Worker Pattern Ends the Hallucination Chain

Multi-agent systems don't fail because agents are dumb — they fail because agents delegate badly. The orchestrator-worker pattern (one capable agent decomposes and delegates, cheaper workers handle subtasks) is winning production because it architecturally prevents the failure mode that kills every other approach: hallucination propagation through a chain of trusting agents.

## Forces

- **Single-agent token bloat forces splitting.** A 10-turn single-agent task compounds context at n(n+1)/2 — a 10-turn workflow costs ~55× a single query. Splitting forces token budgets down per agent and caps total spend per task
- **Agents that trust each other's outputs amplify errors.** In ChatDev-style conversational chains, the 66.7% error rate compounds. In supervisor-worker hierarchies with a grounded orchestrator, error rates stay bounded because one agent with full context vets everything
- **Model cost stratification is now a first-class architectural concern.** Orchestrator-worker enables 40–60% cost reduction by routing capable-model reasoning to the orchestrator only, while workers run cheaper, task-specific models
- **Gartner's 1,445% surge in multi-agent inquiries (Q1 2024 → Q2 2025)** brought a wave of teams discovering that picking the wrong coordination pattern costs more than the model itself
- **40% of multi-agent pilots fail within six months of production** — almost always because of orchestration brittleness, not model capability

## The Move

The orchestrator-worker pattern treats the graph as a policy decision, not a conversation:

- **One orchestrator receives every task.** It decomposes, routes, and assembles — it never trusts a worker blindly. It holds full task state and decides when to retry, escalate, or terminate
- **Workers are stateless and task-specific.** Each worker runs a narrow model with a narrow toolset. No worker sees the full conversation — only its input and the orchestrator's instruction
- **The orchestrator maintains a "grudging trust" model.** Workers produce outputs that feed back to the orchestrator, which evaluates them before passing to the next step. Outputs that fail evaluation trigger retry or re-decomposition, not blind continuation
- **Token budgets are enforced per worker, not per task.** This caps the blast radius of a runaway agent and makes cost predictable. A worker that exceeds its budget fails cleanly; the orchestrator decides what happens next
- **Self-check loops are non-negotiable in agentic RAG.** Agents that retrieve and generate without a faithfulness gate invent facts from partial context. The aliac.eu production guide cites a real case: an agent retrieved 8 chunks, used 6, and fabricated the seventh — no span scored faithfulness, no judge gated the answer
- **CrewAI's hierarchical process (v0.98+)** implements this pattern natively — a manager agent delegates with explicit task assignments and timeout budgets. The failure mode is ~150ms added latency per delegation, which is the right tradeoff for bounded hallucinations
- **LangGraph's state machine approach** makes orchestrator logic explicit and traceable: every transition is a node, every edge is a defined policy. Teams at Klarna, Replit, and Elastic use this for durable execution — if a task fails mid-run, the graph resumes rather than restarts
- **AutoGen is in maintenance mode as of October 2025** — its successor is the Microsoft Agent Framework (a merger of AutoGen + Semantic Kernel, GA planned Q1 2026). Don't start new projects on AutoGen

## Evidence

- **Shopify Sidekick (Shopify Engineering, Aug 2025):** Evolved from a simple tool-calling system into a full agentic platform using Anthropic's agentic loop. Key architectural insight: "Vibe testing is not going to cut it — it needs to be principled and statistically rigorous, otherwise you should be shipping with a false sense of security." Shopify built LLM-based evaluation and GRPO training into their agent platform from day one
  — [Shopify Engineering](https://shopify.engineering/building-production-ready-agentic-systems)
- **Multi-agent production metrics (Thread Transfer, Jul 2025):** ChatDev achieves 33.3% correctness. Logistics systems using structured orchestration show 27% throughput gains and 22% cost reduction. AppWorld shows 86.7% failure on cross-app workflows — almost entirely from unstructured coordination patterns
  — [Thread Transfer](https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns/)
- **CrewAI production deployment (Markaicode, May 2026):** Tested on AWS EKS (eu-west-1, m5.xlarge). Recommendation: hierarchical process for >3 agents, Pydantic models for all task I/O to enforce data contracts, OpenTelemetry spans on every task to detect bottlenecks before they cascade. Redis-backed stateless workers scale linearly to 100+ concurrent crews
  — [Markaicode](https://markaicode.com/architecture/crewai-system-design-architecture-1048)
- **Agentic RAG hard failure case (aliac.eu):** Production agent retrieved 8 chunks, generated a draft, and shipped it. Two days later a fabricated fact was flagged. The root cause: no faithfulness scoring span fired, no judge gated the answer. Self-check loops must be architectural, not optional
  — [aliac.eu](https://aliac.eu/blog/agentic-rag-in-production)
- **Framework convergence data (Gheware DevOps, Jan 2026):** LangGraph is the production default (used at Klarna/Replit/Elastic). CrewAI is the fastest path to prototypes for content/support pipelines. AutoGen is dead — successor is Microsoft Agent Framework. 2026 decision: start with LangGraph unless you have an explicit reason not to
  — [Gheware DevOps](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Gotchas

- **Picking sequential over hierarchical when you have >3 agents.** Sequential chains beyond 5 agents deadlock and time out. The moment a workflow needs branching, conditional retry, or human escalation, sequential breaks
- **Giving workers too much context.** The point of splitting is isolation. If every worker gets the full conversation, you've gained nothing — you have the same hallucination propagation risk with extra latency
- **Skipping observability until production.** Multi-step agent workflows create debugging challenges that don't exist in traditional software. LangSmith (deep LangGraph integration), Arize Phoenix (OpenTelemetry-native), and Langfuse (self-hostable) are all first-class options — pick one before you ship, not after your first incident
- **No cost guardrails before launch.** Agents can burn through five-figure budgets over a weekend on a looping task. Budget enforcement at the orchestrator level — per-worker caps, per-task ceilings — is not optional
- **Treating agentic RAG as "add a loop to classic RAG."** Agentic RAG trades latency and tokens for faithfulness. If your use case is single-hop lookups, classic RAG is faster and cheaper. Agentic RAG pays off on multi-hop, ambiguous, or corpus-specific queries where the agent can self-correct mid-generation
