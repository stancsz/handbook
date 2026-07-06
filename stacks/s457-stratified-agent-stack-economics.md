# S-457 · The Stratified Agent Stack and Its Hidden Cost Model

The agent stack is not a monolith — it is six layers with different rates of change, different lock-in profiles, and different defensibility. Most teams build it as one thing and pay for that mistake in production.

## Forces

- **AutoGen entered maintenance in October 2025** — the orchestrator you bet on 18 months ago may be deprecated before your product ships. Monolithic bets on a single framework layer carry platform risk identical to single-cloud lock-in.
- **Raw token cost is a fiction.** A "5-cent task" becomes $1–3 once you include retries on failure, human review of uncertain outputs, latency cost, and operator time. The real cost-per-completed-task runs 5–50× the token headline.
- **37% of enterprises now run 5+ AI models in production** — single-provider routing is the new single-cloud risk. The model layer commoditizes fastest; the organizational world model (your context and memory) is the hardest-to-rebuild defensible asset.
- **Gartner projects 40%+ of agentic AI projects will cancel by end of 2027** due to unclear business value, not technical failure. The teams shipping are the ones that scoped narrowly and instrumented relentlessly.
- **Demo-to-production success rates diverge dramatically.** One practitioner reported 92% test reliability collapsing to 55% in production — with $847/month token bills running against a $200/month budget.

## The Move

Treat the agent stack as six separable layers, each with its own selection criteria:

**1. Infrastructure / Sandboxing (fastest-moving layer)**
- Options: Shuru, E2B, Modal, Firecracker wrappers
- This layer handles code execution isolation and resource governance
- Swap this layer without touching orchestration or model choices
- Sandboxing is becoming its own specialized product category — don't build it yourself

**2. Orchestration (determines production stability)**
- **LangGraph** (graph-based state machines, 90K+ GitHub stars) — production default; used at Klarna, Replit, Elastic; best observability and durable execution; steeper learning curve prevents painful rewrites at 6–12 months
- **CrewAI** (role-based crews, 20K+ stars) — fastest path to working prototype; ideal for content pipelines and support ticket routing where roles map cleanly to domains
- **AutoGen** — in maintenance as of October 2025; successor is Microsoft Agent Framework; avoid for new projects
- Default to LangGraph unless you have a specific reason not to — the graph model earns its complexity in production

**3. Model Routing (commoditizing fast)**
- Run at least two providers — OpenAI for latency-sensitive paths, Anthropic for reasoning-heavy tasks
- Route by task type, not globally: classifier agents can run on smaller/cheaper models than synthesis agents
- Context is the highest lock-in and hardest-to-rebuild zone; protect it before you protect the model choice

**4. Context / Memory**
- MongoDB or PostgreSQL + pgvector for combined transactional + vector storage
- Store raw conversation history, retrieval indexes, and organizational knowledge separately — they have different TTLs and retrieval patterns
- Start simple: basic keyword retrieval before investing in hybrid three-tier memory systems that require real interaction data to tune

**5. Tools / Integration**
- MCP (Model Context Protocol) is emerging as the standard tool-call interface; adopt it for new tool integrations
- REST APIs remain the dominant pattern for external system integration
- Limit tool count per agent to avoid context dilution — more tools means worse performance on each

**6. Evaluation / Observability**
- Log every tool call, prompt, response, and decision from day one — never retrofit observability
- Use LangSmith, Phoenix (by Arize), or Langfuse for trace-level visibility
- Build automated evaluation against known-good examples before quality drift starts
- Production targets for agentic RAG: faithfulness ≥ 0.9, answer relevancy ≥ 0.85, context precision ≥ 0.8

## Evidence

- **Blog post:** The agent stack is stratifying — 37% of enterprises use 5+ models, context is highest lock-in, Gartner: 40% of agentic projects cancel by 2027 — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Engineering blog:** LangGraph at production scale — used at Klarna, Replit, and Elastic for durable stateful workflows; "default to LangGraph unless you have strong reasons not to" — [devops.gheware.com](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Post-mortem:** MeetSpot agent — 92% test reliability → 55% production reliability; $847/month token spend vs $200 budget; 47 distinct data format issues discovered post-launch — [calderbuild.github.io](https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/)
- **Cost analysis:** Raw token cost 0.5–15¢/task; all-in cost 5–50× that once retries, human fallback, and latency are included — [xwits.dev](https://xwits.dev/blog/economics-of-ai-agents)
- **Framework comparison:** AutoGen in maintenance October 2025 (successor: Microsoft Agent Framework); CrewAI for rapid prototyping, 20K+ stars; production systems using CrewAI ship faster but face rewrites when scope grows — [jetthoughts.com](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025/)
- **Survey data:** 57% of enterprises with AI initiatives have at least one multi-agent system in production in 2026, up from 12% in 2024 — [ajentik.com](https://www.ajentik.com/insights/multi-agent-systems-production-guide)

## Gotchas

- **AutoGen maintenance trap:** Teams that built on AutoGen 12–18 months ago are now migrating mid-product. Check framework maintenance status before selecting — active development vs. maintenance mode is a hard filter.
- **Token cost illusion:** Prompt caching changes the economics significantly (up to 90% cost reduction on repeated patterns). Implement it before instrumenting cost controls — otherwise your baseline is wrong.
- **Context window is not free:** Verbose system prompts (up to 8,000 tokens of fixed overhead per call) get billed on every invocation even when irrelevant. Audit your system prompt size per agent.
- **Over-engineering memory:** Three-tier hybrid retrieval sounds impressive but the tuning (similarity thresholds, keyword weights, merge strategies) only works when you have enough real agent interactions to measure against. Simple keyword retrieval ships in days; three-tier memory takes weeks and a data backlog you may not have yet.
- **Human-in-the-loop is permanent, not temporary:** Teams treat HITL as a launch-day crutch to remove later. In regulated domains (legal, medical, financial), it is the permanent architecture — design it as such from the start or retrofit it under deadline pressure.
