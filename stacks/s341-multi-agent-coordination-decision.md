# S-341 · The Multi-Agent Coordination Decision: When to Split, How to Connect

The default answer should be "don't." Most teams split into multi-agent systems too early, pay 2–5x the token cost, and end up with harder debugging than a single-agent with better prompting. But when the work has genuine boundaries — different access controls, different toolsets, different models — splitting agents is the only path to reliable production systems.

## Forces

- **Gartner tracked a 1,445% surge in multi-agent inquiries** from Q1 2024 to Q2 2025 — teams are moving from one-agent prototypes to production multi-agent deployments, but many are doing it for the wrong reasons.
- **Multi-agent costs 2–5x more in tokens** than a single-agent doing the same work. Cost is justified only when specialization measurably improves output quality — not just because it feels cleaner architecturally.
- **89% of teams have observability but only 52% have evals** — the observability/eval gap is the primary reason multi-agent debugging is still mostly guesswork, and adding agents compounds it.
- **The tool complexity wall hits around 20–50 tools** per agent. Beyond that, boundaries become unclear and tool selection accuracy degrades regardless of prompt engineering.

## The Move

**Step 1 — Exhaust single-agent first.** A well-structured single agent can handle more than teams expect. Split only when you can name a specific failure mode that splitting solves. The burden of proof is on the split, not against it.

**Step 2 — Choose your coordination pattern by failure mode.**

| Pattern | When to use it | Failure mode |
|---------|---------------|--------------|
| **Supervisor (hierarchical)** | One agent controls and delegates to specialists | Easiest to debug — supervisor trace shows full decision path |
| **Peer (handoff)** | Stage-based work, e.g. sales → support handoff | Cleanest for sequential domains; OpenAI Swarm is built around this |
| **Market (bidding)** | Multiple agents compete for a task, supervisor picks winner | Adds latency; use only when task routing genuinely needs competition |
| **Shared-state (workspace)** | Agents work on shared artifacts simultaneously | Highest coordination overhead; only when parallel writes on shared objects are core to the task |

**Step 3 — Every handoff boundary needs a validated schema with version numbering.** Untyped handoffs kill multi-agent workflows faster than any other issue. The schema is a contract — treat it like an API.

**Step 4 — Model the economics before you commit.** A 4-agent orchestrator-worker workflow costs $5–8 per complex task in inference alone. For high-volume tasks, that's a budget crisis. For infrequent high-stakes tasks, it's fine.

**Step 5 — Start with supervisor, not peer.** It's the most debuggable pattern. Graduate to peer/market only when you've validated that the handoff logic actually works.

## Evidence

- **Shopify Engineering (Aug 2025):** Sidekick evolved from tool-calling into a sophisticated agentic platform. Shopify hit the tool complexity wall at 20–50 tools — unclear boundaries and unexpected combinations. They solved it with just-in-time instruction injection: only loading a tool's rules when that tool is actively called, keeping the system prompt lean. Key lessons: "Stay simple — resist adding tools without clear boundaries," "Start modular — use patterns like JIT instructions from the beginning," and "Avoid multi-agent architectures early — simple single-agent systems can handle more complexity than you expect." — [Shopify Engineering](https://shopify.engineering/building-production-ready-agentic-systems)

- **RaftLabs / Gartner data (Nov 2025):** Four orchestration patterns cover most production use cases: hierarchical, pipeline, orchestrator-worker, and peer-to-peer. 57% of organizations already have agents in production. 40% of enterprise agentic AI projects will be canceled by 2027 due to unclear business value. 89% of teams have observability but only 52% have evals — explaining why multi-agent debugging is mostly guesswork. Orchestrator-worker at 4 agents costs $5–8 per complex task. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)

- **Gravity (May 2026):** Four coordination patterns cover production: supervisor (controller delegates), peer (handoff), market (bidding), shared-state (workspace). Multi-agent costs 2–5x more in tokens — worth it when specialization measurably improves quality. Default to single-agent; multi-agent earns its place when the work has real boundaries (different access controls, different tools, different models). Supervisor is easiest to debug. — [Gravity](https://gravity.fast/blog/ai-agent-multi-agent-coordination)

- **Framework signals (2026):** Production workloads → LangGraph (durable state, checkpointing, time-travel debug, LangSmith tracing; used by Klarna, LinkedIn, Uber). Fast prototyping → CrewAI (role-based, conversational, fastest setup). OpenAI-centric shops → OpenAI Agents SDK (tightest integration, minimal boilerplate). AutoGen → in maintenance mode; Microsoft consolidating around Agent Framework. — [Jobs By Culture](https://jobsbyculture.com/blog/ai-agent-frameworks-compared-2026)

- **Production cost reality (2026):** Three cost buckets: LLM API (40–70% of total), Infrastructure (15–35%), Hidden costs including retries and debugging (15–30%). For a moderately active agent running 100–200 tasks/day, monthly API cost runs €30–80. Multi-agent orchestration compounds these — a single complex task through a 4-agent workflow reaches $5–8 in inference alone. — [The Operator Collective](https://theoperatorcollective.org/blog/real-cost-running-ai-agents-production)

## Gotchas

- **Adding agents to solve a prompting problem.** If your single agent is hallucinating or making bad tool choices, a second agent won't fix it — you'll just have two agents hallucinating together. Fix the evaluation loop first.
- **Assuming the supervisor pattern scales to large teams of agents.** It works well at 2–4 agents. Beyond that, the supervisor becomes a bottleneck and the handoff schemas become unmanageable. That's when pipeline or market patterns earn their overhead.
- **Skipping eval infrastructure before going multi-agent.** If you can't measure single-agent performance, you can't attribute multi-agent failures. Build evals before the split, not after.
- **Treating observability as evaluation.** LangSmith traces and Phoenix spans show you what happened — not whether it was right. 89% of teams have traces; far fewer have automated judgment of output quality.
