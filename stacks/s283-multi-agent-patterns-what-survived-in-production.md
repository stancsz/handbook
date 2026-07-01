# S-283 · Multi-Agent Patterns: What Survived in Production

Multi-agent hype peaked in 2024–2025. Teams expected swarms of agents to converge into emergent intelligence. What actually shipped is narrower, more deliberate — and more useful. The failure modes are now documented, and the patterns that work have concrete evidence behind them.

## Forces

- **More agents ≠ more intelligence.** Three independent strands of evidence — MIT, Google, and practitioner reports — converge on the same finding: adding agents without a specific coordination need mostly redistributes the same information through additional latency and cost.
- **Coordination overhead scales combinatorially.** Peer-to-peer with 10 agents creates 45 communication channels. A supervisor/worker pattern with 10 agents creates 10. The pattern choice isn't aesthetic — it determines whether failure cascades.
- **Structural failures, not prompting bugs.** Most multi-agent failures look like bad outputs until you trace the message-passing graph. Then you find: agents making decisions with stale state, supervisors that become bottlenecks, and no recovery path when one agent hangs.
- **Gartner documented a 1,445% surge in multi-agent inquiries** from Q1 2024 to Q2 2025. That surge generated a lot of expensive lessons.

## The Move

Three patterns have durable production evidence. Choose by failure mode tolerance, not by what's popular.

### 1. Supervisor / Router — Best for: fan-out with aggregation
A single supervisor decomposes a task and dispatches to specialized agents, then synthesizes results.
- Supervisor owns the decision: which agents to call, in what order, how many times
- Supervisor routes on intent classification (LLM-based or rule-based threshold)
- Works well for: document intelligence pipelines, ticket routing, multi-domain queries
- Failure mode: supervisor becomes the bottleneck — keep it lightweight, offload complexity to workers
- Real production pattern at multiple enterprise teams: classifier routes incoming docs → specialized agents (legal, financial, technical) → synthesis agent produces final output

### 2. Parallel Fan-Out / Map-Reduce — Best for: independent sub-tasks
A dispatcher sends the same task to multiple agents simultaneously, then aggregates results.
- Agents work independently — no inter-agent communication
- Aggregation step scores, ranks, or votes on outputs
- Works well for: code review (security + style + test-coverage simultaneously), multi-perspective research, parallel tool execution
- Failure mode: redundant work if tasks aren't truly independent; wasted compute on overlapping analysis
- Example: PR dispatch to security, style, and test-coverage agents simultaneously → supervisor aggregates and notifies on threshold violations

### 3. Sequential Pipeline — Best for: dependent steps with handoff
Agents pass output as input to the next agent, with explicit handoff contracts.
- Each agent's output schema is the next agent's input contract
- Works well for: research (plan → search → draft → review → publish), multi-stage processing
- Failure mode: any stage failure kills the pipeline; hard to parallelize
- This is the most common starting point and the most common production pattern for bounded workflows

### When NOT to split into multiple agents
- Tasks that share significant context — splitting forces serialization through message passing, adding latency without adding capability
- Tasks where one model's capability is the bottleneck — a better model solves more than multiple weaker agents
- Tasks requiring shared mutable state — agents with independent memory diverge on shared facts

## Evidence

- **Gartner State of AI 2026:** 1,445% surge in multi-agent inquiries Q1 2024 → Q2 2025. 57.3% of organizations report agents in production (LangChain State of AI Agents Survey 2026).
- **Medium / Micheal Lanham, April 2026:** "Three strands of evidence landed in the same year and all pointed the same way: failure in multi-agent systems is structural, not a prompting bug, and most of what looked like 'more agents means more intelligence' was just redundant rearrangement of the same information." Documents the three patterns (flow, orchestration, collaboration) with their cascade surfaces.
- **RockB / baeseokjae.github.io, 2026:** Maps three dominant enterprise production patterns with the coordination math: peer-to-peer with 10 agents = 45 communication channels; supervisor/worker = 10. Documents Document Intelligence Pipeline (hierarchical supervisor + specialized agents + synthesis), Code Review Automation (parallel fan-out + aggregation), and Customer Operations Automation (intent-routing specialist dispatch).
- **Technspire, December 2025:** Four categories consistently shipped to production — developer tooling, internal ops automation, research and analytics, customer-facing support — all with bounded scope and clear success criteria. "Agents shipped where tasks have clear success criteria and low individual blast radius."
- **Gheware DevOps Blog, January 2026:** LangGraph leads in production-hardened graph-based control; CrewAI leads in prototype velocity; AutoGen (now AG2) maintains a durable niche in conversational systems. Key stat: 65% of teams hit a wall within 12 months and rewrite — framework ceiling reached too late.

## Gotchas

- **Tool abstraction leaks.** When you add MCP tools to a LangGraph graph, they become first-class nodes. When you add them to CrewAI, they're callable functions. The abstraction boundary matters when things break — graph tracing is more debuggable than function-call logging.
- **State doesn't survive agent restarts.** If an agent crashes mid-task, you need an append-only event log (session) that the replacement picks up from. Most teams discover this after their first production incident.
- **Handoff contracts rot.** The schema that worked at launch gets extended by one agent, silently breaks another, and you're debugging silently degraded outputs weeks later. Treat handoff schemas like API contracts: version them, validate them.
- **Cost compounds per agent per step.** A 3-agent pipeline with 2 retrieval steps each generates token costs that teams underestimate by 3–5x until the first billing cycle.
- **The supervisor bottleneck.** The most common architectural mistake: a brilliant supervisor that becomes the single point of serialization. If your supervisor is doing more than routing and aggregating, it has become the thing it was meant to distribute.
