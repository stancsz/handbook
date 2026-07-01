# S-296 · The Stratifying Agent Stack

Your "agent" is actually six systems pretending to be one. The orchestration framework, the memory layer, the tool registry, the sandbox, the observability backend, and the model itself all evolve at different rates. Teams that treat it as a monolith rebuild every quarter. Teams that treat it as a layered architecture hold.

## Forces

- **Stack churn is the norm, not the exception.** 70% of regulated enterprises rebuild their AI agent stack every 3 months or faster. The culprit isn't one bad layer — it's that bundling them together means any fracture propagates everywhere.
- **Different layers have different defensibility profiles.** The model is a commodity (OpenAI/Anthropic API). The orchestration logic, org-specific tool integrations, and accumulated run data are the actual moat. Betting on a monolithic framework locks you into all of its tradeoffs simultaneously.
- **Sandboxing is the overlooked seventh layer.** When agents run code, execute web requests, or call internal APIs, the isolation boundary is often an afterthought — until a prompt injection triggers a $47K fraudulent refund through a customer support agent.

## The move

**Treat the agent stack as six independently-swappable layers, each with its own upgrade cadence and vendor profile:**

1. **Foundation model** (fast-moving, commodity) — Anthropic Claude or OpenAI GPT for reasoning-heavy tasks; open-source (Llama, Qwen) for cost-sensitive, latency-tolerant workloads.
2. **Orchestration/state machine** (stable, critical path) — LangGraph for production systems needing durable execution, checkpoints, and time-travel debugging. CrewAI for rapid prototyping of role-based pipelines. AutoGen is in maintenance mode as of October 2025.
3. **Memory/persistence** (moderate churn) — pgvector for teams under ~5–10M vectors. Pinecone/Qdrant/Weaviate at scale. Hybrid retrieval (dense + BM25) + reranker fixes most naive-RAG failures.
4. **Tool registry / integration layer** (high churn, high defensibility) — MCP (Model Context Protocol, open-sourced by Anthropic November 2024) is rapidly becoming the cross-cloud standard for connecting agents to enterprise tools. LangGraph's MCP integration treats MCP tools as first-class graph nodes with full streaming.
5. **Sandbox/execution isolation** (emerging as its own layer) — Firecracker microVMs, E2B, Modal, Shuru, and Vercel Sandbox. Each covers a different threat tier. OS-process sandboxes (Seatbelt, bubblewrap) vs. microVMs vs. full VMs are not interchangeable. The choice depends on your actual threat model, not the one you read about first.
6. **Observability/eval** (underinvested) — Less than 1 in 3 teams are satisfied with their observability and guardrail solutions. 63% of enterprises plan to increase observability investment. LangSmith, Phoenix, or custom structured logging.

## Evidence

- **Engineering blog:** Philipp Dubach's "Don't Go Monolithic; The Agent Stack Is Stratifying" (HN-linked, February 2026) — articulates the six-layer model and tracks how 37% of enterprises now use 5+ AI models in production (up from 29%), a direct consequence of layer-level substitution.
- **Survey/analysis:** Cleanlab's "AI Agents in Production 2025" — surveyed 1,837 engineering/AI leaders; only 95 had agents live in production. Stack churn rate of 70% tied directly to monolithic bundling. Primary barrier to deployment: quality, not cost.
- **Engineering blog:** "AI Agents in Production: Architecture Patterns for Reliable, Safe, and Scalable Agentic Systems" (April 2026) — distillation of production lessons: "we're no longer asking 'can we build agents?' but 'how do we build agents that are reliable, safe, and cost-effective at scale?'"
- **HN Show HN:** Opensoul — open-source marketing agent stack built on Paperclip (6 agents: Director, Strategist, Creative, Producer, Growth Marketer, Analyst), each running autonomously on scheduled heartbeats with task delegation between agents.
- **Framework review:** JetThoughts "LangGraph vs CrewAI vs AutoGen 2025" — AutoGen maintenance mode, LangGraph at Klarna/Replit/Elastic, CrewAI for role-based prototyping. LangGraph 1.0 (October 2025) reached 90M monthly downloads with deployments at Uber, JP Morgan, BlackRock, Cisco, LinkedIn.
- **Architecture deep-dive:** Paperclip on GitHub (69,955 stars as of June 2026, MIT licensed) — open-source orchestration platform modeling agents as employees with org charts, budgets, heartbeats, and governance. LLM-agnostic (Claude, Codex, Gemini, OpenClaw).

## Gotchas

- **Orchestration lock-in is real.** LangGraph's checkpointing and state management create data structures that don't port cleanly. Evaluate framework tenure before committing to its state schema.
- **RAG is a control loop, not a pipeline.** Naive RAG → Corrective RAG → Agentic RAG. Adding a relevance grader between retrieval and generation cut hallucination-inducing retrievals by 60–70% in production. A self-check loop (faithfulness judge gating the answer) is what separates agentic RAG from a bolted-on retrieval layer.
- **The sandbox layer is where real incidents happen, not in the prompt.** The $47K customer support fraud and Firecracker glibc hangs in minimal VMs both came from execution isolation, not model behavior. If agents call APIs, execute code, or browse web — the sandbox is not optional.
- **Stack churn compounds evaluation debt.** Each rebuild loses continuity in how the system behaves. Teams that survive the 70% churn rate are the ones who kept their eval harness framework-agnostic from day one.
