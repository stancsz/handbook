# S-438 · The Trace vs. Eval Gap

You instrumented your agent. Traces are flowing. You still cannot explain why it failed last Tuesday at 3am — because traces tell you what happened, not whether it was right.

## Forces

- **Breadth vs. depth** — LangSmith, Phoenix, and custom logging cover every step; teams mistake coverage for validation
- **Debugging confidence vs. actual correctness** — a trace showing a successful tool call followed by confident nonsense looks identical to a trace showing a correct answer
- **Eval infrastructure vs. product velocity** — evals require golden datasets, behavioral tests, and maintenance; traces are a one-line SDK install
- **Multi-agent compounding** — every additional agent multiplies the number of failure modes; 4-agent workflows ($5–8/task inference cost) are routine, yet debugging tools have not caught up

## The move

Trace everything. But define three distinct layers — each answers a different question:

- **Layer 1 — Traces:** What happened? Every LLM call, tool invocation, and state transition logged. LangSmith Phoenix, or custom JSON-L structured logs. Minimum viable observability.
- **Layer 2 — Evals:** Was it correct? Structured scoring against a golden dataset or behavioral assertions. Covers hallucination detection, tool-call accuracy, output format compliance. Without this layer, you are guessing.
- **Layer 3 — Assertions:** Will it stay correct? Regression suites that run on every deploy or on a schedule. Catch model-version regressions before users do.

The gap: 89% of teams have traces; only 52% have evals. That 37-point spread is where production debugging becomes archaeology.

### Practical stack

- **Traces:** LangSmith (for LangChain/LangGraph), Arize Phoenix (open, model-agnostic), or self-hosted OpenTelemetry → ClickHouse/Postgres
- **Evals:** RAGAs, Braintrust, LangSmith Evals, or custom Pydantic-based assertion suites
- **Golden datasets:** Build incrementally — save every confirmed failure as a test case
- **Model regression guard:** After upgrading a model or changing a prompt, run the full eval suite; track scores over time

### Evaluating multi-agent systems

Single-agent evals are hard. Multi-agent evals are harder because:
- Agents produce intermediate outputs that feed into other agents
- A failure at step 3 of 7 is invisible in the final output
- Coordination failures (wrong agent called, stale context passed) don't show up in end-to-end metrics

Per Amazon's published lessons from building agentic systems at scale: HITL (human-in-the-loop) evaluation becomes critical for multi-agent because automated metrics fail to capture emergent miscoordination. Specific dimensions that require human judgment: inter-agent communication quality, task decomposition appropriateness, conflict resolution logic, and whether collective behavior serves the business objective.

### Untyped handoffs are the #1 multi-agent failure mode

Before investing in observability tooling, type your agent interfaces. A 4-agent pipeline where Agent A passes a freeform string to Agent B produces failures that look like hallucination, context overflow, or bad reasoning — when the real cause is a schema drift at the handoff boundary.

## Evidence

- **Industry survey:** 89% of teams have observability; 52% have evals. Multi-agent debugging is described as "mostly guesswork" — *RaftLabs, Multi-Agent Systems: Architecture Patterns for Production AI (Nov 2025)* — https://www.raftlabs.com/blog/multi-agent-systems-guide
- **Gartner finding:** 1,445% surge in multi-agent system inquiries (Q1 2024 → Q2 2025); 57% of organizations already have agents in production; 40% of agentic AI projects at risk of cancellation by 2027. Primary cited blocker: inference cost (49%); under-invested in validation infrastructure is the compounding factor — *RaftLabs citing Gartner, same source*
- **Amazon engineering:** HITL evaluation is critical for multi-agent systems because automated metrics fail to capture inter-agent coordination failures, task decomposition appropriateness, conflict resolution logic, and collective behavior alignment. Evaluation must assess: inter-agent communication quality, specialization appropriateness, conflict resolution strategies, logical consistency across agent contributions — *AWS ML Blog, "Evaluating AI agents: Real-world lessons from building agentic systems at Amazon" (2025)* — https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon
- **Cost benchmark:** Inference costs compound to $5–8 per complex task for a 4-agent workflow. 76–100% of AI budgets are spent on inference for nearly half of teams — *RaftLabs, same source above*

## Gotchas

- **Traces without evals are a false guarantee** — you know what happened, not whether it was right. Every production incident will find you replaying traces looking for the bug.
- **Golden datasets rot** — model upgrades, prompt changes, and product updates all invalidate test cases. Budget eval maintenance as ongoing work, not a one-time setup.
- **Multi-agent traces cross agent boundaries** — standard distributed tracing tools often lose context when switching agents. Verify your instrumentation handles cross-agent state propagation before you need it.
- **The "it worked in the trace" trap** — an agent that calls the right tool with the wrong parameters looks identical to one that calls the right tool correctly. Parameter validation belongs in the eval layer, not just the trace layer.
