# S-286 · Real Agentic AI Costs: What 4 Production Systems Actually Spent

You cannot price an agentic system from benchmarks. Every article either says "it depends" or cites toy examples. Here's what four real deployments actually spent over six months — with the breakdown that reveals where the money goes.

## Forces

- **LLM cost dominates.** API spend is 60–80% of total operating cost, dwarfing infra. Teams that optimize for cheaper infra while ignoring token efficiency are solving the wrong problem.
- **Multi-agent workflows compound costs non-linearly.** A 4-agent orchestrator-worker task costs $5–8 per execution. Teams that design multi-agent architectures without modeling economics discover this too late.
- **Per-execution cost varies 10x by architecture.** Single-agent with 2–3 tools: $0.05–0.10/execution. Multi-agent with 5+ agents: $0.40–0.51/execution. The stack choice is a cost decision.
- **Optimization is real but bounded.** Teams cut costs 40–70% with caching, model routing, and step reduction. The floor is set by the task complexity, not the tooling.

## The move

Model your cost before you build. These are the real numbers:

**Per-system monthly costs (Oct 2025 – Apr 2026):**

| System | Type | Framework | Steps/Run | Monthly Volume | Monthly Cost | Cost/Execution |
|--------|------|-----------|-----------|----------------|--------------|----------------|
| A | Support triage | LangGraph | 2.4 | 12,000 | $636 | $0.053 |
| B | Document processor | LangGraph | 4.8 | 8,500 | $1,248 | $0.147 |
| C | Sales research crew | CrewAI | 8.2 | 3,200 | $1,380 | $0.431 |
| D | Customer onboarding | LangGraph + Temporal | 12+ | ~3,500 | $1,996 | $0.570 |

**Where the money actually goes:**
- **Single-step agents:** LLM API = ~60% of cost; infra = ~40%
- **Multi-step/multi-agent:** LLM API = 70–80% of cost; infra becomes marginal
- **Context window management** is the highest-leverage optimization — each saved round-trip multiplies across high-volume runs
- **Model routing** (Claude Haiku for validation steps, Opus for synthesis) cut costs 30–40% without measurable quality loss
- **Semantic caching** (retrieve semantically similar past completions before calling LLM) reduced execs by 15–25% on support-triage workloads

## Evidence

- **Production cost study:** 4 real deployments tracked October 2025–April 2026. Single-agent systems: $0.05–0.15/execution. Multi-agent (3–6 agents): $0.43–0.57/execution. LLM API drives 60–80% of total cost. — [Inventiple: Agentic AI Production Cost Analysis](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)
- **Multi-agent economics:** 4-agent orchestrator-worker workflows cost $5–8 per complex task. Inference cost compounds across agents. 89% of teams have observability but only 52% have evals. — [RaftLabs: Multi-Agent Systems Architecture Patterns](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Token cost benchmarking:** A 5-step agent breakdown shows input tokens dominate early steps (query analysis), output tokens dominate late steps (synthesis). Per-step token accounting reveals the highest-leverage optimization targets. — [WisGate: AI Agent Token Cost Benchmark](https://wisgate.ai/blogs/ai-agent-token-cost-benchmark-5-step-agent-breakdown)

## Gotchas

- **Benching on per-token price is misleading.** A $0.50/exec system using Haiku + caching beats a $0.05/exec system using Opus with no optimization. Compare cost per task outcome, not per token.
- **Adding agents multiplies cost faster than capability.** Going from 1 to 3 agents often adds 3–4x cost per task before accounting for retry overhead. Measure the marginal quality gain.
- **Infra cost is a distraction for most teams.** Teams spending engineering cycles on Kubernetes optimization while ignoring LLM API costs are optimizing the wrong axis. Lock in the LLM cost model first.
- **Context management has a cliff.** Sessions approaching context limits don't degrade gracefully — they jump in cost and latency. Budget for window management from day one.
