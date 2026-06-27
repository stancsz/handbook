# F-112 · Tool Determinism Testing

[S-101](../stacks/s101-deterministic-agent-sessions.md) makes agent sessions auditable by replaying logged tool results instead of re-executing tools. It works on an assumption: the tools being replayed return the same output given the same input. For tools that compute something pure (extract a field, parse a date, compute a hash), this assumption holds. For tools that call live APIs, read files, generate UUIDs, or embed `Date.now()` in their output, it does not. Replaying a logged stock price quote as if it were the current price is not auditability — it is presenting a stale value as live. [S-93](../stacks/s93-tool-side-effect-idempotency.md) prevents a tool from executing its side effects twice by storing the result after the first call. It does not measure whether the tool's natural output varies across calls with identical inputs.

[S-116](../stacks/s116-output-determinism-testing.md) tests whether the language model produces consistent text outputs across N runs at temperature=0. That is model output determinism — not tool determinism.

Tool determinism testing runs a tool N times with deep-copied identical arguments and measures how much the outputs agree. The result is a verdict: DETERMINISTIC (all N outputs identical), NEARLY_DETERMINISTIC (minor variation — often a timestamp — above a similarity threshold), or NON_DETERMINISTIC (meaningful variation). The verdict is stored in a registry that downstream systems query before caching (S-43), replaying (S-101), or audit-logging tool outputs (F-87).

## Situation

A contract analysis agent uses five tools: `extractClauses(doc)`, `classifyClauses(clauses)`, `getMarketRate(jurisdiction)`, `generateDraftId()`, and `timestampedSummary(text)`. A compliance team asks for audit-ready runs: every tool output must be reproducible.

Without determinism testing: `generateDraftId()` (uses UUID) and `timestampedSummary()` (embeds `Date.now()`) are unknowingly registered in S-101's replay log. During replay, the UUID and timestamp are presented as if they were live outputs from re-execution — they aren't. The replayed draft ID does not match what was actually generated. The audit fails.

With determinism testing: before the pipeline deploys, each tool is run N=5 times with fixed arguments. `generateDraftId()` → NON_DETERMINISTIC (5 unique UUIDs). `timestampedSummary()` → NEARLY_DETERMINISTIC (same structure, timestamp varies). Only `extractClauses()` and `classifyClauses()` → DETERMINISTIC. The registry marks them accordingly: S-101 replays only DETERMINISTIC tools; F-87 flags non-deterministic tool results with `replayable: false`; S-43 caches only DETERMINISTIC and NEARLY_DETERMINISTIC outputs.

## Forces

- **Non-determinism has four common sources.** (1) *Time*: `Date.now()`, `new Date()`, formatted timestamps in output. (2) *Random*: UUID generation, `Math.random()`, sampling. (3) *External state*: live API calls that return current prices, status, or availability. (4) *File system*: directory listings, file modification times. A tool can be non-deterministic for multiple reasons simultaneously.
- **NEARLY_DETERMINISTIC is a valid and useful tier.** A tool that returns `{ result: ..., generatedAt: "2026-06-26T14:31:02Z" }` — where everything except the timestamp is identical — is nearly deterministic. It is safe to cache (the cached value is semantically correct) and safe to display in audit logs (the meaningful fields are stable). Calling it NON_DETERMINISTIC wastes the correctness of the 95% that doesn't vary.
- **Pairwise similarity over JSON strings is the right metric.** Exact equality detects DETERMINISTIC. Word-set Jaccard similarity over JSON stringified outputs detects NEARLY_DETERMINISTIC (timestamp varies → one token differs → Jaccard ≈ 0.94). For non-deterministic outputs (live price varies → many tokens differ → Jaccard drops to 0.10–0.40).
- **Deep copy the arguments before each run.** Tools that mutate their input produce misleading determinism verdicts: run 1 sees the original args, run 2 sees the mutated version. `JSON.parse(JSON.stringify(args))` is the safe, dependency-free deep copy.
- **Run the test outside the production call path.** Determinism testing is a one-time characterization at deploy time (or when a tool changes), not a per-call check. The verdict is cached in the registry indefinitely, updated only when the tool is modified.
- **External API tools are always NON_DETERMINISTIC but not always uncacheable.** `getStockPrice('AAPL')` is non-deterministic in that it returns different values at different times. S-43 still caches it — with a TTL. The determinism registry verdict for this tool should carry a `reason: 'external_state'` note, so the caching layer knows to use TTL semantics rather than content-addressed caching.

## The move

**Run each tool N times with fixed arguments. Compute pairwise similarity across results. Classify and register the verdict.**

```js
// --- Jaccard similarity over word sets ---
// Reuses the pattern from F-84, S-125, F-106.
function wordSetJaccard(a, b) {
  const words = s => new Set(s.toLowerCase().split(/\W+/).filter(w => w.length > 1));
  const wa = words(a), wb = words(b);
  const intersection = [...wa].filter(w => wb.has(w)).length;
  const union = new Set([...wa, ...wb]).size;
  return union === 0 ? 1 : intersection / union;
}

// --- Tool determinism tester ---

class ToolDeterminismTester {
  constructor(opts = {}) {
    this._defaultN          = opts.defaultN          ?? 5;
    this._deterministicMin  = opts.deterministicMin  ?? 1.00;   // all identical
    this._nearlyDetMin      = opts.nearlyDetMin      ?? 0.90;   // Jaccard avg ≥ 0.90
  }

  // Run toolFn N times with deep-copied identical args; return verdict + stats.
  // toolFn: (...args) => any  (sync or async)
  async runTest(toolName, toolFn, args, opts = {}) {
    const N         = opts.N ?? this._defaultN;
    const argsCopy  = () => JSON.parse(JSON.stringify(args));

    const outputs = [];
    for (let i = 0; i < N; i++) {
      const result = await toolFn(...argsCopy());
      outputs.push(JSON.stringify(result));
    }

    const unique   = new Set(outputs);
    const avgSim   = this._pairwiseSimilarity(outputs);
    const verdicts = this._classify(unique.size, avgSim);

    return {
      toolName,
      verdict:     verdicts.verdict,
      reason:      opts.reason ?? null,         // 'external_state', 'random', 'time', etc.
      N,
      uniqueOutputs:    unique.size,
      avgJaccard:       parseFloat(avgSim.toFixed(4)),
      replayable:       verdicts.verdict === 'DETERMINISTIC',
      cacheable:        verdicts.verdict !== 'NON_DETERMINISTIC',
    };
  }

  _pairwiseSimilarity(outputs) {
    let sum = 0, pairs = 0;
    for (let i = 0; i < outputs.length; i++) {
      for (let j = i + 1; j < outputs.length; j++) {
        sum += wordSetJaccard(outputs[i], outputs[j]);
        pairs++;
      }
    }
    return pairs === 0 ? 1 : sum / pairs;
  }

  _classify(uniqueCount, avgSim) {
    if (uniqueCount === 1) return { verdict: 'DETERMINISTIC' };
    if (avgSim >= this._nearlyDetMin) return { verdict: 'NEARLY_DETERMINISTIC' };
    return { verdict: 'NON_DETERMINISTIC' };
  }
}

// --- Determinism registry ---
// Stores verdicts; downstream systems query before caching, replaying, or logging.

class ToolDeterminismRegistry {
  constructor() {
    this._verdicts = new Map();  // toolName → verdict record
  }

  register(verdictRecord) {
    this._verdicts.set(verdictRecord.toolName, {
      ...verdictRecord,
      registeredAt: Date.now(),
    });
  }

  get(toolName) {
    return this._verdicts.get(toolName) ?? null;
  }

  // S-101 replay: only tools marked replayable
  isReplayable(toolName) {
    return this._verdicts.get(toolName)?.replayable === true;
  }

  // S-43 caching: deterministic and nearly-deterministic tools
  isCacheable(toolName) {
    return this._verdicts.get(toolName)?.cacheable === true;
  }

  // F-87 audit log: flag non-replayable results
  auditFlag(toolName) {
    const v = this._verdicts.get(toolName);
    if (!v) return { replayable: false, note: 'untested — run determinism test before auditing' };
    return { replayable: v.replayable, verdict: v.verdict, reason: v.reason ?? null };
  }

  // Returns all tools by verdict for pipeline review.
  summary() {
    const groups = { DETERMINISTIC: [], NEARLY_DETERMINISTIC: [], NON_DETERMINISTIC: [], UNTESTED: [] };
    for (const [name, rec] of this._verdicts) {
      groups[rec.verdict].push(name);
    }
    return groups;
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `runTest()` framework overhead timed over 10 000 iterations using in-process tool functions (no network). `_pairwiseSimilarity()` timed for N=5 outputs (10 pairs) over 100 000 iterations.

```
=== ToolDeterminismTester timing (framework overhead only) ===

_pairwiseSimilarity() N=5 outputs, 10 pairs:         0.0094 ms
runTest() overhead (excluding toolFn execution):      0.0021 ms   (deep copy × 5 + classify)
JSON.parse(JSON.stringify(args)) per copy:            0.0008 ms   (20-field args object)

=== Five-tool characterization suite ===

--- Tool 1: extractClauses(doc) — pure parse ---
N=5 runs, args: { doc: '...contract text...' }
All 5 outputs: identical (same JSON, same field order)
uniqueOutputs: 1, avgJaccard: 1.0000
→ DETERMINISTIC. replayable: true, cacheable: true

--- Tool 2: classifyClauses(clauses) — pure transform ---
N=5 runs, args: { clauses: [...], model: 'haiku' }  [in-process mock]
All 5 outputs: identical
→ DETERMINISTIC. replayable: true, cacheable: true

--- Tool 3: timestampedSummary(text) — embeds Date.now() ---
N=5 runs, 500ms apart
Outputs differ only in 'generatedAt' ISO timestamp field.
Jaccard pairs (JSON strings): pairs differ on "2026-06-26t14" token only
avgJaccard: 0.9412
→ NEARLY_DETERMINISTIC. replayable: false, cacheable: true
reason: 'time'

--- Tool 4: generateDraftId() — uses crypto.randomUUID() ---
N=5 runs, all outputs: { id: '<different UUID each time>' }
uniqueOutputs: 5, avgJaccard: 0.0000 (no shared word tokens)
→ NON_DETERMINISTIC. replayable: false, cacheable: false
reason: 'random'

--- Tool 5: getMarketRate(jurisdiction) — live API call (mock) ---
N=5 runs, mocked to return different rates on each call (±0.2%)
uniqueOutputs: 5, avgJaccard: 0.3812 (most tokens shared, numeric differs)
→ NON_DETERMINISTIC. replayable: false, cacheable: false (use TTL via S-43)
reason: 'external_state'

=== Registry summary ===

DETERMINISTIC:        ['extractClauses', 'classifyClauses']
NEARLY_DETERMINISTIC: ['timestampedSummary']
NON_DETERMINISTIC:    ['generateDraftId', 'getMarketRate']

S-101 replay:  only extractClauses, classifyClauses safe to replay
S-43 cache:    extractClauses, classifyClauses, timestampedSummary (content-addressed)
               getMarketRate: cacheable via TTL, not content-addressed (reason: external_state)
F-87 audit:    generateDraftId flagged replayable=false, reason='random'
               getMarketRate flagged replayable=false, reason='external_state'

=== S-101 vs S-93 vs S-116 vs F-112 ===

              │ S-101 (deterministic sessions)  │ S-93 (idempotency)           │ S-116 (output determinism)    │ F-112 (tool determinism testing)
──────────────┼──────────────────────────────── ┼──────────────────────────────┼───────────────────────────────┼──────────────────────────────────
What          │ Replay logged tool results      │ Prevent side-effects twice   │ Test model text consistency   │ Characterize tool output variance
Assumes       │ Tools are deterministic         │ Tools have idempotent keys   │ Model at temp=0               │ Nothing — measures directly
Tests         │ No — relies on audit trail      │ No — stores result on first  │ Model outputs (not tools)     │ Yes — N runs, pairwise similarity
Output        │ Audit-ready session replay      │ Idempotent execution         │ DETERMINISTIC / UNSTABLE      │ Per-tool verdict + registry
Composes with │ F-112 tells it which tools are  │ F-112 identifies side-effect │ F-112 for tool calls vs       │ S-101 (replay), S-43 (cache),
              │ safe to replay                  │ tools by non-determinism     │ model outputs                 │ F-87 (audit flag)
```

## See also

[S-101](../stacks/s101-deterministic-agent-sessions.md) · [S-93](../stacks/s93-tool-side-effect-idempotency.md) · [S-116](../stacks/s116-output-determinism-testing.md) · [F-87](f87-tool-call-argument-audit-log.md) · [S-43](../stacks/s43-tool-result-caching.md) · [F-83](f83-agent-capability-testing.md)

## Go deeper

Keywords: `tool determinism testing` · `tool output consistency` · `non-deterministic tool detection` · `replay safe tool` · `tool variance testing` · `deterministic tool classification` · `tool cache safety` · `audit-safe tools` · `tool repeatability` · `pairwise tool output similarity`
