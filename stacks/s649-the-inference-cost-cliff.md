# S-649 · The Inference Cost Cliff

Agentic flows cost 5–25x more than chat. Teams discover this not in planning but in production — after they've committed architecture, built workflows, and shipped to users. The cost cliff doesn't arrive at scale; it arrives at 500 users.

## Forces

- **Every loop, retry, and tool call multiplies tokens.** A fraud detection agent at 50 users ($5K/month) hits $15K/month at 500 users — without any change to architecture or model. The multiplication comes from ReAct loops, context reloading, and retry chains that nobody modeled upfront.
- **Context is the dominant cost driver.** 80–90% of AI spend in agentic systems goes to inference, not infrastructure. The dominant factor is token volume: context window reloads, over-fetched retrieval candidates, and tool schemas burned into every prompt.
- **Teams only see costs after they're locked in.** Agent architectures commit you to a token-per-task ratio. By the time costs surface, rewriting the architecture is a months-long project, not a config change.
- **Model routing is the highest-leverage lever.** The spread between cheapest and most expensive model routing for the same task can reach 190x. Teams that don't build routing from day one burn money on every step.

## The move

Model the economics before you commit to architecture.

**Tier your agents by cost sensitivity:**
- High-volume, low-complexity steps (routing, classification, simple lookups): route to the cheapest capable model. GPT-4o-mini or a small open-source model handles most tool-use decisions.
- Reasoning and planning steps: use frontier models selectively. These are where you pay for quality — but gate them behind routing logic, not a flat pipeline.

**Build for model routing from the start:**
- Use a router agent or classification layer that assesses task complexity and selects the appropriate model tier before routing to specialized agents.
- Audit token-per-task ratios at each step. The retrieval → analysis → synthesis pipeline compounds costs. Cut context at each boundary.

**Instrument costs at step granularity:**
- Track cost per workflow type, not just per month. A customer support agent has different economics than a code review agent. You can't optimize what you don't measure.
- Set per-step cost budgets with hard fallbacks (cheaper model, cache hit, or graceful degradation) rather than letting any step run to completion on a frontier model.

**Plan for the scale cliff:**
- Model what 500 users looks like. Then model 5,000. The cost curve is not linear — it's super-linear because each user multiplies multi-turn interactions.
- The cliff hits at 500–1,000 concurrent users for most cloud-API architectures. Know which tier you're building toward and whether the unit economics hold.

## Evidence

- **Cost benchmarks (2026):** Tool-using agents cost $200–$800/month at 1K requests/day; multi-agent RAG pipelines run $1K–$5K/month. Simple chatbots top out at $30–$150/month. — TokenFence (https://tokenfence.dev/blog/ai-agent-cost-benchmarks-2026-real-numbers)
- **Real team scaling story:** A fintech startup's fraud detection agent: $5K/month at 50 users (Q3 2025). Same architecture, 500 users by January 2026: $15K/month. At 700–1,000 concurrent users, unit economics inverted and the project was killed. — TechAhead (https://www.techaheadcorp.com/blog/inference-cost-explosion)
- **Market data:** Gartner tracked a 1,445% surge in multi-agent inquiries (Q1 2024 → Q2 2025). 49% of organizations cite high inference cost as the top deployment blocker. 40% of AI agent projects are forecast to be cancelled by 2027 due to cost. 76–100% of AI budgets are spent on inference alone. — RaftLabs citing Gartner (https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Routing leverage:** Model routing — sending each task to the cheapest capable model — creates up to 190x cost difference per task. This is the single highest-leverage cost optimization available. — AgentMarketCap (https://agentmarketcap.ai/blog/2026/04/15/agent-compute-finops-crisis-production-inference-costs)
- **HN primary source:** Developer running 11-agent production fleet on GKE since February 2026. Each agent runs as a separate Claude Code CLI session with MCP servers. Architecture decomposition required specifically because single-agent context windows couldn't hold the reasoning chains for complex tasks. — Agent.ceo (CTO of GenBrain AI) (https://agent.ceo/blog/multi-agent-architecture-patterns)

## Gotchas

- **You can't cost-control your way out of a bad architecture.** Budget caps on API calls just make agents fail gracefully, not cheaply. The cost-per-task is baked into the workflow design.
- **Retrieval over-fetching is invisible until it's expensive.** Fetching 20 chunks and letting the LLM filter 17 is not free. Re-rankers add an LLM call but can cut the context load enough to pay for themselves on complex queries.
- **Not all tool calls are equal.** A web search tool call costs $0.01–$0.05 per call. A code execution call costs $0.10–$0.50. A multi-step code review chain can cost $1–$5 per task. Treat each tool tier like a different service class with different budgets.
- **The "demo to production" cost jump isn't a 2x problem.** Teams expect 2–3x costs at scale. The actual multiplier from demo (10 users, simple flows) to production (500 users, full workflow complexity) is typically 10–25x. Plan accordingly.
