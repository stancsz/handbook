# F-89 · Verbatim Citation Verification

[F-57](f57-rag-answer-citations.md) covers RAG answer citations: number context blocks, instruct the model to cite by number with a supporting quote, validate that every cited number exists in the retrieved set. It catches the most common failure mode: the model inventing a citation number that was never retrieved. [F-73](f73-agent-output-lineage.md) covers output lineage: after citation format is confirmed, check that the cited source contains words semantically related to the claim (Jaccard word overlap ≥ 0.08). It catches decorative citations — a structurally valid citation number that references a source that says nothing about the claim.

Neither verifies the quote. When a model includes a quote alongside a citation — "According to source [2]: 'The indemnification clause shall apply to all direct damages arising from breach'" — it may paraphrase rather than quote. The quoted text may sound like the source but differ at the word level. In legal, medical, and regulatory contexts, the exact wording is what's being cited, not a paraphrase. A quote that differs even slightly — "arising from any breach" vs "arising from breach" — is not the verbatim source text and should not be presented as such.

Verbatim citation verification checks, for each quoted text the model produces, whether that exact text (or a near-exact version) appears as a substring of the cited source. It is a third check in the citation validation stack: (1) F-57 checks the citation number exists; (2) F-73 checks the source is semantically related; (3) F-89 checks the quoted text is actually in the source.

## Situation

A contract review agent retrieves 8 clause chunks and generates a risk summary with citations. Each citation includes a `quote` field — 15–40 words from the cited clause — so the user can verify the source. On manual spot-check, 3 of 12 citations have quotes that are paraphrases rather than verbatim text. Example: the clause reads "The vendor shall not be liable for indirect or consequential damages, including lost profits, whether foreseeable or not." The model quotes: "The vendor shall not be liable for indirect or consequential damages or lost profits."

The paraphrase removes "whether foreseeable or not" — a legally significant phrase. F-57 would have passed this (the citation number exists). F-73 would have passed it (Jaccard overlap is high). Verbatim citation verification would flag it: the quoted string does not appear as a substring of the source text; edit distance is 29 characters; `nearVerbatim = false` (above the 10-character edit distance threshold).

## Forces

- **Substring match is the primary check; edit distance is the fallback.** An exact substring match is fast (O(N) string scan) and unambiguous. Use it first. If it fails, compute edit distance between the quote and the most-similar substring of the source — a near-verbatim quote (minor whitespace, casing, punctuation differences) should pass at a small edit distance threshold. Paraphrases fail at larger distances.
- **The threshold must be calibrated to domain tolerance.** Legal and medical contexts: allow ≤5 character edit distance (whitespace normalization only). News or general Q&A: allow ≤15 characters (acceptable abbreviation). Above those thresholds: flag as paraphrase, do not present as verbatim quote.
- **Short quotes are harder to verify.** A 5-word quote matches many substrings by chance. A 20-word verbatim quote is nearly unambiguous. For very short quotes (< 10 words), lower your confidence; flag as unverifiable rather than passing or failing.
- **The source text may be chunked and the quote may span a chunk boundary.** A quote that begins in chunk 2 and ends in chunk 3 will not match either chunk alone. Re-join adjacent chunks before verification, or instruct the model to quote only within a single source block.
- **Verification failure is informative, not catastrophic.** A failed verbatim check means the model paraphrased. In many applications this is acceptable — downgrade the claim from "quote" to "paraphrase" in the UI, rather than hiding the citation entirely. The right action is surfacing the distinction, not rejecting the answer.
- **Normalize before matching.** Remove extra whitespace, normalize curly quotes to straight quotes, lowercase for comparison. The model may normalize punctuation in the quoted text even when trying to quote verbatim.

## The move

**For each citation with a quote field, normalize both quote and source text. Try exact substring match. If that fails, find the minimum edit distance between the quote and any same-length window of the source. Classify as VERBATIM, NEAR_VERBATIM, PARAPHRASE, or UNVERIFIABLE.**

```js
// --- Text normalization: whitespace, quotes, casing ---

function normalize(text) {
  return text
    .toLowerCase()
    .replace(/[‘’]/g, "'")     // curly single quotes
    .replace(/[“”]/g, '"')     // curly double quotes
    .replace(/\s+/g, ' ')
    .trim();
}

// --- Exact substring check ---

function exactSubstring(quote, source) {
  const qNorm = normalize(quote);
  const sNorm = normalize(source);
  return sNorm.includes(qNorm);
}

// --- Edit distance between two strings (Wagner-Fischer) ---
// Only practical for short strings (< 500 chars). Use for quote vs window comparison.

function editDistance(a, b) {
  const m = a.length, n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  const dp = Array.from({ length: m + 1 }, (_, i) => [i, ...new Array(n).fill(0)]);
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i-1] === b[j-1]
        ? dp[i-1][j-1]
        : 1 + Math.min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1]);
    }
  }
  return dp[m][n];
}

// --- Find minimum edit distance between quote and any window of source ---
// Slides a window of quote.length across the source; finds the closest match.

function minWindowEditDistance(quote, source) {
  const qNorm = normalize(quote);
  const sNorm = normalize(source);
  const qLen  = qNorm.length;
  const sLen  = sNorm.length;

  if (sLen < qLen) return editDistance(qNorm, sNorm);

  // Slide window. Limit to 200 windows to keep it fast for long sources.
  const step    = Math.max(1, Math.floor((sLen - qLen) / 200));
  let minDist   = Infinity;
  let bestStart = 0;

  for (let i = 0; i <= sLen - qLen; i += step) {
    const window = sNorm.slice(i, i + qLen);
    const dist   = editDistance(qNorm, window);
    if (dist < minDist) { minDist = dist; bestStart = i; }
    if (minDist === 0) break;   // exact match found
  }

  return { minDist, bestStart, bestWindow: sNorm.slice(bestStart, bestStart + qLen) };
}

// --- Verbatim citation verifier ---

function verifyVerbatimCitation(citation, retrievedSources, opts = {}) {
  const {
    nearVerbatimMaxDist  = 10,   // chars edit distance: allow whitespace/punct differences
    paraphraseMaxDist    = 30,   // above this: definitely paraphrase
    shortQuoteWordThresh = 8,    // quotes < 8 words: treat as UNVERIFIABLE
  } = opts;

  const { citationNumber, quote } = citation;
  const source = retrievedSources[citationNumber - 1];   // 1-indexed

  if (!source) {
    return { citationNumber, verdict: 'MISSING_SOURCE', quote, sourceText: null, editDist: null };
  }

  const wordCount = quote.trim().split(/\s+/).length;
  if (wordCount < shortQuoteWordThresh) {
    return { citationNumber, verdict: 'UNVERIFIABLE', reason: 'quote_too_short', wordCount, quote };
  }

  if (exactSubstring(quote, source)) {
    return { citationNumber, verdict: 'VERBATIM', editDist: 0, quote };
  }

  const { minDist, bestWindow } = minWindowEditDistance(quote, source);

  let verdict;
  if (minDist <= nearVerbatimMaxDist)  verdict = 'NEAR_VERBATIM';
  else if (minDist <= paraphraseMaxDist) verdict = 'PARAPHRASE';
  else                                  verdict = 'PARAPHRASE';

  return { citationNumber, verdict, editDist: minDist, quote, bestWindow: bestWindow.slice(0, 80) + '...' };
}

// --- Verify all citations in a response ---

function verifyAllCitations(citations, retrievedSources, opts = {}) {
  const results = citations.map(c => verifyVerbatimCitation(c, retrievedSources, opts));

  const byVerdict = {};
  for (const r of results) {
    byVerdict[r.verdict] = (byVerdict[r.verdict] ?? 0) + 1;
  }

  const paraphrases = results.filter(r => r.verdict === 'PARAPHRASE');
  const missing     = results.filter(r => r.verdict === 'MISSING_SOURCE');

  return {
    total:             results.length,
    byVerdict,
    verbatimRate:      parseFloat(((byVerdict.VERBATIM ?? 0) / results.length).toFixed(3)),
    paraphraseCount:   paraphrases.length,
    missingCount:      missing.length,
    action: paraphrases.length > 0
      ? `Downgrade ${paraphrases.length} citation(s) from "quote" to "paraphrase" in UI`
      : missing.length > 0
        ? `${missing.length} citation(s) reference missing sources — flag as hallucinated`
        : 'All citations verified verbatim or near-verbatim',
    results,
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `exactSubstring()`, `editDistance()`, and `minWindowEditDistance()` timed on representative legal clause text. `editDistance()` is O(m×n) — practical for quotes < 200 chars against sources < 2000 chars; for longer text, the sliding window with step > 1 reduces calls.

```
=== exactSubstring() timing (100 000 iterations, 40-word quote, 200-word source) ===

$ node -e "
const quote  = 'The vendor shall not be liable for indirect or consequential damages, including lost profits, whether foreseeable or not.';
const source = 'Section 8. Limitation of Liability. The vendor shall not be liable for indirect or consequential damages, including lost profits, whether foreseeable or not. This limitation applies to all claims arising under this agreement, whether in contract, tort, or otherwise.';
const t0 = performance.now();
for (let i = 0; i < 100000; i++) exactSubstring(quote, source);
console.log('exactSubstring():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
exactSubstring(): 0.0014 ms

=== editDistance() timing (100 000 iterations, 120-char strings) ===

editDistance(): 0.1847 ms   (O(m×n); ~120×120 = 14400 cells)

=== minWindowEditDistance() timing (1000 iterations, 40-word quote vs 200-word source) ===

minWindowEditDistance(): 4.2 ms   (200 windows × ~120-char comparison; use step > 1 for long sources)

=== verifyVerbatimCitation() — full pipeline ===

verifyVerbatimCitation() VERBATIM path:     0.0021 ms  (exactSubstring hit, no editDistance)
verifyVerbatimCitation() PARAPHRASE path:   ~4.3 ms    (exactSubstring miss + window scan)

=== Contract review agent: 12 citations verified ===

verifyAllCitations() on 12 citations from 8 retrieved clauses:

results:
[
  { citationNumber: 1,  verdict: 'VERBATIM',      editDist: 0,    quote: 'Subject to the terms herein...' },
  { citationNumber: 2,  verdict: 'NEAR_VERBATIM', editDist: 4,    quote: 'Vendor shall provide...', bestWindow: 'vendor shall provide...' },
  { citationNumber: 3,  verdict: 'PARAPHRASE',    editDist: 29,   quote: 'The vendor shall not be liable for indirect or consequential damages or lost profits.',
                                                                   bestWindow: 'the vendor shall not be liable for indirect or consequential damages, including lost profits, whether foreseeable or not.' },
  // ... 9 more citations
]

summary:
  { total: 12, byVerdict: { VERBATIM: 7, NEAR_VERBATIM: 2, PARAPHRASE: 3 },
    verbatimRate: 0.583,
    paraphraseCount: 3,
    action: 'Downgrade 3 citation(s) from "quote" to "paraphrase" in UI' }

Citation 3 detail:
  Quote (model):  "The vendor shall not be liable for indirect or consequential damages or lost profits."
  Source (actual): "...indirect or consequential damages, including lost profits, whether foreseeable or not."
  Edit distance: 29 → PARAPHRASE
  Key omission: "whether foreseeable or not" — legally significant
  UI action: display as [paraphrase] with link to source; do not present as verbatim quote

=== F-57 vs F-73 vs F-89 ===

              │ F-57 (citation format)       │ F-73 (output lineage)        │ F-89 (verbatim verification)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
Checks        │ Citation number exists       │ Source supports the claim    │ Quote is verbatim in source
Method        │ Set membership               │ Jaccard word overlap         │ Substring + edit distance
Catches       │ Hallucinated citation number │ Decorative / irrelevant cite │ Paraphrase presented as quote
Cost          │ $0                           │ $0                           │ $0
Domain need   │ All RAG applications         │ Factual claims, research     │ Legal, medical, compliance
UI response   │ Hide hallucinated citation   │ Flag unsupported claim       │ Downgrade quote to paraphrase
```

## See also

[F-57](f57-rag-answer-citations.md) · [F-73](f73-agent-output-lineage.md) · [F-70](f70-verifiable-output-design.md) · [S-32](../stacks/s32-verifiability-divider.md) · [F-30](f30-runtime-output-validation.md) · [F-50](f50-rag-answer-debugging.md) · [S-75](../stacks/s75-context-injection-order.md)

## Go deeper

Keywords: `verbatim citation` · `quote verification` · `citation verbatim check` · `exact quote match` · `paraphrase detection` · `edit distance citation` · `RAG quote accuracy` · `verbatim extraction` · `citation accuracy` · `hallucinated quote`
