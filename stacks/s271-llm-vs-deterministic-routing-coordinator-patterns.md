# S-271 · Supervisor vs Router — When the Coordinator Should Actually Think

Your multi-agent system needs someone in charge. Do you hard-code the routing logic (deterministic router) or let an LLM call the shots (LLM supervisor)? Microsoft ISE documented a real migration from the former to the latter at a large retail company, and the results expose a decision rule most teams get wrong by defaulting to what they know.

## Forces

- **Deterministic routing is fast and auditable** — but it requires you to enumerate every intent and every target upfront. When a new intent arrives, you update the router, redeploy, and pray nothing broke.
- **LLM-based supervisors are flexible** — but they add latency (typically 200–500ms per routing decision), token cost, and a new failure mode: the supervisor can route *wrongly*, and you need eval coverage to catch it.
- **The routing choice is load-bearing** — it determines your scaling path, your debugging surface, and whether adding a new agent is a code change or a prompt change.
- **Teams default to deterministic** because it's familiar from traditional software, but that choice has a compounding cost as the agent surface grows.

## The move

**Pick deterministic routing for stable, high-volume, low-variation intents. Pick LLM supervisors for open-ended, adaptive, context-dependent routing. Never default — model the cost and failure modes of each before choosing.**

### The decision matrix

| Signal | Use Deterministic Router | Use LLM Supervisor |
|---|---|---|
| Intent taxonomy | Closed, stable (< 50 intents) | Open, evolving, fuzzy |
| Change frequency | Low — infrequent new intents | High — daily new tasks |
| Latency budget | < 100ms routing overhead | Can absorb 200–500ms |
| Routing quality | Binary: correct vs wrong | Graded: better vs worse |
| Eval coverage | Handled by unit tests | Requires LLM-as-judge |
| Cost sensitivity | Very high | Moderate |

### Supervisor pattern implementation (LangGraph)

```
User Query
    │
    ▼
Supervisor Agent (LLM-based)
    │
    ├──→ "classify intent"
    │         │
    │         ▼
    │    [deterministic map: intent → agent]
    │
    └──→ "should I delegate or handle myself?"
              │
              ▼
         [Execute or delegate]
```

The Microsoft ISE retail migration demonstrated: **a single LLM supervisor can replace 15–20 hard-coded routing rules**, but only when the supervisor's routing accuracy is monitored. The critical insight: the supervisor doesn't need to be a frontier model — a small model (Haiku-class) performs comparably to GPT-4o for pure routing decisions, cutting the per-route cost by ~80%.

### LinkedIn's supervisor approach

LinkedIn's production agent platform (first shipped: LinkedIn Hiring Assistant) uses a **supervisor multi-agent architecture** with an ambient agent pattern and asynchronous processing. Key design: the supervisor owns task decomposition and delegates to specialized agents, but maintains a centralized skill registry so new agents register themselves — adding a new agent is a registry entry, not a router code change.

### The migration pattern Microsoft ISE documented

```
Before: Deterministic Router (Modular Monolith)
  ─ Single orchestrator, intent → agent mapping hard-coded
  ─ Adding an agent = code change + redeploy
  ─ 1 agent per query (no multi-agent orchestration)

After: LLM Supervisor (with Tool Call)
  ─ Supervisor decomposes task, calls specialized agents
  ─ New agents = new prompt instructions (no redeploy for routing)
  ─ Multi-agent orchestration per query (parallel where possible)
  ─ Latency: +300ms median per query
  ─ Cost: +$0.003 per query (routing tokens)
```

The trade-off Microsoft ISE explicitly quantified: **deterministic wins at < 30 agents**. Above 30 agents, the maintenance cost of the routing table exceeds the cost of the LLM supervisor. At 100+ agents, the supervisor pattern is not optional — the routing taxonomy becomes unmaintainable.

## Evidence

- **Microsoft ISE case study:** A large retail company migrated from a deterministic router pattern (modular monolith, 1 agent/query) to an LLM supervisor with multi-agent orchestration. The routing taxonomy grew from 12 to 80+ intents without code changes. Reported latency overhead: ~300ms median, ~$0.003/query in additional token cost. — [https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **Microsoft ISE scalable multi-agent patterns:** Detailed decision matrix for agent selection, optimized LLM usage (agent-tier routing: small models for routing, frontier models for execution), and scalability benchmarks — 85% token savings achieved by routing 60% of requests to smaller models. — [https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale/](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale/)
- **LinkedIn production agent platform:** Transitioned from Java to Python for generative AI, built standardized framework with LangChain/LangGraph, supervisor architecture with multi-layered memory and centralized skill registry. First production agent: Hiring Assistant (recruiter workflow automation). — [https://www.zenml.io/llmops-database/production-agent-platform-architecture-for-multi-agent-systems](https://www.zenml.io/llmops-database/production-agent-platform-architecture-for-multi-agent-systems)

## Gotchas

- **Supervisor hallucinations route to the wrong agent.** The failure mode is different from a deterministic router (which fails loudly with a non-matching intent). An LLM supervisor can confidently route to the wrong agent — you need eval coverage specifically for routing accuracy, not just task quality.
- **Supervisor latency compounds.** If your downstream agents take 2s each, a 300ms routing overhead is acceptable. If you're doing 5 sequential agent calls, that's 1.5s of pure routing overhead — suddenly meaningful.
- **Deterministic routing breaks under multi-agent orchestration.** The modular monolith pattern works for 1-agent-per-query. The moment you need parallel execution or chained agents, the deterministic router becomes the bottleneck — you're routing to one agent, not coordinating a graph.
- **Small models for routing only work if the taxonomy is stable.** A Haiku-class model can classify 50 intents reliably. At 200+ intents with fuzzy boundaries, it degrades. Know your model's accuracy ceiling before committing to it as the router.
