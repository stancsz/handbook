# S-418 · The Reliability Ceiling

Most agent architectures top out at 85–90% task completion on non-trivial workflows. Teams that don't know this spend months building demos that fail silently in production.

## Situation

You run an agent to automate document review, lead triage, or ticket routing. It works beautifully in testing. In production, it silently succeeds at 6 of 7 steps, hallucinates the 7th, and outputs a well-formatted answer that is completely wrong. The user reads it, trusts it, acts on it. This is the reliability ceiling — and most teams discover it the hard way.

## Forces

- **Agents that look like successes are the most dangerous failures.** Coherent, well-formatted output that is factually wrong is worse than an obvious error. Traditional software crash rates would be treated as severity-1 incidents; agent failure rates of 10–15% are treated as expected.
- **The demo-to-production gap is structural, not incidental.** Demos run on curated inputs with human oversight. Production runs on messy real-world data, silent loops, and unattended execution. The architecture that works in a notebook fails in production not because of bugs but because of compounding edge cases.
- **More agent complexity means more failure surfaces.** Every additional tool call, LLM decision, and multi-step reasoning increases the probability of a silent failure somewhere in the chain. The reliability ceiling isn't a fixed number — it drops as workflow complexity rises.
- **Evaluation is the bottleneck nobody talks about.** Automated metrics fail to capture coordination failures, subtle hallucinations, and context drift. Human-in-the-loop evaluation at scale is expensive and slow, but the alternatives miss failures that matter.

## The move

**Design for the ceiling, not the demo.**

- **Build deterministic scaffolding around LLM decision points.** Use a state machine or DAG workflow engine (Temporal, LangGraph) to control execution topology. Let the LLM decide *what* to do at bounded decision nodes — not *how* to sequence the work. The scaffold prevents the agent from drifting into undefined states.

- **Separate the critical path from the reasoning path.** For high-stakes outputs, use the agent to draft and the deterministic layer to verify. The scaffold runs the checklist; the model does the creative work. This halves the reliability ceiling collapse on consequential tasks.

- **Add hard circuit breakers before adding features.** Every agent loop needs: a maximum step count, a budget cap (with per-step cost tracking), a timeout per tool call, and a dead-letter queue for unresolvable states. Cost overrun incidents range from $15 in 10 minutes to $47,000 over 11 days — alerts alone are insufficient; enforcement is required.

- **Evaluate like Amazon: HITL on coordination, automated metrics on components.** Single-agent accuracy is testable with LLM-as-judge or ground-truth comparison. Multi-agent coordination failures require human reviewers watching inter-agent communication. Evaluate at the right granularity — not everything needs human review, but inter-agent handoffs almost always do.

- **Accept 85% and build for it.** Rather than engineering toward 100% on simple tasks, design the human-in-the-loop checkpoint at the right failure probability. For 1-in-10 failures, add review at the output stage. For 1-in-20, automated sampling with human audit is sufficient. The question is not "how do we eliminate failures" but "where do failures cost the least to catch."

## Evidence

- **Production study — 12 months, 14 live agents:** After a year of real-world deployments, the consistent finding is an 85–90% task completion ceiling on non-trivial workflows. The most dangerous failure mode is "the agent completes the task but produces a wrong result that looks right." Viqus documented that 1 in 10 users experiences a failure that a traditional software team would consider severity-1. — [Viqus Blog: What We Learned Deploying AI Agents in Production for 12 Months](https://viqus.ai/blog/ai-agents-production-lessons-2026)

- **Enterprise evaluation framework — Amazon AI agents:** HITL evaluation is critical for multi-agent systems specifically because automated metrics fail to capture coordination failures, inter-agent communication breakdowns, conflict resolution failures, and logical inconsistencies when multiple agents contribute to a single decision. Amazon recommends evaluating inter-agent handoffs separately from individual agent accuracy. — [AWS: Evaluating AI Agents — Real-World Lessons from Building Agentic Systems at Amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

- **Orchestration framework comparison — production teams:** LangGraph is favored by teams with strict reliability requirements because its graph-based state machine gives explicit control over execution topology. CrewAI is favored for rapid prototyping. The key insight: production teams systematically choose explicit control over flexible scaffolding as reliability stakes rise. — [Nexus: LangGraph vs CrewAI — Multi-Agent Orchestration Compared (2025)](https://agent.nexus/blog/langgraph-vs-crewai)

## Gotchas

- **"The agent worked in testing" is not a reliability signal.** Testing covers the happy path. Production uncovers the edge cases where the agent calls the right tool with slightly wrong parameters, completes the task but in the wrong format, or drifts into a retry loop that burns tokens without progress.
- **Automated evaluation metrics will miss the failures that cost you.** LLM-as-judge works for single-output accuracy. It does not reliably catch subtle hallucinations, format drift, or coordination failures between agents. Budget the human review hours accordingly.
- **The 85% ceiling is for simple workflows.** It drops to 60–70% for multi-step tasks with tool orchestration, and to 40–50% for open-ended research tasks. Do not benchmark on simple tasks and assume the same ceiling applies to complex ones.
