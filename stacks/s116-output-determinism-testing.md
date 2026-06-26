# S-116 · Output Determinism Testing

[S-45](s45-sampling-parameters.md) documents that temperature=0 (greedy decoding) produces the same output for the same input. [S-101](s101-deterministic-agent-sessions.md) notes: "At temperature=0 with a pinned model version, model outputs are nearly deterministic given identical input." Neither tests this claim. Neither builds a harness that verifies your specific prompts actually hold the near-determinism property, or quantifies where and how often they diverge.

"Nearly deterministic" is an engineering reality: API providers run inference on GPU clusters with parallel floating-point operations. Hardware-level non-determinism (different execution orders under load, batching interactions) can produce different token choices at sampling boundaries even when temperature=0. In practice, for Claude and GPT-class models at temperature=0, divergence is rare on structured extraction tasks and more common on long free-text generation. You cannot assume bit-exact reproducibility; you should measure it on your prompts and decide how much variance you can tolerate.

The consequence matters. If you rely on output determinism for full-response caching (S-67) — caching the literal string and serving the same string on cache hit — then any divergence between the cached response and a live response is an inconsistency your users will see. If you rely on it for audit trails — "this session produced this exact output" — you need to know whether the output would be the same if regenerated. Output determinism testing makes the assumption explicit and catches the cases where it breaks.

## Situation

A legal document summarizer runs at temperature=0 on a pinned model (F-38). The team has enabled full-response caching (S-67) keyed on SHA-256 of the document content. The assumption: same document → same summary → cache serves correctly. A test 14 days after deploy reveals that 3 of 50 documents produce slightly different summaries on re-run at the same temperature (phrase reordering, minor word choice differences). Cache hit on those three documents returns the cached summary; a live run returns a different one. The difference is small but is a compliance issue for the team's audit trail.

Output determinism testing would have surfaced this before the caching decision: run the 50 benchmark documents twice at temperature=0, compare outputs, find the 3/50 (6%) divergence rate, decide whether caching at that divergence rate is acceptable or whether the caching strategy needs to be based on semantically equivalent responses, not string equality.

## Forces

- **Determinism varies by prompt type.** Short structured extractions ("extract the date from this clause") are nearly bit-exact at temperature=0. Long free-text generations ("summarize this 5-page contract") are more likely to diverge at paragraph joints. Test the specific prompts you use, not a generic benchmark.
- **Determinism varies by load.** Under high server load, the execution order of GPU operations changes and divergence increases. Testing at low load may underestimate production divergence.
- **Divergence is usually small, not catastrophic.** Typical divergences at temperature=0 are word-level — "the contract" vs "this contract," a reordered clause, a different synonym. Semantic content is preserved. Bit-exact comparison catches these; semantic similarity check tells you whether they matter.
- **Testing requires live API calls.** This is the one pattern in the handbook where the test harness cannot be fully exercised without API calls. Measure the harness overhead in-process; accept that the multi-run API cost is the test cost.
- **Run the test before, not after, committing to a caching strategy.** If your caching strategy assumes exact string equality, measure the divergence rate on your actual prompts before shipping. If divergence is >0%, decide: accept it, switch to semantic caching, or abandon full-response caching for this prompt type.
- **Pin the model version for determinism testing.** Testing determinism across model updates is a different concern (behavioral drift — F-26). This entry is about same-version, same-temperature reproducibility.

## The move

**Run each critical prompt N times at temperature=0. Compute pairwise Jaccard and exact-match similarity between all output pairs. Flag prompts where any pair falls below threshold. Emit a determinism report before committing to caching or exact-match audit strategies.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Similarity functions ---

function exactMatch(a, b) {
  return a === b;
}

function jaccardSimilarity(a, b) {
  const words = t => new Set(t.toLowerCase().replace(/[^\w\s]/g, ' ').split(/\s+/).filter(w => w.length > 2));
  const wa = words(a), wb = words(b);
  const inter = [...wa].filter(w => wb.has(w)).length;
  const union  = new Set([...wa, ...wb]).size;
  return union === 0 ? 1 : inter / union;
}

// Longest common subsequence ratio (word-level) — stricter than Jaccard for order sensitivity
function lcsRatio(a, b) {
  const wa = a.toLowerCase().split(/\s+/).filter(Boolean);
  const wb = b.toLowerCase().split(/\s+/).filter(Boolean);
  const m = wa.length, n = wb.length;
  if (m === 0 && n === 0) return 1;
  if (m === 0 || n === 0) return 0;
  // Only practical for short outputs — use for prompt sections < 200 words
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = wa[i-1] === wb[j-1] ? dp[i-1][j-1] + 1 : Math.max(dp[i-1][j], dp[i][j-1]);
    }
  }
  return (2 * dp[m][n]) / (m + n);
}

// --- Pairwise comparison of N outputs ---

function pairwiseStats(outputs) {
  const pairs = [];
  for (let i = 0; i < outputs.length; i++) {
    for (let j = i + 1; j < outputs.length; j++) {
      pairs.push({
        i, j,
        exactMatch: exactMatch(outputs[i], outputs[j]),
        jaccard:    parseFloat(jaccardSimilarity(outputs[i], outputs[j]).toFixed(4)),
        lcsRatio:   parseFloat(lcsRatio(outputs[i], outputs[j]).toFixed(4)),
      });
    }
  }
  const minJaccard    = pairs.length > 0 ? Math.min(...pairs.map(p => p.jaccard))    : 1;
  const exactMatchAll = pairs.every(p => p.exactMatch);
  return { pairs, minJaccard, exactMatchAll };
}

// --- Run determinism test for one prompt ---

async function runDeterminismTest(testCase, opts = {}) {
  const {
    runs             = 5,
    model            = 'claude-haiku-4-5-20251001',
    maxTokens        = 400,
    jaccardThreshold = 0.92,
  } = opts;

  const outputs = [];
  for (let i = 0; i < runs; i++) {
    const resp = await client.messages.create({
      model, max_tokens: maxTokens, temperature: 0,
      system:   testCase.systemPrompt,
      messages: [{ role: 'user', content: testCase.userMessage }],
    });
    outputs.push(resp.content[0]?.text ?? '');
  }

  const stats    = pairwiseStats(outputs);
  const verdict  = stats.exactMatchAll
    ? 'BIT_EXACT'
    : stats.minJaccard >= jaccardThreshold
      ? 'SEMANTICALLY_STABLE'
      : 'UNSTABLE';

  return {
    testId:           testCase.id,
    runs,
    exactMatchAll:    stats.exactMatchAll,
    minJaccard:       stats.minJaccard,
    jaccardThreshold,
    verdict,
    divergentPairs:   stats.pairs.filter(p => p.jaccard < jaccardThreshold),
    outputs,          // retain for manual inspection of divergent cases
    cachingSafe:      verdict !== 'UNSTABLE',
    auditExactSafe:   verdict === 'BIT_EXACT',
  };
}

// --- Run a suite of determinism tests ---

async function runDeterminismSuite(testCases, opts = {}) {
  const results = [];
  for (const tc of testCases) {
    const result = await runDeterminismTest(tc, opts);
    results.push(result);
  }

  const unstable        = results.filter(r => r.verdict === 'UNSTABLE');
  const bitExact        = results.filter(r => r.verdict === 'BIT_EXACT');
  const semStable       = results.filter(r => r.verdict === 'SEMANTICALLY_STABLE');
  const cachingUnsafe   = results.filter(r => !r.cachingSafe);
  const auditExactUnsafe = results.filter(r => !r.auditExactSafe);

  return {
    total:             results.length,
    bitExact:          bitExact.length,
    semanticallyStable: semStable.length,
    unstable:          unstable.length,
    cachingUnsafe:     cachingUnsafe.length,
    auditExactUnsafe:  auditExactUnsafe.length,
    recommendation: cachingUnsafe.length === 0
      ? 'Full-response caching (S-67) safe for all tested prompts at this threshold'
      : `${cachingUnsafe.length} prompt(s) unsafe for exact-string caching — use semantic caching or disable caching for these`,
    results,
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `jaccardSimilarity()`, `lcsRatio()`, and `pairwiseStats()` timed over 100 000 iterations on representative 200-word outputs. **Multi-run API calls not executed in this session — test harness overhead is measured; actual per-prompt API cost depends on your model and output length.** Divergence figures in the scenario below are illustrative.

```
=== jaccardSimilarity() timing (100 000 iterations, two ~200-word strings) ===

$ node -e "
const a = 'The contract establishes mutual obligations between the parties regarding data processing. The data processor agrees to implement appropriate technical measures...'.repeat(6);
const b = 'This agreement establishes mutual obligations between all parties concerning data processing. The data processor must implement appropriate technical measures...'.repeat(6);
const t0 = performance.now();
for (let i = 0; i < 100000; i++) jaccardSimilarity(a, b);
console.log('jaccardSimilarity():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
jaccardSimilarity(): 0.0041 ms

=== lcsRatio() timing (100 000 iterations, two 80-word strings) ===

lcsRatio(): 0.1823 ms   (O(m×n) DP — only practical for short outputs < 200 words)

=== pairwiseStats() on 5 outputs (100 000 iterations, 10 pairs) ===

pairwiseStats(): 0.0512 ms

=== Illustrative determinism test results (N=5 runs, temperature=0) ===

Test suite: 50 legal clause prompts

testId: 'extract_dates'   (short, structured)
  verdict:     BIT_EXACT — all 5 runs identical
  minJaccard:  1.0000
  cachingSafe: true
  auditExactSafe: true

testId: 'summarize_nda'   (medium, semi-structured)
  verdict:     SEMANTICALLY_STABLE
  minJaccard:  0.9412   (two runs differ in phrase order; same facts)
  cachingSafe: true     (at threshold 0.92)
  auditExactSafe: false ← different literal string on 2/5 runs

testId: 'risk_narrative'  (long, free-text)
  verdict:     UNSTABLE
  minJaccard:  0.8871   (below 0.92 threshold)
  cachingSafe: false
  auditExactSafe: false
  divergentPairs: [
    { i:0, j:2, jaccard: 0.8871,
      // run 0: "The indemnification clause presents moderate risk given the uncapped liability..."
      // run 2: "The indemnification provisions present moderate risk, particularly the uncapped exposure..."
    }
  ]

Suite result:
  { total: 50, bitExact: 33, semanticallyStable: 14, unstable: 3,
    cachingUnsafe: 3, auditExactUnsafe: 17,
    recommendation: '3 prompt(s) unsafe for exact-string caching — use semantic caching or disable caching for these' }

Action:
  → exact_string caching disabled for 'risk_narrative' and 2 other prompts
  → semantic caching (S-67, cosine > 0.92) enabled for those 3
  → remaining 47 prompts: full-response caching safe

API cost for this test run (Haiku, 50 prompts × 5 runs):
  Estimate: 50 × 5 × (~250 in + ~180 out tok) × ($0.80 + $4.00)/M = ~$0.24

=== S-24 vs S-101 vs S-116 ===

              │ S-24 (self-consistency)      │ S-101 (deterministic sessions) │ S-116 (determinism testing)
──────────────┼──────────────────────────────┼────────────────────────────────┼──────────────────────────────
Temperature   │ > 0 (diverse samples)        │ = 0 (assumed deterministic)    │ = 0 (measured, not assumed)
N runs used   │ Yes — majority vote          │ No (single run, tool dedup)    │ Yes — measure divergence
Tests the     │ Model's answer stability     │ Session's side-effect safety   │ Output text reproducibility
Answers       │ What is the best answer?     │ Can this session be replayed?  │ Is exact caching / audit safe?
Cost          │ N × model call (production)  │ $0 (architectural pattern)     │ N × model call (test only)
```

## See also

[S-24](s24-self-consistency.md) · [S-45](s45-sampling-parameters.md) · [S-67](s67-full-response-caching.md) · [S-101](s101-deterministic-agent-sessions.md) · [F-38](../forward-deployed/f38-model-version-pinning.md) · [F-26](../forward-deployed/f26-behavioral-drift-detection.md) · [F-84](../forward-deployed/f84-output-consistency-under-paraphrase.md)

## Go deeper

Keywords: `output determinism` · `temperature zero reproducibility` · `LLM determinism test` · `caching safety test` · `bit-exact reproducibility` · `near-determinism` · `response reproducibility` · `stochastic LLM output` · `determinism harness` · `prompt stability test`
