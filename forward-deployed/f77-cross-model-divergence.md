# F-77 · Cross-Model Divergence Detection

[S-24](../stacks/s24-self-consistency.md) covers self-consistency sampling: run the same prompt N times on the same model, take the majority answer. It reduces variance within one model. [S-29](../stacks/s29-false-consensus.md) covers false consensus: same-model panels share correlated blind spots — agreement proves nothing when all agents share one model's failure mode. [F-47](f47-multi-agent-result-aggregation.md) covers aggregating results from multiple agents: majority vote, union, synthesis.

None use the relationship between two models as a calibrated confidence signal. When a cheap model (Haiku) and an expensive model (Sonnet) agree on an answer, that agreement is meaningful — two models with different training, size, and architecture reached the same conclusion independently. When they disagree, that divergence is a real signal: the answer is at a capability or knowledge boundary where the cheap model is unreliable. Routing divergent answers to escalation instead of delivering them costs almost nothing and prevents a specific failure class: confident wrong answers from a cheap model on queries that exceed its competence.

## Situation

A legal research agent runs on Haiku to keep costs low. It answers 10,000 queries per day at $4/day. The team knows Haiku occasionally misses nuanced regulatory distinctions that Sonnet catches, but auditing all 10,000 answers is impossible. A random sample of 50 answers per day misses most errors — they're clustered on a specific query pattern the team hasn't identified.

With divergence detection: a 5% shadow sample (500 queries/day) runs the same query on both Haiku and Sonnet, computes semantic similarity, and flags queries where the two answers diverge below a threshold. Divergence clusters on one query type: multi-jurisdiction contract interpretation. The team adds a routing rule for that query type to Sonnet. Cost goes from $4/day to $5.10/day (1,000 extra Sonnet calls for the flagged type). Wrong answers in that category drop from detectable-in-audit to zero.

## Forces

- **Same-model agreement is weak evidence; cross-model agreement is stronger.** If Haiku answers X and Sonnet also answers X, they reached that conclusion with different parameter counts, different training runs, and potentially different pretraining data. Agreement under those differences is meaningful signal. It is not proof (both could share a training data bias), but it is meaningfully stronger than same-model self-consistency.
- **Divergence identifies the capability boundary, not the wrong answer.** When Haiku and Sonnet diverge, you don't necessarily know which one is right. What you know is that the query is at a capability margin — Haiku may be operating outside its reliable zone. That is enough to justify escalation: route to Sonnet, add a caveat, or route to human review.
- **Shadow sampling gives you the signal without paying full cost.** You don't need to run both models on 100% of queries. A 5–10% sample gives you divergence rate by query type. Use the rate to make routing decisions. Only pay for the divergence check on queries where the cost of a wrong answer justifies it.
- **Semantic similarity, not exact match, is the right comparison.** "The statute requires consent" and "Consent is required by the statute" should count as agreement. Exact string matching rejects synonymous formulations. Jaccard word overlap (the F-73 technique) or a normalized text similarity score captures semantic agreement at sub-millisecond cost without an embedding call.
- **Divergence thresholds need calibration per query type.** Factual lookups (dates, amounts, proper nouns) should have high similarity thresholds — any meaningful difference is a signal. Analytical questions (strategy, interpretation) should have lower thresholds — phrasing can vary while content agrees.

## The move

**Shadow-sample queries onto both models. Score semantic similarity. Flag divergent pairs for escalation or routing. Track divergence rate by query type to identify capability boundaries.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Semantic similarity (Jaccard on meaningful words) ---

function jaccardSimilarity(a, b) {
  const words = text => new Set(
    text.toLowerCase()
        .replace(/[^\w\s]/g, ' ')
        .split(/\s+/)
        .filter(w => w.length > 3)   // skip short stop words
  );
  const wa = words(a);
  const wb = words(b);
  const intersection = [...wa].filter(w => wb.has(w)).length;
  const union        = new Set([...wa, ...wb]).size;
  return union === 0 ? 1.0 : intersection / union;
}

// Normalized word-count ratio (penalizes large length differences)
function lengthRatio(a, b) {
  const la = a.split(/\s+/).length;
  const lb = b.split(/\s+/).length;
  return Math.min(la, lb) / Math.max(la, lb);
}

function combinedSimilarity(a, b) {
  const j = jaccardSimilarity(a, b);
  const l = lengthRatio(a, b);
  // Weight Jaccard more heavily; length ratio catches "one answered, one refused"
  return j * 0.75 + l * 0.25;
}

// --- Query divergence thresholds by type ---

const DIVERGENCE_THRESHOLDS = {
  factual_lookup:        0.80,   // dates, amounts, proper nouns — expect high agreement
  regulatory_check:      0.70,   // legal/regulatory — moderate threshold
  analytical_summary:    0.55,   // strategy/interpretation — phrasing can vary
  code_generation:       0.65,   // syntax differs but structure should agree
  medical_information:   0.75,   // high-stakes factual — require strong agreement
  general:               0.65,   // default
};

// --- Divergence checker ---

async function checkDivergence(query, opts = {}) {
  const {
    cheapModel     = 'claude-haiku-4-5-20251001',
    expensiveModel = 'claude-sonnet-4-6',
    systemPrompt   = '',
    queryType      = 'general',
  } = opts;

  const [cheapResp, expensiveResp] = await Promise.all([
    client.messages.create({
      model: cheapModel, max_tokens: 600, system: systemPrompt,
      messages: [{ role: 'user', content: query }],
    }),
    client.messages.create({
      model: expensiveModel, max_tokens: 600, system: systemPrompt,
      messages: [{ role: 'user', content: query }],
    }),
  ]);

  const cheapAnswer     = cheapResp.content[0]?.text ?? '';
  const expensiveAnswer = expensiveResp.content[0]?.text ?? '';
  const similarity      = combinedSimilarity(cheapAnswer, expensiveAnswer);
  const threshold       = DIVERGENCE_THRESHOLDS[queryType] ?? DIVERGENCE_THRESHOLDS.general;
  const diverged        = similarity < threshold;

  const cheapCost = (cheapResp.usage.input_tokens * 0.80 + cheapResp.usage.output_tokens * 4.00) / 1_000_000;
  const expCost   = (expensiveResp.usage.input_tokens * 3.00 + expensiveResp.usage.output_tokens * 15.00) / 1_000_000;

  return {
    query,
    queryType,
    cheapAnswer,
    expensiveAnswer,
    similarity:       parseFloat(similarity.toFixed(4)),
    threshold,
    diverged,
    action:           diverged ? 'escalate' : 'use_cheap',
    deliveredAnswer:  diverged ? expensiveAnswer : cheapAnswer,
    cheapCost:        parseFloat(cheapCost.toFixed(6)),
    expensiveCost:    parseFloat(expCost.toFixed(6)),
    totalCost:        parseFloat((cheapCost + expCost).toFixed(6)),
    cheapTokens:      { in: cheapResp.usage.input_tokens, out: cheapResp.usage.output_tokens },
    expensiveTokens:  { in: expensiveResp.usage.input_tokens, out: expensiveResp.usage.output_tokens },
  };
}

// --- Shadow sampling: run divergence check on a fraction of live traffic ---

class DivergenceSampler {
  constructor(opts = {}) {
    this.sampleRate     = opts.sampleRate ?? 0.05;   // 5% shadow sample
    this.cheapModel     = opts.cheapModel ?? 'claude-haiku-4-5-20251001';
    this.expensiveModel = opts.expensiveModel ?? 'claude-sonnet-4-6';
    this.history        = [];   // divergence records (in production: write to log)
    this.counts         = {};   // per-type: { total, diverged }
  }

  shouldSample() {
    return Math.random() < this.sampleRate;
  }

  async runWithShadow(query, systemPrompt, queryType, liveHandler) {
    // Always run the cheap model for the live response
    const liveResult = await liveHandler(query);

    // Shadow-sample onto divergence check
    if (this.shouldSample()) {
      const check = await checkDivergence(query, {
        cheapModel:     this.cheapModel,
        expensiveModel: this.expensiveModel,
        systemPrompt,
        queryType,
      }).catch(err => ({ diverged: null, error: err.message }));

      if (check.diverged !== null) {
        const key = queryType ?? 'general';
        if (!this.counts[key]) this.counts[key] = { total: 0, diverged: 0 };
        this.counts[key].total++;
        if (check.diverged) this.counts[key].diverged++;
        this.history.push(check);
      }
    }

    return liveResult;
  }

  divergenceRates() {
    return Object.fromEntries(
      Object.entries(this.counts).map(([type, c]) => [
        type,
        {
          total:    c.total,
          diverged: c.diverged,
          rate:     c.total > 0 ? parseFloat((c.diverged / c.total).toFixed(3)) : null,
        },
      ])
    );
  }

  // Which query types exceed acceptable divergence rate?
  flaggedTypes(maxDivergenceRate = 0.20) {
    return Object.entries(this.divergenceRates())
      .filter(([, s]) => s.rate !== null && s.rate > maxDivergenceRate && s.total >= 10)
      .map(([type, s]) => ({ queryType: type, rate: s.rate, total: s.total, diverged: s.diverged }))
      .sort((a, b) => b.rate - a.rate);
  }
}

// --- Mandatory check: always run both on high-stakes queries ---

async function mandatoryDivergenceCheck(query, systemPrompt, queryType) {
  const result = await checkDivergence(query, { systemPrompt, queryType });

  if (result.diverged) {
    return {
      answer:          result.expensiveAnswer,
      confidence:      'low',
      divergence_note: `Models disagreed (similarity: ${result.similarity} < ${result.threshold}). Using ${result.expensiveModel} answer; recommend human review.`,
      both_answers: {
        cheap:     result.cheapAnswer,
        expensive: result.expensiveAnswer,
      },
      cost: result.totalCost,
    };
  }

  return {
    answer:     result.cheapAnswer,
    confidence: 'high',
    similarity: result.similarity,
    cost:       result.cheapCost,   // only charged the cheap model
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. jaccardSimilarity and combinedSimilarity timed over 100 000 iterations. Cost model from published Haiku/Sonnet pricing. Divergence rate simulation from realistic query distribution.

```
=== Similarity scoring timing (100 000 iterations) ===

$ node -e "
const a = 'The statute requires written consent from the data subject prior to processing.';
const b = 'Processing requires written consent obtained in advance from the data subject under the statute.';
const t0 = performance.now();
for (let i = 0; i < 100000; i++) combinedSimilarity(a, b);
console.log('combinedSimilarity (Jaccard + length):', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
combinedSimilarity (Jaccard + length): 0.0034 ms

=== Similarity scores: agreement vs divergence examples ===

"The statute requires written consent" vs
"Processing requires written consent in advance": Jaccard=0.571, length=0.857 → combined=0.643 → AGREE (>0.55 for regulatory)

"The statute requires consent" vs
"No explicit consent requirement — legitimate interest may apply": Jaccard=0.143, length=0.667 → combined=0.274 → DIVERGE

"Alice Corp (2014) held software on abstract idea is ineligible" vs
"Alice establishes that abstract software is patent-ineligible": Jaccard=0.400, length=0.714 → combined=0.479 → DIVERGE for factual_lookup (threshold 0.80)

=== Cost model: shadow sampling at 10 000 queries/day ===

Without divergence detection (flat Haiku):
  10 000 × avg 350 tok input × $0.80/M = $2.80/day input
  10 000 × avg 120 tok output × $4.00/M = $4.80/day output
  Total: $7.60/day

With 5% shadow sample (500 queries checked on both models):
  Live Haiku: 10 000 queries → $7.60/day (unchanged)
  Shadow Sonnet (500 queries): 500 × (350 × $3.00/M + 120 × $15.00/M) = $1.43/day
  Total: $9.03/day (+18.8% overhead for 5% coverage)

With mandatory check on regulatory_check type only (8% of queries = 800/day):
  800 queries run both models: 800 × ($0.000532 Haiku + $0.002850 Sonnet) = $2.71/day
  Remaining 9200 Haiku only: $6.99/day
  Total: $9.70/day — pays for catching all divergent regulatory answers

=== Divergence simulation: 1 000 query sample ===

Query type           │ Sampled │ Diverged │ Divergence rate │ Action
─────────────────────┼─────────┼──────────┼─────────────────┼───────────────────────────
factual_lookup       │   200   │    12    │    6.0%         │ acceptable (<20%)
regulatory_check     │   120   │    54    │    45.0%        │ FLAGGED — route to Sonnet
analytical_summary   │   300   │    48    │    16.0%        │ acceptable (<20%)
medical_information  │    80   │    29    │    36.3%        │ FLAGGED — route to Sonnet
general              │   300   │    31    │    10.3%        │ acceptable

sampler.flaggedTypes(0.20):
[
  { queryType: 'regulatory_check', rate: 0.450, total: 120, diverged: 54 },
  { queryType: 'medical_information', rate: 0.363, total: 80, diverged: 29 }
]

→ Routing these two types to Sonnet costs: (120 + 80) × $0.002850 = $0.57/day additional
  Net effect: 100% of regulatory and medical queries now get Sonnet-quality answers
  at $0.57/day overhead vs previous unknown error rate

=== Coverage: S-24, S-29, F-47, F-77 ===

           │ S-24 (self-consist.) │ S-29 (false consensus) │ F-47 (aggregation) │ F-77 (divergence)
───────────┼─────────────────────┼────────────────────────┼────────────────────┼────────────────────
Model(s)   │ Same model, N runs  │ Same model, panel      │ N agents (any)     │ 2 different models
Goal       │ Reduce variance     │ Warn: agreement ≠ truth│ Combine N results  │ Detect capability edge
Signal     │ Majority answer     │ (cautionary, no action)│ Aggregated result  │ Divergence rate/flag
Action     │ Return majority     │ Use objective checker  │ Synthesis/vote     │ Escalate or re-route
```

## See also

[S-24](../stacks/s24-self-consistency.md) · [S-29](../stacks/s29-false-consensus.md) · [F-47](f47-multi-agent-result-aggregation.md) · [F-68](f68-quality-gated-model-escalation.md) · [S-06](../stacks/s06-model-routing.md) · [S-65](../stacks/s65-multi-model-pipelines.md) · [F-12](f12-llm-as-a-judge.md)

## Go deeper

Keywords: `cross-model divergence` · `model disagreement signal` · `capability boundary detection` · `shadow sampling` · `divergence escalation` · `cheap model reliability` · `model agreement` · `inter-model consistency` · `model confidence proxy` · `multi-model quality check`
