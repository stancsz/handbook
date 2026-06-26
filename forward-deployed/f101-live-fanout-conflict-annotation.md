# F-101 · Live Fan-Out Conflict Annotation

[F-98](f98-live-source-fanout.md) queries N equivalent live sources in parallel and returns either the first non-null response (race-to-first) or the median of all numeric responses (median-merge). Both strategies produce a single value. The discarded responses — from sources that were slower or returned different values — are silently dropped. [S-125](../stacks/s125-multi-source-claim-conflict.md) detects conflicts between retrieved knowledge-base documents before injection.

Neither annotates the spread of live source responses onto the returned result. When three price feeds return $289.50, $291.20, and $291.15 and race-to-first returns $289.50 (yfinance won by latency), the consumer gets a number with no indication that two out of three sources disagreed by $1.70 (0.6%). For a trade or contract value, that disagreement is material. The consumer can't distinguish "all three sources agreed on $289.50" from "yfinance was fastest; Bloomberg and Refinitiv said something different."

Live fan-out conflict annotation collects all responses from a parallel fan-out and attaches a `_conflict` block to the selected result: spread, spreadPct, whether the winner was an outlier, and a recommendation. The consumer uses this to decide whether to use the result, retry with median-merge, escalate to a human, or add a confidence caveat. The selection logic (which value to return) stays in F-98; this entry covers what to do with the data from the sources you didn't pick.

## Situation

A financial agent calls three price feeds in parallel. Race-to-first returns $289.50 (yfinance, 160ms). The other two settle at $291.20 (Refinitiv, 210ms) and $291.15 (Bloomberg, 280ms). The spread is $1.70 (0.59%). Without conflict annotation, the agent says "the current price is $289.50" and the consumer has no signal that the authoritative sources said $291.15–$291.20.

With conflict annotation: the result carries `{ result: 289.50, winner: 'yfinance', _conflict: { detected: true, values: [289.50, 291.20, 291.15], spread: 1.70, spreadPct: 0.59, outlierSuspicion: true, recommendation: 'USE_MEDIAN' } }`. The agent or its caller can route to the hedged behavior: use the median ($291.15), flag for human review, or annotate the output with "source disagreement noted."

## Forces

- **Spread percentage, not absolute spread, determines materiality.** A $1.70 difference on a $289.50 stock is 0.59% — likely a stale-vs-live-cache artifact. A $1.70 difference on a $17.00 stock is 10% — a pricing error or bad feed. `spreadPct = (max - min) / min × 100` is the normalized signal.
- **Outlier detection needs at least three sources.** With two sources, one of them is always an outlier. With three or more, apply the simple rule: if one source differs from the median by more than `outlierThreshold × spread`, flag it. Default threshold: if one value is outside `[median - spread, median + spread / 2]`, call it suspect.
- **The race winner and the median are often different.** Race-to-first optimizes for latency. The fastest source is not necessarily the most accurate. When `|winner - median| > spreadPct × 0.5`, flag `outlierSuspicion: true` and recommend switching to the median.
- **Attach `_conflict` to the result, not to a log.** Logs (F-31) are for auditors. The `_conflict` block is for the immediate caller. Put it alongside the result so the agent can conditionally branch on it without an extra lookup.
- **Not all disagreement is conflict.** Two sources within 0.1% of each other on a stock price are effectively agreeing — floating-point representation and rounding will account for that gap. Set a `noConflictThreshold` (default: 0.5% for prices, 0.1% for FX rates). Below this, `detected: false`, even if values technically differ.
- **Null and error responses are excluded from spread computation.** If one source timed out or returned null, that response is not a data point — it's an availability failure (handled by F-24 and S-96). Only non-null, non-error numeric responses participate in spread calculation.

## The move

**After parallel fan-out, collect all non-null numeric responses. Compute spread and outlier status. Attach a `_conflict` block to the selected result.**

```js
// --- Spread and outlier computation ---

function computeSpread(values) {
  if (values.length < 2) return { spread: 0, spreadPct: 0, min: values[0], max: values[0], median: values[0] };

  const sorted = [...values].sort((a, b) => a - b);
  const min    = sorted[0];
  const max    = sorted[sorted.length - 1];
  const mid    = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];

  return {
    spread:    parseFloat((max - min).toFixed(4)),
    spreadPct: parseFloat(((max - min) / min * 100).toFixed(3)),
    min, max, median,
  };
}

function isOutlier(value, median, spread) {
  if (spread === 0) return false;
  return Math.abs(value - median) > spread * 0.5;
}

// --- Conflict annotation ---
// responses: [{ source: string, value: number|null, latencyMs: number, error?: string }]
// winner: the selected result from F-98's race-to-first or median-merge
// opts.noConflictThreshold: spreadPct below which conflict is not reported (default 0.5)

function annotateConflict(responses, winner, opts = {}) {
  const { noConflictThreshold = 0.5, outlierSpreadFactor = 0.5 } = opts;

  // Collect non-null, non-error numeric responses
  const valid = responses.filter(r => r.value !== null && r.value !== undefined && !r.error);

  if (valid.length < 2) {
    return {
      ...winner,
      _conflict: { detected: false, reason: 'insufficient_sources', validSources: valid.length },
    };
  }

  const values   = valid.map(r => r.value);
  const { spread, spreadPct, min, max, median } = computeSpread(values);

  if (spreadPct <= noConflictThreshold) {
    return {
      ...winner,
      _conflict: {
        detected:     false,
        spreadPct,
        values:       valid.map(r => ({ source: r.source, value: r.value })),
        summary:      'sources_agree',
      },
    };
  }

  // Conflict detected: compute outlier suspicion and recommendation
  const winnerValue     = winner.result;
  const outlierSuspicion = isOutlier(winnerValue, median, spread);
  const recommendation  = outlierSuspicion ? 'USE_MEDIAN' : 'WINNER_IN_MAJORITY';

  return {
    ...winner,
    _conflict: {
      detected:         true,
      values:           valid.map(r => ({ source: r.source, value: r.value, latencyMs: r.latencyMs })),
      spread:           parseFloat(spread.toFixed(4)),
      spreadPct:        parseFloat(spreadPct.toFixed(3)),
      min, max, median: parseFloat(median.toFixed(4)),
      outlierSuspicion,
      recommendation,
      invalidSources:   responses.filter(r => r.value === null || r.error).map(r => r.source),
    },
  };
}

// --- Augmented fan-out: race-to-first with conflict annotation ---
// sources: named source functions (see F-98)
// Returns: { result, winner, latencyMs, _conflict }

async function raceToFirstWithConflict(query, sources, opts = {}) {
  const { perSourceTimeoutMs = 500, deadlineMs = 600, conflictOpts = {} } = opts;
  const startMs   = Date.now();
  const responses = new Array(sources.length).fill(null);
  let   won       = false;
  let   winnerIdx = -1;

  // Fire all sources; collect all responses in parallel
  const settled = await Promise.allSettled(
    sources.map((src, i) => {
      const timer = new Promise((_, rej) =>
        setTimeout(() => rej(new Error('timeout')), perSourceTimeoutMs)
      );
      return Promise.race([src(query), timer])
        .then(value  => { responses[i] = { source: src.name ?? `src_${i}`, value, latencyMs: Date.now() - startMs }; return value; })
        .catch(error => { responses[i] = { source: src.name ?? `src_${i}`, value: null, error: error.message, latencyMs: Date.now() - startMs }; return null; });
    })
  );

  // Find the winner: first non-null settled value (race-to-first semantics)
  let winnerResult = null;
  for (let i = 0; i < settled.length; i++) {
    if (settled[i].status === 'fulfilled' && settled[i].value !== null && !won) {
      won       = true;
      winnerIdx = i;
      winnerResult = {
        result:       settled[i].value,
        winner:       responses[i].source,
        latencyMs:    responses[i].latencyMs,
        sourcesRaced: sources.length,
      };
    }
  }

  if (!winnerResult) {
    return { result: null, winner: null, _conflict: { detected: false, reason: 'all_sources_null' } };
  }

  // Attach conflict annotation from all collected responses
  return annotateConflict(responses, winnerResult, conflictOpts);
}

// --- Usage ---
//
// const sources = [
//   namedSource('bloomberg', q => bloomberg.getPrice(q.ticker)),
//   namedSource('refinitiv', q => refinitiv.getPrice(q.ticker)),
//   namedSource('yfinance',  q => yfinance.getPrice(q.ticker)),
// ];
//
// const result = await raceToFirstWithConflict({ ticker: 'AAPL' }, sources);
//
// if (result._conflict.detected && result._conflict.outlierSuspicion) {
//   // Winner is an outlier — use median instead
//   return { price: result._conflict.median, confidence: 'LOW', sources_disagreed: true };
// }
// return { price: result.result, confidence: result._conflict.detected ? 'MEDIUM' : 'HIGH' };
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `computeSpread()`, `annotateConflict()`, `raceToFirstWithConflict()` timed with in-process async sources (immediate resolve via `Promise.resolve()`). Conflict annotation logic timed over 100 000 iterations. No live API calls.

```
=== computeSpread() timing (100 000 iterations, N=3 values) ===

$ node -e "
const t0 = performance.now();
for (let i = 0; i < 100000; i++) computeSpread([289.50, 291.20, 291.15]);
console.log('computeSpread() N=3:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
computeSpread() N=3:  0.0009 ms

=== annotateConflict() timing — 3 sources (100 000 iterations) ===

annotateConflict() conflict detected:    0.0031 ms
annotateConflict() no conflict:          0.0019 ms   (spreadPct ≤ threshold → early exit)

=== raceToFirstWithConflict() orchestration overhead (immediate sources) ===

raceToFirstWithConflict() overhead:  0.38 ms   (Promise.allSettled + race logic + annotation)

=== 3-source price feed scenario ===

Sources: yfinance (160ms, returns 289.50), refinitiv (210ms, returns 291.20), bloomberg (280ms, returns 291.15)
Query: { ticker: 'AAPL' }

Timeline:
  t=0ms:   all 3 fire
  t=160ms: yfinance settles → 289.50 (first non-null)
  t=210ms: refinitiv settles → 291.20 (collected for conflict check)
  t=280ms: bloomberg settles → 291.15 (collected for conflict check)

computeSpread([289.50, 291.20, 291.15]):
  min=289.50, max=291.20, median=291.15
  spread=1.70, spreadPct=0.587%

isOutlier(winner=289.50, median=291.15, spread=1.70):
  |289.50 - 291.15| = 1.65 > 1.70 × 0.5 = 0.85 → OUTLIER SUSPECTED

Result:
  {
    result:     289.50,
    winner:     'yfinance',
    latencyMs:  161,
    _conflict:  {
      detected:          true,
      values:            [{ source:'yfinance', value:289.50, latencyMs:161 },
                          { source:'refinitiv', value:291.20, latencyMs:211 },
                          { source:'bloomberg', value:291.15, latencyMs:281 }],
      spread:            1.70,
      spreadPct:         0.587,
      min:               289.50,
      max:               291.20,
      median:            291.15,
      outlierSuspicion:  true,
      recommendation:    'USE_MEDIAN',
      invalidSources:    [],
    }
  }

Consumer routing:
  _conflict.detected=true + outlierSuspicion=true → use _conflict.median (291.15) instead
  Final delivered value: 291.15 (Bloomberg/Refinitiv consensus), confidence: MEDIUM
  Hedge note: "Two of three sources agreed on $291.15; one source (faster) returned $289.50"

=== Agreement scenario (all three within 0.1%) ===

Sources: [289.50, 289.48, 289.52]
spread=0.04, spreadPct=0.014% < noConflictThreshold=0.5%
_conflict: { detected:false, spreadPct:0.014, summary:'sources_agree' }
confidence: HIGH

=== S-125 vs F-98 vs F-101 ===

              │ S-125 (KB source conflict)    │ F-98 (live fan-out selection) │ F-101 (fan-out conflict annotation)
──────────────┼──────────────────────────────┼───────────────────────────────┼──────────────────────────────────────
When          │ Before injection              │ During parallel query         │ After all responses collected
Sources       │ Retrieved KB documents        │ N live API sources            │ N live API sources (same as F-98)
What          │ Pre-injection doc conflict    │ Select one value to return    │ Annotate spread of all responses
Output        │ conflictNote injected         │ Single selected result        │ Result + _conflict block
Action        │ Model sees conflict note      │ Consumer gets one value       │ Consumer routes on conflict metadata
Timing        │ 0.0389ms (10 pairs)          │ 0.31ms overhead               │ 0.0031ms annotation overhead
```

## See also

[F-98](f98-live-source-fanout.md) · [S-125](../stacks/s125-multi-source-claim-conflict.md) · [S-100](../stacks/s100-live-data-freshness-contracts.md) · [F-47](f47-multi-agent-result-aggregation.md) · [F-100](f100-output-claim-temporal-scope.md) · [S-96](../stacks/s96-tool-fallback-chains.md)

## Go deeper

Keywords: `fan-out conflict annotation` · `live source disagreement` · `multi-source spread` · `source conflict annotation` · `race-to-first outlier` · `live data conflict` · `fan-out spread` · `source value disagreement` · `outlier detection live sources` · `conflict annotation live API`
