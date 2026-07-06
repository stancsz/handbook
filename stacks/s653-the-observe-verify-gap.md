# S-653 · The Observe-Verify Gap

Most agentic teams have invested in tracing. Fewer have invested in knowing whether their agents are actually right. Observability tells you what happened. Evals tell you whether it was correct. The gap between them is where production agents silently degrade — and where debugging multi-agent failures becomes "mostly guesswork."

## Forces

- **Tracing is cheap and built-in.** LangSmith, Phoenix, and Langfuse make it trivial to log every LLM call, tool invocation, and token count. 89% of teams with agents in production have this.
- **Evals require deliberate design.** Good evals need golden datasets, scoring rubrics, and recurring runs. They're slow to build and easy to defer. Only 52% of teams have them.
- **Multi-agent failure is compounding.** An error in one agent propagates to the next. Without evals at each handoff boundary, you discover the cascade only when the output is wrong — and by then, tracing tells you what broke, not why the system let it break.
- **Naive eval is not eval.** Passing a prompt with expected inputs and outputs through once is a sanity check, not a monitoring system. Real evals run against regressions, drift, and edge cases across versions.

## The Move

Separate observability (what happened) from evaluation (was it correct), and instrument both with the same trace context so failures link to their cause.

- **Build evals at agent handoff boundaries, not at the workflow level.** Multi-agent handoffs are where schemas drift and context drops. Each boundary gets a contract: "did the output match the expected schema and intent?" RaftLabs calls untyped handoffs the #1 killer of multi-agent workflows — every boundary needs validated schemas with version numbering.
- **Start with deterministic checks.** Linting, test runners, schema validation, and rule-based feedback are fast, cheap, and catch the low-hanging fruit before you need LLM-as-judge. Hook these into CI — not just manual review.
- **Use LLM-as-judge for quality dimensions that rules can't catch.** Semantic correctness, tone, relevance, and reasoning quality require an LLM evaluator. Run these on a sample (10–20%) of production traces, not every call — cost compounds fast.
- **Co-locate traces and eval results.** LangSmith, Arize Phoenix, and Langfuse all support attaching eval scores to traces. When a workflow fails, the trace shows the execution path AND the eval failure in the same view. Without this, debugging a 4-agent pipeline means manually correlating logs across services.
- **Set regression thresholds, not just pass rates.** A 70% pass rate means nothing without knowing what degraded. Track eval scores per agent, per handoff, and per tool call. Alert on delta, not absolute value.
- **Run evals on pre-deploy, not just post-fail.** Integrate eval suites into your deployment pipeline. Anthropic's Agent SDK provides lifecycle hooks for this — plug in your verification logic at the agent level, not just the workflow level.

## Evidence

- **Research:** 89% of agentic teams have observability but only 52% have evals — a 37-point gap that explains why multi-agent debugging is "mostly guesswork." Teams report that observability without evaluation catches failures after the fact; evaluation without observability can't diagnose them. — [RaftLabs: Multi-Agent Systems Architecture Patterns](https://www.raftlabs.com/blog/multi-agent-systems-guide) (Nov 2025)
- **Research:** A 4-agent orchestrator-worker workflow costs $5–8 per complex task in inference alone. Evals run on every deployment compound this cost — which is why sampling strategies and deterministic checks are the production norm, not LLM-judging every trace. — [RaftLabs: Multi-Agent Systems Architecture Patterns](https://www.raftlabs.com/blog/multi-agent-systems-guide) (Nov 2025)
- **Framework guidance:** LangChain's free "Building Reliable Agents" course recommends starting with LangSmith tracing, then layering in structured evaluation datasets (golden inputs + expected outputs), then automating scoring via LLM-as-judge. The course emphasizes that the eval loop — trace → identify failure → add test case → verify fix — is the core reliability practice. — [LangChain Academy: Agent Observability & Evaluation](https://academy.langchain.com/courses/building-reliable-agents) (2025)
- **Framework:** Arize Phoenix is positioned specifically for teams that have LangSmith's observability but want ML-native evaluation — embedding drift detection, retrieval quality metrics, and model performance monitoring alongside LLM traces. — [CTAIO: Agent Observability Tools Comparison](https://ctaio.dev/en/labs/agentic-orchestration/observability-tools) (2025)

## Gotchas

- **A passing eval suite with no coverage of edge cases is theater.** If your golden dataset only covers happy paths, it will pass right up until the first adversarial input.
- **LLM-as-judge has its own hallucination problem.** A judge model that rates outputs too generously creates false confidence. Calibrate judges against human-scored samples, especially when scoring nuanced quality dimensions.
- **Evals become stale if they don't track code changes.** Adding a new tool or changing a prompt without updating the eval suite means your safety net has a hole in it. Treat eval suites as first-class code with the same review process.
- **Cost of evals is often underestimated.** Running LLM-judged evals on every commit against a corpus of 1,000 test cases can cost more than the inference for the agent itself. Budget for this and use sampling strategically.
