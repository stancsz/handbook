# S-238 · Deterministic Guardrails — Enforcing Safety Outside the LLM Loop

Once an agent is looping with tools, the LLM inside it is no longer the right place to catch failures. A model that has already decided to call `rm -rf /`, exfiltrate customer PII, or email executives with forged authority has already passed the dangerous gate. The enforcement layer that actually saves you lives between the model's *intent* and the action's *execution* — and increasingly, teams are discovering that deterministic pattern-matching beats LLM-guarding-LLM every time.

## Forces

- **LLM-as、通訳 is a slow, expensive, circular solution** — using one LLM to critique another adds latency, cost, and the judge's own failure modes (hallucination, injection). The question "is this prompt injection?" routed to the same model class you're trying to protect is not a robust architecture
- **Production failure data is now explicit** — the AIUC-1 Consortium (March 2026) reported 80% of organizations deploying AI agents experienced risky behaviors (unauthorized system access, improper data exposure), while only 21% reported complete visibility into agent actions. This isn't theoretical
- **Over-blocking kills trust; under-blocking causes incidents** — the cost asymmetry is extreme: broken UX from false positives is visible and immediate, while a $47K weekend incident or GDPR fine is rare and catastrophic. Teams that calibrate conservatively pay in user churn; teams that calibrate aggressively pay in breach response
- **The four-layer model surfaces where each guardrail type belongs** — input filtering (before the model), action constraining (before execution), output monitoring (before delivery), behavioral flagging (before patterns become incidents). Each layer has different tooling requirements and different failure modes

## The move

Build the enforcement stack as four distinct, composable layers between your agent and the real world:

**Layer 1 — Input filtering (pre-model)**
- Reject or sanitize prompt injection patterns before they reach the LLM
- Enforce token/size budgets at the gateway, not inside the agent loop
- Block payloads with known adversarial patterns (CVE-style signatures for prompt injection)
- Pattern-match against your own context: if a user input references a tool name the agent has access to but the user shouldn't control directly, flag it

**Layer 2 — Action constraining (pre-execution)**
- Intercept every tool call between model output and execution
- Apply deterministic policy: `rm -rf /`, `DROP TABLE`, `send_email` to external recipients above a threshold — block by pattern, not by LLM judgment
- Tools like **Vigil** (HN, 2025) implement 22 rules across 8 threat categories — destructive shell, SSRF, path traversal, SQL injection, data exfiltration, prompt injection, encoded payloads, credential exposure — with <2ms latency and zero network calls
- **Do not route permission decisions to the same LLM class you're protecting** — the attack surface compounds

**Layer 3 — Output monitoring (pre-delivery)**
- Scan responses for PII, toxic content, and out-of-scope disclosures before reaching the user
- Validate response schema if the agent promises structured output
- Log the full trace for compliance: every LLM call, tool invocation, intermediate decision

**Layer 4 — Behavioral flagging (pre-incident)**
- Track action patterns over time, not just per-request
- Flag privilege creep (agent accessing resources it hasn't needed before), behavioral drift (success rate dropping), and rate anomalies (sudden burst of tool calls)
- Correlate with cost signals — a spike in expensive LLM calls often precedes an agent loop incident

## Evidence

- **HN Show HN (2025):** Vigil — zero-dependency, <2ms pattern-matching safety guardrails for AI agent tool calls. 22 rules across 8 threat categories. No LLM, no network calls, works offline. MIT license. — [Vigil on HN](https://news.ycombinator.com/item?id=47190721)
- **Industry report (March 2026):** AIUC-1 Consortium found 80% of organizations deploying agents reported risky behaviors including unauthorized system access and data exposure; only 21% had complete visibility into agent actions. Four-layer guardrail architecture recommended as the mitigation framework. — [Supergood Solutions / AIUC-1 briefing summary](https://supergood.solutions/blog/future-friday-agent-guardrails-production-2026)
- **Production incident pattern:** Guardrails placed downstream of model calls (checking output, not action) miss the real enforcement point. The $847/month → 92% → 55% production failure pattern (Calder's Lab, Jan 2025) was resolved not by better prompting but by instrumenting the tool call interception layer. — [Calder's Lab production retrospective](https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough)

## Gotchas

- **LLM-based guardrails create circular trust** — "Is this prompt injection?" answered by the same model class you're guarding is asking a fox to guard the henhouse. Use LLM-as-judge for nuanced, context-dependent decisions (e.g., is this request in scope?), not for deterministic threat detection
- **Tool definition surface area is a guardrail surface area** — every tool you expose is a potential vector. Teams that added MCP tools without scoping execution permissions paid for it in incident response. The principle of least privilege applies to tool exposure, not just credential access
- **Behavioral guardrails require historical context** — per-request checks catch obvious violations but miss privilege creep and drift. You need trace logging and aggregation across sessions to surface patterns, not just per-call blocking
- **Over-blocking creates operational debt** — if your guardrails break the agent's legitimate use cases, users find workarounds (clipboard, screenshots, manual copy-paste). False-positive rates above ~1% drive users to defeat the safety system entirely
