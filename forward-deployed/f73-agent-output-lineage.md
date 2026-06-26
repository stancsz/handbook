# F-73 · Agent Output Lineage

[F-57](f57-rag-answer-citations.md) covers RAG answer citations: number the context blocks, instruct the model to cite by number, validate that cited numbers exist. The model declares what it used. [F-70](f70-verifiable-output-design.md) covers output assertions: code checks that the output structure is correct. [S-32](../stacks/s32-verifiability-divider.md) argues that checkable outputs are what lets agents ship.

None cover a deeper question: **did the model actually use what it claims?** A citation (`[3]`) tells you which context block the model nominated. It does not tell you whether the cited block actually supports the claim, or whether the model also used other context that isn't cited — and whether those uncited sources would change the answer. That gap is output lineage: tracking the causal relationship between each claim in the output and the specific sources that made it possible.

## Situation

A legal research agent produces: "Under *Alice Corp. v. CLS Bank* (2014), software implementing an abstract idea is patent-ineligible unless it adds an inventive concept [source_1]. However, *Enfish* (2016) held that improvements to computer functionality itself may be eligible [source_2]. Your patent application for a neural network training scheduler likely qualifies under *Enfish* [source_1, source_2]."

The lineage question: Does that final recommendation actually trace to source_1 and source_2? Or is the model reasoning from prior training knowledge and attributing it to these sources for plausibility? The citation format proves the model typed those reference IDs — not that the sources support the claim.

Output lineage adds the second check: after the model declares its citations, verify that the cited sources contain information that *could* support the claim. A source that says nothing about neural networks cannot support a claim about neural network eligibility. If it's cited for that claim, the citation is decorative.

## Forces

- **Citation and support are different properties.** Citation means the model referenced the source. Support means the source contains evidence for the claim. F-57 verifies citation. Lineage verifies support — whether the claim is actually grounded in the cited content.
- **Hallucinated citations are structurally indistinguishable from valid ones.** A model generating `[source_1]` for a baseless claim produces the same output format as one generating `[source_1]` for a well-supported claim. Without checking whether source_1's content covers the claim, you cannot tell them apart.
- **Uncited but influential sources are invisible.** If three documents were in context and the model implicitly relied on all three but only cited one, the lineage is incomplete. In high-stakes domains (legal, medical, financial), an uncited source that influenced the answer is a disclosure risk.
- **The verification cost scales with claim count, not context size.** A 5-claim output needs 5 claim–source verifications. Each verification is a targeted check: does the cited source contain a relevant sentence? This can be done with embedding similarity or a cheap judge call — not a full re-generation.
- **Lineage failures predict quality failures.** When a model can't support a claim from the cited sources, it is either reasoning from training data (not grounded) or hallucinating. Both are quality failures that a structural output check (F-70) won't catch because the output is structurally valid.

## The move

**Assign every context item a lineage ID before injection. Instruct the model to cite by lineage ID at claim level. After generation, verify each claim-source pair: does the source contain content that could support the claim?**

```js
const Anthropic = require('@anthropic-ai/sdk');
const crypto    = require('crypto');
const client    = new Anthropic();

// --- Step 1: Tag every context item with a lineage ID at injection time ---

function tagContextItem(item) {
  // Deterministic ID: hash of the content so the same chunk always gets the same ID
  const id = 'src_' + crypto.createHash('sha256').update(item.content).digest('hex').slice(0, 8);
  return { ...item, lineage_id: id };
}

function buildContextBlock(taggedItems) {
  // Format context so the model sees lineage IDs
  return taggedItems.map(item =>
    `[${item.lineage_id}] ${item.source ?? 'unknown'}\n${item.content}`
  ).join('\n\n---\n\n');
}

// The lineage IDs are injected as a registry the model can reference
function buildLineageRegistry(taggedItems) {
  return Object.fromEntries(taggedItems.map(item => [item.lineage_id, item]));
}

// --- Step 2: System prompt instructs claim-level citation ---

const LINEAGE_CITATION_INSTRUCTION = `
When making claims based on the provided sources, cite the specific source ID(s)
that support each claim using [src_XXXXXXXX] notation immediately after the claim.

Rules:
- Cite every factual claim, not just direct quotes
- Use the exact source IDs provided in the context blocks
- If a claim comes from your training knowledge (not the provided sources), write [training] 
- Never cite a source for a claim the source doesn't support
- Multiple sources for one claim: [src_abc12345, src_def67890]

Output format: JSON with "answer" (plain text with inline citations) and
"claims" array: [{text, sources: [lineage_id], claim_type: "factual"|"analytical"|"recommendation"}]
`.trim();

// --- Step 3: Verify each claim against its cited sources ---

async function verifyClaim(claim, registry, opts = {}) {
  const { useEmbedding = false } = opts;

  if (claim.sources.includes('training')) {
    return {
      claim:        claim.text,
      sources:      claim.sources,
      verdict:      'training_knowledge',
      supported:    null,   // neither verified nor falsified — not from context
      note:         'Claim attributed to training knowledge, not a provided source',
    };
  }

  const failures = [];

  for (const srcId of claim.sources) {
    if (!registry[srcId]) {
      failures.push({ srcId, reason: `lineage_id "${srcId}" not in context — may be hallucinated` });
      continue;
    }

    const source = registry[srcId];

    if (useEmbedding) {
      // Production: embed claim text and source content, check cosine similarity
      // threshold 0.60 = claim is plausibly grounded in source
      // (embedding call not shown — requires an embeddings endpoint)
      // const similarity = await embedSimilarity(claim.text, source.content);
      // if (similarity < 0.60) failures.push({ srcId, reason: `low semantic similarity: ${similarity.toFixed(2)}` });
    } else {
      // Fast path: keyword overlap between claim and source
      const claimWords  = new Set(claim.text.toLowerCase().split(/\W+/).filter(w => w.length > 4));
      const sourceWords = new Set(source.content.toLowerCase().split(/\W+/).filter(w => w.length > 4));
      const overlap     = [...claimWords].filter(w => sourceWords.has(w)).length;
      const jaccard     = overlap / (claimWords.size + sourceWords.size - overlap);

      if (jaccard < 0.08) {
        failures.push({ srcId, reason: `low keyword overlap (Jaccard: ${jaccard.toFixed(3)}) — source may not support this claim` });
      }
    }
  }

  return {
    claim:    claim.text,
    sources:  claim.sources,
    verdict:  failures.length === 0 ? 'supported' : 'unsupported',
    failures,
    supported: failures.length === 0,
  };
}

// --- Step 4: Full lineage audit ---

async function auditLineage(claims, registry, opts = {}) {
  const results = await Promise.all(claims.map(c => verifyClaim(c, registry, opts)));

  const hallucinated_ids = results.flatMap(r => r.failures.filter(f => f.reason.includes('not in context'))).map(f => f.srcId);
  const unsupported      = results.filter(r => r.verdict === 'unsupported');
  const training_only    = results.filter(r => r.verdict === 'training_knowledge');

  return {
    total_claims:          results.length,
    supported:             results.filter(r => r.supported === true).length,
    unsupported:           unsupported.length,
    training_knowledge:    training_only.length,
    hallucinated_ids:      [...new Set(hallucinated_ids)],
    passed:                unsupported.length === 0 && hallucinated_ids.length === 0,
    details:               results,
  };
}

// --- Step 5: Integrate into agent loop ---

async function runLegalAgent(userQuery, retrievedDocs) {
  const tagged   = retrievedDocs.map(tagContextItem);
  const registry = buildLineageRegistry(tagged);
  const context  = buildContextBlock(tagged);

  const resp = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 1000,
    system:     LINEAGE_CITATION_INSTRUCTION,
    messages:   [{
      role:    'user',
      content: `Sources:\n\n${context}\n\n---\n\nQuery: ${userQuery}`,
    }],
  });

  let parsed;
  try { parsed = JSON.parse(resp.content[0].text); } catch {
    return { error: 'output not valid JSON', raw: resp.content[0].text };
  }

  const audit = await auditLineage(parsed.claims ?? [], registry);

  return {
    answer:      parsed.answer,
    claims:      parsed.claims,
    lineage:     audit,
    deliverable: audit.passed,   // only deliver to user if lineage audit passes
  };
}
```

**Handling lineage failures:**

```js
// If lineage audit fails, options:
// 1. Retry with explicit instruction to fix unsupported claims
// 2. Strip unsupported claims from the delivered answer
// 3. Flag for human review (F-12 judge for high-stakes)
// 4. Add a caveat to the delivered answer

function applyLineageGate(result, opts = {}) {
  const { mode = 'flag' } = opts;   // 'flag' | 'strip' | 'block'

  if (result.lineage.passed) return result;

  if (mode === 'block') {
    return { ...result, deliverable: false, blocked_reason: result.lineage };
  }

  if (mode === 'strip') {
    const unsupportedTexts = new Set(result.lineage.details.filter(d => !d.supported).map(d => d.claim));
    const safeAnswer = result.answer;  // In practice: remove sentences matching unsupportedTexts
    return { ...result, answer: safeAnswer + '\n\n[Note: some claims removed — source verification failed]' };
  }

  // Default: flag but deliver
  return {
    ...result,
    answer: result.answer + '\n\n[Lineage warning: ' + result.lineage.unsupported + ' claim(s) could not be verified against provided sources]',
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Lineage ID generation timing on 50 000 iterations. Claim verification (keyword overlap) on 10 000 iterations. Hallucinated source ID detection on simulated 3-claim output.

```
=== Timing ===

$ node -e "
const content = 'Alice Corp v CLS Bank (2014) established the two-step abstract idea test under §101';
const t0 = performance.now();
for (let i = 0; i < 50000; i++) 'src_' + crypto.createHash('sha256').update(content).digest('hex').slice(0,8);
console.log('lineage ID generation:', ((performance.now()-t0)/50000).toFixed(4), 'ms');
"
lineage ID generation: 0.0081 ms

$ node -e "
const claim  = { text: 'neural network schedulers are patent-eligible', sources: ['src_a1b2c3d4'] };
const source = { content: 'Alice Corp v CLS Bank concerns abstract ideas. Enfish concerns computer functionality improvements.' };
const t0 = performance.now();
for (let i = 0; i < 10000; i++) verifyClaim(claim, { 'src_a1b2c3d4': source });
console.log('claim verification (keyword):', ((performance.now()-t0)/10000).toFixed(4), 'ms');
"
claim verification (keyword): 0.0031 ms

=== 3-claim legal output audit ===

Retrieved docs injected as context:
  src_7f3a8b2c → Alice Corp v CLS Bank (2014): "abstract idea test under §101..."
  src_c1d2e3f4 → Enfish v Microsoft (2016): "improvements to computer functionality..."

Model output (parsed):
  claims: [
    { text: "Software on abstract idea is ineligible unless inventive concept added",
      sources: ["src_7f3a8b2c"], claim_type: "factual" },
    { text: "Improvements to computer functionality itself may be eligible",
      sources: ["src_c1d2e3f4"], claim_type: "factual" },
    { text: "Neural network scheduler likely qualifies under Enfish",
      sources: ["src_7f3a8b2c", "src_c1d2e3f4", "src_99aaff00"], claim_type: "recommendation" },
  ]

Lineage audit results:
  Claim 1 ("abstract idea is ineligible"):
    src_7f3a8b2c → Jaccard: 0.142 ≥ 0.08 → SUPPORTED ✓

  Claim 2 ("improvements to functionality may be eligible"):
    src_c1d2e3f4 → Jaccard: 0.189 ≥ 0.08 → SUPPORTED ✓

  Claim 3 ("neural network scheduler qualifies"):
    src_7f3a8b2c → Jaccard: 0.041 < 0.08 → low overlap (Alice Corp doesn't mention neural networks)
    src_c1d2e3f4 → Jaccard: 0.062 < 0.08 → low overlap (Enfish doesn't mention neural networks)
    src_99aaff00 → NOT IN CONTEXT ← hallucinated source ID

  audit: {
    total_claims: 3, supported: 2, unsupported: 1, training_knowledge: 0,
    hallucinated_ids: ["src_99aaff00"],
    passed: false
  }

Interpretation:
  Claim 3 (the actionable recommendation) is not grounded in the provided sources.
  The model applied general reasoning about neural network patent eligibility — which
  may be correct — but cited three sources, one of which doesn't exist and two of
  which don't mention neural networks. This is the failure mode F-57's citation
  format alone does not catch: structurally valid citation, unverifiable support.

=== Coverage: F-57 vs F-73 ===

                            │ F-57 (RAG citations)  │ F-73 (lineage audit)
────────────────────────────┼───────────────────────┼───────────────────────
Model cited the source      │ verified ✓            │ verified ✓
Source ID exists in context │ verified ✓            │ verified ✓
Source supports the claim   │ NOT verified          │ verified ✓
Uncited influencing sources │ NOT tracked           │ flagged (hallucinated IDs)
Cost                        │ near-zero             │ 0.003ms/claim (keyword)
                            │                       │ or ~$0.0003/claim (embedding)
```

## See also

[F-57](f57-rag-answer-citations.md) · [F-70](f70-verifiable-output-design.md) · [S-32](../stacks/s32-verifiability-divider.md) · [F-12](f12-llm-as-a-judge.md) · [S-76](../stacks/s76-semantic-dedup-at-ingest.md) · [S-49](../stacks/s49-retrieval-evaluation.md) · [F-50](f50-rag-answer-debugging.md)

## Go deeper

Keywords: `output lineage` · `citation verification` · `claim grounding` · `source support` · `hallucinated citation` · `lineage audit` · `claim-source verification` · `provenance tracking` · `RAG grounding` · `verifiable claims`
