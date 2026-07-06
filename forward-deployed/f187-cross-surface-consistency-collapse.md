# F-187 · Cross-Surface Consistency Collapse

A semantically identical request — "grant user X access to resource Y" — arrives via three surfaces: REST API (structured fields), web UI (natural language + context blob), and a batch pipeline (flat CSV row). The model produces three different decisions. This is not a prompt bug. It is a structural failure mode that lab evals never catch because they test one surface at a time.

## Forces

- **LLMs are surface-sensitive in ways deterministic code is not.** Models pick up cues from payload structure, optional field presence, formatting conventions, and surrounding context — not just intent. An API that sends `{"action": "grant", "resource": "repo-42"}` vs a UI that sends "Grant access to repo-42" produce different token distributions even when the underlying ask is identical.
- **Lab evals test one surface in isolation.** Benchmarks like AgentBench and MT-Bench use a single input format. Cross-surface consistency is not in any standard evaluation suite.
- **Production routes the same intent through multiple entry points.** Mobile apps, web UIs, API gateways, Slack bots, scheduled batch jobs — each has different data shapes. Without a normalization layer, the LLM sees different inputs for the same business decision.
- **The failure is invisible until users compare notes.** One team gets access, another doesn't, and nobody knows why until a user escalates. By then the trust damage is done.

## The Move

**Normalize intent before it reaches the model.** Treat the LLM decision surface as a black box that must receive canonical input — not a chameleon that adapts to whatever shape the caller sends.

The normalization layer lives between your API gateway / UI backend and the LLM call. Its job: extract the canonical intent from whatever surface produced it, then emit a single, consistent prompt structure.

```python
# minimal normalization layer
from dataclasses import dataclass
from typing import Literal

@dataclass
class CanonicalIntent:
    action: str           # e.g. "grant_access"
    subject: str          # e.g. "user:alice@example.com"
    resource: str         # e.g. "repo:analytics-v2"
    intent_text: str       # canonical NL description of the ask
    surface: Literal["api", "ui", "batch", "slack"]  # for audit trail only

def normalize_to_canonical(raw: dict | str, surface: str) -> CanonicalIntent:
    """Extracts intent from any surface shape. The LLM never sees surface-specific structure."""
    if surface == "api":
        return CanonicalIntent(
            action=raw["action"],
            subject=raw["subject"],
            resource=raw["resource"],
            intent_text=f"{raw['action'].replace('_', ' ')} {raw['subject']} to {raw['resource']}",
            surface=surface,
        )
    elif surface == "ui":
        # UI sends a free-text description + metadata blob
        return CanonicalIntent(
            action=_classify_action(raw["description"]),
            subject=raw["metadata"]["user"],
            resource=raw["metadata"]["target_resource"],
            intent_text=raw["description"],
            surface=surface,
        )
    elif surface == "batch":
        row = raw  # flat CSV dict
        return CanonicalIntent(
            action=row["operation"],
            subject=f"user:{row['user_id']}",
            resource=f"{row['resource_type']}:{row['resource_id']}",
            intent_text=f"{row['operation']} for user {row['user_id']}",
            surface=surface,
        )
    raise ValueError(f"Unknown surface: {surface}")

def build_llm_prompt(intent: CanonicalIntent) -> str:
    """Single prompt template — one shape for all surfaces."""
    return (
        f"Decide whether to {intent.action} for the following request.\n"
        f"Subject: {intent.subject}\n"
        f"Resource: {intent.resource}\n"
        f"Request: {intent.intent_text}\n"
        "Respond with APPROVE or DENY and a one-sentence reason."
    )

# LLM call receives identical structure regardless of originating surface
intent = normalize_to_canonical(raw_request, surface=detect_surface(raw_request))
prompt = build_llm_prompt(intent)
response = llm.call(prompt)
```

**Verification: consistency test suite.** Run the same canonical intent through N surface-shape variants. Score them with an LLM judge that compares decisions, not outputs:

```python
def consistency_score(intent: CanonicalIntent, surface_variants: list[dict]) -> float:
    """What fraction of surface variants produce the same decision?"""
    canonical_prompt = build_llm_prompt(intent)
    canonical_response = llm.call(canonical_prompt)
    canonical_decision = _extract_decision(canonical_response)

    agrees = 0
    for variant_raw in surface_variants:
        variant_intent = normalize_to_canonical(variant_raw, surface=variant_raw["_surface"])
        variant_prompt = build_llm_prompt(variant_intent)
        variant_response = llm.call(variant_prompt)
        if _extract_decision(variant_response) == canonical_decision:
            agrees += 1
    return agrees / (len(surface_variants) + 1)

# Alert threshold: if score < 0.95 across 5 surface variants, block the surface
# and surface a P2 alert — cross-surface consistency is degrading
```

Key points:
- **Never let surface shape reach the model.** The normalization layer absorbs format differences.
- **Audit the surface field but don't let it influence the prompt.** Surface is metadata for traceability, not a prompt variable.
- **Test consistency as a first-class metric.** Add it to your eval pipeline alongside accuracy and latency.
- **Re-evaluate after model upgrades.** A new model version may introduce new surface sensitivities.

## Receipt

> Receipt pending — July 1, 2026

The normalization pattern is well-established in traditional API design but rarely applied to LLM decision surfaces. The consistency_score metric is a practical implementation of the FM-4 detection method from arXiv:2605.01604. Run it against your top-20 highest-volume decision types and set an alert at <95% agreement.

## See also

- [F-84 · Output Consistency Under Paraphrase](f84-output-consistency-under-paraphrase.md) — paraphrase is a single-surface analog; this entry covers multi-surface
- [F-26 · Behavioral Drift Detection](f26-behavioral-drift-detection.md) — monitors output distribution over time; cross-surface consistency is a proactive variant
- [S-238 · Deterministic Guardrails Outside the LLM Loop](stacks/s238-deterministic-guardrails-outside-the-llm-loop.md) — pre-LLM normalization as a guardrail pattern
