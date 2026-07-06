# S-646 · The Multi-Agent Error Compounding Problem

[Multi-agent pipelines look like specialization but behave like amplification — each agent's errors become the next agent's context. The more agents in your pipeline, the more confident your wrong answers become.]

## Forces
- **Errors compound forward, confidence compounds backward.** Agent A's hallucinated customer ID becomes Agent B's trusted input. By step five, you have a polished, internally consistent, completely wrong result that nobody questions because it looks authoritative.
- **The math is brutal.** A 5% per-agent error rate gives an 18.5% failure probability in a 4-agent chain and a 26.5% failure probability in a 6-agent chain. The failure rate grows superlinearly with chain depth.
- **Observability doesn't solve what it can't see.** Standard request-level logging misses where errors entered the chain. You need per-agent checkpointing to isolate which step introduced the bad data.
- **More agents feels like more capability.** Teams add agents to handle edge cases. Each new agent is a new error-injection point. The architecture gets more complex and less reliable simultaneously.

## The move
Break the compounding loop with layered defense-in-depth:

- **Place HITL checkpoints before irreversible actions.** Gate tool calls with side effects (email sends, DB writes, financial transactions) and before high-stakes decisions behind a human review step.
- **Use output validation at every agent boundary.** Schema validation (Pydantic/JSON Schema) catches structural drift. A secondary LLM call or rule-based checker catches semantic inconsistency before it propagates downstream.
- **Implement token budgets and model-gating per step.** Route simple extraction to smaller/faster models; reserve expensive reasoning for synthesis. This also creates natural cost checkpoints.
- **Design for graceful degradation, not binary success.** If one agent fails, the pipeline should surface a partial answer with explicit uncertainty flags rather than either crashing or fabricating a fill-in.
- **Log at the agent-handoff boundary, not the request level.** Each agent-to-agent transfer is a potential error injection point. Tag it, timestamp it, version the context.
- **Treat confidence scores as circuit breakers.** Below a defined threshold, halt and escalate rather than continue with low-quality context.

## Evidence
- **DeepRails Research:** Multi-agent error compounding — a 4-agent pipeline at 5% per-agent error rate produces 18.5% overall failure probability; a 6-agent chain hits 26.5%. The analysis explicitly notes that "the earlier an error enters the chain, the more damage it does." — [deeprails.com/research/multi-agent-safety-production-guardrails](https://www.deeprails.com/research/multi-agent-safety-production-guardrails)
- **Inventiple:** Production agentic hallucination is qualitatively different from chatbot hallucination — an agent hallucination can delete records, send incorrect emails, or trigger transactions before review occurs. Defense requires five layered guardrails (input sanitization, tool schema validation, output validation, semantic checks, business-rule validation). — [inventiple.com/blog/agentic-ai-guardrails-hallucination-prevention](https://www.inventiple.com/blog/agentic-ai-guardrails-hallucination-prevention)
- **Technspire:** Four categories consistently shipped to production in 2025: developer tooling (tight feedback loops via compile/test), internal ops automation, document processing, and customer-facing Q&A. All share a common trait: short chains, well-scoped domains, or human-in-the-loop gates. — [technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas
- **Adding more agents is the wrong fix for edge cases.** If an agent fails on 10% of inputs, the right move is better prompting or a better model, not adding a "corrector" agent — that just adds another error-injection point.
- **Confidence thresholds set too high create livelock.** Agents that halt on any uncertainty will loop on ambiguous inputs. Calibrate thresholds against actual per-step error rates from your traces.
- **Output validation only catches what you specify.** A rule-based checker won't catch novel hallucinations. Pair schema validation with a lightweight semantic check (a second model call or a retrieval-accuracy probe).
- **Context truncation between agents silently drops evidence.** If agent A produces 8k tokens but agent B's context window is 4k, the truncation discards the tail — which may contain the corrective information. Check your handoff context sizes explicitly.
