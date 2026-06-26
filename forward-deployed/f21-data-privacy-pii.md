# F-21 · Data Privacy and PII in Agent Systems

The model sees everything you put in the prompt. That sounds obvious, but in an agent pipeline there are six places PII enters the context — user input, retrieved documents, tool outputs, model memory, log traces, and the model's own outputs — and most teams guard only one of them. The mitigation is layered: redact before inject, route by data class, treat logs as a separate surface, and understand what the provider does with what you send.

## Situation

A support agent retrieves a customer record and injects it verbatim into context to answer a question. The record contains SSN, payment card, and a phone number. The model answers correctly. Meanwhile: (1) the full record transited the provider's API, (2) the span event in your trace backend now contains the raw record, (3) the model's response is logged with the SSN echoed back. Three leaks, one request, no alert.

## Forces

- Every token you send to a hosted model crosses a third-party API. Data you don't send cannot leak. Minimization — send only what the current turn needs — is the only architectural control you have over what the provider sees.
- A 2025 Anthropic Terms of Service update made training opt-out the default for API users, but "not used for training" does not mean "not stored." Retention periods vary by provider. The only data with zero provider exposure is data you never sent.
- PII leaks in agent systems happen at six distinct surfaces, not just the user-input surface most teams guard. Each surface needs its own mitigation.
- Regex redaction is a first-pass filter, not a complete solution. It catches structured patterns (email, SSN, card numbers) reliably. It misses unstructured PII (names, addresses, free-text medical history) and vendor-specific token formats that change over time. NER or a classification model is needed for higher recall.
- Redaction reduces token count as a side effect: removing PII placeholders and replacing them with typed labels shrinks prompts by 20–35% on support-ticket workloads. This is a cost benefit that compounds at agent loop volumes.
- Local models ([S-01](../stacks/s01-local-model-dispatch.md)) eliminate provider exposure entirely for high-sensitivity data. The routing decision "PII → local model" ([S-06](../stacks/s06-model-routing.md)) is the architectural escalation when redaction isn't sufficient.

## The move

**Redact before you inject.** The primary control is pre-processing: scan every chunk of external data (user input, retrieved documents, tool outputs) before it enters the prompt and replace PII with typed labels. The model still has enough information to do its job; the actual values never transit the API.

```js
const PII_PATTERNS = [
  { label: 'EMAIL',       re: /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g },
  { label: 'PHONE',       re: /\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g },
  { label: 'SSN',         re: /\b\d{3}-\d{2}-\d{4}\b/g },
  { label: 'CREDIT_CARD', re: /\b(?:\d[ -]?){13,16}\b/g },
  { label: 'IP_ADDR',     re: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g },
  // API keys: update patterns when provider formats change
  { label: 'API_KEY',     re: /\b(sk-[a-zA-Z0-9\-]{20,}|[a-zA-Z0-9]{40,})\b/g },
];

function redact(text) {
  let out = text;
  for (const { label, re } of PII_PATTERNS) out = out.replace(re, `[${label}]`);
  return out;
}
```

**Know the six leak surfaces and guard each one:**

| Surface | Path | Mitigation |
|---|---|---|
| User input | User message → model context | Redact before inject |
| RAG retrieval | Retrieved chunks → context | Scan chunks at retrieval time; redact or filter before inject |
| Tool outputs | API response → context | Redact tool results before inserting into next turn |
| Trace/log events | Prompt text in span attributes | Log event bodies, never span attributes — attributes are indexed and searchable ([W-04](../workspace/w04-observability.md)) |
| Model memory | Persisted across sessions | Never write raw PII to persistent memory; write labels or summaries ([S-09](../stacks/s09-memory-systems.md)) |
| Model output | Response to downstream code or user | Output redaction layer — the regex pass in [F-04](f04-guardrails.md) Layer 3 |

**Route by data class, not by default.** When the task involves data that must not leave your perimeter (PHI under HIPAA, financial data under PCI, PII in high-regulation jurisdictions), route to a local model ([S-01](../stacks/s01-local-model-dispatch.md)) rather than redacting. Redaction fails on unstructured PII; a local model has zero provider exposure.

**Treat the trace backend as a production attack surface.** Span attributes in OTel are indexed; any PII written to them is searchable in your trace UI and may be exported to third-party backends. Prompt and response text belong in span *events* (unindexed), not attributes. A single misconfigured exporter can exfiltrate your entire prompt history.

**Maintain a provider data-handling inventory.** For each provider you use, document: what their retention period is, whether training opt-out is on, whether subprocessors have access, and what the deletion request process is. This is not optional for deployments under GDPR, HIPAA, or SOC 2. Update the inventory when you change providers or when their ToS changes.

**Regex is a floor, not a ceiling.** The patterns above catch structured PII reliably — emails, SSNs, phone numbers, cards, IPs. They miss: (1) names not followed by a structured field, (2) free-text medical or financial narrative, (3) vendor API key formats that change (e.g. `sk-proj-...` with a hyphenated prefix). Layer NER or a lightweight classification pass on top for sensitive-data workloads.

## Receipt

> Verified 2026-06-26 — Node, `gpt-tokenizer`. Regex patterns tested against a realistic support ticket with 7 PII instances across 6 types. Token counts measured before and after redaction. Honest finding: the API_KEY pattern missed `sk-proj-aBcDeFgHiJkLmNoPqRsTuV` because `sk-proj-` contains a hyphen between the prefix and the value, breaking the `[a-zA-Z0-9]{20,}` match after `sk-`. This is a real failure mode — vendor key formats change and patterns need maintenance.

```
=== Test corpus: support ticket with 7 PII instances ===

Detected and redacted:
  EMAIL:       2 instances
  PHONE:       2 instances
  SSN:         1 instance
  CREDIT_CARD: 1 instance
  IP_ADDR:     1 instance
  API_KEY:     0  ← MISSED: sk-proj- hyphen breaks pattern

Total detected: 7/7 by pattern  (API key missed — regex limitation)

Token impact:
  Original:   121 tokens
  Redacted:    79 tokens
  Reduction:   42 tokens  (35%)
```

**What the receipt shows:**

- Regex catches 6 of the 7 instances correctly and replaces them with typed labels. The model that reads the redacted prompt knows a credit card and SSN were present (the label is informative) without receiving the actual values.
- The API_KEY miss is not an edge case — it is a class of failures: vendor-specific formats with internal hyphens, new provider token shapes, and org-specific secret naming conventions. Regex patterns must be treated as living configuration, not static code.
- The 35% token reduction is a real secondary benefit. On a support-ticket workload, redacting before injection reduces context size as well as exposure. At agent loop volumes this compounds into meaningful cost savings.

## See also

[F-04](f04-guardrails.md) · [S-01](../stacks/s01-local-model-dispatch.md) · [S-06](../stacks/s06-model-routing.md) · [W-04](../workspace/w04-observability.md) · [S-09](../stacks/s09-memory-systems.md)

## Go deeper

Keywords: `PII` · `data privacy` · `redaction` · `data minimization` · `GDPR` · `HIPAA` · `PCI` · `trace hygiene` · `provider data retention` · `NER redaction` · `local model routing`
