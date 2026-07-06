# S-588 · Typed Schemas at Agent Boundaries

When two agents hand off work, the handoff is the failure point. Without enforced schemas, a researcher agent that outputs "the data looks fine" becomes the input to a writer agent that needs exact column names, date ranges, and confidence intervals. Typed schemas are the load-bearing contracts that make multi-agent workflows actually work.

## Forces

- **LLM output is untyped by default.** An agent can return prose, a dict, a partial JSON, or nothing recognizable. Every consumer agent must either guess or fail.
- **Schema drift accumulates invisibly.** A producer agent changes its output format in v2. The consumer agent was never notified. Both fail silently until a human notices the downstream report is wrong.
- **The boundary is where observability ends.** Most agent debugging stops at "did it call a tool?" The schema contract between agents is invisible in traces unless explicitly instrumented.
- **Typed handoffs force design upstream.** When you must define the output schema before writing the producer agent, you clarify the task. The schema is the spec.

## The move

Enforce versioned, typed schemas at every agent-to-agent boundary. Not as best-practice gentle advice — as a hard gate in the execution pipeline.

- **Define schemas before agents.** The consumer agent's required inputs are the producer agent's output spec. Write the schema first, then build the agent.
- **Use Pydantic or Zod models**, not JSON-schema strings. Type-safe serialization catches contract violations at parse time, not at runtime when the downstream agent tries to read a field.
- **Version every schema.** Append `_v2`, `_v3` to schema names. When the producer changes output format, increment the version. The consumer explicitly declares which schema version it accepts.
- **Gate on schema compliance.** Before an agent output flows to the next agent, validate it against the expected schema. Reject and retry, don't pass garbage downstream.
- **Mirror your internal data contracts.** If your microservices use protobuf or Avro, your agent handoffs should use the same types. Consistency reduces translation errors at org boundaries.
- **Document schema semantics, not just structure.** A field named `timestamp` can mean "when the event occurred" or "when we received it." Write the distinction in the schema docstring.

## Evidence

- **Blog: Multi-Agent System Design (2026):** "Untyped handoffs between agents kill multi-agent workflows faster than any other issue. Every agent-to-agent boundary needs a validated schema with version numbering." — https://baeseokjae.github.io/posts/multi-agent-system-design-guide-2026
- **HN / tech blog (2025):** "If you are not saving your context for decision making and your context is unstructured, you're going to have a bad time" — a primary failure mode observed in partial-AI software development workflows where agent-to-agent communication was untyped. — https://news.ycombinator.com/item?id=47114201
- **Blog: 4 Pitfalls of Agentic Engineering (2026):** "Skills aren't silver bullets; they're soft constraints" — the failure to hard-enforce output format means agents drift from intended behavior over iterations, a symptom of missing structural contracts. — https://kieranzhang.dev/blog/agentic-4-pitfalls

## Gotchas

- **Over-specifying is as bad as under-specifying.** If your schema has 47 required fields, producers will start mocking the values just to pass validation. Keep schemas minimal and focused on the handoff contract, not the full data model.
- **Schema validation adds latency.** Validate once at the boundary, not repeatedly inside each agent. Pipelining validation before the agent runs (as a pre-flight check) is cheaper than failing mid-workflow.
- **Versioning creates compatibility debt.** Every schema version needs a migration path. A schema registry with deprecation windows is worth building on day one, not retrofitting after v1 breaks everything.
- **Human-in-the-loop breaks the typed contract.** When a human reviews agent output before handoff, the schema validation is bypassed and the downstream agent receives human-polished but untyped content. Treat human review as a separate step with its own schema.
