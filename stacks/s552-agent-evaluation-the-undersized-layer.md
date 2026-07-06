# S-552 · Agent Evaluation: The Undersized Layer

When a chatbot gives a bad answer, it's annoying. When an agent takes a bad action, it can corrupt data, break a deployment, or send the wrong message to a customer. Teams spend months optimizing agent logic, prompt engineering, and tool schemas — then run production agents with no automated way to detect when output quality degrades. The observability and evaluation layer is the most consistently undersized component of production agent stacks.

## Forces

- Agent output is non-deterministic, making behavioral regression invisible without explicit measurement infrastructure
- Evaluation costs scale with task complexity: multi-agent systems multiply observability requirements by the number of agents and coordination edges between them
- Token costs — the obvious cost driver — are now dwarfed by human oversight and senior engineering time in real production cost breakdowns
- Model provider updates (prompt changes, capability shifts) silently alter behavioral paths without any code change to trigger alerts
- Multi-agent systems compound failure modes: one agent's degraded output becomes the next agent's degraded input, with no trace of where the cascade started
- Automated evaluation frameworks exist but are treated as optional polish rather than production prerequisites

## The move

Build the evaluation and observability layer before you need it, not after a production incident forces it.

- **Log every agent turn as a structured trace**, not just the final output. Capture: input state, model used, tool calls invoked, intermediate outputs, final output, latency, and cost. LangSmith, Arize Phoenix, or a custom event bus — the tool matters less than the fidelity.
- **Define automated eval datasets from day one.** Ground-truth examples for each task type (code generation, summarization, classification, routing). Run regression suites on every model or prompt change, not just when humans notice a regression.
- **Instrument the cost-per-outcome metric, not just per-token.** A $0.0001 call that triggers a $200 human remediation is not cheap. Track cost alongside quality scores across the full resolution path.
- **Emit trace spans for multi-agent coordination edges.** When Agent A delegates to Agent B, the delegation context, decision rationale, and any context transformations must be queryable. Without this, debugging a multi-agent failure means reconstructing the full conversation from memory.
- **Set automated quality gates before production.** Minimum pass rates per task type, hallucination checks against retrieved context, refusal rate monitoring, and cost-per-session thresholds.
- **Treat model updates as deployment events.** Version your evaluation suite alongside your agent code. A new model version requires re-running the full eval suite before routing live traffic.

## Evidence

- **Industry cost analysis:** Token costs now represent only 8% of simple-agent run costs, ~16% of RAG agent costs, and ~27% of multi-agent costs. The dominant line in all three classes is senior engineering oversight. Teams optimizing token spend while ignoring evaluation overhead are solving the wrong budget. — *Digital Applied, "AI Agent Build & Run Cost Index 2026" (July 3, 2026)* — https://www.digitalapplied.com/blog/ai-agent-build-run-cost-index-2026

- **Practitioner architecture guide:** "Not investing in agent output evaluation early enough. Knowing whether an agent's output is good requires more than human review. Automated evaluation — comparing outputs against known-good examples, scoring for specific quality criteria, tracking quality trends over time — should be built from the beginning, not retrofitted when you notice quality drift." — *Keneland.com, "Building Production Agentic AI Systems: A Practitioner's Architecture Guide" (June 2026)* — https://keneland.com/blog/building-production-agentic-ai-systems-a-practitioner-s-architecture-guide

- **End-of-year production retrospective:** Four categories shipped to production in 2025 (developer tooling, internal ops automation, research/analysis, customer support augmentation). In all four, the teams that stalled or rolled back were the ones without automated eval — quality drifted silently until user complaints triggered firefighting. — *Technspire, "State of Agentic AI End-2025: What Made It to Production" (December 18, 2025)* — https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons

- **HN multi-agent stack discussion:** "If you are not saving your context for decision making and your context window is filling up — you are losing important data. Most production agent systems I have seen undersize evaluation until they have a production incident." — *HN user camkego, comment on HN thread on agent stack stratification (2025)* — https://news.ycombinator.com/item?id=47114201

## Gotchas

- **LangSmith and Phoenix are not the same category.** LangSmith is an opinionated hosted platform with eval pipelines built in. Phoenix (Arize) is an open-source observability layer you host yourself. Teams using Phoenix still need to build their own eval runner on top of it; don't assume the observability platform solved eval.
- **Human review is a floor, not a ceiling.** Spot-checking outputs does not catch quality drift that happens gradually across hundreds of sessions. Automated regression suites with statistical sampling are required at scale.
- **Multi-agent eval is harder than single-agent eval.** You need to evaluate not just each agent's output, but the quality of the handoff between agents — whether the delegation context was sufficient, whether the receiving agent's output would have been better with different upstream context.
- **Cost-per-outcome requires outcome labeling.** You can't compute cost per successful outcome without a label for whether each outcome succeeded. Build this into the feedback loop from the start, not as a post-hoc analysis.
- **Eval data is as valuable as the agent code itself.** Teams that don't version their eval datasets lose reproducibility. Eval data belongs in the same repo, with the same review process, as the agent code it validates.
