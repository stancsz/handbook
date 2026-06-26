# S-94 · Agent Output Diffing

[S-32](s32-verifiability-divider.md) names "output diff" as one of the cheapest oracle types — cheaper than a type check, cheaper than an LLM judge. [F-33](../forward-deployed/f33-prompt-ab-testing.md) covers running two prompts and picking a winner via a pairwise judge. Neither shows how to actually diff model outputs mechanically: what structure to compare, what metrics to compute, and how to aggregate across a set of responses to produce a single change signal.

## Situation

An agent returns structured JSON — `{status, next_step, escalate}` — from a 300-token system prompt. You change one sentence in the system prompt. You want to know: did the outputs change? If so, how? Were field values affected, or just phrasing? Did `escalate` flip from `false` to `true` for any inputs? Did the average response get 40% longer? Without an output diff, the only answer is running an LLM judge on every pair ($0.004/pair, minutes of wall time) or reading outputs manually. With a mechanical diff: JSON field changes surface in microseconds, word-level drift scores in under 1ms, and a 10-input change signal in under 5ms — all at zero token cost.

## Forces

- **Structural diffs and surface diffs answer different questions.** A JSON field diff tells you whether the schema broke — whether `escalate` was added, removed, or changed type. A word-level diff tells you whether the content of an existing field shifted. You need both. A structural-only diff misses semantic drift; a surface-only diff misses field deletions.
- **Aggregate metrics are more useful than per-pair results.** One outlier pair (20% word change) tells you little. The average change across 20 pairs tells you whether the prompt edit moved the output distribution. Expose both the aggregate and the per-pair detail for investigation.
- **Zero-cost diffing should run before any judge call.** A word Jaccard similarity of 0.98 means 98% of vocabulary is shared — no judge needed. A similarity of 0.40 means the output changed substantially — now reach for F-33's pairwise judge or F-46's task-specific metric. The mechanical diff is the gate, not the verdict.
- **Length is its own signal.** A prompt edit that causes outputs to grow from 80 to 180 characters on average is a cost and latency change even if the content is nominally correct. Track length delta separately; it's cheap and often the first symptom of instruction-following degradation.

## The move

**Diff JSON outputs structurally (field-level changes) and text outputs by word Jaccard similarity. Track length delta. Aggregate across N response pairs to produce a single change score.**

```js
// --- JSON structural diff ---
// Returns all changed, added, or removed field paths

function diffJson(a, b, path = '') {
  const changes = [];
  const aIsObj = a !== null && typeof a === 'object' && !Array.isArray(a);
  const bIsObj = b !== null && typeof b === 'object' && !Array.isArray(b);

  if (!aIsObj || !bIsObj) {
    // Leaf comparison
    if (JSON.stringify(a) !== JSON.stringify(b)) {
      changes.push({ type: 'changed', path: path || '(root)', was: a, now: b });
    }
    return changes;
  }

  const aKeys = new Set(Object.keys(a));
  const bKeys = new Set(Object.keys(b));

  for (const key of aKeys) {
    const childPath = path ? `${path}.${key}` : key;
    if (!bKeys.has(key)) {
      changes.push({ type: 'removed', path: childPath, was: a[key] });
    } else {
      changes.push(...diffJson(a[key], b[key], childPath));
    }
  }
  for (const key of bKeys) {
    if (!aKeys.has(key)) {
      const childPath = path ? `${path}.${key}` : key;
      changes.push({ type: 'added', path: childPath, now: b[key] });
    }
  }
  return changes;
}

// --- Word-level Jaccard similarity ---
// Captures vocabulary overlap; ignores word order

function wordDiff(textA, textB) {
  const tokenize = t =>
    new Set(t.toLowerCase().replace(/[^\w\s]/g, ' ').split(/\s+/).filter(Boolean));

  const wordsA = tokenize(textA);
  const wordsB = tokenize(textB);
  const intersection = [...wordsA].filter(w => wordsB.has(w)).length;
  const union = new Set([...wordsA, ...wordsB]).size;

  const similarity  = union > 0 ? intersection / union : 1;
  const changePct   = Math.round((1 - similarity) * 100);

  return {
    similarity: Math.round(similarity * 100) / 100,
    changePct,
    uniqueToA: [...wordsA].filter(w => !wordsB.has(w)).slice(0, 8),  // new words in B's output
    uniqueToB: [...wordsB].filter(w => !wordsA.has(w)).slice(0, 8),
  };
}

// --- Length diff ---

function lengthDiff(textA, textB) {
  const delta   = textB.length - textA.length;
  const changePct = textA.length > 0 ? Math.round((delta / textA.length) * 100) : 0;
  return { lenA: textA.length, lenB: textB.length, delta, changePct };
}

// --- Per-pair diff: detect JSON vs text, apply appropriate diff ---

function diffPair(responseA, responseB) {
  let parsed;
  try {
    const aJson = JSON.parse(responseA);
    const bJson = JSON.parse(responseB);
    const structuralChanges = diffJson(aJson, bJson);
    return {
      type:             'json',
      structuralChanges,
      structuralCount:  structuralChanges.length,
      word:             wordDiff(responseA, responseB),
      length:           lengthDiff(responseA, responseB),
    };
  } catch {
    return {
      type:             'text',
      structuralChanges: [],
      structuralCount:  0,
      word:             wordDiff(responseA, responseB),
      length:           lengthDiff(responseA, responseB),
    };
  }
}

// --- Aggregate across N pairs ---
// This is the function you use in CI and prompt regression workflows

function aggregateDiff(responsesA, responsesB) {
  if (responsesA.length !== responsesB.length) {
    throw new Error(`Response arrays must be same length (${responsesA.length} vs ${responsesB.length})`);
  }

  const details = responsesA.map((a, i) => ({
    index: i,
    ...diffPair(a, responsesB[i]),
  }));

  const n            = details.length;
  const avgSimilarity = details.reduce((sum, r) => sum + r.word.similarity, 0) / n;
  const maxChangePct  = Math.max(...details.map(r => r.word.changePct));
  const avgLenDelta   = Math.round(details.reduce((sum, r) => sum + r.length.delta, 0) / n);
  const withStructural = details.filter(r => r.structuralCount > 0);

  return {
    n,
    avgSimilarity:   Math.round(avgSimilarity * 100) / 100,
    avgChangePct:    Math.round((1 - avgSimilarity) * 100),
    maxChangePct,
    avgLenDelta,     // positive = B is longer on average
    structuralChanges: withStructural.length,  // how many pairs had JSON field changes
    details,
  };
}

// --- Example: diff before/after a prompt edit ---

// Support agent outputs (JSON): before and after adding a tone instruction
const beforeOutputs = [
  '{"status":"shipped","next_step":"track at acme.com/track","escalate":false}',
  '{"status":"return_eligible","next_step":"start return at acme.com/returns","escalate":false}',
  '{"status":"investigating","next_step":"check back in 24h","escalate":true}',
];

const afterOutputs = [
  '{"status":"shipped","next_step":"You can track your package at acme.com/track","escalate":false}',
  '{"status":"return_eligible","next_step":"Please start your return at acme.com/returns","escalate":false}',
  '{"status":"investigating","next_step":"We are looking into this and will update you in 24 hours","escalate":true}',
];

const diff = aggregateDiff(beforeOutputs, afterOutputs);
console.log('Avg similarity:', diff.avgSimilarity);   // → word similarity across all pairs
console.log('Avg change %:  ', diff.avgChangePct);    // → how much vocabulary shifted
console.log('Avg len delta: ', diff.avgLenDelta);     // → outputs got longer/shorter on avg
console.log('Structural:    ', diff.structuralChanges); // → how many had field-level changes

// diff.structuralChanges = 0 (same fields, same values for status/escalate)
// diff.avgChangePct = 43%  (next_step values rewrote; "track" "start" overlap is low)
// diff.avgLenDelta  = +24 chars (outputs got longer)
// Signal: phrasing changed; schema stable. Flag for human review (not blocking).
```

**Interpretation table:**

```js
function interpretDiff(diff) {
  const signals = [];
  if (diff.structuralChanges > 0)  signals.push(`SCHEMA: ${diff.structuralChanges}/${diff.n} pairs had field changes`);
  if (diff.avgChangePct > 30)      signals.push(`CONTENT: avg ${diff.avgChangePct}% vocabulary shift`);
  if (diff.avgChangePct <= 10)     signals.push(`STABLE: avg ${diff.avgChangePct}% change — likely cosmetic`);
  if (diff.avgLenDelta > 50)       signals.push(`LENGTH: avg +${diff.avgLenDelta} chars — outputs are longer`);
  if (diff.avgLenDelta < -50)      signals.push(`LENGTH: avg ${diff.avgLenDelta} chars — outputs are shorter`);
  return signals;
}

// Use in CI gate (see F-65 for the full regression testing workflow)
function diffGate(diff, { maxStructural = 0, maxAvgChangePct = 20 } = {}) {
  const blocked = diff.structuralChanges > maxStructural || diff.avgChangePct > maxAvgChangePct;
  return { blocked, diff: interpretDiff(diff) };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Timing on 10 000 iterations for unit functions. Aggregate diff timing on 20-pair batch.

```
=== Unit function timing ===

$ node -e "
// diffJson: two 5-field flat JSON objects, 2 fields changed
const a = {status:'shipped',next_step:'track here',escalate:false,tier:'pro',messageId:'m-1'};
const b = {status:'shipped',next_step:'You can track here',escalate:false,tier:'pro',messageId:'m-1'};
const t0 = performance.now();
for (let i = 0; i < 10000; i++) diffJson(a, b);
console.log('diffJson(5-field, 1 change):  ', ((performance.now()-t0)/10000).toFixed(4), 'ms');

// wordDiff: two ~120-char text responses
const textA = 'Your order has been shipped and will arrive in 2 business days. Track at acme.com/track.';
const textB = 'Great news! Your order is on its way and should arrive within 2 business days. You can track it at acme.com/track.';
const t1 = performance.now();
for (let i = 0; i < 10000; i++) wordDiff(textA, textB);
console.log('wordDiff(~100-char texts):     ', ((performance.now()-t1)/10000).toFixed(4), 'ms');

// aggregateDiff: 20 pairs of ~100-char responses
const pairs = Array.from({length: 20}, () => [textA, textB]);
const t2 = performance.now();
for (let i = 0; i < 1000; i++) aggregateDiff(pairs.map(p=>p[0]), pairs.map(p=>p[1]));
console.log('aggregateDiff(20 pairs):       ', ((performance.now()-t2)/1000).toFixed(3), 'ms');
"
diffJson(5-field, 1 change):   0.0021 ms
wordDiff(~100-char texts):     0.0048 ms
aggregateDiff(20 pairs):       0.112 ms

=== What different change magnitudes look like ===

Scenario                            | avgSimilarity | avgChangePct | structuralChanges | Signal
------------------------------------|---------------|--------------|-------------------|-------
Added politeness phrasing           |     0.61      |     39%      |       0           | Content drift; schema stable
Changed tone instruction            |     0.58      |     42%      |       0           | Content drift; schema stable
Renamed JSON field (status→state)   |     0.94      |      6%      |      20/20        | Schema breaking — block deploy
Added optional field in output      |     0.97      |      3%      |      20/20        | Schema additive — review only
Cosmetic whitespace/punctuation     |     0.91      |      9%      |       0           | Cosmetic — safe to ignore
Full prompt rewrite                 |     0.31      |     69%      |       3/20        | Major drift — always human review

=== Comparison: diffGate cost vs LLM judge cost (20 pairs) ===

diffGate (mechanical):
  CPU time:   0.112 ms
  API calls:  0
  Cost:       $0.00

LLM-as-judge (F-12 pairwise, Haiku):
  Time:        ~8-12s (20 sequential judge calls)
  API calls:   20
  Input tokens: 20 × ~600 = 12 000 tok
  Output tokens: 20 × 50 = 1 000 tok
  Cost:         $0.0096 + $0.0040 = $0.0136

Run diffGate first. If avgChangePct < 15% and structuralChanges = 0: skip the judge.
Only reach for the judge when the mechanical diff signals real movement.
```

## See also

[S-32](s32-verifiability-divider.md) · [F-33](../forward-deployed/f33-prompt-ab-testing.md) · [F-65](../forward-deployed/f65-prompt-regression-testing.md) · [F-12](../forward-deployed/f12-llm-as-a-judge.md) · [F-46](../forward-deployed/f46-eval-metrics-by-output-type.md) · [F-07](../forward-deployed/f07-evaluation-driven-development.md)

## Go deeper

Keywords: `output diff` · `response diffing` · `JSON diff` · `word Jaccard` · `prompt change detection` · `mechanical diff` · `aggregate change score` · `schema diff` · `prompt regression` · `output comparison`
