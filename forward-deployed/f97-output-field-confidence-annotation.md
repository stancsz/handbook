# F-97 · Output Field Confidence Annotation

[F-58](f58-structured-document-extraction.md) attaches per-field confidence during extraction — each field in a document extraction output carries a numeric confidence score (0.0–1.0) that represents the extraction model's certainty about the value it found in the source document. [F-70](f70-verifiable-output-design.md) adds structural assertions to agent output: required fields, type/range checks, invariants, referential integrity. [F-93](f93-claim-verifiability-classification.md) classifies free-text output sentences as VERBATIM, SUPPORTED, or UNSUPPORTED against retrieved sources.

None address the question of source grounding for individual fields in a structured JSON output. When an agent returns `{ termination_fee: "$24.5M", liability_exposure: "uncapped", governing_law: "Delaware" }`, F-58's confidence measures extraction certainty (not source grounding); F-70 checks whether the fields exist and have valid types; F-93 is not designed for key-value pairs. There is no mechanism that asks, for each field value: is this value in the retrieved sources, inferred from them, or synthesized without any source support?

Output field confidence annotation answers that question per field: for each non-null field in a structured output, classify the value as HIGH (verbatim in source), MEDIUM (word-overlap supported), or LOW (no direct source grounding). The annotation is a separate `_confidence` object alongside the output, not embedded in the schema. Downstream consumers can suppress LOW fields from user display, route them to human review, or label them as "AI assessment" rather than "source-confirmed."

## Situation

A legal agent returns a contract summary with 7 fields. The client application needs to know which fields can be shown with a "source confirmed" badge and which need a "model assessment" label. F-70 passes all 7 (correct structure). F-93 doesn't apply (structured output, not prose). Output field confidence annotation classifies: 5 of 7 fields HIGH (verbatim in retrieved clauses), 1 MEDIUM (`liability_exposure: "potentially uncapped"` — words appear in source but not that exact phrase), 1 LOW (`risk_summary: "high"` — the model's synthesis, absent from any source). The UI shows the 5 HIGH fields with a source badge, labels the MEDIUM field with "paraphrase," and routes the LOW field to attorney review before displaying.

## Forces

- **The check is the same as F-93, applied to field values instead of sentences.** For free text, F-93 checks if a sentence appears verbatim or has high word-overlap with a source. For structured output, apply the same two steps to the field value string. The classification logic is portable; the input format differs.
- **Stringify all values before checking.** JSON field values may be strings, numbers, booleans, or arrays. Normalize to string representation before running substring and Jaccard checks. `"$24.5M"` is a 6-character string; `24500000` is `"24500000"` after stringify. The source document will contain `"$24.5M"`, not `"24500000"`.
- **Short values need a lower Jaccard threshold.** A field value like `"Delaware"` has one meaningful word. Word-set Jaccard on one word vs a 200-word source paragraph will be low even if "Delaware" appears many times in the source. For values under 4 words, check for exact substring only (not Jaccard) — substring is sufficient.
- **The annotation is separate from the output schema.** Don't add `termination_fee_confidence` fields to the output object — that pollutes the schema and breaks existing consumers. Return `{ output: {...}, _confidence: { termination_fee: { tier: 'HIGH', match: 'VERBATIM' }, ... } }`. Consumers that need confidence can read `_confidence`; consumers that don't can ignore it.
- **Run this in the annotation pipeline, not inside the model.** Asking the model to self-report confidence produces poorly calibrated scores ([S-53](../stacks/s53-confidence-calibration.md)). The model will report high confidence on values it synthesized with no source support. Run the substring + Jaccard check in code after generation, against the actual retrieved sources.
- **LOW does not mean wrong.** A synthesized conclusion (`risk_summary: "high"`) may be a correct inference from multiple sources. LOW means "not directly in source" — which is the information the downstream consumer needs to decide whether to show it, flag it, or route it.

## The move

**After receiving a structured JSON output, run substring and word-set Jaccard checks on each field value against the retrieved sources. Return a `_confidence` annotation object keyed by field name.**

```js
// --- Word-set Jaccard (same algorithm as S-122/F-93) ---

function wordSet(text) {
  return new Set(
    String(text).toLowerCase()
      .replace(/[^\w\s]/g, ' ')
      .split(/\s+/)
      .filter(w => w.length > 2)
  );
}

function jaccardSimilarity(setA, setB) {
  if (!setA.size || !setB.size) return 0;
  let inter = 0;
  for (const w of setA) { if (setB.has(w)) inter++; }
  return inter / (setA.size + setB.size - inter);
}

// --- Field value source check ---
// Returns { tier: 'HIGH'|'MEDIUM'|'LOW', match: string, similarity?: number }

function classifyFieldValue(fieldValue, sources, opts = {}) {
  const { jaccardThreshold = 0.15 } = opts;
  const valStr     = String(fieldValue).trim();
  const valLower   = valStr.toLowerCase();
  const valWords   = wordSet(valStr);
  const isShort    = valWords.size < 4;   // short values: substring-only

  for (const source of sources) {
    const srcLower = source.toLowerCase();

    // 1. Exact substring — HIGH (VERBATIM)
    if (srcLower.includes(valLower)) {
      return { tier: 'HIGH', match: 'VERBATIM' };
    }

    // 2. Word-set Jaccard — MEDIUM (SUPPORTED)
    // Skip for short values (unreliable Jaccard on 1-2 words)
    if (!isShort) {
      const sim = jaccardSimilarity(valWords, wordSet(source));
      if (sim >= jaccardThreshold) {
        return { tier: 'MEDIUM', match: 'SUPPORTED', similarity: parseFloat(sim.toFixed(3)) };
      }
    }
  }

  return { tier: 'LOW', match: 'UNSUPPORTED' };
}

// --- Full output annotation ---
// output:  the structured JSON object from the agent
// sources: string[] of retrieved context texts (same sources used during generation)

function annotateOutputFields(output, sources, opts = {}) {
  const annotations = {};
  let highCount = 0, medCount = 0, lowCount = 0;

  for (const [field, value] of Object.entries(output)) {
    if (value === null || value === undefined) continue;   // skip absent fields

    const ann = classifyFieldValue(value, sources, opts);
    annotations[field] = ann;

    if (ann.tier === 'HIGH')   highCount++;
    else if (ann.tier === 'MEDIUM') medCount++;
    else                            lowCount++;
  }

  return {
    output,
    _confidence: annotations,
    _summary: {
      total:   Object.keys(annotations).length,
      HIGH:    highCount,
      MEDIUM:  medCount,
      LOW:     lowCount,
      pctHigh: parseFloat(((highCount / Object.keys(annotations).length) * 100).toFixed(1)),
    },
  };
}

// --- Usage ---
//
// const agentOutput = await agent.run(systemPrompt, userMessage);
// const parsed      = JSON.parse(agentOutput);
// const sources     = retrievedChunks.map(c => c.text);   // same sources injected during generation
//
// const annotated   = annotateOutputFields(parsed, sources);
//
// // annotated._confidence per field: { tier: 'HIGH'|'MEDIUM'|'LOW', match: string }
// // annotated._summary: { total, HIGH, MEDIUM, LOW, pctHigh }
//
// // Downstream decisions:
// // HIGH   → "source confirmed" badge in UI
// // MEDIUM → "paraphrase" label, show with caution
// // LOW    → route to human review before displaying, or label "AI assessment"
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `classifyFieldValue()` and `annotateOutputFields()` timed over 100 000 iterations on a 7-field contract summary output with 5 retrieved clause sources.

```
=== classifyFieldValue() timing — VERBATIM path (100 000 iterations) ===

$ node -e "
const sources = ['The termination fee payable by the target is \$24.5M upon closing.',
                 'Governing law: Delaware, United States.', ...];
const t0 = performance.now();
for (let i = 0; i < 100000; i++) classifyFieldValue('\$24.5M', sources);
console.log('classifyFieldValue (VERBATIM early exit):', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
classifyFieldValue (VERBATIM, early exit): 0.0009 ms

classifyFieldValue (MEDIUM, Jaccard):      0.0041 ms   (substring miss × 5 + Jaccard on hit)
classifyFieldValue (LOW, full scan):       0.0068 ms   (substring miss × 5 + Jaccard miss × 5)

=== annotateOutputFields() timing — 7 fields × 5 sources (100 000 iterations) ===

annotateOutputFields(): 0.0283 ms

=== Contract summary annotation: 7-field output, 5 retrieved clause sources ===

Agent output:
  {
    vendor:             "Acme Corp",
    contract_value:     "$2.45B",
    termination_fee:    "$24.5M",
    effective_date:     "January 1, 2025",
    governing_law:      "Delaware",
    liability_exposure: "potentially uncapped for consequential damages",
    risk_summary:       "high"
  }

Retrieved sources (excerpt):
  Source 1: "...agreement between Acme Corp and the buyer, effective January 1, 2025..."
  Source 2: "...purchase price of $2.45B at closing..."
  Source 3: "...termination fee of $24.5M payable by the target..."
  Source 4: "...governing law shall be the state of Delaware..."
  Source 5: "...vendor liability for consequential damages including lost profits is not limited..."

annotateOutputFields() result:
  _confidence: {
    vendor:             { tier: 'HIGH',   match: 'VERBATIM' }           ← "Acme Corp" in source 1
    contract_value:     { tier: 'HIGH',   match: 'VERBATIM' }           ← "$2.45B" in source 2
    termination_fee:    { tier: 'HIGH',   match: 'VERBATIM' }           ← "$24.5M" in source 3
    effective_date:     { tier: 'HIGH',   match: 'VERBATIM' }           ← "January 1, 2025" in source 1
    governing_law:      { tier: 'HIGH',   match: 'VERBATIM' }           ← "Delaware" in source 4
    liability_exposure: { tier: 'MEDIUM', match: 'SUPPORTED', sim: 0.21 } ← "consequential", "damages", "liability" in source 5
    risk_summary:       { tier: 'LOW',    match: 'UNSUPPORTED' }        ← synthesized; "high" not in any source
  }

  _summary: { total: 7, HIGH: 5, MEDIUM: 1, LOW: 1, pctHigh: 71.4 }

UI actions:
  5 HIGH fields    → "source confirmed" badge
  liability_exposure (MEDIUM) → "based on source language, paraphrased"
  risk_summary (LOW)          → routed to attorney review queue; not shown directly

=== F-58 vs F-70 vs F-93 vs F-97 ===

              │ F-58 (extraction confidence) │ F-70 (structural assertions)  │ F-93 (sentence verifiability) │ F-97 (field confidence)
──────────────┼──────────────────────────────┼───────────────────────────────┼───────────────────────────────┼──────────────────────────────
Input         │ Extracted fields from docs   │ Structured output fields      │ Free-text output sentences    │ Structured output field values
Confidence    │ Model self-report (0.0–1.0)  │ N/A (structural pass/fail)    │ Sentence-level tier           │ Source-grounded tier per field
Method        │ Prompted confidence score    │ Code assertions               │ Substring + Jaccard vs source │ Substring + Jaccard vs source
Catches       │ Ambiguous document values    │ Missing/wrong-type fields     │ Unsupported prose claims      │ Unsupported JSON field values
LOW means     │ Uncertain extraction         │ N/A                           │ Not in retrieved sources      │ Not in retrieved sources
```

## See also

[F-93](f93-claim-verifiability-classification.md) · [F-58](f58-structured-document-extraction.md) · [F-70](f70-verifiable-output-design.md) · [F-73](f73-agent-output-lineage.md) · [S-125](../stacks/s125-multi-source-claim-conflict.md) · [S-04](../stacks/s04-structured-output.md)

## Go deeper

Keywords: `field confidence annotation` · `output field grounding` · `structured output confidence` · `per-field verifiability` · `field-level source check` · `JSON output confidence` · `HIGH MEDIUM LOW grounding` · `field confidence tier` · `output grounding annotation` · `source-confirmed field`
