# S-281 · Agent Evaluation Is the Missing Layer Nobody Builds Until Production Breaks

Teams instrument their APIs, monitor their databases, and alert on their infrastructure — but most agentic systems ship with no automated evaluation layer at all. The result: quality drift goes invisible for weeks, regression goes undetected until a customer reports it, and cost anomalies don't surface until the monthly bill arrives. Evaluation is the unsexy, underfunded layer that separates production-grade agents from expensive prototypes.

## Forces

- **LLM outputs resist automated checks.** Unlike deterministic code, agent outputs need ground-truth comparison, task-completion scoring, and behavioral regression detection — none of which traditional CI handles.
- **Evaluation is harder than building.** A naive test suite that asserts "output contains X" misses the real failure modes: hallucination, tool misuse, context poisoning, and goal abandonment. Building meaningful evals takes more engineering than building the agent.
- **Human review doesn't scale.** At 100 agent runs/day, manual review is feasible. At 10,000, it is not. Teams that defer automated evaluation hit a wall when they try to ship faster.
- **The eval loop must match the agent loop.** Agents act, observe, and retry. Evaluating them requires matching that cycle — checking not just the final output but the tool calls made, the state transitions, and whether the agent recovered from errors.
- **Quality drifts without data.** RAG freshness degrades. Model versions change. Prompt drift accumulates. Without a continuous evaluation signal, degradation is indistinguishable from normal variance.

## The Move

Build evaluation into the agent loop from day one — not as a post-production QA step, but as a first-class component with the same engineering rigor as the agent itself.

**Structured eval categories that catch real failure modes:**

- **Task completion rate** — did the agent achieve the stated goal, not just produce plausible text? Use deterministic check functions where possible (e.g., "did the ticket get created with the right fields?"). For subjective tasks, use LLM-as-judge with a rubric.
- **Tool call accuracy** — is the agent calling the right tools with the right parameters? Track precision, recall, and false-positive rates per tool. A single bad tool call can make the entire run worthless.
- **Hallucination rate** — does the agent's output match the retrieved grounding context? Factual consistency checks against RAG sources catch the most dangerous failures: confident wrong answers.
- **Cost per task type** — token consumption segmented by agent task type, model tier, and pipeline stage. Flag anomalous spend before month-end.
- **Behavioral regression** — run golden-dataset eval sets on every significant change. A 3% regression on task-completion rate across 20 task types is easy to miss in human review; automated regression detection catches it immediately.

**Evaluation infrastructure patterns that scale:**

- **Golden datasets with known-good outputs.** Curate 50-200 representative task examples per agent role with expected outputs and key decisions. Run against every build. Store results in a time-series DB (e.g., TimescaleDB, SQLite) to track trends.
- **LLM-as-judge with structured rubrics.** Where deterministic checks aren't possible, use a judge model with a scored rubric (1-5 on specific criteria). Consistency matters more than accuracy — judge the same way every time.
- **Shadow mode production evals.** Route a sample (1-5%) of production agent runs through the eval pipeline alongside normal execution. No latency impact; continuous quality signal. Many teams report 3-5% of production runs reveal eval-worthy issues they never knew existed.
- **Observability with traces, not logs.** LangSmith, Phoenix (by Arize), or custom OpenTelemetry traces capture the full agent execution graph: state transitions, tool calls, LLM calls, and outputs. Logs tell you what happened; traces tell you why the agent made each decision.
- **Cost anomaly alerting.** Set per-task-type budget thresholds. Alert when a single run exceeds 2x the p95 cost for its category — catches infinite loops, tool-call storms, and context stuffing before they drain budget.

**Tool choices by stage:**

| Stage | Recommended Tools | Notes |
|---|---|---|
| Tracing & observability | LangSmith, Arize Phoenix, OpenTelemetry | Phoenix wins on open-source flexibility; LangSmith wins for LangChain/LangGraph shops |
| Eval frameworks | RAGAs, DeepEval, custom judge pipelines | RAGAs for RAG quality; DeepEval for general LLM app regression |
| Golden dataset storage | TimescaleDB, SQLite, CSV + DVC | Track version history; treat like model weights |
| Regression CI | GitHub Actions, Buildkite | Run golden eval on every PR; gate merge on regression threshold |

## Evidence

- **Blog: Keneland — "Building Production Agentic AI Systems"** — Practitioner notes that automated evaluation (comparing outputs against known-good examples, scoring for specific quality criteria, tracking quality trends over time) should be built from the beginning, not retrofitted when quality drift becomes noticeable. Also notes the failure mode: teams don't know whether their agent is right, wrong, or uncertain. — [https://keneland.com/blog/building-production-agentic-ai-systems-a-practitioner-s-architecture-guide](https://keneland.com/blog/building-production-agentic-ai-systems-a-practitioner-s-architecture-guide)
- **Blog: Xcapit — "The Real Cost of Running AI Agents in Production" (Nov 2025)** — Documents that observability/monitoring accounts for 10-20% of total production cost, and that monitoring quality metrics (retrieval hit rate, hallucination rate, grounding check failures, token efficiency) is the non-negotiable foundation. Notes LLMs and RAG systems degrade over time without measurement — retrieval quality, generation relevance, and grounding accuracy must be tracked continuously. — [https://www.xcapit.com/en/blog/real-cost-ai-agents-production](https://www.xcapit.com/en/blog/real-cost-ai-agents-production)
- **MLOps World 2025, Digits presentation** — Hannes Hapke (co-author of *Generative AI Design Patterns and Machine Learning Production Systems*) shared implementation details on production agent evaluation components: trace-based instrumentation, automated quality scoring, and regression detection for agent behavior changes. — [https://digits.com/blog/mlops-world-2025-slides](https://digits.com/blog/mlops-world-2025-slides)

## Gotchas

- **Don't evaluate what you can't define.** If you can't articulate what "good" looks like for a given task, you can't build a meaningful eval. Write the rubric before the agent, not after.
- **LLM-as-judge is consistent but biased.** The judge model shares blind spots with the agent model. Use deterministic checks wherever possible; use LLM-judge only for dimensions where deterministic evaluation is infeasible.
- **Sampling bias in shadow mode.** If production traffic skews toward easy cases, a 1% sample underrepresents failure modes. Stratify your eval sample to cover the full distribution, not just what users happen to ask.
- **Eval infrastructure rot.** Golden datasets that aren't maintained become noise within a quarter. Assign ownership, automate freshness checks, and retire stale test cases.
- **Cost eval is downstream of behavior eval.** Catching a $50K/month spend anomaly requires knowing what $50K/month looks like — which requires behavioral evaluation baselines first. Don't start with cost; start with task completion and work up.
