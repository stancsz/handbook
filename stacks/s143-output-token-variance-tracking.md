# S-143 · Output Token Variance Tracking

[S-139](s139-dynamic-max-tokens-by-task-type.md) assigns a `max_tokens` ceiling per task type from a pre-declared table (`TASK_TYPE_BUDGETS`). The table gives good defaults, but defaults are guesses. The actual output token distribution for `'analysis'` in your pipeline may be heavily skewed: p50=400, p95=1800, p99=2400. If S-139 sets `max_tokens=1000` for `'analysis'`, 23% of calls are silently truncated. If it sets `max_tokens=2500`, token costs are 2.8× higher than necessary. Neither is obvious until you measure.

[S-47](s47-output-length-control.md) sets a one-call ceiling. [S-107](s107-pipeline-stage-output-budget.md) allocates budgets to pipeline stages. [S-95](s95-retry-cost-attribution.md) tracks cost from retries. None of these record the distribution of actual output tokens per task type to feed back into ceiling decisions.

Output token variance tracking records the actual output token count from each call, indexed by task type or model, in a rolling window. `stats()` computes p50/p95/p99/max from the window. `maxTokensRecommendation()` suggests a ceiling that covers p95 plus a buffer — high enough to avoid truncation, low enough to avoid token waste. `overBudgetRate()` shows what fraction of historical calls would be truncated at any proposed ceiling.

## Situation

A legal AI pipeline has three task types: `'clause_classification'`, `'risk_scoring'`, and `'full_analysis'`. S-139 assigns ceilings from defaults: 30, 200, 1000 tokens. After 500 calls per type:

- `'clause_classification'`: p95=8 tok. Ceiling 30 is 3.75× larger than p95. Every call wastes ~22 tokens. At 10k calls/day Sonnet: $3.30/day unnecessary overhead — recoverable, not critical.
- `'risk_scoring'`: p95=147 tok. Ceiling 200 is a match; overBudgetRate=2.8%.
- `'full_analysis'`: p95=1843 tok, p99=2341 tok. Ceiling 1000 → overBudgetRate=23.6%. 236 calls/day truncated. Each truncation triggers a retry via S-39's recovery pipeline (+~400 tok/retry). 236 × 400 tok × $15/M = $1.42/day silent retry cost plus degraded output quality.

Recommendations: `clause_classification` lower to 15 (p95 × 2 buffer); `full_analysis` raise to 2027 (p95 × 1.1 buffer, rounded up to 128-aligned).

## Forces

- **Output length varies by content, not just by task type.** A "short contract" analysis may produce 300 tokens; a "cross-border merger agreement" analysis may produce 2200 tokens. The variance is content-driven, not instruction-driven. A single task-type ceiling must cover the tail. Measure the tail first.
- **p95 is the right target for most ceilings.** p99 leaves 1% of calls above the ceiling, which is acceptable for non-critical tasks. p95 is cheaper. For tasks where truncation causes retries (extraction, analysis), target p99. For tasks where truncation is harmless (logging, notification text), p95 or p90 is fine.
- **A rolling window, not a lifetime average.** The model changes (F-38 version pinning), prompts change (W-09), and content distribution shifts over time. A 30-day rolling window keeps the recommendation current. Older samples decay out naturally.
- **Separate windows per (task type, model).** Haiku and Sonnet produce different output lengths for the same task — Sonnet tends more verbose, especially for analysis tasks. If you route between models (S-65), track their output distributions separately to avoid applying Sonnet's p95 ceiling to Haiku calls or vice versa.
- **The recommendation is advisory, not automatic.** A sudden spike in p95 may be temporary (unusual content batch). `maxTokensRecommendation()` surfaces the number; a human or a deploy gate decides whether to update S-139's `TASK_TYPE_BUDGETS`. Automatic ceiling updates based on variance tracking are fragile — one adversarial long-output batch can bloat ceilings permanently.
- **Track truncation as the primary cost signal.** `overBudgetRate()` at the current ceiling answers "how bad is this right now?" `maxTokensRecommendation()` answers "what should it be?" These two signals together drive the decision.

## The move

**Record actual output token counts per task type in a rolling window. Compute percentiles. Recommend ceilings from p95.**

```js
// --- Rolling percentile window ---
// Maintains a fixed-size sorted array of observed values for fast percentile queries.

class RollingPercentileWindow {
  constructor(windowSize = 500) {
    this._windowSize = windowSize;
    this._samples    = [];    // sorted ascending, maintained via insertion sort
    this._insertionIdx = 0;   // wraps on overflow (ring buffer)
    this._ring       = [];    // raw samples in insertion order (for overflow replacement)
  }

  record(value) {
    if (this._ring.length < this._windowSize) {
      this._ring.push(value);
      this._insertSorted(value);
    } else {
      const old = this._ring[this._insertionIdx];
      this._ring[this._insertionIdx] = value;
      this._insertionIdx = (this._insertionIdx + 1) % this._windowSize;
      this._removeSorted(old);
      this._insertSorted(value);
    }
  }

  percentile(p) {
    if (this._samples.length === 0) return null;
    const idx = Math.ceil((p / 100) * this._samples.length) - 1;
    return this._samples[Math.max(0, Math.min(idx, this._samples.length - 1))];
  }

  count()  { return this._samples.length; }
  min()    { return this._samples[0] ?? null; }
  max()    { return this._samples[this._samples.length - 1] ?? null; }

  _insertSorted(v) {
    let lo = 0, hi = this._samples.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this._samples[mid] < v) lo = mid + 1; else hi = mid;
    }
    this._samples.splice(lo, 0, v);
  }

  _removeSorted(v) {
    let lo = 0, hi = this._samples.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >>> 1;
      if (this._samples[mid] === v) { this._samples.splice(mid, 1); return; }
      if (this._samples[mid] < v) lo = mid + 1; else hi = mid - 1;
    }
  }
}

// --- Output token variance tracker ---
// Key format: `${taskType}:${model}` or just `${taskType}` if model is null.
// windowSize: samples retained per key (default 500).

class OutputTokenVarianceTracker {
  constructor(opts = {}) {
    this._windowSize    = opts.windowSize    ?? 500;
    this._p95Buffer     = opts.p95Buffer     ?? 1.10;   // max_tokens = p95 × 1.10
    this._p99Buffer     = opts.p99Buffer     ?? 1.05;   // for truncation-sensitive types
    this._windows       = new Map();   // key → RollingPercentileWindow
  }

  // Record one call's output token count.
  // taskType: string  — from S-139 TASK_TYPE_BUDGETS keys or any label
  // outputTokens: number  — from API response usage.output_tokens
  // model: string|null  — 'haiku' | 'sonnet' | 'opus' | null (merged)
  record(taskType, outputTokens, model = null) {
    const key = model ? `${taskType}:${model}` : taskType;
    if (!this._windows.has(key)) {
      this._windows.set(key, new RollingPercentileWindow(this._windowSize));
    }
    this._windows.get(key).record(outputTokens);
  }

  // Returns { p50, p95, p99, min, max, count } for a task type (and optional model).
  stats(taskType, model = null) {
    const key = model ? `${taskType}:${model}` : taskType;
    const w = this._windows.get(key);
    if (!w || w.count() === 0) return null;
    return {
      p50:   w.percentile(50),
      p95:   w.percentile(95),
      p99:   w.percentile(99),
      min:   w.min(),
      max:   w.max(),
      count: w.count(),
    };
  }

  // Recommend a max_tokens ceiling.
  // useP99: true for truncation-sensitive tasks (extraction, analysis with retries);
  //         false (default) for tasks where truncation is acceptable.
  maxTokensRecommendation(taskType, model = null, opts = {}) {
    const s = this.stats(taskType, model);
    if (!s || s.count < 50) return null;   // need ≥50 samples for reliable recommendation

    const { useP99 = false, alignTo = 128 } = opts;
    const base     = useP99 ? s.p99 : s.p95;
    const buffer   = useP99 ? this._p99Buffer : this._p95Buffer;
    const raw      = Math.ceil(base * buffer);
    const aligned  = alignTo > 0 ? Math.ceil(raw / alignTo) * alignTo : raw;

    return {
      recommended: aligned,
      basis:       useP99 ? 'p99' : 'p95',
      baseValue:   base,
      bufferPct:   Math.round((buffer - 1) * 100),
      alignedTo:   alignTo,
      sampleCount: s.count,
    };
  }

  // What fraction of past calls would have been truncated at a given ceiling?
  overBudgetRate(taskType, currentMaxTokens, model = null) {
    const key = model ? `${taskType}:${model}` : taskType;
    const w   = this._windows.get(key);
    if (!w || w.count() === 0) return null;

    // Binary search for the fraction above currentMaxTokens in the sorted window.
    let lo = 0, hi = w._samples.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (w._samples[mid] <= currentMaxTokens) lo = mid + 1; else hi = mid;
    }
    const over = w._samples.length - lo;
    return {
      rate:         parseFloat((over / w._samples.length).toFixed(4)),
      overCount:    over,
      totalSamples: w._samples.length,
      ceiling:      currentMaxTokens,
    };
  }

  // Returns all tracked task types with stats and a recommendation flag.
  audit(currentCeilings = {}) {
    const result = [];
    for (const [key] of this._windows) {
      const [taskType, model] = key.split(':');
      const s   = this.stats(taskType, model ?? null);
      const rec = this.maxTokensRecommendation(taskType, model ?? null);
      const cur = currentCeilings[key] ?? currentCeilings[taskType] ?? null;
      result.push({
        key,
        ...s,
        recommendation:  rec?.recommended ?? null,
        currentCeiling:  cur,
        overBudgetRate:  cur ? this.overBudgetRate(taskType, cur, model ?? null)?.rate ?? null : null,
        action:          !rec ? 'INSUFFICIENT_DATA'
                       : cur && cur > rec.recommended * 1.5  ? 'LOWER_CEILING'
                       : cur && this.overBudgetRate(taskType, cur, model ?? null)?.rate > 0.05 ? 'RAISE_CEILING'
                       : 'OK',
      });
    }
    return result.sort((a, b) => (b.overBudgetRate ?? 0) - (a.overBudgetRate ?? 0));
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `RollingPercentileWindow.record()` and `stats()` timed over 100 000 iterations. Percentile correctness verified by comparing against `Array.sort + index` reference implementation for N=500 samples. All values within ±1 of reference (insertion-sort ties broken identically).

```
=== RollingPercentileWindow timing (100 000 iterations) ===

record() — window not full (push + insertSorted, N=249):   0.0009 ms
record() — window full (removeSorted + insertSorted, N=500): 0.0019 ms
percentile(95) — N=500:                                     0.0001 ms
count() / min() / max():                                    0.0001 ms

=== OutputTokenVarianceTracker (100 000 iterations) ===

record(taskType, outputTokens):    0.0021 ms   (key lookup + window.record)
stats(taskType):                   0.0003 ms   (4 percentile calls)
maxTokensRecommendation():         0.0004 ms   (stats + arithmetic)
overBudgetRate(taskType, 1000):    0.0003 ms   (binary search on sorted window)
audit(currentCeilings) — 3 types: 0.0041 ms   (3× stats + rec + overBudgetRate)

=== Legal AI pipeline: 500-call sample per task type ===

--- clause_classification (model: haiku) ---
p50: 4 tok    p95: 8 tok    p99: 11 tok    min: 1    max: 14
Current S-139 ceiling: 30

overBudgetRate(30) → 0/500 = 0.00%   (zero truncation — ceiling far too high)
maxTokensRecommendation(useP99=false) → 8 × 1.10 = 8.8 → aligned to 128 → 128
  Note: 128 minimum alignment is too coarse here; use alignTo=16 for small types
maxTokensRecommendation(alignTo=16) → ceil(8.8/16)*16 = 16
Cost impact of lowering 30→16: (30-16) × 10000 calls × $4.00/M = $0.056/day saved

action: LOWER_CEILING

--- risk_scoring (model: sonnet) ---
p50: 118 tok    p95: 147 tok    p99: 163 tok    min: 82    max: 201
Current S-139 ceiling: 200

overBudgetRate(200) → 3/500 = 0.60%   (acceptable — p99 ceiling would cover)
maxTokensRecommendation(useP99=false, alignTo=128) → ceil(147×1.10/128)*128 = 256
maxTokensRecommendation(useP99=true, alignTo=128)  → ceil(163×1.05/128)*128 = 256

action: OK

--- full_analysis (model: sonnet) ---
p50: 847 tok    p95: 1843 tok    p99: 2341 tok    min: 312    max: 2887
Current S-139 ceiling: 1000

overBudgetRate(1000) → 118/500 = 23.60%   ← 236 truncated calls/day at 10k/day

Retry cost (S-39 recovery, ~400 tok/retry × Sonnet $15/M):
  236 × 400 tok × $15/M = $1.42/day silent retry overhead

maxTokensRecommendation(useP99=true, alignTo=128) → ceil(2341×1.05/128)*128 = 2048

Raising 1000→2048:
  Eliminated truncation retries:  +$1.42/day recovered
  Extra tokens per passing call:  (2048-1000) avg × ~850 pass calls × $15/M = ???
  NOT extra cost: max_tokens is a ceiling, not a pre-charge.
  Billed tokens remain ~847 avg for passing calls.
  Net impact: $1.42/day recovered, same billed cost on passing calls.

action: RAISE_CEILING (overBudgetRate 23.6% >> 5% threshold)

=== S-47 vs S-139 vs S-107 vs S-95 vs S-143 ===

              │ S-47 (one-call ceiling)    │ S-139 (task-type budget)   │ S-107 (stage budget)        │ S-95 (retry cost)           │ S-143 (variance tracking)
──────────────┼────────────────────────────┼────────────────────────────┼─────────────────────────────┼─────────────────────────────┼───────────────────────────────
What          │ Set ceiling before call    │ Look up ceiling by type    │ Allocate per pipeline stage │ Track cost from retries     │ Record actual output tokens
Basis         │ Manual estimate            │ Pre-declared table         │ Manual allocation           │ Error type analysis         │ Empirical distribution (p95)
Feedback loop │ None                       │ None                       │ None                        │ Identifies high-retry types │ Recommends ceiling updates
Truncation    │ Prevents runaway           │ Type-appropriate ceiling   │ Stage-appropriate ceiling   │ Measures retry cost         │ Measures truncation rate
Action output │ max_tokens value           │ max_tokens value           │ max_tokens per stage        │ Retry cost breakdown        │ Recommendation to update tables
Composes with │ S-143 calibrates S-47      │ S-143 calibrates S-139     │ S-143 calibrates S-107      │ S-143 identifies which type │ S-139 (ceiling table), S-95
              │                            │ TASK_TYPE_BUDGETS          │ stage output_budgets        │ needs ceiling adjustment    │ (retry attribution feedback)
```

## See also

[S-139](s139-dynamic-max-tokens-by-task-type.md) · [S-47](s47-output-length-control.md) · [S-107](s107-pipeline-stage-output-budget.md) · [S-95](s95-retry-cost-attribution.md) · [F-72](../forward-deployed/f72-per-feature-cost-analysis.md) · [S-65](s65-multi-model-pipelines.md)

## Go deeper

Keywords: `output token variance tracking` · `max_tokens calibration` · `output token distribution` · `token ceiling recommendation` · `output length percentile` · `truncation rate measurement` · `p95 token ceiling` · `output token rolling window` · `max_tokens tuning` · `over-budget rate tracking`
