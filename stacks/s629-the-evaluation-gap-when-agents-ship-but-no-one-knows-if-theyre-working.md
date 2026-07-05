# S-629 · The Evaluation Gap: When Agents Ship but Nobody Knows If They're Working

Your agent passed the demo. It handles the happy path beautifully. Six months in production, nobody has checked whether it's actually doing what you think it is — because the tooling to do that cleanly didn't exist. Until recently.

## Forces

- **LLM eval benchmarks don't transfer to agents.** Traditional benchmarks (MMLU, HumanEval) test a single model's capabilities. Agentic systems add tool use, multi-step reasoning, state mutation, and human oversight — dimensions those benchmarks can't reach.
- **Agent behavior is path-dependent.** A trace that looks fine at step 3 may have taken a bad fork at step 1 and gotten lucky. Single-output grading misses this.
- **Context length makes manual review unsustainable.** Production agents generate thousands of tokens per run. Reviewing even a 1% sample requires dedicated human hours nobody budgets for.
- **Automated metrics lie about reliability.** Answer correctness scores can look high while the agent is calling the wrong tools, looping unnecessarily, or ignoring guardrails — all silently.

## The move

Treat agent evaluation as a first-class engineering concern, not a post-launch afterthought. The production teams that actually know whether their agents are working have built this stack:

**1. Trace everything, not just outputs.**
LangSmith processes traces from 400+ companies, logging every tool call, LLM call, and state transition per span. Arize Phoenix provides the open-source equivalent with full customization. Phoenix supports LLM-as-judge evaluation that can score faithfulness, answer relevance, and context precision on every run — not just samples. Comet also enables evaluation across 109 production deployments simultaneously.

**2. Use LLM-as-judge with domain calibration, not raw prompting.**
Amazon's AWS agentic systems team found that off-the-shelf judge prompts drift from business standards within weeks. The fix: feed human-labeled examples and few-shot cases into evaluators so scores actually reflect your policy, not generic quality. LangSmith's "Polly" built-in AI assistant specifically surfaces behavioral questions inside traces — "did the agent pick the right tool at step 3?" — rather than scoring final text.

**3. Build offline eval suites into CI/CD, not just online scoring.**
Offline: run candidate versions against a curated test set before deploy. Online: score live traffic to catch regression and drift. Both gates should tie to numeric thresholds — not vibes. Per the LangChain 2025 State of AI Agents report, 57% of organizations have agents in production, but quality (not cost) is now the primary deployment barrier — largely because quality measurement is still immature.

**4. For multi-agent systems, human-in-the-loop is not optional.**
Amazon's evaluation framework identifies three things HITL catches that automated metrics miss: coordination failures between agents (specific edge cases), whether task decomposition aligns with agent capabilities, and when agents produce contradictory recommendations that require arbitration. Evaluators must assess inter-agent communication quality — not just individual outputs.

**5. Set production targets and enforce them.**
Aithinkerlab's 2026 RAG benchmarks define achievable floors: faithfulness ≥0.9, answer relevancy ≥0.85, context precision ≥0.8. These aren't arbitrary — they map to user-facing failure rates. Ship eval thresholds into your pipeline, not just your dashboard.

## Evidence

- **AWS Blog (Amazon AI team):** HITL is critical for multi-agent eval because automated metrics fail to capture coordination failures, decomposition appropriateness, and contradictory recommendations — dimensions only observable through trace inspection and human judgment. — [URL](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)
- **LangChain State of AI Agents 2025:** 57% of organizations now have agents in production; quality (not cost) cited as the primary deployment barrier. LangSmith processes 1T+ spans monthly from 400+ companies. — [URL](https://www.optinampout.com/blogs/agent-observability-transforms-production-ai.html) (citing LangChain 2025 report)
- **Codeables.dev:** LangSmith trace-first design enables per-step behavioral questions ("did agent pick right tool at step 3?") versus scoring only final output. Arize Phoenix provides equivalent open-source eval-via-observability. — [URL](https://codeables.dev/article/langchain-langsmith-vs-arize-phoenix-which-is-better-for-multi-turn)
- **Comet (109 production deployments):** Automated metrics on final outputs miss 73% degradation in reasoning quality when critical info is buried in long contexts — a failure pattern unique to multi-turn agent traces, not single-turn LLM calls. — [URL](https://www.comet.com/site/blog/multi-agent-systems)
- **Aithinkerlab 2026 RAG Guide:** Production targets: faithfulness ≥0.9, answer relevancy ≥0.85, context precision ≥0.8. Agentic RAG with knowledge graphs cut hallucination ~62% across 47 production deployments (May 2026 MLOps Community benchmark). — [URL](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns)
- **Technspire (December 2025):** Four categories shipped reliably in 2025: developer tooling (tight feedback loops), internal ops automation, customer service (narrow scope), and data extraction. The common thread: bounded scope + testable behavior + observable runtime. — [URL](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Vanilla LLM-as-judge drifts.** Off-the-shelf evaluators trained on generic quality corpora don't encode your business rules. Re-calibrate with domain-specific human labels every 4–6 weeks, or scores become noise.
- **Sampling is not observability.** Spot-checking 1% of runs tells you about that 1%. Production agent failures are often path-dependent and non-random — a bad fork at step 1 can produce a correct-looking final output through luck.
- **Context length hides failures.** When agents handle long threads, safety guardrails and company policy instructions get buried in the middle of the context window. The model starts hallucinating tools or crossing persona boundaries. This is a structural problem that better prompting doesn't fix — you need trace-level inspection.
- **Offline evals alone aren't enough.** A test set frozen at deploy time will drift from production distribution. Online scoring catches real-world regression; offline scoring catches pre-deploy regressions. Both are required.
