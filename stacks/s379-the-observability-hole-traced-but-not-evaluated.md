# S-379 · The Observability Hole — Traced but Not Evaluated

You have traces. LangSmith is showing you every LLM call, every tool invocation, every token. You have spans, trees, latency histograms. But when the agent fails in production, you still don't know *why* — and the traces tell you exactly nothing about semantic correctness. This is the observability hole: teams instrumenting agents for operational visibility while leaving semantic quality completely dark.

## Forces

- **Traces measure what the system *did*; evals measure whether the output was *right*.** A trace can show that the agent called the right tool with the right arguments — but not whether the resulting answer was accurate, grounded, or safe for the use case
- **LLM outputs are semantically opaque to traditional APM.** HTTP 200 can deliver a confident hallucination. Latency is green while answer quality is red. Datadog and New Relic were never built for this class of failure
- **89% of teams have observability but only 52% have evals** — the gap is structural, not negligent. Evals are harder: they require ground truth, reference datasets, and judgment criteria that don't change per prompt
- **The debug loop breaks at the wrong layer.** When a user reports "the agent gave a wrong answer," traces tell you what happened; evals would have caught it before the user did

## The move

Build evals as first-class infrastructure, not as a post-launch afterthought. Treat them like unit tests for your agent's *reasoning*, not just its connectivity.

**Minimum viable eval stack for production agents:**
- **Trace + eval pairing** — every production trace should have a corresponding eval result attached. LangSmith supports this natively; Langfuse and Arize Phoenix can do it via API
- **Reference-free metrics as a floor** — use RAGAS-style faithfulness, answer relevancy, and context precision scores (computed via LLM-as-judge) so you don't need a golden dataset to start
- **Retrieval precision ≥ 70%, generation groundedness ≥ 90%, end-to-end task success ≥ 85%** as production guardrails
- **Pytest/CI integration** — run evals in the deployment pipeline, not just in notebooks. DeepEval's native Pytest integration makes this the lowest-friction path for Python stacks
- **Eval the retrieval step, not just generation** — the leading cause of agent failure in production is bad retrieval, not bad generation. Your eval suite should measure recall, precision, and context relevancy independently

**Observability platform selection by constraint:**

| Platform | When to pick |
|---|---|
| **LangSmith** | Already using LangChain/LangGraph; need end-to-end tracing with built-in eval UI; willingness to pay ~$200/mo |
| **Langfuse** | Self-hosting requirement; open-source preference; need full control over data; team ≤ 10 |
| **Arize Phoenix** | RAG evaluation focus; drift detection priority; already using OpenTelemetry |

## Evidence

- **Gheware DevOps AI Blog:** LangGraph dominates enterprise with 90,000+ GitHub stars across the LangChain ecosystem; 65% of teams building with LangGraph eventually need to rewrite their orchestration — observability debt is cited as a primary driver
  — [devops.gheware.com](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **RaftLabs:** 89% of organizations have agent observability in place, but only 52% have evals — a gap that explains why multi-agent debugging is "mostly guesswork" in production. Multi-agent inference costs $5–8 per complex task; debugging those tasks without evals means every failure is a manual investigation
  — [raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **TURION.AI:** Arize Phoenix is the preferred choice for RAG evaluation and drift detection. Langfuse provides self-hosting as a first-class option. LangSmith leads on LangChain integration but carries a $200+/month cost floor. Direct cost comparison: Langfuse self-hosted vs. LangSmith hosted is a data-sovereignty decision more than a feature decision
  — [turion.ai/blog/langsmith-vs-langfuse-vs-arize-phoenix/](https://turion.ai/blog/langsmith-vs-langfuse-vs-arize-phoenix/)

## Gotchas

- **Evals drift with model versions.** The same eval suite can report different pass rates when you switch from GPT-4o to Claude 3.5 Sonnet — benchmark your eval suite itself before treating it as ground truth
- **LLM-as-judge has its own hallucinations.** Using a cheaper model as the judge for a more expensive model's outputs creates systematic bias. Calibrate your judge model separately from your agent model
- **Coverage is not correctness.** Running 1,000 evals against the wrong distribution of inputs (e.g., only happy-path queries) gives you false confidence. Sample your eval sets from production traffic, not from curated test cases
