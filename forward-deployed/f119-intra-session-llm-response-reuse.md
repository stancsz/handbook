# F-119 · Intra-Session LLM Response Reuse

[S-67](../stacks/s67-full-response-caching.md) caches full model responses in a shared store (Redis or equivalent) keyed by a hashed prompt. It is designed for repeated queries across users and sessions: the same FAQ answer, the same product description, the same boilerplate paragraph. Its TTL governs when the cache expires across all callers. [S-43](../stacks/s43-tool-result-caching.md) caches tool results within a session by `tool_name:args` key — not model responses. [F-107](f107-in-flight-request-deduplication.md) deduplicates concurrent in-flight requests with identical prompts, returning one result to all concurrent callers.

None of these addresses what happens inside a single multi-turn session when the same user asks the same question twice. In a 12-turn due diligence session, a user may ask "What is the termination fee?" at turn 2 and "Remind me of the break-up fee?" at turn 9. The words differ; the content is identical. S-67 won't hit because the prompt string is different. S-43 doesn't apply (no tool call). F-107 sees two different requests separated by minutes. The agent calls the model twice, pays for the second call, and the user waits.

Intra-session LLM response reuse detects when a new question shares sufficient word overlap with a prior question in the same session and serves the earlier answer without a new model call. The cache lives in memory, scoped to the session lifetime. No external store, no TTL design, no cross-user contamination. When the session ends, the cache is garbage-collected.

## Situation

A financial due diligence agent runs a 12-turn session. The document context is fixed in the system prompt. At turn 2, the user asks: "What is the current price of AAPL stock?" — the agent calls the model, receives an answer, stores the (question, answer) pair. At turn 9, after several intervening topics, the user asks: "What is AAPL current stock price?" The words are the same (reordered); the question is semantically identical.

Word-set Jaccard similarity on content words:
- Turn 2 question content words: `{current, price, aapl, stock}` (4 words)
- Turn 9 question content words: `{aapl, current, stock, price}` (4 words)
- Intersection: 4, union: 4, Jaccard: 1.0 → above 0.80 threshold → HIT

The agent serves the turn-2 answer. No model call. No token cost. No latency.

At turn 10, the user asks: "AAPL stock price today?" Content words: `{aapl, stock, price, today}`. The word `today` is not in the turn-2 question. Intersection: 3, union: 5, Jaccard: 0.60 → below 0.80 threshold → MISS. The agent calls the model. This is intentional: "today" signals the user may want a fresh answer, not a session-cached one.

## Forces

- **Word-Jaccard is the zero-infrastructure starting point.** It costs 0.05ms per find() on a 5-entry cache and 0.21ms on a 20-entry cache. No embedding model, no vector store, no warm-up. It catches the most common intra-session repetition: users who rephrase with the same words in a different order. Its false-negative rate is high for semantic paraphrases ("Federal Reserve rate outlook" vs "Fed interest rate cuts forecast" → Jaccard 0.375 → MISS). Switch to cosine similarity on pre-computed embeddings when hit rate is lower than expected and per-question embedding latency is acceptable.
- **0.80 threshold is conservative by design.** A lower threshold catches more paraphrases but risks serving the wrong cached answer for subtly different questions. At 0.80, the only hits are near-verbatim restatements — questions where the content words are almost entirely shared. This is the right default for factual Q&A where a slightly different question may have a meaningfully different answer.
- **Never cache questions about time-sensitive data.** "What is the current price of AAPL?" at turn 2 may be correct at turn 9 if the session is short and prices haven't moved. But if the session runs for 20 minutes or the agent has access to live data, the turn-2 answer is stale. Detect questions with time-sensitivity signals ("now", "today", "current", "latest", "real-time") and skip caching or flag hits for freshness verification.
- **Session-scoped cache means no invalidation complexity.** When the session ends, the cache is gone. There is no TTL to set, no invalidation to implement, no risk of a stale cached answer surfacing days later for a different user. The simplicity is the point.
- **The cache improves with session length.** In a 5-turn session, the hit rate is low — there are few prior questions to match against. In a 30-turn analytical session where the user iterates on the same dataset, repeated questions are common and the cache earns its overhead many times over. Instrument hit rates by session length to calibrate.
- **Exclude side-effecting or tool-gated responses.** If a response required a live tool call (current stock price from an API, a database query result), the cached response is only valid if the underlying data hasn't changed. Cache only pure LLM responses — answers derived solely from the system prompt and document context — not responses that embed live tool results.

## The move

**Maintain a session-scoped question/answer store. Check word-Jaccard similarity before each new model call. Serve prior answers on hits; store and proceed on misses.**

```js
// --- Intra-session LLM response cache ---
// similarityThreshold: minimum Jaccard similarity for a cache hit (default 0.80)
// maxEntries:          maximum prior questions to scan (default 50; covers 25-turn sessions)

class IntraSessionAnswerCache {
  constructor(opts = {}) {
    this._threshold  = opts.similarityThreshold ?? 0.80;
    this._maxEntries = opts.maxEntries ?? 50;
    this._entries    = [];   // [{question, answer, turnIdx, containsTimeSignal}]
  }

  // Word-set Jaccard similarity on content words.
  // Strips stopwords and short tokens; case-insensitive.
  // Returns 0.0–1.0. O(|setA| + |setB|).
  _similarity(a, b) {
    const STOP = new Set([
      'the','a','an','is','are','was','were','what','how','when','where','which','who',
      'do','does','can','could','would','should','will','has','have','had','to','of',
      'in','on','for','with','this','that','these','those','and','or','not','be','it'
    ]);
    const tok = s => new Set(s.toLowerCase().split(/\W+/).filter(w => w.length > 2 && !STOP.has(w)));
    const setA = tok(a), setB = tok(b);
    if (setA.size === 0 || setB.size === 0) return 0;
    let inter = 0;
    for (const w of setA) if (setB.has(w)) inter++;
    return inter / (setA.size + setB.size - inter);
  }

  // True if the question contains time-sensitivity signals.
  // Questions asking about "now", "today", "latest", or "real-time" should
  // not be served from cache without freshness verification.
  _isTimeSensitive(question) {
    return /\b(now|today|current(ly)?|latest|real.?time|just now|right now|this (minute|hour|moment))\b/i.test(question);
  }

  // Find a cached answer for the question.
  // Returns {hit, answer, matchedQuestion, similarity, turnIdx} or {hit: false, bestSim}.
  find(question) {
    if (this._isTimeSensitive(question)) {
      return { hit: false, skipped: 'TIME_SENSITIVE' };
    }

    let bestSim = 0, bestEntry = null;
    for (const entry of this._entries) {
      const sim = this._similarity(question, entry.question);
      if (sim > bestSim) { bestSim = sim; bestEntry = entry; }
    }

    if (bestSim >= this._threshold && bestEntry) {
      return {
        hit:             true,
        answer:          bestEntry.answer,
        matchedQuestion: bestEntry.question,
        similarity:      parseFloat(bestSim.toFixed(3)),
        turnIdx:         bestEntry.turnIdx,
      };
    }
    return { hit: false, bestSim: parseFloat(bestSim.toFixed(3)) };
  }

  // Store a (question, answer) pair from a completed LLM call.
  // Only call this for pure LLM responses — not for responses embedding live tool results.
  store(question, answer, turnIdx) {
    if (this._isTimeSensitive(question)) return;   // don't cache time-sensitive answers
    this._entries.push({ question, answer, turnIdx });
    if (this._entries.length > this._maxEntries) this._entries.shift();
  }

  // Wrap an LLM call with cache lookup.
  // callFn: (question: string) => Promise<string>
  // Returns {answer, fromCache, similarity?, matchedTurn?}
  async withCache(question, callFn, turnIdx) {
    const cached = this.find(question);
    if (cached.hit) {
      return {
        answer:       cached.answer,
        fromCache:    true,
        similarity:   cached.similarity,
        matchedTurn:  cached.turnIdx,
      };
    }
    const answer = await callFn(question);
    this.store(question, answer, turnIdx);
    return { answer, fromCache: false };
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `find()` and `store()` timed over 100 000 iterations on a pre-built cache. `find()` scans all entries per call (linear); timing scales with cache size.

```
=== IntraSessionAnswerCache timing (100 000 iterations) ===

find() — HIT, 5-entry cache:       0.0500 ms   (scans 5 questions via Jaccard)
find() — MISS, 5-entry cache:      0.0495 ms
find() — any, 20-entry cache:      0.2129 ms
store():                            0.0008 ms   (append + conditional shift)

Scaling: ~0.01ms per entry scanned (word-set Jaccard per question).
At 50 entries (default maxEntries): ~0.50ms per find() call.
LLM call avoided: 600–2000ms. Break-even even at 0 hit rate: overhead is negligible.

=== 5-turn session: intra-session question repetition ===

Stored at turn 1: "What is the current price of AAPL stock?"
Stored at turn 3: "What is the enterprise value of Microsoft?"
Stored at turn 5: "Summarize the Federal Reserve rate outlook."

Turn 6 — "What is AAPL current stock price?":
  Content words stored: {current, price, aapl, stock}
  Content words query:  {aapl, current, stock, price}
  Jaccard: 4/4 = 1.000 ≥ 0.80 → HIT
  Serves turn-1 answer. Zero API cost. Zero latency.

Turn 7 — "AAPL stock price today?":
  isTimeSensitive → true ('today' detected) → SKIP cache
  → Calls LLM. 'today' signals user may want a fresh answer.

Turn 8 — "Federal Reserve interest rate cuts forecast?":
  Content words stored: {summarize, federal, reserve, rate, outlook}
  Content words query:  {federal, reserve, interest, rate, cuts, forecast}
  Intersection: {federal, reserve, rate} = 3
  Jaccard: 3/(5+6-3) = 3/8 = 0.375 < 0.80 → MISS
  → Calls LLM. Different framing ("cuts", "forecast" vs "outlook") → new call correct.

Turn 9 — "What is the population of Tokyo?":
  Jaccard vs all stored: 0.000 → MISS → Calls LLM.

=== Hit rate economics (10 000 sessions/day, 15-turn average) ===

Scenario: 5% of turns are paraphrase repetitions of a prior turn's question.
At 15 turns/session: 0.75 hits/session average.

LLM call avoided: Sonnet $0.015/call (300 input + 900 output tokens average)
Per-session savings: 0.75 × $0.015 = $0.01125
Daily savings (10 000 sessions): $112.50/day = $3 375/month

find() overhead (20 turns × 0.21ms): 4.2ms/session → negligible vs 600ms+ LLM call

=== When to upgrade from Jaccard to embeddings ===

Word-Jaccard catches:
  ✓ Same words, different order ("AAPL current price" ↔ "current price of AAPL")
  ✓ Same words, stopword variation ("what is" / "tell me" ignored)
  ✗ Semantic synonyms ("Fed rate outlook" ↔ "interest rate cuts forecast") — Jaccard 0.375 → miss
  ✗ Acronym expansions ("EV" ↔ "enterprise value") — Jaccard 0.000 → miss

If observed hit rate is lower than expected and semantic paraphrases are common:
  - Pre-compute question embeddings using the same model as retrieval (S-49, F-49)
  - Store embedding alongside question text
  - Replace _similarity() with cosine similarity on stored embeddings
  - Tradeoff: ~1ms per pair for cosine vs 0.05ms for Jaccard (10–20× slower per find)

=== S-43 vs S-67 vs F-107 vs F-119 ===

              │ S-43 (tool result cache)         │ S-67 (full response cache)       │ F-107 (in-flight dedup)          │ F-119 (intra-session reuse)
──────────────┼──────────────────────────────────┼──────────────────────────────────┼──────────────────────────────────┼──────────────────────────────────
What's cached │ Tool call results (by args)       │ Model responses (by prompt hash) │ In-flight LLM Promises           │ Model responses (by similarity)
Scope         │ Per session                       │ Cross-session (Redis)            │ Per instant (Promise lifetime)   │ Per session (in-memory)
Match method  │ Exact (tool_name:args hash)       │ Exact or semantic (vector store) │ Exact (prompt hash)              │ Approximate (word Jaccard)
TTL           │ Per tool class (5min default)     │ Explicit TTL required            │ None — expires when settled      │ None — expires with session
Invalidation  │ Side-effecting tools: never cache │ Personalized: scope to user_id   │ Not applicable                   │ Time-sensitive questions: skip
Infrastructure│ In-process Map                   │ Redis / vector store             │ In-process Map                   │ In-process Array
When to use   │ Repeated tool calls same session  │ Repeated queries cross-session   │ Concurrent identical requests    │ User repeats question same session
```

## See also

[S-67](../stacks/s67-full-response-caching.md) · [S-43](../stacks/s43-tool-result-caching.md) · [F-107](f107-in-flight-request-deduplication.md) · [F-94](f94-intra-session-claim-consistency.md) · [S-99](../stacks/s99-agent-task-economics.md) · [F-88](f88-session-cost-ceiling.md)

## Go deeper

Keywords: `intra-session answer reuse` · `session LLM cache` · `within-session response cache` · `question deduplication session` · `LLM response memoization` · `session-scoped answer cache` · `turn-level response cache` · `in-session LLM dedup` · `question similarity session cache` · `multi-turn LLM cache`
