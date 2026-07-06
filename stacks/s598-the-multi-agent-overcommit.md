# S-598 · The Multi-Agent Overcommit

Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. Most of those teams are about to learn the same lesson: more agents do not reliably produce better outcomes — they produce compounding costs, cascading failures, and traces that nobody can read. The multi-agent overcommit happens when teams reach for coordination patterns before they have exhausted what a single capable agent can do.

## Forces

- **More agents is not more intelligence.** The intuition that two LLMs working together outperform one is wrong more often than right. Most production multi-agent systems exist because the work has genuine boundaries — different access controls, different tool sets, different models — not because coordination adds capability.
- **Costs compound non-linearly.** A 4-agent orchestrator-worker workflow costs $5–8 per complex task. Each agent adds its own prompt, context shaping, and inference calls. Two-to-five times the token cost for the same task is common. Teams discover this from the bill, not from the design doc.
- **Typed handoffs are the hard part.** The failure mode that kills multi-agent workflows fastest is not the agents themselves — it is untyped, unvalidated data flowing between them. Without schema-enforced contracts at every agent boundary, silent data corruption cascades through the entire system.
- **Observability does not equal evaluation.** 89% of teams running multi-agent systems have distributed tracing. Only 52% have evals. The result: beautiful flame graphs of a system nobody can verify is working correctly.
- **Gartner projects 40% of agentic AI projects will be cancelled by end of 2027** — many of them multi-agent systems that were shipped before the team understood what they had built.

## The Move

Default to a single agent. Add a second only when the work has a genuine boundary — a different model, a different toolset, a different access scope, or a natural handoff point. Then choose the coordination pattern that matches the shape of that boundary.

**Four patterns cover most production use cases:**

- **Supervisor (controller delegates):** One central agent decomposes a task and delegates to specialists. Easiest to debug — the supervisor trace shows the full decision path. Best for: 3–8 agents, hierarchical task decomposition, enterprise workflows where auditability matters. Error amplification factor ~4.4× (vs 17× for poorly structured alternatives).
- **Peer / Handoff:** Tasks progress through stages, each owned by a different agent. No central controller. Best for: pipeline-style work where outputs from one stage naturally become inputs to the next. OpenAI's Agents SDK is built around this pattern. Clean and observable when stage boundaries are sharp.
- **Market (auction/bidding):** A task is broadcast and agents bid on it. Best for: load distribution across equivalent workers, dynamic routing. Rarely the right choice for deterministic workflows — adds nondeterminism and debugging overhead.
- **Shared-state (workspace):** All agents operate on a shared artifact or memory store. Best for: collaborative writing, code generation where multiple specialists must reference the same evolving context.

**At every agent boundary, enforce a typed schema contract:**

```python
# Every handoff needs: schema version, required fields, optional fields, TTL
@dataclass
class AnalystReport:
    schema_version: str = "1.0"
    summary: str           # required
    confidence: float       # 0.0–1.0
    citations: list[str]    # required
    expiry_seconds: int = 300

    def validate(self) -> bool:
        return (
            self.schema_version.startswith("1.")
            and 0.0 <= self.confidence <= 1.0
            and len(self.citations) > 0
        )
```

Without this, an agent that slightly misinterprets its predecessor's output corrupts the entire downstream chain — and you will not find out until the final output is wrong.

**Model the economics before committing to architecture.** A multi-agent design that costs $6/task needs to demonstrably outperform a well-prompted single-agent design at the same task by enough margin to justify 5× the spend at volume. If you cannot measure that gap, default to single-agent.

## Evidence

- **Gartner Research:** 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025; 40% of agentic AI projects projected cancelled by end of 2027 — [Gartner Multi-Agent Research, via RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Production cost data:** Multi-agent inference costs compound to $5–8 per complex task; 57% of organizations already running agents in production; 89% have observability but only 52% have evals — [RaftLabs Multi-Agent Systems Guide, November 2025](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Design thesis:** Multi-agent earns its place when work has genuine boundaries, not because coordination adds capability; four patterns (supervisor, peer, market, shared-state) cover production use cases — [Gravity Fast, Multi-Agent Coordination Patterns, May 2026](https://gravity.fast/blog/ai-agent-multi-agent-coordination)
- **Framework comparison:** LangGraph (graph-based production control, steepest learning curve), CrewAI (fastest prototyping, role-based teams), AutoGen consolidating into AG2 (Azure-optimized), OpenAI Agents SDK (lightweight handoffs), Google ADK (newer, opinionated) — [Humaineeti AI, Multi-Agent Orchestration Frameworks, April 2026](https://www.humaineeti.ai/resources/multi-agent-orchestration-frameworks)
- **RAG retrieval baseline:** Naive RAG pipelines fail 40% of the time at retrieval — hybrid BM25 + dense search with reranking is now standard production practice — [Lushbinary, RAG Production Guide 2026](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)
- **MCP adoption:** 78% of enterprises have MCP in production as of May 2026; protocol donated to Linux Foundation late 2025 accelerating enterprise adoption; public registry at 9,400+ servers — [MCP Adoption Statistics CTO Survey, May 2026](https://agileleadershipdayindia.org/blogs/mcp-model-context-protocol-enterprise/mcp-adoption-statistics-cto-survey.html)

## Gotchas

- **The supervisor becomes a bottleneck.** A central orchestrator handling all decomposition decisions is easy to reason about — until it starts failing in ways that take down every downstream agent simultaneously. Build supervisor fallbacks and circuit breakers before scaling agent count.
- **Context window pressure scales with agent count.** Each agent that reads shared context adds its tokens to the total. A 6-agent system where every agent re-reads the full conversation history will hit context limits and degrade unexpectedly.
- **Multi-agent evaluation is harder than single-agent.** Each agent needs its own eval harness. Cross-agent failures — where the bug is in the handoff, not in any individual agent — require end-to-end test scenarios that are expensive to construct and brittle to maintain.
- **Framework lock-in is real.** LangGraph, CrewAI, and AutoGen each have distinct mental models. Migrating a 12-agent CrewAI system to LangGraph is a significant rewrite, not a port. Choose the framework whose mental model matches your team's — not the one with the best blog posts.
- **Sandboxing is stratifying as its own layer.** E2B, Modal, Shuru, and Firecracker wrappers are converging as the isolation layer for agent code execution. Treat sandboxing as a separate infrastructure concern from orchestration — do not bake it into your agent framework.
