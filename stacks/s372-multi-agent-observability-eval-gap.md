# S-372 · The Multi-Agent Observability Trap: Visibility ≠ Veritude

You have traces for everything. LangSmith shows every LLM call. OpenTelemetry captures every tool invocation. You can replay any agent session. But you still can't answer: "Is my agent actually getting better?" The gap isn't monitoring — it's evaluation. Teams building multi-agent systems have built pipelines to *see* agent behavior. Far fewer have built the infrastructure to *judge* it.

## Forces

- **Observability is easy to bolt on; evaluation requires domain-specific ground truth.** Tracing a 12-step agent pipeline is a logging problem. Defining whether step 7's output is actually correct is a business logic problem that requires human-labeled data, golden outputs, or formal specifications most teams don't have.
- **Multi-agent complexity multiplies the eval surface area.** A single-agent eval covers one behavior path. A 4-agent orchestrator-worker workflow has exponentially more interaction states — inter-agent handoff quality, conflict resolution, role adherence, emergent behaviors that only appear under specific agent combinations.
- **The eval gap compounds with scale.** At 10 agents and 50 concurrent sessions, the observability stack generates gigabytes of trace data. But without automated evals, you discover quality regressions only through user complaints or manual spot-checks.
- **Automated metrics lie for agentic systems.** BLEU scores, ROUGE, exact-match — none of these capture whether an agent chose the right tool, decomposed a task correctly, or handled an edge case gracefully. The signal lives in process, not output.

## The Move

Separate *tracing* (capturing what happened) from *evaluation* (judging whether it was correct), and build both with the same rigor.

### For tracing — capture the decision graph, not just calls
- Record tool selections, routing decisions, and state transitions as structured events, not just log lines
- Use span-level metadata to capture: agent role, task decomposition level, retry count, fallback triggered
- Tag handoff points between agents with both sender intent and receiver interpretation

### For evaluation — build a three-tier eval stack
- **Tier 1 — Automated process metrics:** Tool selection accuracy, handoff schema validation, output format correctness. These run on every commit and catch regressions.
- **Tier 2 — LLM-as-judge on behavioral dimensions:** Use a strong model to score agent outputs on criteria that require judgment (relevance, coherence, role adherence). Not perfect but fast and directional.
- **Tier 3 — Human-in-the-loop for edge cases:** Sample the top 1-5% of high-stakes or anomalous sessions for human review. Amazon's guidance: human evaluation is critical for assessing "coordination failure in specific edge cases" and "whether agent specialization aligns with agent capabilities."

### For multi-agent specifically — eval the contracts, not just the endpoints
- The highest-value eval for multi-agent systems isn't "did agent A output something correct?" — it's "did agent B receive what it needed from agent A?" Validate the schema compatibility at every handoff boundary
- Use deterministic schema validators (JSON Schema, Pydantic) on every inter-agent message — catching type drift before it becomes a runtime failure

## Evidence

- **Research report:** 89% of organizations running multi-agent systems have observability tooling, but only 52% have evaluation frameworks — the gap explains why multi-agent debugging remains "mostly guesswork" despite mature trace infrastructure. — [RaftLabs: Multi-Agent Systems Architecture Patterns](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Enterprise guidance:** In multi-agent evaluation, HITL is critical for assessing "inter-agent communication to identify coordination failure in specific edge cases, evaluating the appropriateness of agent specialization and whether task decomposition aligns with agent capabilities, and validating potential conflict resolution strategies when agents produce contradictory recommendations." — [AWS/Amazon: Evaluating AI Agents](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)
- **Industry risk signal:** Gartner projects over 40% of agentic AI projects will be canceled by end of 2027, with inadequate evaluation cited as a root cause — organizations can ship agents but can't demonstrate they work correctly. — [Gartner via Microsoft Learn](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/multi-agent-patterns)

## Gotchas

- **LLM-as-judge is useful but not authoritative.** It's fast and cheap for regression detection, but it inherits the judge model's biases and can miss domain-specific correctness criteria. Use it as a sieve, not a verdict.
- **Eval datasets rot faster than code.** Agent behavior changes with model updates, prompt changes, and tool schema changes. If your evals are based on last quarter's agent behavior, they're measuring the wrong thing.
- **Tracing everything is the wrong default.** A 4-agent workflow with full trace capture generates ~10x more data than a single-agent workflow. Be selective — capture decision points, handoffs, and error conditions; log routine execution at lower verbosity.
