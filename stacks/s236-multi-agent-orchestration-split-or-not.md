# S-236 · Multi-Agent Orchestration: When to Split, How to Coordinate

Splitting one agent into several specialized ones is the most common architectural decision in agentic systems — and the one teams get wrong most often. The threshold for splitting is real, the coordination cost is real, and the tooling is finally converging.

## Forces

- **The "God Prompt" cliff.** Single-agent reasoning degrades 73% when critical information gets buried in long contexts. A monolithic agent's safety guardrails get buried under conversation history, and persona bleed causes hallucination (e.g., a "coder" persona hallucinating non-existent libraries). — [Comet Blog, Sharon Campbell-Crow, Jan 2026](https://www.comet.com/site/blog/multi-agent-systems)
- **Orchestration overhead compounds.** Five agents × three tool calls = 15+ LLM calls per request. Each LLM call introduces variance; chained agents multiply it. Failures propagate — one agent's bad output becomes the next agent's bad input. — [DevStarSJ Blog, Mar 2026](https://devstarsj.github.io/ai/architecture/2026/03/14/multi-agent-ai-architecture-patterns-2026)
- **Token duplication is expensive.** MetaGPT wastes 72% of tokens on duplicated context across agents; CAMEL wastes 86%. In a 5-agent pipeline running 10k requests/day, that's real money. — [Zylos Research, Jan 2026](https://zylos.ai/research/multi-agent-orchestration-2025/)
- **The right orchestration paradigm depends on what you're coordinating, not preference.** LangGraph (graph/state machine), CrewAI (role-based), and AutoGen (conversation) pick fundamentally different abstractions — and picking the wrong one at scale means a rewrite in 6-12 months. — [Gheware DevOps Blog, Jan 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Observability is the #1 production barrier.** Teams can't debug multi-agent failures because they can't trace which agent step produced which output. Without instrumentation, a failure in agent 3 of 5 is invisible until it hits the user. — [Zylos Research](https://zylos.ai/research/multi-agent-orchestration-2025/)

## The Move

### When to split an agent
- The task requires two or more distinct tool sets (e.g., web search + code execution + database query)
- Different context windows would benefit from different model sizes (e.g., fast Haiku for routing, Sonnet for reasoning)
- Persona or role drift is causing output contamination (a "reviewer" agent keeps injecting "writer" suggestions)
- Parallel work can happen simultaneously — splitting enables genuine concurrency

### The 2025-2026 orchestration stack — two protocols, not one
- **MCP (Model Context Protocol):** Anthropic's open standard for giving agents tools and resources. Anthropic donated MCP to the Linux Foundation in December 2025. It operates within a single agent's boundary. Think: "agent-to-tool" connection. — [DEV Community / Barbara Wu, Mar 2026](https://dev.to/barbara_wu/mcp-vs-a2a-the-two-protocols-defining-the-ai-agent-economy-4b5m)
- **A2A (Agent-to-Agent Protocol):** Google's protocol (April 2025) for inter-agent coordination — discovery, task negotiation, and result exchange. 150+ enterprises supporting (Google, Salesforce, SAP, Atlassian). AWS Bedrock natively supports A2A. Hosted by Linux Foundation, v0.3 (July 2025). Think: "agent-to-agent" connection. — [DEV Community](https://dev.to/barbara_wu/mcp-vs-a2a-the-two-protocols-defining-the-ai-agent-economy-4b5m)
- **Together they form the enterprise default:** MCP handles tool access; A2A handles team coordination. — [Nexus Blog, Nov 2025](https://agent.nexus/blog/langgraph-vs-crewai)

### Choose your orchestration paradigm by workload shape
| Paradigm | Framework | Best for | Mental model |
|---|---|---|---|
| State machine | LangGraph | Complex, production-grade workflows; long-running tasks requiring checkpoints | "Design the state graph" |
| Role-based crew | CrewAI | Fastest path to working prototypes; multi-role collaboration with sequential or parallel task flow | "Assemble the team" |
| Conversation | AutoGen (AG2) | Collaborative reasoning between agents with turn-taking | "Agents negotiate" |
| Supervisor/hierarchical | Custom or Temporal | Multi-step workflows with a single decision-maker routing to specialists | "Boss-worker hierarchy" |
| Peer-to-peer/swarm | Custom | Fault-tolerant, distributed, 20+ agents | "Flat network" |

### Four coordination patterns and when to use them
- **Supervisor:** One central agent routes to specialists. Simple, auditable. Single point of failure. — [DevStarSJ Blog](https://devstarsj.github.io/ai/architecture/2026/03/14/multi-agent-ai-architecture-patterns-2026)
- **Hierarchical:** Supervisor delegates to sub-supervisors. Scales to 20+ agents. Coordination overhead grows with depth. — [Zylos Research](https://zylos.ai/research/multi-agent-orchestration-2025/)
- **Pipeline:** Agents process sequentially, each consuming the prior's output. Simple, deterministic. No parallelism. — [DevStarSJ](https://devstarsj.github.io/ai/architecture/2026/03/14/multi-agent-ai-architecture-patterns-2026)
- **Swarm:** 50+ agents self-organize. Robotics, optimization. Extremely hard to debug. — [Zylos Research](https://zylos.ai/research/multi-agent-orchestration-2025/)

### Cost architecture — model routing is your biggest lever
- Model selection is the single highest-leverage cost decision. Claude Sonnet 4 ($3/$15 per 1M tokens in/out) vs GPT-4o ($2.50/$10) vs GPT-4o-mini ($0.15/$0.60) — the difference is 2–5x on your monthly bill. — [TokenFence Blog, Mar 2026](https://tokenfence.dev/blog/claude-vs-gpt4o-cost-comparison-ai-agents-2026)
- **Intelligent routing:** Route simple tasks (routing, classification, formatting) to Haiku or GPT-4o-mini; reserve Sonnet/4o for reasoning and generation. — [CallSphere Blog, Jan 2026](https://callsphere.ai/blog/ai-agent-cost-optimization-strategies-production)
- **Token budgets and semantic caching** can cut LLM API costs 50–80%. Multi-agent workflows quietly drain thousands through hidden retries, oversized context windows, and redundant tool calls. — [Galileo AI Blog, Jun 2026](https://galileo.ai/blog/ai-agent-cost-optimization-observability)
- **65% of teams hit a wall within 12 months** and have to rewrite when cost visibility is absent. — [Gheware](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Evidence

- **Enterprise adoption:** 72% of enterprise AI projects now involve multi-agent systems, up from 23% in 2024. — [Zylos Research, Multi-Agent Orchestration Patterns 2025](https://zylos.ai/research/multi-agent-orchestration-2025/)
- **Real-world results:** 80% reduction in insurance claims processing time; $18.7M annual savings in banking fraud detection — both from multi-agent systems. — [Zylos Research](https://zylos.ai/research/multi-agent-orchestration-2025/)
- **Observability gap:** 72-hour context degradation causes 73% reasoning performance drop on single-agent systems. — [Comet Blog, Multi-Agent Systems](https://www.comet.com/site/blog/multi-agent-systems)
- **Production failure rate:** 65% of teams hit a wall within 12 months and rewrite their multi-agent architecture. Default to LangGraph unless strong reasons not to — the steeper learning curve prevents painful rewrites. — [Gheware DevOps Blog, LangGraph vs CrewAI vs AutoGen 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **CrewAI scale:** 47,000 GitHub stars, $18M Series A from Insight Partners. — [Nexus Blog, LangGraph vs CrewAI](https://agent.nexus/blog/langgraph-vs-crewai)
- **A2A ecosystem:** 150+ enterprises supporting (Google, Salesforce, SAP, Atlassian), AWS Bedrock natively supports A2A. — [DEV Community / Barbara Wu](https://dev.to/barbara_wu/mcp-vs-a2a-the-two-protocols-defining-the-ai-agent-economy-4b5m)

## Gotchas

- **Don't split for parallelism you don't have.** If two agents don't genuinely have independent work to do, running them concurrently adds latency (waiting for both) and cost (two inference passes). Sequential pipeline agents should only branch when there's real concurrency opportunity.
- **Context passing is a leaky abstraction.** What you pass between agents is not "the result" — it's a text representation of it. The receiving agent must parse, re-embed, and re-reason over it. Build structured output schemas (JSON mode, Pydantic) for inter-agent contracts, not raw text.
- **Orchestration framework choice is expensive to reverse.** LangGraph's graph topology is explicit and debuggable but verbose. CrewAI is fast to prototype but can become unmaintainable at 15+ agents. Get the paradigm right for your scale, not your starting point.
- **Observability isn't optional at 3+ agents.** You need trace-level instrumentation for every agent step: which agent ran, which model, which tools, token count, latency, and output quality tags. Without this, you're flying blind when a pipeline fails at 2am.
- **Token duplication silently kills your cost model.** Measure actual token usage per agent before assuming the pipeline is efficient. MetaGPT's 72% duplication rate is not an outlier — it's typical for poorly designed inter-agent communication.
