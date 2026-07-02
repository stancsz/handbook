# S-395 · Agent Cost Circuit Breakers — The Missing Production Layer

The moment an agent enters a retry loop, the architecture that made it capable becomes the thing that burns $47,000. Teams build the capability layer obsessively and skip the control layer entirely — then discover the gap only when the invoice arrives.

## Forces

- **Agentic workloads consume 10-100x more tokens than conversational AI.** A chat session uses a few thousand tokens; a planning-execute-verify-retry agent chain uses multiples of that, per agent, per cycle — and cycles compound
- **Capability and control live in different architectural layers.** The agent cannot self-limit its own spend without defeating its purpose. The cap must live outside the agent's trust boundary
- **Failure that looks like success is invisible to normal monitoring.** The $47K LangChain incident ran for 11 days "working" — the billing statement was the alert
- **Token costs dropped 85% since 2023, but output tokens remain 3-5x input cost.** Output-heavy agent patterns are the primary cost driver in production — and the part most teams undercontrol

## The move

The control layer has three components that must be independent of the agent:

**1. Hard spend ceiling enforced at the transport layer, not the prompt.**
The budget must fire before the API call, not after an alert. Enforce it at the HTTP/client layer where you control the `max_tokens` and cost attribution per agent. Prompt-level "stay within budget" instructions fail — the model has no accurate token-counting introspection and no incentive to self-restrain.

**2. Loop detection as a named exception class, not a heuristic.**
Distinguish `RetryableError` (legitimate transient failure) from `SelfLoopDetected` (two tools talking past each other, model not noticing). The duplicate detector fires on both; make retries explicit by raising thresholds specifically for retry paths. A legitimate retry and a runaway loop look identical without this distinction.

**3. Per-agent budget attribution from the API response, not metering.**
Every `client.messages.create` response carries `usage.input_tokens` and `usage.output_tokens`. Use these fields directly as the value charged against the per-agent budget. Do not build a separate metering layer — it introduces drift and becomes the new failure point.

**4. Tiered model routing as structural cost control, not optimization.**
Route deterministic, high-volume tasks (classification, extraction, formatting) to cheap models (Mistral, Gemini Flash). Reserve frontier models (Claude Opus, GPT-5) for genuine reasoning tasks. Teams report 60-75% cost savings from disciplined routing without quality regression on the right task types.

## Evidence

- **Postmortem:** Multi-agent LangChain system entered a retry loop, ran 11 days undetected, accumulated $47,000 in API charges — discovered via monthly billing statement. No per-agent spend limit, no runtime timeout, no token-usage anomaly detection. The agents were "working" until the loop — the architecture had no kill switch. — [Kognita Blog](https://www.kognita.co/blog/ai-agent-runaway-cost-no-kill-switch)
- **Postmortem:** Logistics automation system for a major retailer triggered a hallucination loop where two autonomous agents referenced each other's outputs as ground truth. A single extra token in the prompt chain amplified into a cascading error. $15,000 overnight before the card was charged. — [Moment School](https://momentschool.com/en/blog/ai-agent-loop-cost-15k-incident-analysis)
- **Benchmarking:** Enterprises average $85,521/month in AI operational costs as of 2025. 60–85% of that spend is recoverable through prompt caching, intelligent model routing, and hard budget enforcement. — [Zylos Research, 2026](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)

## Gotchas

- **Caching alone is not sufficient.** Prompt caching reduces redundant context processing but does not stop runaway loops — the loop still generates new output tokens on every iteration
- **Context window limits do not cap spend.** Hitting the context limit causes degraded responses or errors, not cost control. The ceiling must be a separate enforcement mechanism
- **Billing alerts are not circuit breakers.** An alert that fires after the invoice is already run is not a control — it is a report. The breaker must interrupt the call, not report it
- **Star counts are misleading.** AutoGen has 58,500 GitHub stars (higher than LangGraph's 33,400) but is in maintenance mode as of 2026. The production-default framework is now LangGraph with MCP for tool integration — the ecosystem has consolidated
