# F-137 · Linguistic Hedge Detector

[F-78](f78-confidence-gated-delivery.md) measures output confidence by sampling the model N>1 times at temperature > 0 and computing variance across outputs. Low variance = high confidence; high variance = low confidence; responses below the confidence threshold are withheld entirely. It requires multiple model runs and is incompatible with temperature 0. [F-93](f93-claim-verifiability-classification.md) classifies claims in the output as verifiable, unverifiable, or opinion — it categorizes claim types, not confidence levels.

Neither covers a simpler signal that is available for free in every response: the model's own language. When a model is uncertain, it says so. "I believe", "probably", "I'm not sure", "might", "approximately" — these phrases are not ornamental; they are first-person uncertainty disclosure. A model that returns `"The termination fee is $2.45M"` is expressing a different confidence level than one that returns `"The termination fee is approximately $2M — I'm not entirely certain about this figure."` The linguistic signal is in the text; extracting it costs zero tokens and runs in under 0.02ms.

A linguistic hedge detector scans output text for uncertainty phrases organized into categories: epistemic markers (`I believe`, `I think`, `I'm not sure`), modal qualifiers (`probably`, `possibly`, `might`, `could be`), evidential hedges (`seems like`, `appears to be`), and quantifier hedges (`approximately`, `roughly`, `around`). It returns a tier — CERTAIN, HEDGED, or UNCERTAIN — that drives three actions: deliver normally, attach an uncertainty annotation, or route to a higher-capability model or human review.

## Situation

A contract extraction pipeline delivers structured outputs to a downstream compliance system. The compliance system treats all fields as authoritative — it does not re-verify individual values against source documents.

Production review finds two failure classes:

1. The model correctly signals uncertainty but the pipeline discards the signal. Response: `"The termination fee is approximately $24.5M — though I'm not entirely certain as I noticed two different figures in sections 4 and 8."` The extracted `termination_fee` field is `"24500000"`. The compliance system accepts it without flagging. The source document has a conflicting amendment.

2. A response with 0 hedges delivers incorrect values confidently. The model hallucinated a clause that does not exist. No linguistic signal; no gate; the error propagates.

The linguistic hedge detector addresses class 1. For class 2, F-134 (ensemble voting) is the right tool — linguistic certainty cannot detect hallucination. Run both: ensemble voting catches structural disagreement; the hedge detector catches the model's own expressed uncertainty about values it did extract.

## Forces

- **Category matters for routing, not just count.** An epistemic hedge on a specific field (`"I'm not sure about the governing_law"`) is more actionable than a quantifier hedge (`"approximately 2026"`). Log the category alongside each detected phrase. Route epistemic hedges to human review; attach quantifier hedges as confidence annotations for the downstream consumer.
- **Domain-specific patterns need explicit rules.** The quantifier pattern `/approximately\s+\d/` catches `"approximately 3"` but not `"approximately $2M"`. Add domain-specific patterns for currency, percentages, and dates: `/approximately\s+[\$£€]?[\d,]+/`. Build the rule list from observed output failures, not from exhaustive coverage.
- **False positives on domain vocabulary.** Financial analysis outputs legitimately use "approximately" for ranges, estimates, and projections — not as a confidence signal. Domain context matters. For a contract extraction pipeline, "approximately $2M" is a hedge. For a market analysis pipeline producing intentional estimates, it is expected. Tune the threshold, not the patterns.
- **Hedging in the reasoning trace is different from hedging in the final answer.** If the model produces a chain-of-thought scratchpad before the structured output, the scratchpad may contain exploration language (`"let me consider whether..."`) that is not uncertainty in the final extracted value. Apply the detector only to the field-level output, not the full response text, when the two are separable.
- **The tier boundary (2 hedges for HEDGED, 3 for UNCERTAIN) is tunable.** These defaults are calibrated for contract extraction where false negatives are expensive (wrong values accepted) and false positives are cheaper (extra reviews). For high-frequency classification tasks where human review is not scalable, raise the UNCERTAIN threshold. Set thresholds from labeled data where available.
- **Compose with F-134 ensemble, not as a substitute.** Ensemble voting detects structural disagreement among model runs; the hedge detector captures self-expressed uncertainty within a single run. They are complementary signals. Use ensemble first (catches the cases where multiple extractions disagree); use hedge detection as a final pass on the output text regardless of ensemble confidence.

## The move

**Scan output text for uncertainty phrases. Tier the result as CERTAIN, HEDGED, or UNCERTAIN. Route by tier before delivery.**

```js
// --- Linguistic hedge detector ---
// Scans model output text for uncertainty language before delivery.
// Zero token cost. Works at temperature=0. Model-agnostic.
// Returns: { hedged, hedgeCount, phrases: [{phrase, position, category}], tier }
// Tiers: CERTAIN (0 hedges) → deliver; HEDGED (1-2) → annotate; UNCERTAIN (3+) → retry or escalate.
// Compose with F-134 (ensemble voting) — both detect uncertainty via different signals.

var HEDGE_RULES = [
  { pattern: /\bi\s+(believe|think|suppose|assume|guess)\b/gi,           category: 'epistemic'   },
  { pattern: /\bi['']m\s+not\s+(sure|certain|confident|entirely\s+sure)\b/gi, category: 'epistemic' },
  { pattern: /\bas\s+far\s+as\s+i\s+know\b/gi,                          category: 'epistemic'   },
  { pattern: /\bto\s+(my|the\s+best\s+of\s+my)\s+knowledge\b/gi,        category: 'epistemic'   },
  { pattern: /\b(approximately|roughly|around)\s+[\$£€\d]/gi,            category: 'quantifier'  },
  { pattern: /\b(probably|possibly|perhaps|maybe|might|could\s+be)\b/gi, category: 'modal'       },
  { pattern: /\bseems?\s+(like|to\s+be)\b/gi,                            category: 'evidential'  },
  { pattern: /\bappears?\s+to\s+be\b/gi,                                 category: 'evidential'  },
];

// Configurable tier thresholds.
var HEDGE_THRESHOLDS = { UNCERTAIN: 3, HEDGED: 1 };

function detectHedging(text, thresholds) {
  thresholds = thresholds || HEDGE_THRESHOLDS;
  var phrases = [];

  for (var i = 0; i < HEDGE_RULES.length; i++) {
    var rule = HEDGE_RULES[i];
    var re   = new RegExp(rule.pattern.source, rule.pattern.flags);
    var m;
    while ((m = re.exec(text)) !== null) {
      phrases.push({ phrase: m[0], position: m.index, category: rule.category });
    }
  }

  phrases.sort(function(a, b) { return a.position - b.position; });

  var tier;
  if (phrases.length === 0)                          tier = 'CERTAIN';
  else if (phrases.length < thresholds.UNCERTAIN)    tier = 'HEDGED';
  else                                               tier = 'UNCERTAIN';

  return { hedged: phrases.length > 0, hedgeCount: phrases.length, phrases: phrases, tier: tier };
}

// --- Integration: delivery gate after extraction ---

function deliverWithHedgeCheck(output, outputText) {
  const result = detectHedging(outputText);

  if (result.tier === 'CERTAIN') {
    return { output, confidence: 'HIGH', hedgeDetection: result };
  }

  if (result.tier === 'HEDGED') {
    // Attach annotation; log for F-116 monitoring
    log({ event: 'hedge_detected', tier: 'HEDGED', hedgeCount: result.hedgeCount, phrases: result.phrases });
    return {
      output,
      confidence: 'LOW',
      uncertainty: { hedgeCount: result.hedgeCount, phrases: result.phrases },
      hedgeDetection: result,
    };
  }

  // UNCERTAIN: route to higher-capability model or human review
  log({ event: 'hedge_detected', tier: 'UNCERTAIN', hedgeCount: result.hedgeCount, phrases: result.phrases });
  return { output: null, confidence: 'NONE', reason: 'LINGUISTIC_UNCERTAINTY', hedgeDetection: result };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `detectHedging()` timed over 100 000 iterations at three confidence levels.

```
=== LinguisticHedgeDetector timing (100 000 iterations) ===

detectHedging() — CERTAIN   (0 phrases): 0.0065 ms
detectHedging() — HEDGED    (2 phrases): 0.0115 ms
detectHedging() — UNCERTAIN (4 phrases): 0.0114 ms

=== Scenario A: CERTAIN — extract delivered normally ===

Output text: "The contract terminates on 2026-12-31. The governing law is New York.
             The termination fee is $2.45M."

hedgeCount=0  tier=CERTAIN
→ deliver normally at full confidence

=== Scenario B: HEDGED — annotation attached ===

Output text: "I believe the contract terminates on 2026-12-31.
             The governing law is probably New York."

hedgeCount=2  tier=HEDGED
  [epistemic]  "I believe"  at position 0
  [modal]      "probably"   at position 70
→ deliver with { confidence: "LOW", uncertainty: { hedgeCount: 2, phrases: [...] } }
→ log for F-116 per-field error rate tracking

=== Scenario C: UNCERTAIN — route to higher model ===

Output text: "I think the contract terminates around December 2026.
             I'm not sure about the governing law — it might be New York or Delaware."

hedgeCount=3  tier=UNCERTAIN
  [epistemic]  "I think"       at position 0
  [epistemic]  "I'm not sure"  at position 54
  [modal]      "might"         at position 96
→ do not deliver; retry with claude-sonnet-4-6 or route to human review

=== F-78 vs F-137 ===

              │ F-78 (logprob/sampling)        │ F-137 (linguistic hedge)
──────────────┼────────────────────────────────┼───────────────────────────────────────
Signal source │ Output probability distribution │ First-person uncertainty language
Temperature   │ Requires T > 0 (sampling)       │ Works at T=0
Cost          │ N runs × full generation cost   │ 0.012 ms, 0 tokens
Model-agnostic│ Requires logprob API access     │ Yes — text match only
Catches       │ Distributional uncertainty      │ Self-expressed uncertainty
Misses        │ Confident hallucinations        │ Unhedged wrong answers
Combine with  │ F-134 ensemble                  │ F-134 ensemble
```

## See also

[F-78](f78-confidence-gated-delivery.md) · [F-93](f93-claim-verifiability-classification.md) · [F-134](f134-extraction-ensemble-voter.md) · [F-116](f116-per-field-extraction-error-rate-tracking.md) · [F-133](f133-extraction-retry-escalation-policy.md)

## Go deeper

Keywords: `linguistic hedge detection` · `uncertainty language detection` · `hedge phrase detector` · `output confidence language` · `epistemic hedge detection` · `model self-expressed uncertainty` · `text-based confidence gate` · `hedge phrase gate` · `uncertainty annotation` · `first-person uncertainty signal`
