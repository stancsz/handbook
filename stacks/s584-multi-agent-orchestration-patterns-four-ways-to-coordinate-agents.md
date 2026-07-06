# S-584 · Multi-Agent Orchestration Patterns — Four Ways to Coordinate Agents

When one agent can't finish the job, you split it. But "split how" isn't obvious — and picking the wrong coordination model costs you months of debugging, latency spikes, or silent failures. The field has converged on four patterns, each with a clear trigger condition.

## Forces

- **A monolithic agent degrades with scope.** Context window performance drops ~73% when critical info is buried mid-context, and persona bleed causes guardrails to collapse. But splitting adds coordination overhead that can outweigh the gain.
- **Parallelization is tempting but error propagation is brutal.** Running N agents in parallel looks fast. When one fails or hallucinates mid-pipeline, recovering cleanly is non-trivial.
- **The right pattern depends on task structure, not preference.** Sequential, parallel, hierarchical, and dynamic patterns each dominate in different task shapes — teams pick based on aesthetics and regret it.
- **Infrastructure is the real differentiator.** Every orchestration comparison focuses on the framework, but production systems break on routing, error handling, cost controls, and cross-agent observability — all infra problems.

## The move

Map your task shape before choosing a framework. Four patterns, four triggers:

- **Sequential (pipeline):** Tasks have a strict dependency chain. Output of step N is input of step N+1. Use for: research → write → review flows. Simple to debug; latency = sum of all steps.
- **Parallel (swarm):** Tasks are independent and can run concurrently. Use for: batch analysis, multi-source gathering, A/B variant generation. Latency = max of slowest step; needs a fan-in merge strategy.
- **Hierarchical (supervisor):** A manager agent decomposes tasks and routes to specialists. Use for: complex, multi-domain requests where a single agent can't have coherent expertise across all domains. The supervisor handles retry logic and quality gates.
- **Dynamic (event-driven):** Agents register capabilities and task routing is data-driven, not code-driven. Use for: open-ended, unpredictable workloads. Highest flexibility; hardest to debug and trace.

Once you know the pattern, pick the framework that maps cleanly:

| Pattern | Best fit |
|---------|----------|
| Sequential | LangGraph (graph edges = dependencies) |
| Hierarchical | CrewAI (built-in manager/agent delegation) |
| Parallel | Raw asyncio, Temporal, or LangGraph's parallel branching |
| Dynamic | Custom state machine or AutoGen's group chat |

CrewAI's Flow abstraction is the recommended starting point even for Crews — it provides the state management and control flow that raw agent runs lack.

## Evidence

- **Engineering blog (TrueFoundry):** Four orchestration patterns — sequential, parallel, hierarchical, and dynamic — cover "most real-world multi-agent designs." The "real bottleneck is infrastructure: routing, guardrails, tracing, and cost controls across every agent and model call." — https://www.truefoundry.com/blog/multi-agent-architecture
- **Developer tooling analysis:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." The defensibility profile of each layer is very different — going monolithic is the wrong call. — https://news.ycombinator.com/item?id=47114201
- **Production lessons (Netguru R&D):** Building an internal sales agent (Omega) revealed the key evaluation criteria: integration depth, observability, and control over system behavior as requirements evolve. "The real differentiator isn't which LLM you choose — it's how much control you retain as your system grows." — https://www.netguru.com/blog/ai-agent-tech-stack
- **Memory architecture (Sistava engineering):** Running ~1,000 AI employees continuously for 2+ months in production taught them that a single vector store "completely broke." Memory requires three tiers: hot (Redis/PostgreSQL checkpoints), cold (vector store for cross-session knowledge), and document (Markdown/JSON for persistent project state). — https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture
- **Multi-agent systems (Comet):** "Lost in the middle" context degradation reaches 73% on reasoning tasks when information is mid-context. "Natural sycophancy" causes single agents to double down on hallucinations. Decomposing into specialized agents is the structural fix, not prompting. — https://www.comet.com/site/blog/multi-agent-systems
- **Production state (Technspire, Dec 2025):** Four categories shipped consistently in 2025: developer tooling (tight feedback loops), internal ops automation (clear success criteria), research/analysis (tool-augmented LLMs), and customer support (human-in-the-loop drafts). Everything else stalled in pilots. — https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons

## Gotchas

- **Parallel looks faster but introduces fan-in risk.** You need a merge strategy that handles partial failures — one agent returning bad data can poison the aggregate. Build this before you parallelize.
- **LangGraph's graph-as-code is powerful but verbose.** For simple sequential flows, it's overkill. CrewAI's Flow is purpose-built for the 80% case and has better production ops integration out of the box.
- **Multi-agent observability is unsolved.** LangSmith and Phoenix help, but cross-agent trace correlation requires explicit span propagation — which most teams skip until they have a production incident.
- **Hierarchical patterns create single points of failure.** If the supervisor agent degrades, the whole system stalls. Build explicit timeout and fallback behavior into the supervisor, not just the workers.
