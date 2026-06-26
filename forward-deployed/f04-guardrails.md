# F-04 · Agentic Safety and Guardrails

Agents that can call tools and act on the world need explicit layers that constrain what they can say, retrieve, and do — before something gets to production that you cannot take back.

## Forces
- A single content filter is not enough; attackers tune for it and it covers only one surface
- Prompt injection can arrive through retrieved documents, not just user input
- Safety latency compounds across a pipeline — slow rail checks become the bottleneck
- The model itself cannot be the only safety layer; it is also the attack target

## The move

Three independent layers, in sequence. Failing any layer stops the request.

**Layer 1 — Input validation.** Normalize the input (Unicode NFKC, strip homoglyphs, Base64-decode obvious encodings). Detect direct injection: system-prompt keywords appearing in the user turn, instruction-override patterns ("ignore previous instructions"), and role-switch attempts. A pattern library is a start; pair it with a content safety classifier for coverage.

**Layer 2 — Model-level classifier.** Run a purpose-built safety model as a sidecar before and after your main call. Two production-ready open-source options:
- **Llama Guard 3** (Meta, HuggingFace): multilabel classifier covering 14 hazard categories (MLCommons taxonomy S1–S14). Sub-second on a single GPU; benchmark on your own hardware.
- **ShieldGemma** (Google): similar scope, available via Hugging Face or Google's API.

These are not rule-based filters. They generalize to novel phrasing in a way regex cannot.

**Layer 3 — Output and execution controls.** Filter the model's final output through a PII redaction step (regex + NER for high-sensitivity fields). Enforce tool call restrictions at the executor level: allowlist which tools can be called in which contexts, set per-tool rate limits, and reject any tool call whose parameters fail schema validation. Do not rely on the model to self-censor its own tool calls.

**Optional: structured rail definitions with NeMo Guardrails.** NVIDIA's [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) (open-source, pip-installable) lets you define all five rail types — input, dialog, retrieval, execution, output — in its Colang 2.0 DSL. Illustrative fragment:

```colang
# colang 2.0 — illustrative
flow user asks off topic
  user said something "off topic"
  bot refuse request
    "I can only help with questions about this product."
```

On GPU, per-check latency is under 50 ms. LangChain integration is available.

**Attack vectors to build tests for:** direct injection (user turn); indirect injection (malicious content in a RAG-retrieved document — see [S-07](../stacks/s07-rag.md)); multi-turn manipulation (building context across messages to shift behavior); Base64 and Unicode homoglyph evasion; role-switch via system-prompt mimicry.

The minimum bar for production is the three-layer model above. The [OWASP AI Security and Privacy Guide](https://owasp.org/www-project-ai-security-and-privacy-guide/) (free, published) is the canonical reference for scoping your threat model.

## Receipt
> Sourced from NeMo Guardrails GitHub repo, Llama Guard 3 and ShieldGemma HuggingFace model cards, and the OWASP AI Security and Privacy Guide. Tool availability and latency figures confirmed via public documentation, verified 2026-06-25. Colang snippet is illustrative — run against a real Guardrails installation to validate syntax.

## See also
[F-13](f13-prompt-injection.md) · [F-03](f03-failure-modes.md) · [S-03](../stacks/s03-tool-use.md) · [F-01](f01-shipping-ai.md) · [F-21](f21-data-privacy-pii.md)

## Go deeper
Keywords: `NeMo Guardrails` · `Llama Guard` · `ShieldGemma` · `prompt injection` · `OWASP AI Security` · `defense in depth` · `content safety classifier`
