# S-249 · The Eval Gap — Why Agents Ship Without Proof

The agent builds and runs. The dashboard shows activity. Nobody knows if it's working.

## Forces

- **Agents have invisible failure modes.** Unlike APIs that return errors, agents produce plausible wrong outputs. A code-review agent that approves bad PRs looks identical to one that approves good ones — until the incident report.
- **Observability and evaluation are not the same thing.** Teams instrument LangSmith traces and see the agent thinking. That is not evidence of correctness — it's a process recording. You can watch a car drive into a ditch.
- **The eval gap compounds with multi-agent.** 89% of teams have observability, only 52% have evals. Add four agents coordinating and you have exponential surface area for silent failure — with inference costs of $5–8 per complex task. You're flying blind and paying per mile.
- **Naive RAG masks eval failures.** 73% of RAG failures originate in retrieval, not generation. The LLM generates a confident answer from bad context. Standard evals won't catch this — you need retrieval-level signal.

## The Move

Build the eval loop before the agent ships, not after the first incident.

- **Layer 1 — Tool/unit evals:** Does each tool do what its schema claims? Use deterministic tests against known inputs and golden outputs. This catches regressions that agent-level evals miss.
- **Layer 2 — Agent-level evals:** Does the agent call the right tools in the right order for known task types? Use LLM-as-judge on curated datasets. Compare trace structure, not just final output.
- **Layer 3 — End-to-end evals:** Does the full workflow produce the correct outcome? Measure task success rate on a held-out evaluation set. This is where multi-agent handoff quality surfaces.
- **Layer 4 — HITL for multi-agent:** Human-in-the-loop is not optional for multi-agent systems. Automated metrics fail to catch inter-agent coordination failures, contradictory recommendations, and emergent behaviors. Amazon's agent team found HITL essential for validating whether task decomposition aligns with agent capabilities and whether collective behavior serves the intended business objective.
- **Instrument retrieval separately.** Before evaluating agent outputs, verify that retrieval is actually working. Track recall@k, measure whether relevant chunks appear in the top-k. If retrieval is broken, the agent is downstream of a broken pipe.

## Evidence

- **Analyst report:** 89% of teams have agent observability but only 52% have evals, and 40% of agentic AI projects are at risk of cancellation by 2027 — Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. — [RaftLabs / Gartner](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Engineering blog:** Amazon's agent evaluation team found automated metrics insufficient for multi-agent systems; HITL is essential for assessing inter-agent communication, conflict resolution, and whether collective behavior serves business objectives. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Benchmarking post:** Naive RAG pipelines fail 40% of the time at retrieval; 73% of RAG failures originate in retrieval, not generation. Score fusion is harder than it looks — BM25 and cosine scores are on different scales, requiring normalization. — [Lushbinary RAG Production Guide 2026](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)
- **HN discussion:** Teams running partial-AI software development note that saving context for decision-making is non-obvious — many agents execute without capturing the reasoning trace needed for post-hoc evaluation. — [Hacker News](https://news.ycombinator.com/item?id=47114201)
- **Framework comparison:** A 4-agent orchestrator-worker workflow costs $5–8 per complex task. Model the economics before committing to architecture — inference cost compounds across agents. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- **LangSmith traces are not evals.** Watching the agent think is observability. Verifying the output is correct on known benchmarks is evaluation. Most teams have the former and call it the latter.
- **LLM-as-judge has a proximity bias.** When the judge uses the same model family as the agent, it tends to rate outputs higher. Cross-validate with a different model family or human raters.
- **Handoffs are the most fragile point in multi-agent systems.** Every agent-to-agent boundary needs a validated schema with version numbering. Untyped handoffs kill workflows faster than any other issue — they produce silent type errors that surface as bizarre agent behavior.
- **Eval datasets rot.** If your evaluation set never changes but your agent keeps improving, you eventually measure nothing. Set a cadence for refreshing golden datasets, at minimum quarterly.
