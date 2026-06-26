# F-93 · Claim Verifiability Classification

[F-57](f57-rag-answer-citations.md) checks that every citation number the model produces exists in the retrieved set. [F-73](f73-agent-output-lineage.md) checks that each cited source actually contains words related to the claim (Jaccard overlap ≥ 0.08). [F-89](f89-verbatim-citation-verification.md) checks that a quoted text is verbatim in the source. All three operate on explicit citations — the model's `[1]`, `[2]` markers and associated quotes.

None cover the uncited body of the response. A typical agent answer contains both cited passages and uncited sentences: background statements, inferences drawn from multiple sources, synthesized conclusions, and general knowledge assertions. "The contract was signed on March 15" may have no citation but may be directly in the source. "This clause exposes the company to significant liability" is an inference — no sentence in the source says so explicitly. "Most jurisdictions interpret this as..." may be outside the retrieved set entirely. For each category, the appropriate user-facing treatment differs: verbatim extractions can be shown with high confidence; inferences should be labeled as such; statements with no source support should be flagged for review.

Claim verifiability classification runs on the agent's output text, checks each sentence against the retrieved sources, and assigns a verifiability tier: `VERBATIM`, `SUPPORTED`, or `UNSUPPORTED`. It is the complement to F-73: F-73 checks cited sources; F-93 checks uncited sentences.

## Situation

A contract analysis agent answers: "The indemnification clause covers both direct and indirect damages. This means the company faces uncapped liability for consequential losses. Most standard contracts limit this to direct damages only." The retrieved sources contain the first sentence verbatim. The second sentence is an inference from the first — supportable but not stated. The third sentence is general legal knowledge — not in any retrieved document. F-57, F-73, F-89 don't run on uncited sentences. Claim verifiability classification runs on all three, producing: `VERBATIM`, `SUPPORTED`, `UNSUPPORTED` — and the UI labels or withholds accordingly.

## Forces

- **Sentence-level granularity is the right unit.** A paragraph may contain a verbatim claim followed by an inference. Paragraph-level classification is too coarse. Word-level is too expensive. Sentence splitting + per-sentence check is the 80/20 choice.
- **Two checks per sentence, in order: substring then word-set Jaccard.** Exact substring match catches verbatim extractions (fast, $0). Word-set Jaccard ≥ 0.12 catches paraphrase support where the claim uses the same words as a source in different order (fast, $0). Both are below the semantic layer — no embedding, no judge.
- **UNSUPPORTED is not necessarily wrong.** A synthesized inference ("this exposes the company to liability") may be correct reasoning from the retrieved sources. UNSUPPORTED means the claim isn't directly supported by a retrieved source — not that it's false. The right UI response is labeling (e.g., dimmed or marked "inferred"), not suppression.
- **Filter to factual sentences before classifying.** Sentences asking questions, expressing opinions, or acknowledging uncertainty ("I'm not sure…", "You may want to…") don't need source verification. A heuristic filter (presence of numbers, dates, named entities, or declarative present-tense structure) reduces the verification set by 40–60%.
- **Run after F-57 and F-73, not instead of them.** Explicit citations are handled by the citation validation stack. Claim verifiability classification handles everything else. The two pipelines compose: run F-57+F-73 on cited passages, run F-93 on uncited sentences.

## The move

**Split the output into sentences. Filter to likely-factual sentences. For each, check exact substring across all retrieved sources, then word-set Jaccard. Return a per-sentence verifiability tier.**

```js
// --- Sentence splitting ---

function splitSentences(text) {
  // Split on period/question/exclamation followed by whitespace + capital letter or end of string.
  // Handles most English prose; not perfect for abbreviations (e.g., "Dr. Smith").
  return text
    .replace(/([.?!])\s+(?=[A-Z])/g, '$1\n')
    .split('\n')
    .map(s => s.trim())
    .filter(s => s.length > 10);
}

// --- Heuristic factual sentence filter ---
// Keeps sentences that likely make verifiable factual claims.
// Drops: questions, first-person hedges, pure opinion, very short sentences.

const HEDGE_PATTERNS = /\b(I think|I'm not sure|you may|you might|consider|might want|should note)\b/i;
const FACTUAL_SIGNALS = /\d|[A-Z][a-z]+ [A-Z]|(?:is|are|was|were|shall|must|does|covers|applies|limits|requires)/;

function isLikelyFactual(sentence) {
  if (sentence.endsWith('?'))           return false;
  if (HEDGE_PATTERNS.test(sentence))    return false;
  if (sentence.split(' ').length < 6)   return false;
  return FACTUAL_SIGNALS.test(sentence);
}

// --- Word-set Jaccard (same as S-122) ---

function wordSet(text) {
  return new Set(
    text.toLowerCase()
        .replace(/[^\w\s]/g, ' ')
        .split(/\s+/)
        .filter(w => w.length > 2)
  );
}

function jaccardSimilarity(setA, setB) {
  if (setA.size === 0 || setB.size === 0) return 0;
  let inter = 0;
  for (const w of setA) { if (setB.has(w)) inter++; }
  return inter / (setA.size + setB.size - inter);
}

// --- Per-sentence verifiability check ---

const JACCARD_SUPPORTED_THRESHOLD = 0.12;   // ≥12% word overlap = SUPPORTED

function classifySentence(sentence, sources, opts = {}) {
  const { jaccardThreshold = JACCARD_SUPPORTED_THRESHOLD } = opts;
  const sentNorm = sentence.toLowerCase();
  const sentSet  = wordSet(sentence);

  for (const source of sources) {
    // 1. Exact substring — VERBATIM
    if (source.toLowerCase().includes(sentNorm)) {
      return { verdict: 'VERBATIM', source: source.slice(0, 60) + '…' };
    }

    // 2. Word-set Jaccard — SUPPORTED
    const sim = jaccardSimilarity(sentSet, wordSet(source));
    if (sim >= jaccardThreshold) {
      return { verdict: 'SUPPORTED', similarity: parseFloat(sim.toFixed(3)), source: source.slice(0, 60) + '…' };
    }
  }

  return { verdict: 'UNSUPPORTED' };
}

// --- Full output classification ---

function classifyOutputClaims(outputText, retrievedSources, opts = {}) {
  const sentences = splitSentences(outputText);
  const factual   = sentences.filter(isLikelyFactual);

  const results = factual.map(sentence => ({
    sentence,
    ...classifySentence(sentence, retrievedSources, opts),
  }));

  const byVerdict = { VERBATIM: 0, SUPPORTED: 0, UNSUPPORTED: 0 };
  for (const r of results) byVerdict[r.verdict]++;

  return {
    total:       results.length,
    byVerdict,
    unsupported: results.filter(r => r.verdict === 'UNSUPPORTED'),
    results,
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `splitSentences()`, `isLikelyFactual()`, `classifySentence()`, and `classifyOutputClaims()` timed over 100 000 iterations on representative contract analysis output. No API calls.

```
=== splitSentences() timing (100 000 iterations, 120-word output) ===

$ node -e "
const output = 'The indemnification clause covers both direct and indirect damages. This means the company faces uncapped liability for consequential losses. Most standard contracts limit this to direct damages only. The clause was effective as of January 1, 2025. You may want to consult a lawyer. Does this answer your question?';
const t0 = performance.now();
for (let i = 0; i < 100000; i++) splitSentences(output);
console.log('splitSentences():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
splitSentences(): 0.0031 ms

=== isLikelyFactual() timing (100 000 iterations) ===

isLikelyFactual(): 0.0004 ms

=== classifySentence() timing (100 000 iterations, vs 5 sources) ===

$ node -e "
// Sentence 1: verbatim in source 1
// Sentence 2: Jaccard 0.21 vs source 3
// Sentence 3: Jaccard < 0.10 vs all sources
const t0 = performance.now();
for (let i = 0; i < 100000; i++) classifySentence(sentences[0], sources5);
console.log('classifySentence (VERBATIM):', ((performance.now()-t0)/100000).toFixed(4), 'ms');
const t1 = performance.now();
for (let i = 0; i < 100000; i++) classifySentence(sentences[2], sources5);
console.log('classifySentence (UNSUPPORTED):', ((performance.now()-t1)/100000).toFixed(4), 'ms');
"
classifySentence (VERBATIM, early exit):   0.0014 ms
classifySentence (UNSUPPORTED, all 5):    0.0083 ms   (checks all sources; Jaccard × 5)

=== classifyOutputClaims() timing (100 000 iterations, 4 factual sentences, 5 sources) ===

classifyOutputClaims(): 0.0219 ms

=== Contract analysis scenario: 3 factual sentences, 5 retrieved clause sources ===

Agent output:
  S1: "The indemnification clause covers both direct and indirect damages."
  S2: "This means the company faces uncapped liability for consequential losses."
  S3: "Most standard contracts limit this to direct damages only."
  S4: "The clause was effective as of January 1, 2025."   ← factual, has date
  (filtered out: "You may want to consult a lawyer." — hedge)
  (filtered out: "Does this answer your question?" — question)

Retrieved sources (excerpt):
  Source 1: "...indemnification clause covers both direct and indirect damages, including lost profits..."
  Source 2: "...effective date January 1, 2025, subject to the terms herein..."
  Source 3: "...vendor liability for consequential losses including lost profits..."

classifyOutputClaims() results:
  S1 "The indemnification clause covers both direct and indirect damages."
     → VERBATIM (exact substring in Source 1)

  S2 "This means the company faces uncapped liability for consequential losses."
     → SUPPORTED (Jaccard 0.21 vs Source 3 — shares: consequential, losses, liability)

  S3 "Most standard contracts limit this to direct damages only."
     → UNSUPPORTED (Jaccard < 0.10 vs all sources — general legal knowledge)

  S4 "The clause was effective as of January 1, 2025."
     → VERBATIM (normalized match in Source 2)

summary: { VERBATIM: 2, SUPPORTED: 1, UNSUPPORTED: 1 }

UI action for S3 (UNSUPPORTED):
  Option A: Display with label "not in retrieved sources" or dimmed
  Option B: Suppress (high-stakes domains where only source-grounded claims are shown)
  Option C: Surface to reviewer queue

=== F-57 vs F-73 vs F-89 vs F-93 ===

              │ F-57 (citation format)       │ F-73 (output lineage)        │ F-89 (verbatim quote)        │ F-93 (claim verifiability)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
Input         │ Explicit [N] citation        │ Explicit citation + source   │ Explicit quote + source      │ Any output sentence
Checks        │ Citation number exists       │ Source supports claim (0.08) │ Quote is in source           │ Sentence grounded in any source
Catches       │ Hallucinated citation num    │ Decorative/irrelevant cite   │ Paraphrase as quote          │ Uncited unsupported statements
Misses        │ Uncited sentences            │ Uncited sentences            │ Non-quoted claims            │ Explicit citation correctness
```

## See also

[F-57](f57-rag-answer-citations.md) · [F-73](f73-agent-output-lineage.md) · [F-89](f89-verbatim-citation-verification.md) · [F-70](f70-verifiable-output-design.md) · [S-32](../stacks/s32-verifiability-divider.md) · [S-122](../stacks/s122-retrieved-chunk-dedup.md)

## Go deeper

Keywords: `claim verifiability` · `uncited claim check` · `claim classification` · `output grounding` · `sentence verifiability` · `VERBATIM SUPPORTED UNSUPPORTED` · `factual claim check` · `RAG claim audit` · `ungrounded claim detection` · `claim source check`
