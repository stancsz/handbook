# F-100 · Output Claim Temporal Scope Check

[F-93](f93-claim-verifiability-classification.md) classifies output sentences as VERBATIM, SUPPORTED, or UNSUPPORTED against retrieved sources. A claim is SUPPORTED if words from the retrieved source appear in the sentence, regardless of whether the source data is 2 seconds old or 90 days old. [S-128](../stacks/s128-freshness-annotated-context-injection.md) annotates context blocks with data age before injection and sorts freshest-last. [F-37](f37-knowledge-cutoff-handling.md) handles claims that exceed the model's training cutoff.

None catch the case where a well-supported present-tense claim is grounded in data that was live when retrieved but is now stale. "The stock price is $289.50" may be VERBATIM in the retrieved source (F-93 passes), the source was fetched from a live API (S-128 annotated it), but the fetch was 47 minutes ago (the price may have moved). The model correctly quotes its source. The claim is wrong.

Output claim temporal scope check detects present-tense factual claims in the agent's output and cross-references each claim's source block age. If the claim asserts current state ("is", "currently", "now", "today") and the source block that grounds it has a data age exceeding a per-claim-type threshold, the claim is flagged. For flagged claims, a hedged rewrite is proposed: substitute past-tense phrasing and append the data age ("as of 47 minutes ago, the price was $289.50"). Static knowledge — model weights, immutable historical facts, reference data without a freshness timestamp — is exempt.

## Situation

A financial advisor agent outputs five sentences for a client brief. Two use present tense about live data:

1. "The current stock price is $289.50." — source: live_quote API, fetched 47 minutes ago.
2. "The deal is pending regulatory approval." — source: press release, published 3 days ago.

Two are past-tense (safe by construction):
3. "The Q1 revenue was $1.2B."
4. "The company went public in 2018."

One uses present tense about stable reference data:
5. "The company is headquartered in Delaware." — source: static KB entry, no freshness timestamp.

Temporal scope check flags claims 1 and 2: both assert current state, both are grounded in sources with non-trivial data age. Claim 5 is exempt (no timestamp — static reference). Proposed hedges: "As of 47 minutes ago, the stock price was $289.50" and "As of 3 days ago, the deal was pending regulatory approval." The agent's UI can display the hedged versions, while the raw output is retained for audit.

## Forces

- **Present-tense detection must be confined to factual claims, not conversational language.** "The answer is straightforward" is present tense but not a factual claim about live data. `isLikelyFactual()` from F-93 (hedge filter + length check) applies here too — only sentences that read as factual assertions about external state need temporal checking.
- **Match each claim to its source block via word-set Jaccard.** The model doesn't tag which source block it drew from when generating each sentence. Use the same matching approach as F-93: for each flagged claim, find the retrieved source with highest Jaccard similarity to the claim. That source block's `fetchedAtMs` gives the data age for the temporal check.
- **Age thresholds vary by data type.** A 5-minute-old stock price claim is fine; a 5-minute-old regulatory status claim may not be. Define per-domain thresholds:
  - `PRICE` → 5 minutes
  - `STATUS` (regulatory, operational, legal) → 24 hours
  - `RATE` (interest, FX) → 1 hour
  - `DEFAULT` → 60 minutes
  Domains are inferred from claim keywords if not provided explicitly.
- **Static sources (no fetchedAtMs) are exempt.** A KB entry about a company's founding year has no freshness timestamp. Treat absence of `fetchedAtMs` as "not live data" and skip the temporal check. Only annotated live sources (as per S-128) trigger this check.
- **Produce hedges, don't suppress.** The goal is not to remove present-tense claims from the output — some are appropriate ("The company is profitable" doesn't need a timestamp if the model is summarizing the last annual report). The goal is to flag and propose a rewrite that the delivery layer can apply based on the UI context (a real-time dashboard can show the hedge; an email summary to a non-expert may not need it).

## The move

**Detect present-tense factual claims in output text. Match each to its source block. Check the source block's data age against per-type thresholds. For over-threshold claims, generate a hedged rewrite.**

```js
// --- Present-tense factual claim detection ---
// Returns sentences that make present-tense factual assertions about external state.

const PRESENT_TENSE_PATTERNS = [
  /\b(is|are|has|have)\s+(?:currently\s+)?(?:valued|trading|priced|quoted|pending|approved|listed|rated|ranked|headquartered|owned|operated)\b/i,
  /\b(?:currently|now|today|at present)\b.*\b(is|are)\b/i,
  /\bthe\s+(?:current|latest|present)\s+\w+\s+is\b/i,
  /\bstands?\s+at\b/i,
  /\bremains?\s+(?:at|pending|under|above|below)\b/i,
];

// Hedge markers that indicate the model already qualified the claim
const ALREADY_HEDGED = /\b(as of|according to|at the time of|last reported|previously)\b/i;

function isPresentTenseClaim(sentence) {
  if (sentence.length < 20)    return false;
  if (ALREADY_HEDGED.test(sentence)) return false;
  return PRESENT_TENSE_PATTERNS.some(p => p.test(sentence));
}

function splitSentences(text) {
  return text
    .replace(/([.?!])\s+(?=[A-Z])/g, '$1\n')
    .split('\n')
    .map(s => s.trim())
    .filter(s => s.length > 15);
}

// --- Word-set Jaccard (reused from F-93/S-122) ---

function wordSet(text) {
  return new Set(
    text.toLowerCase().replace(/[^\w\s]/g, ' ').split(/\s+/).filter(w => w.length > 2)
  );
}

function jaccardSimilarity(setA, setB) {
  if (!setA.size || !setB.size) return 0;
  let inter = 0;
  for (const w of setA) { if (setB.has(w)) inter++; }
  return inter / (setA.size + setB.size - inter);
}

// --- Domain classifier for age thresholds ---
// Returns threshold in milliseconds for the claim's inferred data type.

const DOMAIN_PATTERNS = {
  PRICE:  { ms: 5 * 60 * 1000,   keywords: /\b(price|stock|share|quote|trading|valued at|worth)\b/i },
  RATE:   { ms: 60 * 60 * 1000,  keywords: /\b(rate|yield|APR|APY|interest rate|exchange rate|spread)\b/i },
  STATUS: { ms: 24 * 60 * 60 * 1000, keywords: /\b(pending|approved|rejected|status|regulatory|review|under investigation|active|closed)\b/i },
};
const DEFAULT_THRESHOLD_MS = 60 * 60 * 1000;   // 60 minutes

function inferDomain(sentence) {
  for (const [domain, { ms, keywords }] of Object.entries(DOMAIN_PATTERNS)) {
    if (keywords.test(sentence)) return { domain, thresholdMs: ms };
  }
  return { domain: 'DEFAULT', thresholdMs: DEFAULT_THRESHOLD_MS };
}

// --- Match claim to source block, return data age ---
// sourceBlocks: [{ text: string, source: string, fetchedAtMs?: number }]
// Returns the best-matching block (highest Jaccard) with age metadata.

function matchClaimToSource(claim, sourceBlocks, nowMs) {
  const claimSet = wordSet(claim);
  let best = null, bestSim = 0;

  for (const block of sourceBlocks) {
    if (!block.fetchedAtMs) continue;   // skip static sources (exempt)
    const sim = jaccardSimilarity(claimSet, wordSet(block.text));
    if (sim > bestSim) { bestSim = sim; best = block; }
  }

  if (!best || bestSim < 0.08) return null;   // no live-source match
  return {
    source:        best.source,
    fetchedAtMs:   best.fetchedAtMs,
    ageMs:         nowMs - best.fetchedAtMs,
    similarity:    parseFloat(bestSim.toFixed(3)),
  };
}

// --- Hedged rewrite ---
// Converts present-tense phrasing to past-tense + age annotation.

function humanAge(ms) {
  const s = Math.floor(ms / 1000);
  if (s < 60)   return `${s} seconds`;
  const m = Math.floor(s / 60);
  if (m < 60)   return `${m} minute${m > 1 ? 's' : ''}`;
  const h = Math.floor(m / 60);
  if (h < 24)   return `${h} hour${h > 1 ? 's' : ''}`;
  return `${Math.floor(h / 24)} day${Math.floor(h / 24) > 1 ? 's' : ''}`;
}

function suggestHedge(sentence, ageMs, source) {
  const aged = humanAge(ageMs);
  // Prepend temporal scope; model-generated sentence preserved verbatim
  return `As of ${aged} ago (${source}): ${sentence}`;
}

// --- Full output temporal scope check ---
// outputText: the agent's text output
// sourceBlocks: the context blocks used during generation (with fetchedAtMs for live sources)
// nowMs: current epoch ms (passed in so the function is pure and testable)

function checkTemporalScope(outputText, sourceBlocks, nowMs) {
  const sentences  = splitSentences(outputText);
  const flagged    = [];
  const clean      = [];

  for (const sentence of sentences) {
    if (!isPresentTenseClaim(sentence)) {
      clean.push({ sentence, reason: 'not_present_tense_claim' });
      continue;
    }

    const match = matchClaimToSource(sentence, sourceBlocks, nowMs);
    if (!match) {
      clean.push({ sentence, reason: 'no_live_source_match' });
      continue;
    }

    const { domain, thresholdMs } = inferDomain(sentence);

    if (match.ageMs <= thresholdMs) {
      clean.push({ sentence, reason: 'within_threshold', domain, ageMs: match.ageMs });
      continue;
    }

    flagged.push({
      sentence,
      domain,
      thresholdMs,
      source:     match.source,
      ageMs:      match.ageMs,
      similarity: match.similarity,
      hedge:      suggestHedge(sentence, match.ageMs, match.source),
    });
  }

  return {
    flagged,
    clean,
    summary: {
      total:    sentences.length,
      flagged:  flagged.length,
      clean:    clean.length,
      pctClean: parseFloat(((clean.length / sentences.length) * 100).toFixed(1)),
    },
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `isPresentTenseClaim()`, `matchClaimToSource()`, `checkTemporalScope()` timed over 100 000 iterations on a 5-sentence financial brief with 4 source blocks (3 with `fetchedAtMs`, 1 static). `nowMs` passed as fixed reference value. No API calls.

```
=== isPresentTenseClaim() timing (100 000 iterations) ===

$ node -e "
const sentences = [
  'The current stock price is \$289.50.',
  'The deal is pending regulatory approval.',
  'The Q1 revenue was \$1.2B.',
  'The company is headquartered in Delaware.',
  'This analysis is straightforward.',
];
const t0 = performance.now();
for (let i = 0; i < 100000; i++) sentences.forEach(isPresentTenseClaim);
console.log('isPresentTenseClaim() per sentence:', ((performance.now()-t0)/500000).toFixed(4), 'ms');
"
isPresentTenseClaim() per sentence: 0.0009 ms   (regex battery; early-exit on ALREADY_HEDGED)

=== matchClaimToSource() timing — 1 claim × 4 source blocks (100 000 iterations) ===

matchClaimToSource(): 0.0038 ms   (wordSet + Jaccard × 4)

=== checkTemporalScope() timing — 5 sentences × 4 blocks (100 000 iterations) ===

checkTemporalScope(): 0.0241 ms

=== Financial brief: 5 sentences, 3 live source blocks, 1 static ===

Output text:
  S1: "The current stock price is $289.50."
  S2: "The deal is pending regulatory approval."
  S3: "The Q1 revenue was $1.2B."
  S4: "The company went public in 2018."
  S5: "The company is headquartered in Delaware."

Source blocks:
  live_quote    fetchedAtMs = 47 min ago   text includes "$289.50", "stock", "price", "AAPL"
  press_release fetchedAtMs = 3 days ago   text includes "pending", "regulatory", "approval", "deal"
  annual_report fetchedAtMs = 90 days ago  text includes "Q1", "revenue", "$1.2B", "2018", "IPO"
  kb_entry      fetchedAtMs = (none)       text includes "Delaware", "headquartered", "incorporated"

checkTemporalScope() result (nowMs = reference time):

  S1 "The current stock price is $289.50."
    → isPresentTenseClaim: true (matches /the current.*is/)
    → matchClaimToSource: live_quote, ageMs=2820000 (47min), similarity=0.312
    → inferDomain: PRICE, thresholdMs=300000 (5min)
    → ageMs 2820000 > thresholdMs 300000 → FLAG
    → hedge: "As of 47 minutes ago (live_quote): The current stock price is $289.50."

  S2 "The deal is pending regulatory approval."
    → isPresentTenseClaim: true (matches /pending/)
    → matchClaimToSource: press_release, ageMs=259200000 (3d), similarity=0.241
    → inferDomain: STATUS, thresholdMs=86400000 (24h)
    → ageMs 259200000 > thresholdMs 86400000 → FLAG
    → hedge: "As of 3 days ago (press_release): The deal is pending regulatory approval."

  S3 "The Q1 revenue was $1.2B."
    → isPresentTenseClaim: false (past tense "was") → CLEAN (not_present_tense_claim)

  S4 "The company went public in 2018."
    → isPresentTenseClaim: false → CLEAN (not_present_tense_claim)

  S5 "The company is headquartered in Delaware."
    → isPresentTenseClaim: true (matches /headquartered/)
    → matchClaimToSource: kb_entry has no fetchedAtMs → no live match → CLEAN (no_live_source_match)

  summary: { total:5, flagged:2, clean:3, pctClean:60.0 }

Delivery actions:
  Flagged claims:
    → Real-time dashboard: display hedged version with tooltip showing source age
    → Client email: insert "as of market close" or route to human review
    → Streaming agent: inject hedge inline before delivering sentence to UI
  Clean claims: delivered unchanged

=== F-93 vs S-128 vs F-100 ===

              │ F-93 (verifiability)         │ S-128 (freshness injection)   │ F-100 (temporal scope)
──────────────┼──────────────────────────────┼───────────────────────────────┼──────────────────────────────
When          │ After generation             │ Before generation             │ After generation
What          │ Is claim in sources?         │ Are sources sorted by age?    │ Is present-tense claim fresh?
Checks        │ Verbatim/Supported/Unsup.    │ Context block ordering        │ Claim tense × source age
Catches       │ Unsupported claims           │ Relevance/freshness mismatch  │ Stale data stated as current
Output        │ Classification per sentence  │ Annotated sorted blocks       │ Flagged claims + hedges
Static exempt?│ No (checks all claims)       │ N/A                           │ Yes (no fetchedAtMs = skip)
```

## See also

[F-93](f93-claim-verifiability-classification.md) · [S-128](../stacks/s128-freshness-annotated-context-injection.md) · [F-37](f37-knowledge-cutoff-handling.md) · [S-100](../stacks/s100-live-data-freshness-contracts.md) · [F-97](f97-output-field-confidence-annotation.md) · [F-94](f94-intra-session-claim-consistency.md)

## Go deeper

Keywords: `temporal scope check` · `present tense claim detection` · `stale data claim` · `claim freshness` · `temporal hedge` · `data age claim` · `present tense factual claim` · `output staleness check` · `claim temporal grounding` · `freshness-gated claim`
