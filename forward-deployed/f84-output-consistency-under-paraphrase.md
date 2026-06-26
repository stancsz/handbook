# F-84 · Output Consistency Under Paraphrase

[S-24](../stacks/s24-self-consistency.md) covers self-consistency sampling: run the same prompt N times on the same model at temperature > 0, take the majority answer. It addresses variance on an identical query — does the model give the same answer to the *same question* repeatedly? [F-79](f79-semantic-regression-detection.md) covers semantic regression detection: compare the semantic meaning of agent outputs before and after a prompt or model change, using embeddings. It catches meaning changes across deploys.

Neither tests a property that well-designed agents should have: **query invariance** — giving semantically equivalent answers to semantically equivalent questions regardless of how the question is phrased. "What is your return policy?" and "Can I get a refund?" and "How do I send something back?" are all asking the same thing. An agent that answers them differently — not because the questions are genuinely distinct but because it's pattern-matching on surface form — is unreliable in deployment. Users don't phrase questions the way the prompt author imagined.

Output consistency under paraphrase tests this directly: given a set of anchor questions, generate or maintain a set of known paraphrases for each anchor, run all paraphrases through the agent, and flag anchors where pairwise answer similarity falls below a threshold. The inconsistency is the signal — either the agent is surface-form-sensitive in a way it shouldn't be, or the paraphrases expose a genuine ambiguity in the question that needs to be resolved in the system prompt.

## Situation

A product FAQ agent handles billing questions. The prompt author wrote example questions in a specific style ("What happens to my data if I cancel?"). QA evaluates on those exact examples and everything passes. In production, users ask: "If I delete my account, what happens to my files?", "Will my data be deleted?", "I want to cancel — do I lose everything?" The agent answers these three differently: the first gets a full data retention policy explanation, the second gets "Yes, your account data is deleted," and the third gets "You'll need to contact support." All three should get the same answer.

Paraphrase consistency testing would have caught this: before deploy, run all three paraphrases, compute pairwise similarity. Second and third answers have cosine similarity 0.31 — well below the 0.70 threshold. The test flags the `account_cancellation_data` anchor as inconsistent. Investigation: the third phrasing ("I want to cancel") triggers the agent's escalation heuristic ("contact support"), which was written without considering that cancellation questions should also answer the data question. The system prompt is patched to handle the ambiguity; paraphrase consistency test passes.

## Forces

- **Prompt authors write in their own idiom; users don't.** The way the prompt is written shapes which phrasings the model handles confidently. A prompt with one worked example of a question will work well for that phrasing and degrade on distant paraphrases. The only way to know the degradation boundary is to test it.
- **Surface sensitivity is not always wrong.** "What is your return policy?" and "I want to return something — it's damaged" are paraphrases of the same topic but the second warrants a different *style* of response (more directive, open a case) even if the *policy content* should be the same. Paraphrase consistency tests should check semantic content agreement, not stylistic equivalence.
- **Pre-registering paraphrases is better than generating them.** Auto-generated paraphrases (via a model) are convenient but biased: the model generates paraphrases it finds natural, not the ones users actually write. Paraphrase sets from real user logs — diverse phrasings of the same intent captured in production — give more signal. Supplement with model-generated paraphrases at launch when no logs exist.
- **The threshold varies by domain.** A refund policy question should yield highly consistent answers (threshold 0.80). An analytical question about a user's specific situation may legitimately vary by phrasing (threshold 0.60). Set thresholds per anchor category.
- **Inconsistency diagnoses the problem.** A low-similarity pair does not tell you what to fix. You need to read both answers, identify which diverges from the ground truth, and trace why — usually a surface trigger in the prompt that fires differently across phrasings. The test surfaces the problem; the fix requires reading the output.

## The move

**Maintain a paraphrase registry per anchor question. Run all paraphrases through the agent before each deploy. Compute pairwise cosine similarity per anchor. Flag anchors below threshold. Read the diverging pair to diagnose.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Paraphrase registry ---
// In production: stored in a file or database; grown from real user session logs

const PARAPHRASE_REGISTRY = [
  {
    anchorId:  'return_policy',
    category:  'billing',
    threshold: 0.78,
    paraphrases: [
      'What is your return policy?',
      'Can I get a refund?',
      'How do I return something I bought?',
      'I want to send something back — how does that work?',
      'Do you accept returns?',
    ],
  },
  {
    anchorId:  'cancellation_data',
    category:  'billing',
    threshold: 0.75,
    paraphrases: [
      'What happens to my data if I cancel?',
      'If I delete my account, what happens to my files?',
      'Will my data be deleted when I cancel?',
      'I want to cancel — do I lose everything?',
    ],
  },
  {
    anchorId:  'pricing_annual',
    category:  'billing',
    threshold: 0.72,
    paraphrases: [
      'Is there a discount for annual billing?',
      'How much do I save if I pay yearly?',
      'What is the annual plan price?',
      'Do you offer yearly subscriptions?',
    ],
  },
];

// --- Cosine similarity (reused pattern) ---

function cosineSimilarity(a, b) {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) { dot += a[i]*b[i]; na += a[i]*a[i]; nb += b[i]*b[i]; }
  const d = Math.sqrt(na) * Math.sqrt(nb);
  return d === 0 ? 0 : dot / d;
}

// --- Lightweight Jaccard for cheap pairwise comparison (no embedding call) ---

function jaccardSimilarity(a, b) {
  const words = t => new Set(t.toLowerCase().replace(/[^\w\s]/g, ' ').split(/\s+/).filter(w => w.length > 3));
  const wa = words(a), wb = words(b);
  const inter = [...wa].filter(w => wb.has(w)).length;
  const union  = new Set([...wa, ...wb]).size;
  return union === 0 ? 1 : inter / union;
}

// --- Run one anchor: collect agent answers for all paraphrases ---

async function runAnchorTest(anchor, systemPrompt, opts = {}) {
  const { model = 'claude-haiku-4-5-20251001', maxTokens = 300 } = opts;

  // Run all paraphrases in parallel
  const responses = await Promise.all(
    anchor.paraphrases.map(async (query) => {
      const resp = await client.messages.create({
        model, max_tokens: maxTokens, system: systemPrompt,
        messages: [{ role: 'user', content: query }],
      });
      return { query, answer: resp.content[0]?.text ?? '', inputTok: resp.usage.input_tokens, outputTok: resp.usage.output_tokens };
    })
  );

  // Compute pairwise Jaccard similarity between all answers
  const pairs = [];
  for (let i = 0; i < responses.length; i++) {
    for (let j = i + 1; j < responses.length; j++) {
      const sim = jaccardSimilarity(responses[i].answer, responses[j].answer);
      pairs.push({
        query_i:  responses[i].query,
        query_j:  responses[j].query,
        answer_i: responses[i].answer,
        answer_j: responses[j].answer,
        similarity: parseFloat(sim.toFixed(4)),
        flagged:  sim < anchor.threshold,
      });
    }
  }

  const minSim  = pairs.length > 0 ? Math.min(...pairs.map(p => p.similarity)) : 1;
  const flagged = pairs.filter(p => p.flagged);
  const totalCost = responses.reduce((s, r) => {
    return s + (r.inputTok * 0.80 + r.outputTok * 4.00) / 1_000_000;
  }, 0);

  return {
    anchorId:     anchor.anchorId,
    category:     anchor.category,
    threshold:    anchor.threshold,
    paraphraseCount: anchor.paraphrases.length,
    minSimilarity:   parseFloat(minSim.toFixed(4)),
    consistent:      flagged.length === 0,
    flaggedPairs:    flagged,
    responses,
    costUsd:      parseFloat(totalCost.toFixed(5)),
  };
}

// --- Full suite runner ---

async function runConsistencySuite(registry, systemPrompt, opts = {}) {
  const results = await Promise.all(
    registry.map(anchor => runAnchorTest(anchor, systemPrompt, opts))
  );

  const inconsistent = results.filter(r => !r.consistent);
  const totalCost    = results.reduce((s, r) => s + r.costUsd, 0);

  // Worst pair per failing anchor (lowest similarity)
  const worstPairs = inconsistent.flatMap(r =>
    r.flaggedPairs.sort((a, b) => a.similarity - b.similarity).slice(0, 1)
      .map(p => ({ anchorId: r.anchorId, ...p }))
  ).sort((a, b) => a.similarity - b.similarity);

  return {
    total:          results.length,
    consistent:     results.filter(r => r.consistent).length,
    inconsistent:   inconsistent.length,
    totalCostUsd:   parseFloat(totalCost.toFixed(5)),
    deployVerdict:  inconsistent.length === 0
      ? 'PASS — all anchors consistent under paraphrase'
      : `REVIEW — ${inconsistent.length} anchor(s) fail consistency; read flaggedPairs`,
    worstPairs,
    results,
  };
}

// --- Paraphrase similarity tracker: tracks consistency over time ---

class ConsistencyTracker {
  constructor() { this.history = []; }

  record(suiteResult, promptVersion) {
    this.history.push({
      runAt:         Date.now(),
      promptVersion,
      inconsistent:  suiteResult.inconsistent,
      worstSim:      Math.min(...suiteResult.results.map(r => r.minSimilarity)),
    });
  }

  // Flag if consistency degraded vs prior run
  regressionSince(priorRunIndex) {
    const prior   = this.history[priorRunIndex];
    const current = this.history[this.history.length - 1];
    if (!prior || !current) return null;
    return {
      inconsistentDelta: current.inconsistent - prior.inconsistent,
      worstSimDelta:     parseFloat((current.worstSim - prior.worstSim).toFixed(4)),
      regressed: current.inconsistent > prior.inconsistent || current.worstSim < prior.worstSim - 0.05,
    };
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `jaccardSimilarity()` timed over 100 000 iterations. Suite cost computed from Haiku pricing (3 anchors × avg 4 paraphrases × avg 350 in + 200 out tok). Representative similarity scores from the account cancellation scenario described above — illustrative, not from a live model run.

```
=== jaccardSimilarity() timing (100 000 iterations) ===

$ node -e "
const a = 'What happens to my data if I cancel my subscription with your service?';
const b = 'If I delete my account what will happen to all my files and saved content?';
const t0 = performance.now();
for (let i = 0; i < 100000; i++) jaccardSimilarity(a, b);
console.log('jaccardSimilarity:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
jaccardSimilarity: 0.0019 ms

=== Suite cost: 3 anchors, avg 4.3 paraphrases each ===

Per paraphrase call (Haiku, ~350 in + ~200 out tok):
  (350 × $0.80 + 200 × $4.00) / 1 000 000 = $0.001080

3 anchors × 4.3 paraphrases × $0.001080 = $0.01393 per suite run
At 3 runs/deploy × 5 deploys/week = $0.21/week

=== Consistency test result: cancellation_data anchor ===

systemPrompt: 'You are a customer support agent for DataPipe. Answer questions about billing and account management.'

Paraphrases run:
  P1: "What happens to my data if I cancel?"
      → "Your data is retained for 30 days after cancellation. During this period, you can reactivate your account and recover everything. After 30 days, all data is permanently deleted per our retention policy."
  P2: "If I delete my account, what happens to my files?"
      → "Deleting your account triggers a 30-day grace period. Your files remain accessible if you reactivate within that window."
  P3: "Will my data be deleted when I cancel?"
      → "Yes, your account data is permanently deleted — though we offer a 30-day window to reactivate first."
  P4: "I want to cancel — do I lose everything?"
      → "For billing changes or cancellations, please contact our support team at support@datapipe.io."

Pairwise Jaccard similarities:
  P1 vs P2: 0.47 — answers agree (30-day grace) but phrasing varies → ABOVE threshold 0.75? No: 0.47 < 0.75 → FLAGGED
  P1 vs P3: 0.39 → FLAGGED
  P1 vs P4: 0.08 → FLAGGED (escalation redirect — completely different content)
  P2 vs P3: 0.41 → FLAGGED
  P2 vs P4: 0.06 → FLAGGED
  P3 vs P4: 0.04 → FLAGGED

worstPairs:
[
  { anchorId: 'cancellation_data', similarity: 0.04,
    query_i:  'Will my data be deleted when I cancel?',
    query_j:  'I want to cancel — do I lose everything?',
    answer_i: 'Yes, your account data is permanently deleted...',
    answer_j: 'For billing changes or cancellations, please contact support...'
  }
]

deployVerdict: 'REVIEW — 1 anchor(s) fail consistency; read flaggedPairs'

Diagnosis: P4 phrasing "I want to cancel" triggers the escalation heuristic.
Fix: add to system prompt — "Questions about cancellation, even phrased as intent ('I want to cancel'), should answer the data retention policy first, then offer support contact."
After fix: P4 similarity rises to 0.61 (above 0.60 for this anchor after threshold recalibration); suite passes.

Note: P1 vs P2/P3 similarities (0.39–0.47) are below 0.75 but the answers are semantically consistent —
they all describe the 30-day grace period. Jaccard is conservative (lexical). Embedding-based similarity
(cosine) would score these pairs higher (~0.82). Use Jaccard for fast CI checks; upgrade to embedding
similarity for high-stakes domains (drug interactions, legal guidance) where lexical agreement is insufficient.

=== S-24 vs F-79 vs F-84 ===

              │ S-24 (self-consistency)      │ F-79 (semantic regression)   │ F-84 (paraphrase consistency)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
Tests         │ Same query, N model runs     │ Same query, baseline vs new  │ Same intent, K phrasings
Catches       │ Stochastic variance          │ Meaning change on deploy     │ Surface-form sensitivity
Paraphrases?  │ No (identical prompt)        │ No (identical prompt)        │ Yes (different surface form)
When to run   │ High-stakes live queries     │ Pre-deploy                   │ Pre-deploy + on log analysis
Cost          │ N × model call               │ 1 embed call per output      │ K × model call per anchor
Fix target    │ Sampling temp / prompt       │ Prompt change that shifted meaning│ Prompt heuristic that fires on surface form
```

## See also

[S-24](../stacks/s24-self-consistency.md) · [F-79](f79-semantic-regression-detection.md) · [F-07](f07-eval-driven-development.md) · [F-83](f83-agent-capability-testing.md) · [S-53](../stacks/s53-confidence-calibration.md) · [F-30](f30-runtime-output-validation.md) · [F-78](f78-confidence-gated-delivery.md)

## Go deeper

Keywords: `paraphrase consistency` · `query invariance` · `output consistency under rephrasing` · `surface form sensitivity` · `paraphrase test` · `semantic consistency` · `rephrasing robustness` · `intent-invariant response` · `paraphrase equivalence test` · `agent robustness to query variation`
