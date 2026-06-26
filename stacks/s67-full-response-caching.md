# S-67 · Full Response Caching

[S-08](s08-prompt-caching.md) caches the prompt prefix inside the model API. [S-43](s43-tool-result-caching.md) caches tool results within a session. Full response caching is the third layer: for a given prompt, store the model's complete output and return it directly on the next identical (or near-identical) query, skipping inference entirely. At 30% repeat-query rates, this cuts inference calls by nearly a third at zero cost to answer quality.

## Situation

A product FAQ bot handles 10 000 queries/day. Log analysis shows ~3 000 are exact or near-exact repeats: "How do I cancel my subscription?", "cancel subscription", "how to cancel?". Each pays full inference: ~141 output tokens at $15.00/M = $0.0021/call. Caching the canonical response and returning it on repeats saves $200/month at no quality cost — the cached answer is at least as good as re-running inference.

## Forces

- **Exact-match caching is simple and safe but incomplete.** Hash the canonicalized prompt. A cache hit is guaranteed to be identical to the original call. But "How do I cancel?" and "How can I cancel?" miss each other despite being the same question.
- **Semantic caching catches near-duplicates but adds cost.** Embed the prompt (~$0.00002/call), find the nearest cached neighbor, threshold-gate at ≥0.92. At that threshold, false-positive rate is low. But every call now pays the embedding cost — only worthwhile when exact-match hit rate is below ~15%.
- **Never cache non-deterministic or personalized responses.** Tool call outputs, real-time data, user-specific answers, and truncated responses (`stop_reason: max_tokens`) must not be cached cross-request. Cache only responses that are correct for any user at any time.
- **Cache poisoning is worse than a cache miss.** A wrong answer cached for 24 hours is served to every user who asks the same question for 24 hours. Verify response quality before caching, or accept the natural quality of your prompts and system — but understand the amplification risk.
- **TTL must match content staleness.** Product FAQs: 24h. Prices or schedules: 0 (don't cache). API documentation: 12h.
- **Canonical normalization is not optional.** Without it, "cancel subscription" and "Cancel Subscription " are different cache keys. Strip extra whitespace, lowercase, and trim before hashing.

## The move

**Hash the canonicalized prompt. Check cache before calling the model. Cache the response if eligible. Add semantic caching only when exact-match hit rate is too low to justify the complexity.**

**Exact-match response cache:**

```js
const crypto = require('crypto');

const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24h
const responseCache = new Map(); // replace with Redis in production

function canonicalize(text) {
  return text.trim().toLowerCase().replace(/\s+/g, ' ');
}

function cacheKey(systemPrompt, userPrompt, model) {
  const raw = `${model}||${canonicalize(systemPrompt)}||${canonicalize(userPrompt)}`;
  return crypto.createHash('sha256').update(raw).digest('hex');
}

function isCacheEligible(response) {
  if (response.stop_reason !== 'end_turn') return false;
  if (response.content.some(b => b.type === 'tool_use')) return false;
  return true;
}

async function cachedCall(client, systemPrompt, userPrompt, model = 'claude-sonnet-4-6') {
  const key = cacheKey(systemPrompt, userPrompt, model);
  const hit = responseCache.get(key);

  if (hit && Date.now() - hit.ts < CACHE_TTL_MS) {
    return { ...hit.response, _fromCache: true };
  }

  const response = await client.messages.create({
    model,
    max_tokens: 1024,
    system: systemPrompt,
    messages: [{ role: 'user', content: userPrompt }],
  });

  if (isCacheEligible(response)) {
    responseCache.set(key, { response, ts: Date.now() });
  }

  return response;
}
```

**Semantic caching layer (add when exact-match hit rate < 15%):**

```js
async function semanticCachedCall(embedClient, client, systemPrompt, userPrompt, model) {
  const embedding = await embedClient.embeddings.create({
    model: 'text-embedding-3-small',
    input: canonicalize(userPrompt),
  });
  const vec = embedding.data[0].embedding;

  const nearest = findNearest(vec, semanticIndex); // {key, score} from your vector store
  if (nearest && nearest.score >= 0.92) {
    const entry = responseCache.get(nearest.key);
    if (entry && Date.now() - entry.ts < CACHE_TTL_MS) {
      return { ...entry.response, _fromCache: true, _semanticScore: nearest.score };
    }
  }

  return cachedCall(client, systemPrompt, userPrompt, model);
}
```

**Cache eligibility table:**

| Condition | Cache? |
|---|---|
| `stop_reason: end_turn`, no tool calls | Yes |
| Contains `tool_use` blocks | No — tool results may be stale |
| Contains real-time data (price, date, inventory) | No |
| Personalized (name, account ID, session details) | No, or scope key to `user_id` |
| `stop_reason: max_tokens` | No — response is truncated |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `crypto` (built-in), `gpt-tokenizer` (cl100k). Inference prices: $3.00/M input, $15.00/M output (claude-sonnet-4-6). Embedding price: $0.02/M tokens (text-embedding-3-small).

```
=== Hash computation overhead ===
$ node -e "
const crypto = require('crypto');
const prompt = 'How do I cancel my subscription?';
const N = 100000;
const t0 = performance.now();
for (let i = 0; i < N; i++) crypto.createHash('sha256').update(prompt).digest('hex');
const t1 = performance.now();
console.log('Per hash:', ((t1-t0)/N).toFixed(4), 'ms');
"
Per hash: 0.0043 ms

Hash check before every call costs <1ms — negligible vs inference latency.

=== Token measurement (27-tok system prompt, 7-tok query, 141-tok response) ===

System prompt: 27 tok  "You are a helpful customer support agent..."
User query:     7 tok  "How do I cancel my subscription?"
Response:     141 tok  (step-by-step cancellation instructions)

=== Savings at 10k queries/day, 30% exact-match hit rate ===

Daily cache hits:         3 000
Input savings/day:        3 000 × (27+7) tok × $3.00/M  = $0.31/day
Output savings/day:       3 000 × 141 tok   × $15.00/M  = $6.34/day
Total savings/day:        $6.65
Monthly savings:          $200/month

=== Hit rate vs monthly savings ===

Hit rate    Monthly savings
  5%        $33/month
 10%        $67/month
 20%        $133/month
 30%        $200/month
 50%        $333/month

=== Semantic caching overhead (text-embedding-3-small) ===

Cost/query:   10 000 × $0.00002 = $0.20/day = $6/month
Break-even:   semantic caching earns its cost at ~3% incremental hit improvement
              (3% × $6.65/day ≈ $0.20/day)

Redis for 10 000 cached entries (avg 2 KB each): 20 MB → fits in free tier
```

## See also

[S-08](s08-prompt-caching.md) · [S-43](s43-tool-result-caching.md) · [S-60](s60-prompt-cache-invalidation.md) · [S-35](s35-latency-budget.md) · [S-17](s17-embeddings.md) · [F-08](../forward-deployed/f08-agent-cost-control.md)

## Go deeper

Keywords: `response caching` · `semantic caching` · `exact match cache` · `prompt hash` · `cache TTL` · `inference cache` · `query deduplication` · `cache eligibility` · `cache key design` · `FAQ cache`
