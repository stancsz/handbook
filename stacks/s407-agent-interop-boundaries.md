# S-407 · Agent Interop Boundaries

When multi-agent systems fail in production, it is almost never because an individual agent broke. It is because the boundary between two agents — what they passed, how they parsed it, and what they assumed — silently collapsed.

## Forces

- **Agents are probabilistic; boundaries need contracts.** The output of one agent is natural language that another agent must interpret. This is not an API contract — it is a shared bet on intent.
- **Adding an agent is not like adding a microservice.** Microservice boundaries carry type schemas and versioned APIs. Agent boundaries carry ambiguity in both directions.
- **The tutorial cliff hides boundary debt.** Framework tutorials show multi-agent demos that work because the author hand-tuned what each agent receives. Production scales the inputs; boundary failures compound.
- **Observability covers the wrong layer.** Teams instrument agent reasoning traces but do not instrument what passes across agent boundaries — until it breaks silently in production.

## The move

Define the interop boundary as a first-class artifact, not a byproduct of the prompt.

- **Schema the contract.** Every agent-to-agent handoff uses a structured output (JSON with a Zod/Pydantic schema, not free text). Even if the receiving agent only uses two fields, the schema forces the sending agent to commit to a shape.
- **Boundary-level logging.** Treat every inter-agent message as an event: timestamp, sender, receiver, payload hash, parse success/failure. This is not agent trace — it is the wire format between agents.
- **Validate before the next agent runs.** Before agent B processes agent A's output, run a validation pass: does it conform to the expected schema? If not, route to a repair or escalation path — do not proceed with a best-effort parse.
- **Keep boundary payloads minimal and intent-rich.** Pass the conclusion and its supporting evidence, not the full chain of reasoning. The receiving agent does not need the entire trajectory — it needs the decision and the context to verify it.
- **Pin the interface, not the implementation.** The contract between agents should be versioned and stable; the internal behavior of each agent can evolve. Changing what agent A outputs should require a boundary schema review, not just a prompt update.
- **Add a human review gate on first deploy.** When a new agent boundary goes live, route outputs to a human review queue for the first N runs. Treat this as calibration, not babysitting — use it to tighten the schema.

## Evidence

- **Engineering blog (Xpress AI):** Documented the "tutorial cliff" — visual programming and async frameworks produce agents that work in demos but fail silently after extended operations. Root cause: the abstraction hides the boundary between what one agent decided and what the next agent received. Published their Xaibo architecture migration to dependency injection and protocol-based modularity as the fix. — [Xpress AI — Operationalizing AI Agents: Lessons from 2025](https://xpress.ai/blog/2025-agent-lessons)
- **Engineering blog (RaftLabs, 100+ AI products shipped):** Multi-agent workflows fail at boundaries — not because individual agents are unreliable, but because the data they pass to each other is unstructured. Recommended treating inter-agent messages as the critical failure surface, not agent prompts. Backed by Gartner data showing 57% of organizations have agents in production but most are getting deployments wrong. — [RaftLabs — Multi-Agent Systems: Architecture Patterns for Production AI](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Primary source (HN, show_hacker):** Opensoul's 6-agent marketing stack revealed that the Director agent's primary failure mode was malformed task cards passed to specialized agents — not agent capability, but boundary contract violations. Each agent's tool schemas were fine; the cross-agent message format was not. — [Hacker News — Show HN: Opensoul](https://news.ycombinator.com/item?id=47336615)

## Gotchas

- Structured output (JSON mode) does not guarantee schema conformance — model outputs can still violate the schema. Validate with a parser, not just generation.
- Over-structuring the boundary kills agent flexibility. The schema should cover what matters for the next agent, not replicate the full internal state of the current one.
- Adding a schema and a validation step looks like overhead until the first silent failure surfaces in production. Boundary contracts pay off in debugging time, not development time.
