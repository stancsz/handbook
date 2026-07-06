# S-446 · The Agent Stack Is Stratifying

You bought the "one framework to rule them all" pitch. Twelve months later your LangChain agents are tangled with your orchestration logic, your tool integrations die when you migrate, and your cost-per-task is 10× what you projected. The agentic stack is not monolithic — it has six distinct layers, and the teams shipping reliably are treating each one as a separate decision.

## Forces

- **Context is your most defensible and most irreplaceable asset** — but it's also the highest lock-in and hardest-to-rebuild layer. Treat it accordingly
- **The M×N tool integration problem** scales brutally: N tools × M frameworks = M×N custom connectors. MCP makes it M+N, but only if you isolate connectors from orchestration
- **Orchestration and durable execution are different problems** — LangChain/LangGraph solve agent behavior; Temporal solves resumable long-running workflows. They're not competitors
- **Multi-agent is not always better** — it multiplies cost, latency, and failure surface. Three agents beat one only when the coordination overhead pays for itself in parallelization or specialization
- **Gartner: 40%+ of agentic AI projects will be canceled by end of 2027** due to escalating costs, unclear ROI, and inadequate risk controls — the ones surviving are the ones with bounded scope and measured cost-per-task

## The move

**Treat the agent stack as six independent layers, each with its own tradeoffs:**

1. **Context / Memory** — The highest-value, highest-lock-in layer. Your organizational world model, retrieval pipelines, and semantic memory. This is where investment compounds. Do not outsource it to a framework that might pivot.
2. **Orchestration / Agent logic** — LangGraph for graph-based production control with checkpointing; CrewAI for fastest prototyping with role-based teams; custom state machines when you need zero abstraction overhead.
3. **Security / Governance** — Policy gates before any side-effect tool (deployments, deletes, spending, customer messages). Add this before you ship, not after.
4. **Agent primitives** — The lowest lock-in layer. Swap models and agent frameworks freely when the layers above and below are decoupled.
5. **Sandboxing / Execution** — E2B, Modal, Firecracker microVMs, Shuru. Sandboxing is becoming its own category because agents that can execute code or call tools need hard containment boundaries.
6. **Infrastructure** — Docker, Kubernetes, serverless. Increasingly commoditized.

**When to add Temporal to LangGraph:** workflows that run longer than 30 seconds, call 3+ external systems, must survive process crashes, or pause for hours/days waiting for human approval. Not a replacement for LangChain — a layer underneath it.

**Choose orchestration by phase, not by dogma:** prototype with CrewAI (fastest iteration), harden with LangGraph (best production observability and checkpointing), add Temporal when durability requirements emerge.

**Measure cost-per-successful-task, not cost-per-API-call.** A 5-step multi-agent workflow at $0.40/task that resolves 80% of tickets cleanly beats a 2-step single-agent at $0.05/task that resolves 40%.

## Evidence

- **Blog post:** The enterprise AI agent stack is decomposing into six specialized layers — Context (highest lock-in/defensibility) → Orchestration → Security → Agents → Sandboxing → Infrastructure (lowest lock-in). Single-provider lock-in is identified as "the new version of single-cloud risk." — [Philipp D. Dubach, "Don't Go Monolithic; The Agent Stack Is Stratifying"](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)

- **Original research:** 6 months of real production data across 4 agentic AI systems (October 2025–April 2026). Single-agent LangGraph systems: 2.4–4.8 steps/run, ~$0.015–$0.06/call. Multi-agent CrewAI (3 agents, 8.2 steps avg): ~$0.40/task. API costs are 60–80% of total operating cost. Teams that added model routing (GPT-4o for simple tasks, o3 for complex) cut costs 40–70% without quality degradation. — [Inventiple, "The Real Cost of Running Agentic AI in Production"](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)

- **Framework comparison:** LangGraph offers graph-based production control with native checkpointing (best for complex branching and human-in-the-loop); CrewAI enables fastest prototyping with role-based agent teams (best for demos and MVPs); Temporal adds durable execution primitives under LangChain for workflows that must survive crashes and pause for human approval. These are complementary layers, not substitutes. — [Lushbinary, "LangGraph vs CrewAI vs AutoGen: AI Agent Framework Comparison"](https://lushbinary.com/blog/langgraph-vs-crewai-vs-autogen-ai-agent-framework-comparison/)

- **State of production 2025:** Four categories consistently shipped: (1) developer tooling — tight feedback loops (compile + test + human review) made this the safest beachhead; (2) internal ops automation — ticket triage, routing, runbook execution with clear success criteria; (3) research and analysis; (4) customer-facing operations. Gartner projects 40%+ of agentic AI projects cancelled by end of 2027 due to unclear business value. — [Technspire, "State of Agentic AI End-2025: Production Lessons and Patterns"](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

- **Orchestration > model:** Andrew Ng's finding: agentic workflows with GPT-3.5 jumped from 48% to 95.1% on the HumanEval coding benchmark — outperforming zero-shot GPT-4. The orchestration pattern matters more than the model choice for task success. — [Aliac, "Agentic RAG in Production"](https://aliac.eu/blog/agentic-rag-in-production)

- **Agentic RAG patterns:** RAG maturity ladder — naive (retrieve → generate) → advanced (hybrid retrieval + rerankers) → modular (multiple retrieval strategies) → agentic (plan → retrieve → evaluate → self-correct). Classic RAG: 1 LLM call + 1 retrieve, 1–2s latency, best for FAQ and single-doc lookup. Agentic RAG: 3–8 LLM calls + 2–6 retrieves, higher latency, but 89% acceptable answers at Deutsche Telekom (2M+ conversations) and 0.2% hallucination rate at Harvey AI (700+ legal clients). — [Aliac, "Agentic RAG in Production"](https://aliac.eu/blog/agentic-rag-in-production); [Future AGI, "Agentic RAG Systems 2026"](https://futureagi.com/blog/agentic-rag-systems-2025)

## Gotchas

- **Don't add multi-agent orchestration before you need it.** The coordination overhead (latency, cost, failure surface) only pays when agents can genuinely parallelize or specialize. Measure before you add.
- **Tool integrations outlive frameworks.** Building bespoke connectors inside LangChain or CrewAI creates migration debt. Use MCP or an abstraction layer so connectors survive framework swaps.
- **Agentic RAG's self-check loop is non-negotiable in production.** Without a faithfulness judge gating the output, the agent can retrieve 8 chunks and invent a ninth. This is the most common production failure mode.
- **Cost controls must be in the architecture, not the運營 policy.** Token budgets and step limits enforced at the code level catch runaway loops. Trust but verify — and verify programmatically.
