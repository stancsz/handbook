# S-570 · The Semantic Router — The Cheapest Compute Is the One You Don't Bill

The most expensive mistake in a production agent system is not a wrong answer. It's a right answer to a question that didn't need a frontier model. Semantic routing — classifying intent with a lightweight classifier and escalating to the LLM only when necessary — is the highest-leverage production optimization nobody talks about.

## Forces

- **LLM inference dominates cost.** Token prices of $3–15/M input tokens add up fast when 80% of requests are "what's my order status" or "reset my password" — queries a keyword matcher or SLM could handle in milliseconds for fractions of a cent.
- **Context window overflow is a latency and cost amplifier.** More tokens in means more money out and more time waiting. A 1,000-token routing decision beats a 10,000-token full-context LLM call every time — if you've architected for it.
- **The stack stratifies.** As agent systems scale, orchestration splits into specialized layers (per Philipp Dubach's analysis: security, routing, runtime, context, tools, coordination) — and routing is where the first cost-consequence decision gets made on every single request.
- **Multi-agent systems make routing mandatory.** When you have 6 specialized agents (Director, Strategist, Creative, Producer, Growth Marketer, Analyst — per Opensoul's marketing agency model), every task must first land in the right agent's queue. Doing that with 6 simultaneous LLM calls per routing decision is a cost and latency disaster.

## The Move

**Semantic Router with LLM Fallback — route cheap first, escalate expensive only when confidence is low.**

- **Tier 1: Lightweight NLU/SLM classifier.** A fine-tuned SLM (3B–7B parameters) or keyword/N-gram matcher does initial intent classification. For a customer support agent: 15–20 intent classes cover 90% of volume. Classify, route, respond. No LLM involved.
- **Tier 2: Confidence gate with configurable threshold.** Route to LLM only when classifier confidence < 0.85 (or whatever your domain demands). Set this per intent class — "escalate for medical, financial, or novel inputs" — not as a global wall.
- **Tier 3: Model selection on escalation.** When you do escalate, pick the right model for the job. Code tasks → CodeLlama or deepseek-coder. Fast summarization → Haiku or GPT-4o-mini. Multi-step reasoning → Opus or GPT-4o. Don't route everything to the most expensive model.
- **Fallback: Human-in-the-loop for ambiguous cases.** Amazon's agentic evaluation framework (2026) flags HITL as essential for multi-agent systems where coordination failures or contradictory recommendations emerge. Build the handoff before you need it.
- **MCP for tool routing at the tool layer.** The Model Context Protocol handles tool selection after routing — MCP servers expose tools as structured resources, and the agent retrieves relevant ones at execution time rather than predicting tool names from a static list. This shifts tool discovery from prompt engineering to infrastructure.
- **Cost guardrails on escalation paths.** Set per-user or per-session token budgets. When a request escalates, track cumulative spend. Fail fast on runaway loops — a recursive agent calling itself is a production incident.

## Evidence

- **Microsoft's Multi-Agent Reference Architecture** (2025-05-14, 212 stars) explicitly codifies "Semantic Router with LLM Fallback" as Pattern #1: lightweight NLU classifier for initial routing, escalation to LLM when classifier confidence is low — reducing LLM usage while maintaining accuracy. — [github.com/microsoft/multi-agent-reference-architecture](https://github.com/microsoft/multi-agent-reference-architecture/blob/main/docs/reference-architecture/Patterns.md)
- **Amazon's agentic evaluation framework** (AWS Bedrock blog, Feb 2026) reports thousands of agents built since 2025, with HITL evaluation critical for multi-agent coordination failure detection. The framework distinguishes "emergent behaviors" — tool selection accuracy, multi-step reasoning coherence, inter-agent communication — requiring evaluation methods beyond black-box output checking. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)
- **Ragwalla's MCP Enterprise Adoption Report** (July 2025) found 30% reduction in development overhead and 50–75% time savings on common tasks for teams combining MCP with routing-aware architectures. 1,000+ community-built MCP connectors by Feb 2025. MCP reduces the tool-integration surface area so routing logic stays clean. — [ragwalla.com/blog/mcp-enterprise-adoption-report-2025](https://ragwalla.com/blog/mcp-enterprise-adoption-report-2025-challenges-best-practices-roi-analysis)

## Gotchas

- **Routing accuracy is domain-specific and degrades silently.** A classifier trained on support tickets will misclassify sales queries. Build eval sets per intent class and monitor drift quarterly — not just accuracy but per-class precision/recall.
- **The escalation threshold is a business decision, not a technical one.** Setting it at 0.95 means more LLM calls and higher cost. Setting it at 0.70 means more misroutes and degraded user trust. Calibrate against false-positive cost (LLM bill) vs. false-negative cost (wrong agent handles a complaint).
- **Routing state doesn't persist.** A conversation that starts with a cheap classifier can be mid-escalation when the session drops. Reconstructing routing state from chat history requires the same context management discipline as everything else — don't skip it.
- **Multi-agent routing amplifies both wins and failures.** A good router means the right agent handles the request and costs stay low. A bad router means wrong agent + full context wasted + 3 retries. Invest disproportionately in the routing layer — it's the load-bearing wall of multi-agent systems.
