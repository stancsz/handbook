# S-502 · The Stratifying Stack: Six Layers, Three Winners, One Defensible Asset

Every era of computing stratifies into specialized layers with different winners at each. Cloud went IaaS → PaaS → SaaS. The modern data stack went ingestion → warehousing → transformation → BI. The enterprise AI agent stack is doing the same right now — and most teams building agents are ignoring it.

## Forces

- **Monolithic "god prompt" agents hit a wall at 73% context degradation** — when critical information lands in the middle of a long context window, reasoning quality collapses regardless of model capability — [Comet: Multi-Agent Systems](https://www.comet.com/site/blog/multi-agent-systems)
- **Tokens are only 8–27% of production run cost** — the dominant cost is senior oversight and orchestration overhead — [Digital Applied: AI Agent Build & Run Cost Index 2026](https://www.digitalapplied.com/blog/ai-agent-build-run-cost-index-2026)
- **37% of enterprises now run 5+ AI models in production** — single-provider lock-in is the new single-cloud risk — [a16z AI Enterprise 2025, cited via Philipp Dubach](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **AutoGen entered maintenance mode in October 2025** — framework choices now carry real lifecycle risk — [Iterathon: Agent Orchestration 2026](https://iterathon.tech/blog/ai-agent-orchestration-frameworks-2026)
- **Multi-agent workflows grew 327% between June and October 2025** — the architectural question is no longer whether, but how — [Databricks State of AI Agents, cited via MHTECHIN](https://www.mhtechin.com/support/orchestration-frameworks-for-agentic-ai-langchain-autogen-crewai-the-complete-2026-guide)

## The Move

The enterprise AI stack is decomposing into six layers. Each layer has different economics, different rates of change, and a different defensibility profile. Treat each as a separate procurement and integration decision.

**The six layers (high to low defensibility):**

- **Context** (highest lock-in) — organizational world model, process knowledge, entity relationships. This is the asset that compounds. Rebuilding it from scratch costs more than any model swap.
- **Orchestration** — agent coordination, workflow graphs, task delegation. LangGraph (graph-based, production-proven at Klarna/Replit/Elastic) and CrewAI (role-based, fast team-style delegation) are the two live options. AutoGen is in maintenance.
- **Models** — LLM inference layer. The market is commodity. Model cascade: use cheap/fast models for triage, reserve frontier models for high-stakes decisions. Can reduce token costs 40–70% with no quality loss.
- **Tooling** — tool definitions, MCP (Model Context Protocol), REST integrations, code execution sandboxes. Sandboxing is becoming its own specialist category: E2B, Modal, Firecracker wrappers, Shuru.
- **Infrastructure** — compute, hosting, vector database, caching, networking. The foundation layer.
- **Observability** — tracing, span scoring, eval, cost monitoring. Non-negotiable in production. LangSmith and Arize Phoenix are the established names.

**The organizing principle:** context is the moat, not the model. Every architectural decision should preserve optionality on layers 2–6 while treating layer 1 as a long-term compounding investment.

## Evidence

- **Blog post (primary source):** Philipp Dubach's "Don't Go Monolithic; The Agent Stack Is Stratifying" (Feb 2026, updated May 2026) is the canonical framework for this pattern, backed by a16z enterprise data showing 37% multi-model adoption and Gartner predicting >40% of agentic AI projects cancelled by end 2027 due to unclear business value — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Engineering blog:** Microsoft's ISE team documented the production requirements for multi-agent systems: accurate agent selection, optimized LLM usage, efficient orchestration, and scalability — [devblogs.microsoft.com/ise/multi-agent-systems-at-scale](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale)
- **Real-world implementation:** Opensoul — an open-source agentic marketing stack built on Paperclip — deploys 6 agents (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) as an autonomous marketing agency. Stack: Paperclip + Claude/OpenClaw/Codex + PostgreSQL. Runs on heartbeat scheduling with delegation and reporting — [HN Show post](https://news.ycombinator.com/item?id=47336615) + [GitHub](https://github.com/iamevandrake/opensoul)

## Gotchas

- **Building a monolithic agent to avoid "complexity" is a false economy.** The complexity doesn't disappear — it migrates into context degradation, guardrail burial, and persona bleed. Decompose early.
- **Treating the model as the moat is the most common strategic error.** Models commoditize on a 6-month cycle. Your organizational context (customer entities, process knowledge, reasoning chains) compounds and cannot be rebuilt quickly.
- **Don't pick AutoGen for new projects.** It entered maintenance in October 2025. The successor is Microsoft's next Agent Framework, not a version bump.
- **Score spans, not just final outputs.** Multi-agent regressions hide in sub-agents. If you're not tracing each agent's output independently, you're flying blind.
