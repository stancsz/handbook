# S-273 · Untyped Agent Handoffs Kill Multi-Agent Workflows

Multi-agent systems are surging into production — 57% of organizations now run agents live, with Gartner tracking a 1,445% spike in multi-agent inquiries from Q1 2024 to Q2 2025. But the most lethal failure mode isn't the model, the orchestration framework, or the tooling. It's the interface between agents: untyped handoffs that silently corrupt data, cascade errors, and produce wrong outputs at machine speed.

## Forces

- **Multi-agent adoption is outpacing interface design.** Teams rush to deploy more agents but treat the handoff between them as an afterthought — usually a raw string or loosely-typed dict that works in demos and shatters under production noise.
- **Schema drift compounds across agents.** A change to an upstream agent's output format silently propagates to all downstream consumers. Without versioned schemas, a single change can corrupt an entire workflow.
- **The failure is silent, not obvious.** An agent receiving malformed input from a peer may not error — it may just produce plausible-but-wrong output, masking the true cause indefinitely.
- **Eval coverage doesn't match observability coverage.** 89% of teams have observability for multi-agent runs, but only 52% have evals — meaning most teams can see something went wrong but can't automatically prove what, or catch it before shipping.

## The move

Validate every agent-to-agent handoff with a versioned schema contract, enforced before the downstream agent processes the input.

- **Schema contracts with major.minor.patch versioning.** Treat agent output formats like API responses — breaking changes increment the major version, additive changes increment minor, and patches don't affect the interface. Each agent pair negotiates a contract before the workflow ships.
- **Pydantic or Zod validators at every boundary.** Define the expected shape of each handoff explicitly. Fail loudly and immediately if the upstream agent's output doesn't conform — never let malformed data silently propagate to the next agent.
- **The orchestrator validates before routing.** Don't rely on downstream agents to validate their inputs. The orchestrator or routing layer checks compliance before dispatching work to the next agent.
- **Shared schema registry.** All agents in a workflow reference a central schema registry. When a contract changes, the registry is the source of truth and consumers pull the updated schema on next initialization.
- **Fallback behavior at every handoff.** If validation fails, the orchestrator has a predetermined fallback: retry with a different prompt, route to a recovery agent, or fail with a structured error — not a silent downstream hallucination.
- **Track handoff lineage in traces.** Every span or trace should carry the schema version and validation status of the data being passed. This turns a silent failure into a queryable event in LangSmith, Phoenix, or your custom observability layer.

## Evidence

- **Multi-agent blog:** "Untyped handoffs between agents kill multi-agent workflows faster than any other issue. Every agent-to-agent boundary needs a validated schema with version numbering." — [RaftLabs, Multi-Agent Systems: Architecture Patterns for Production AI](https://www.raftlabs.com/blog/multi-agent-systems-guide), November 2025
- **Multi-agent survey:** Four orchestration patterns dominate production: hierarchical, pipeline, orchestrator-worker, and peer-to-peer — each has distinct failure modes, and the handoff problem surfaces in all of them. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide), November 2025; [arXiv:2601.13671](https://arxiv.org/html/2601.13671v1), January 2026
- **Eval/observability gap:** "89% of teams have observability but only 52% have evals. That gap explains why multi-agent debugging is mostly guesswork." — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide), November 2025
- **Production adoption data:** 57% of organizations already running agents in production; Gartner tracked a 1,445% surge in multi-agent system inquiries Q1 2024 → Q2 2025. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide), November 2025
- **Multi-agent cost:** Inference cost compounds across agents — a 4-agent orchestrator-worker workflow costs $5–8 per complex task. Model the economics before committing to architecture. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide), November 2025

## Gotchas

- **Schemas rot.** If agents are updated but the schema registry isn't updated in lockstep, version mismatches cause silent failures. Treat schema updates as a first-class deployment concern, not a metadata exercise.
- **Over-validating kills latency.** Validating every field of every handoff adds overhead. Validate the fields downstream agents actually use — validate shape and presence, not content.
- **Schema changes need consumer buy-in.** Imposing a schema on an agent pair without testing against the downstream agent's actual behavior leads to schemas that pass validation but still produce wrong outputs. Co-design the schema with both agents.
- **Versioning alone isn't enough without rollback.** When a breaking schema change ships, you need the ability to roll back the upstream agent or the handoff to a known-good version — not just detect the mismatch.
