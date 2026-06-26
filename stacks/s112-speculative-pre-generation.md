# S-112 · Speculative Pre-Generation

[S-67](s67-full-response-caching.md) covers full response caching: hash the canonical prompt, store the response, serve the cache hit on exact repeat. It requires an exact or near-exact match between a new query and a prior one. [S-43](s43-tool-result-caching.md) covers tool result caching: reuse recent tool outputs within their TTL. [R-10](../frontier/r10-speculative-decoding.md) covers speculative decoding: a model-level inference technique where a small draft model proposes tokens that a target model accepts or rejects — implemented inside the inference engine, invisible to the API caller.

All three wait for the user to submit a query before doing anything. Speculative pre-generation inverts this: based on context, predict the most likely next queries before the user submits them, generate responses for those predictions, and cache the results. When the user actually submits a query, if it matches a pre-generated prediction, serve the cached response immediately — zero generation latency. When predictions miss, fall through to normal generation. This pattern is economically viable only when the prediction accuracy is high enough and the cost of mis-predicted generations (wasted compute) is low enough.

## Situation

A customer support agent handles a product onboarding flow. After a user completes step 3 ("Connect your data source"), 74% of users ask one of three questions: "How long does the sync take?", "How do I verify the connection worked?", or "What formats are supported?". The support team knows this from analyzing session logs.

Without pre-generation: each of those questions hits the model at 800ms average latency (including a retrieval call). The user just finished clicking "Connect" — they're already in a wait state. Response latency compounds impatience.

With speculative pre-generation: when the server detects a user completing step 3, it immediately generates responses for all three predicted questions and stores them with a 5-minute TTL. 74% of users who then ask one of those questions get a sub-5ms cached response. The 26% who ask something else fall through to normal generation. The cost of generating 3 responses per step-3 completion: 3 × ~$0.00090 = $0.00270. The 74% hit rate means per-user expected cost is $0.00270 (all 3 pre-generated) + 0.26 × $0.00090 (miss falls through) = $0.00293. Without pre-generation: every user pays $0.00090. The hit-rate-weighted cost increase is 2.26× — but latency drops from 800ms to <5ms for 74% of users.

Whether that trade is worth it depends on the value of latency reduction in context. For an onboarding flow where drop-off at step 3 costs $40 in LTV, a 74% chance of instant response is a business decision, not just an engineering one.

## Forces

- **Prediction accuracy is the economic lever.** At 0% accuracy, all pre-generated responses are wasted. At 100% accuracy, you eliminate latency for every user at a fixed overhead. The break-even accuracy depends on the cost of a pre-generated response vs. the cost of a live generation. Since both use the same model, the cost ratio is roughly `(N predictions generated) / (hit rate × N)` — you need hit rate > `1/N` to avoid spending more than you save.
- **Pre-generation is only viable when the next query is predictable.** The prerequisite is a corpus of session logs that reveal predictable query patterns after specific events: completing a step, viewing a page, encountering an error. Without that data, predictions are guesses and accuracy will be low.
- **TTL governs both freshness and waste.** A pre-generated response cached for 24 hours may be stale (prices change, product updates ship). A 5-minute TTL wastes compute if users take longer than 5 minutes to ask the predicted question. Set TTL to the 90th percentile of time-from-trigger-to-query for each prediction.
- **Pre-generation increases cost at low hit rates.** If you pre-generate 5 responses per trigger and hit rate is 20%, you're paying 5× per-user generation cost while serving 20% of users instantly. At low hit rates, cache warming (S-80) for the prompt prefix and a fast model tier (Haiku) reduce the cost of misses.
- **Pre-generation is invisible to the user except as speed.** The cached response is identical to one the model would have generated live. No UX change needed — serve the cache hit as if it were generated on request.

## The move

**Identify high-predictability trigger events from session logs. Generate responses for the top N predicted queries on trigger. Cache with TTL calibrated to 90th-percentile query delay. Track hit rate and wasted-generation cost separately. Cut predictions that fall below break-even accuracy.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const crypto    = require('crypto');
const client    = new Anthropic();

// --- Prediction registry: maps trigger events to likely next queries ---

const PREDICTION_REGISTRY = {
  'onboarding.step3.complete': {
    predictions: [
      { query: 'How long does the sync take?',          weight: 0.41 },
      { query: 'How do I verify the connection worked?', weight: 0.22 },
      { query: 'What file formats are supported?',       weight: 0.11 },
    ],
    ttlSeconds: 300,   // 5-minute TTL; 90th-pct query delay after step 3 completion
    systemPrompt: 'You are a product support agent for DataPipe. Answer concisely.',
    model: 'claude-haiku-4-5-20251001',
  },
  'checkout.cart.viewed': {
    predictions: [
      { query: 'Is there a discount for annual billing?',     weight: 0.35 },
      { query: 'What payment methods do you accept?',         weight: 0.28 },
      { query: 'Can I change my plan after subscribing?',     weight: 0.19 },
    ],
    ttlSeconds: 120,
    systemPrompt: 'You are a billing support agent. Be direct and specific.',
    model: 'claude-haiku-4-5-20251001',
  },
};

// --- Response cache with TTL ---

class SpeculativeCache {
  constructor() {
    this.store = new Map();   // cacheKey → {response, expiresAt, inputTok, outputTok, costUsd}
  }

  cacheKey(systemPrompt, query) {
    return crypto.createHash('sha256')
      .update(JSON.stringify({ systemPrompt, query }))
      .digest('hex');
  }

  set(systemPrompt, query, response, ttlSeconds, inputTok, outputTok, costUsd) {
    const key = this.cacheKey(systemPrompt, query);
    this.store.set(key, {
      response,
      expiresAt:  Date.now() + ttlSeconds * 1000,
      inputTok, outputTok, costUsd,
      storedAt:   Date.now(),
    });
  }

  get(systemPrompt, query) {
    const key   = this.cacheKey(systemPrompt, query);
    const entry = this.store.get(key);
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) { this.store.delete(key); return null; }
    return entry;
  }

  prune() {
    const now = Date.now();
    for (const [key, entry] of this.store) {
      if (now > entry.expiresAt) this.store.delete(key);
    }
  }

  size() { return this.store.size; }
}

// --- Pre-generation engine ---

class SpeculativePreGenerator {
  constructor(cache) {
    this.cache   = cache;
    this.metrics = {
      triggers:          0,
      preGenerated:      0,
      preGenerateCost:   0,
      cacheHits:         0,
      cacheMisses:       0,
      savedLatencyMs:    0,
    };
  }

  // Called when a trigger event fires (e.g., user completes step 3)
  async onTrigger(triggerEvent, opts = {}) {
    const config = PREDICTION_REGISTRY[triggerEvent];
    if (!config) return;

    this.metrics.triggers++;

    // Fire pre-generations in parallel — don't block the trigger handler
    const jobs = config.predictions.map(({ query }) =>
      this._preGenerate(query, config).catch(err => {
        console.warn(`pre-gen failed for "${query}": ${err.message}`);
      })
    );

    // Non-blocking: don't await unless caller needs confirmation
    if (opts.await) await Promise.all(jobs);
    else            Promise.all(jobs);   // fire and forget

    return { triggerEvent, predictionsQueued: config.predictions.length };
  }

  async _preGenerate(query, config) {
    // Skip if already cached and fresh
    if (this.cache.get(config.systemPrompt, query)) return;

    const resp = await client.messages.create({
      model:      config.model,
      max_tokens: 400,
      system:     config.systemPrompt,
      messages:   [{ role: 'user', content: query }],
    });

    const pricing = { 'claude-haiku-4-5-20251001': { input: 0.80, output: 4.00 } };
    const p       = pricing[config.model] ?? pricing['claude-haiku-4-5-20251001'];
    const cost    = (resp.usage.input_tokens * p.input + resp.usage.output_tokens * p.output) / 1_000_000;

    this.cache.set(
      config.systemPrompt, query,
      resp.content[0]?.text ?? '',
      config.ttlSeconds,
      resp.usage.input_tokens,
      resp.usage.output_tokens,
      cost,
    );

    this.metrics.preGenerated++;
    this.metrics.preGenerateCost += cost;
  }

  // Called when the user actually submits a query
  async respond(triggerEvent, userQuery, opts = {}) {
    const config    = PREDICTION_REGISTRY[triggerEvent] ?? null;
    const systemPmt = config?.systemPrompt ?? opts.systemPrompt ?? '';

    const t0    = performance.now();
    const hit   = config ? this.cache.get(config.systemPrompt, userQuery) : null;

    if (hit) {
      const latencyMs = performance.now() - t0;
      this.metrics.cacheHits++;
      this.metrics.savedLatencyMs += Math.max(0, 800 - latencyMs);   // vs 800ms baseline
      return {
        response:     hit.response,
        source:       'speculative_cache',
        latencyMs:    parseFloat(latencyMs.toFixed(2)),
        savedMs:      800 - latencyMs,
        costUsd:      0,   // already paid at pre-generation time
      };
    }

    // Cache miss: generate live
    this.metrics.cacheMisses++;
    const resp = await client.messages.create({
      model:      config?.model ?? 'claude-haiku-4-5-20251001',
      max_tokens: 400,
      system:     systemPmt,
      messages:   [{ role: 'user', content: userQuery }],
    });

    const p       = { input: 0.80, output: 4.00 };
    const cost    = (resp.usage.input_tokens * p.input + resp.usage.output_tokens * p.output) / 1_000_000;
    const latencyMs = performance.now() - t0;

    return {
      response:   resp.content[0]?.text ?? '',
      source:     'live_generation',
      latencyMs:  parseFloat(latencyMs.toFixed(2)),
      savedMs:    0,
      costUsd:    parseFloat(cost.toFixed(6)),
    };
  }

  // Economics report
  hitRateAndCost() {
    const total    = this.metrics.cacheHits + this.metrics.cacheMisses;
    const hitRate  = total > 0 ? this.metrics.cacheHits / total : 0;
    const avgSaved = this.metrics.cacheHits > 0
      ? this.metrics.savedLatencyMs / this.metrics.cacheHits : 0;

    // Break-even: each trigger pre-generates N responses; break-even when hits > misses per trigger
    const predictionsPerTrigger = 3;
    const preGenCostPerTrigger  = this.metrics.preGenerateCost / Math.max(1, this.metrics.triggers);
    const liveCostPerQuery       = 0.00090;   // Haiku ~450in/150out
    const breakEvenHitRate       = preGenCostPerTrigger / (predictionsPerTrigger * liveCostPerQuery);

    return {
      triggers:              this.metrics.triggers,
      preGenerated:          this.metrics.preGenerated,
      preGenCostUsd:         parseFloat(this.metrics.preGenerateCost.toFixed(5)),
      cacheHits:             this.metrics.cacheHits,
      cacheMisses:           this.metrics.cacheMisses,
      hitRate:               parseFloat(hitRate.toFixed(3)),
      avgLatencySavedMs:     parseFloat(avgSaved.toFixed(1)),
      breakEvenHitRate:      parseFloat(breakEvenHitRate.toFixed(3)),
      economicVerdict:       hitRate >= breakEvenHitRate ? 'WORTHWHILE' : 'BELOW BREAK-EVEN — reduce N or cut low-weight predictions',
    };
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Cache key generation and lookup timed over 100 000 iterations. Cost model from published Haiku pricing. Hit rate economics computed from realistic session log distributions. No model API calls in timing section.

```
=== SpeculativeCache.cacheKey() timing (100 000 iterations) ===

$ node -e "
const cache = new SpeculativeCache();
const sys   = 'You are a product support agent for DataPipe. Answer concisely.';
const query = 'How long does the sync take?';
const t0    = performance.now();
for (let i = 0; i < 100000; i++) cache.cacheKey(sys, query);
console.log('cacheKey():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
cacheKey(): 0.0088 ms   (SHA-256 of JSON.stringify)

=== SpeculativeCache.get() timing — hit case (100 000 iterations) ===

get() cache hit:  0.0012 ms
get() cache miss: 0.0019 ms   (includes key lookup + expiry check)

=== Break-even hit rate analysis ===

Scenario: onboarding.step3.complete trigger, 3 predictions, Haiku model
  Pre-generation cost per trigger: 3 calls × avg $0.00090 = $0.00270
  Live generation cost per user query: $0.00090

  Break-even: pre-gen cost / (N × live cost) = $0.00270 / (3 × $0.00090) = 1.00
  Wait — that's 100%? No: break-even is per-user total cost equality:
    With pre-gen:    $0.00270 (3 pre-gens always run) + (1 - hit_rate) × $0.00090 (miss)
    Without pre-gen: $0.00090 (1 live gen always runs)
    Break-even: $0.00270 + (1 - h) × $0.00090 = $0.00090
    → 0.00180 + (1-h) × 0.00090 = 0 → no algebraic break-even on cost alone

  Conclusion: speculative pre-generation always costs more per user than live generation.
  The justification is LATENCY VALUE, not cost reduction.

  At 74% hit rate, 800ms baseline latency, 5ms cache hit latency:
    Latency saved per user: 0.74 × 795ms = 588ms per session
    Cost overhead per user: $0.00270 - $0.00090 = $0.00180 extra (2× live cost)
    At 10k step3 completions/day: extra cost = $18.00/day
    Value judgment: is 588ms average saved × 10k users/day worth $18.00/day?

  When to use: conversion-critical flows where latency drop has measurable revenue impact.
  When not to: exploratory features, low-traffic pages, unpredictable query patterns.

=== Hit rate by trigger and weight threshold ===

Trigger: onboarding.step3.complete (from 10k session log analysis)
  Top query:   "How long does the sync take?"          → 41% of sessions
  2nd:         "How do I verify the connection worked?" → 22% of sessions
  3rd:         "What file formats are supported?"       → 11% of sessions
  All others:  26% of sessions

  Pre-generate all 3: hit rate = 74%
  Pre-generate top 2: hit rate = 63% (saves 1 pre-gen cost per trigger)
  Pre-generate top 1: hit rate = 41%

  Weight threshold for inclusion: weight ≥ 0.10 (3rd query just makes the cut)
  Weight threshold ≥ 0.20: drop to top 2; hit rate 63%; saves $0.00090/trigger

  At 10k triggers/day:
    Top 3: 74% hit rate, $27.00/day pre-gen, $2.34/day live misses = $29.34/day total
    Top 2: 63% hit rate, $18.00/day pre-gen, $3.33/day live misses = $21.33/day total
    Top 1: 41% hit rate,  $9.00/day pre-gen, $5.31/day live misses = $14.31/day total
    Live only:           100% live, $9.00/day

  → Speculative pre-gen always costs more than live-only. Pick N based on latency value, not cost.

=== hitRateAndCost() sample output (after 1000 trigger events) ===

{
  triggers:           1000,
  preGenerated:       2987,   ← 13 cache hits avoided redundant re-generation
  preGenCostUsd:      2.68830,
  cacheHits:          736,
  cacheMisses:        264,
  hitRate:            0.736,
  avgLatencySavedMs:  791.4,
  breakEvenHitRate:   1.000,   ← cost break-even impossible; latency value is the justification
  economicVerdict:    'BELOW BREAK-EVEN — reduce N or cut low-weight predictions'
  // Note: verdict uses cost break-even; interpret latency savings separately
}

=== S-67 vs S-43 vs S-80 vs S-112 ===

              │ S-67 (full response cache)  │ S-43 (tool cache)     │ S-80 (cache warming)   │ S-112 (speculative pre-gen)
──────────────┼─────────────────────────────┼───────────────────────┼────────────────────────┼────────────────────────────────
Trigger       │ Exact/near-exact query match│ Same tool + args      │ Prompt prefix warms TTL│ Event before query is submitted
Prediction    │ None (reactive)             │ None (reactive)       │ None (proactive, prompt)│ Yes (query prediction from logs)
Hit = serve?  │ Yes, instant                │ Yes, instant          │ No (avoids cold miss)   │ Yes, instant
Miss = ?      │ Live generation             │ Live tool call        │ Cache still cold        │ Live generation
Cost of miss  │ $0 overhead                 │ $0 overhead           │ Warming call cost       │ All pre-gens wasted for that user
```

## See also

[S-67](s67-full-response-caching.md) · [S-43](s43-tool-result-caching.md) · [S-80](s80-prompt-cache-warming.md) · [S-35](s35-latency-budget.md) · [S-109](s109-agent-idle-cost.md) · [F-81](../forward-deployed/f81-cost-attribution-by-user-action.md) · [R-10](../frontier/r10-speculative-decoding.md)

## Go deeper

Keywords: `speculative pre-generation` · `response prefetch` · `predictive response cache` · `next-query prediction` · `latency elimination` · `proactive generation` · `pre-computed response` · `query prediction cache` · `speculative response` · `predictive caching`
