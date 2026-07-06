# S-422 · Multi-Agent Orchestration: When to Split and How to Coordinate

You added more tools. Then more context. Then a bigger model. Your single agent still loops, hallucinates tool parameters, and takes 40 seconds per decision. The ceiling is real — and it is not about scale. It is about structural mismatch between what a single agent can reliably do and what your problem requires. The answer most teams arrive at is splitting into multiple agents with explicit coordination — but doing it wrong creates worse problems.

## Forces

- **The single-agent complexity wall** — tool selection accuracy drops below 90%, response latency exceeds thresholds, and the agent hallucinates tool parameters once context exceeds ~3-5 hops
- **Probabilistic vs. deterministic control** — a single agent with 15 tools makes probabilistic routing decisions that compound; a multi-agent graph makes routing explicit and inspectable
- **Inference cost compounding** — complex tasks with single agents generate $5-8 in inference costs per task run; multi-agent pipelines can reduce this by routing simple cases to smaller models
- **Debugging multi-agent is harder than single-agent** — LangChain's State of AI Agent Engineering survey found 28% of developers cite debugging difficulty as their biggest challenge, rising with complexity
- **Observability without evals** — 89% of organizations have observability for agents but only 52% have evaluation frameworks; multi-agent systems amplify this gap

## The Move

The four orchestration patterns that cover most production use cases, in order of complexity:

### 1. Hierarchical (most common in production)
A director agent decomposes a goal and delegates sub-tasks to specialist agents. Used at Amazon (thousands of agents across orgs since 2025), Opensoul (6-agent marketing stack with Director/Strategist/Creative/Producer/Growth/Analyst roles), and Netguru's Omega internal sales agent.

**When to use**: Complex, multi-domain tasks where a coordinator needs to plan before acting. When you need role-based accountability.

### 2. Pipeline
Output of agent A feeds into agent B feeds into agent C. No branching, no loops. Simplest multi-agent pattern.

**When to use**: Linear workflows — research → write → edit → publish. The output contract of each stage must be stable.

### 3. Orchestrator-Worker
A central orchestrator decides which workers to call and aggregates their results. Unlike hierarchical, the orchestrator does not do the work itself — it only coordinates.

**When to use**: Parallelizable sub-tasks where the aggregator needs flexibility. When you want the routing logic to be independently testable.

### 4. Peer-to-Peer
Agents communicate with each other as equals. Most flexible, hardest to debug.

**When to use**: Collaborative reasoning tasks. When no single agent has the full picture and agents must negotiate or share partial results.

### Critical decision: When to split

Split when you observe **any** of these symptoms in a single agent:
- Tool selection accuracy below 90% on your eval set
- Latency exceeds threshold on multi-step tasks
- Agent hallucinates tool parameters or invents intermediate steps
- Prompt engineering for the task exceeds 500 tokens and is still unreliable
- The task spans distinct domains (research + writing + verification) that require different model configurations

**Do not split** when the task is bounded and single-step, when you cannot define clean handoff contracts between agents, or when you lack observability for the individual agents.

### Typed handoffs are non-negotiable

The most common failure in multi-agent systems is untyped handoffs — one agent produces freeform output that the next agent has to parse. Use structured outputs (Pydantic models, JSON schemas) at every boundary. This is the single highest-leverage change teams make when moving from PoC to production.

## Evidence

- **Market data (Nov 2025):** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025; 57% of organizations already running agents in production, but Gartner predicts 40% of agentic AI projects will be canceled by 2027 due to cost and reliability issues — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Production cost data:** 49% of organizations cite high inference cost as their top blocker; complex single-agent tasks run $5-8 per task in inference — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Enterprise production stack:** Netguru's Omega (production sales agent) uses GPT-4o via Azure OpenAI, AutoGen for orchestration, Langfuse for observability, and Promptfoo for evals — [Netguru](https://www.netguru.com/blog/ai-agent-tech-stack), June 2025
- **Multi-agent marketing stack:** Opensoul ships 6 agents (Director/Strategist/Creative/Producer/Growth/Analyst) on Paperclip orchestration, running on scheduled heartbeats with autonomous task delegation — [Hacker News/Opensoul](https://news.ycombinator.com/item?id=47336615)
- **Amazon agent evaluation framework:** Thousands of agents in production required new eval methodologies beyond single-model benchmarks; HITL (human-in-the-loop) became critical for multi-agent systems due to emergent failure modes — [AWS/Amazon ML Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Debugging challenge confirmed:** 28% of AI agent developers cite debugging difficulty as their biggest challenge; 20% cite latency — [LangChain State of AI Agent Engineering survey, cited by Agenticai Flow](https://agenticai-flow.com/en/posts/ai-agent-development-pitfalls-and-solutions-2025)

## Gotchas

- **Do not start multi-agent with an untyped handoff problem** — define the schema for what each agent produces and consumes before writing any agent code
- **Observability without evals is theater** — 89% of teams have traces; only 52% have actual eval suites; multi-agent failures compound silently without eval coverage
- **The coordinator is the most critical agent** — a bad orchestrator poisons every downstream agent; invest disproportionately in its prompt and eval
- **Inference cost is not linear with quality** — routing simple queries to a 32k context model instead of a frontier model can cut costs by 10x with minimal quality loss on the right task type
- **AutoGen entered maintenance in October 2025** — successor is Microsoft Agent Framework (MAF); new projects should use MAF or LangGraph, not AutoGen
