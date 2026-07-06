# S-576 · The Cost Beneath the Cost: Most Agent Spend Is Invisible Until It Isn't

Agent bills arrive in two waves. First: the LLM API invoice, predictable and front-and-center. Second: the tool calls, embedding lookups, external API round-trips, reranking passes, and orchestration overhead that never made it onto the dashboard. Teams that build agents on a budget projection see the first number. Teams that run agents in production discover the second.

## Forces

- **The dashboard lies by omission.** LLM spend is the only line item most observability tools surface. Tool calls, MCP invocations, and third-party API hits are invisible unless explicitly instrumented — and most teams don't instrument them until after the first cost incident.
- **Agentic RAG multiplies the hidden layer.** A single agentic RAG turn hits 3–8 LLM calls and 2–6 retrieval passes. Each pass may invoke an embedding model, a reranker, and a vector DB query — none of which appear in "AI costs" reports.
- **MCP widens the blast radius.** Once an agent can reach 10+ enterprise tools via MCP, a single loop iteration can trigger $0.10–$0.50 in third-party API calls. At scale or in runaway scenarios, this dwarfs the LLM cost.
- ** enterprises face a different problem:** runaway loops are rare but catastrophic — $15 in 10 minutes to $47,000 over 11 days. Most SMB teams won't see a $47K incident, but they will consistently underestimate per-task cost by 30–40%.

## The move

**Instrument the full cost stack before you project your budget. Use per-task granular cost accounting to drive architectural decisions — not just LLM token counts.**

- **Tag every LLM call** with purpose (classify, analyze, draft, refine, summarize) and capture token counts per call. This alone reveals which step in your pipeline is the cost driver.
- **Account for tool call costs explicitly.** MCP tool invocations, vector DB queries, reranking passes, and external API calls have real dollar costs. Add instrumentation at the call site, not as an afterthought.
- **Set per-task budget guards.** The AgentMeter data shows a support ticket resolution can cost anywhere from $0.30 (simple, cached) to $2.80 (complex, multi-hop). A hard ceiling prevents runaway loops from generating open-ended invoices.
- **Route to cheaper models for classification and routing.** The same data shows that ticket classification at $0.01 is 18x cheaper than response refinement at $0.18. Use o3-mini or Haiku for classification and routing; reserve Opus and Sonnet for generation and analysis.
- **Use prompt caching for repeated context.** Repeated document context across agent turns (a legal brief, a codebase overview) can be cached, reducing embedding and context window costs by 40–60% for repetitive workloads.
- **Benchmark the full stack, not just the LLM.** For a support ticket workflow: LLM = $0.80, MCP tools = $0.17, external APIs = $0.13. The LLM is 73% of the total — meaning 27% was invisible. On content generation tasks, the ratio flips: tool and API costs can exceed LLM spend.

## Evidence

- **Blog post (AgentMeter):** Detailed per-task cost breakdown showing support ticket resolution at $1.10 total — $0.80 LLM (73%), $0.17 MCP tools (15%), $0.13 external APIs (12%). Multiple task types benchmarked. — [AgentMeter Blog: How Much Do AI Agents Actually Cost? A Real-World Breakdown](https://www.grislabs.com/blog/agentmeter/how-much-do-ai-agents-cost)
- **Research report (Zylos):** Enterprise AI operational costs average $85,521/month as of 2025; 60–85% of spend is recoverable through prompt caching, model routing, and budget enforcement. Runaway loop incidents cost teams $15 to $47,000. — [Zylos Research: AI Agent Cost Engineering — Production Token Economics](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)
- **Engineering post (Graebener):** Observability is non-negotiable — every agent call should log input context, model reasoning, tools invoked, and final output. Without this, debugging is impossible and cost attribution is blind. — [graebener.tech: Building Production AI Agents: Lessons Learned](https://graebener.tech/blog/building-with-ai-agents)

## Gotchas

- **Per-task cost varies more than per-token cost.** A "simple" support ticket can become a $2.80 interaction if the agent re-retrieves, re-reasons, and escalates. Average cost per task is a better budget unit than cost per token.
- **Prompt caching requires static or semi-static context.** It won't help on tasks with highly variable user inputs. Benchmark before assuming savings.
- **Hard budget limits can produce half-finished agent outputs.** A $0.50 ceiling on a complex task may cut the agent off mid-reasoning. Set limits by task type, not globally.
- **The hidden cost grows with agent capability.** More capable agents make more tool calls, attempt more re-retrievals, and run deeper reasoning chains. Each capability improvement has a cost tail that doesn't appear in model benchmark comparisons.
