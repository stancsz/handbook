# S-180 · Cross-Layer Prompt Instruction Deduplicator

[S-58](s58-prompt-layering.md) defines the four-layer assembly order: base system prompt → operator overlay → user context → turn content. Each layer can restrict or extend the layers below it. What S-58 does not do is remove instructions from lower layers that duplicate instructions already present in higher layers.

Prompt caching (S-08) makes this gap costly. The static system prompt is sent once, cached, and read back at 0.10× input price on every subsequent call. Per-request layers — operator overlays, user context, tenant customizations — are not cached. When an instruction in an uncached layer is identical (or nearly identical) to an instruction in the cached system prompt, you pay full input price for a token sequence the model already has in cache. The cache does not deduplicate across layers; the model processes both, and you are billed for both.

The deduplicator runs at assembly time, before the layers are concatenated. It builds a normalized clause index from the cached (higher-priority) layers and then sweeps through each uncached layer, removing clauses that match against the index. Two match modes: exact (normalize and hash, 0.0266 ms per layer) and near-exact (2-gram Jaccard similarity above 0.80 threshold, 0.6143 ms per layer). Exact mode catches literal copies ("Always cite specific clauses" appearing in both the system prompt and the operator overlay). Near-exact catches paraphrases — the same behavioral directive phrased slightly differently across layers.

This is distinct from S-59 (instruction density): S-59 detects that two _different_ instructions target the same behavior and merges them into one; S-180 detects that the _same_ instruction appears twice and removes the lower-priority copy. Run S-180 first (fast, structural), then S-59 on the deduplicated result (semantic, slower).

## Situation

A multi-tenant contract review service has a 12-instruction system prompt (172 tok, cached). Each request carries a 6-instruction operator overlay (84 tok, uncached) tailored for the tenant. One instruction in the overlay is an exact copy of a system prompt instruction: "Always cite specific clauses when referencing contract terms." Two others are near-paraphrases that do not exceed the 0.80 Jaccard threshold.

Without dedup: the exact duplicate costs 16 tokens at full input price ($0.80/M) on every call. With dedup: the overlay drops to 5 instructions (68 tok); the duplicate is not billed. Over 10 000 calls/day: 160 000 tokens/day saved, $0.13/day, $47/year. In deployments where operator overlays share 5–10 instructions with the system prompt, the savings scale to $235–$470/year at the same call volume.

There is a secondary benefit: a shorter uncached overlay improves cache prefix alignment. The system prompt + shorter overlay together form a more stable prefix across tenants, increasing cache hit rates for the per-call prefix (S-08, S-80).

## Forces

- **Exact dedup is always safe; near-exact requires judgment.** An exact duplicate is provably redundant — the system prompt already contains the instruction. A near-paraphrase (Jaccard 0.82) may carry a meaningful nuance in the word choice. Set the near-exact threshold at 0.80 as a default; lower it only after reviewing what it catches on your actual layers. At 0.70 it starts removing instructions with genuine differentiation.
- **Dedup is unidirectional: lower-priority layers lose, higher-priority layers are protected.** The system prompt is never trimmed; operator overlays are trimmed against the system prompt; user context is trimmed against both. This matches S-58's precedence model.
- **Near-exact dedup adds 0.6 ms per layer per call.** At 10 000 calls/day this is 6 seconds of CPU/day — entirely negligible. If the overlay contains more than 50 clauses, profile the Jaccard scan; for very large overlays switch to vector similarity (S-76 pattern) with a smaller model.
- **The cache break-even is always positive.** Any duplicate token removed from an uncached layer saves (full_price − cache_read_price) = (1.00 − 0.10) × 0.80/M = $0.72/M tokens. Since writing the deduplicator costs nothing at inference time, the break-even is 0 duplicate tokens — any duplicate found produces net savings.
- **Run after layer validation, before concatenation.** The deduplicator assumes each layer is already well-formed (S-56 preflight check). It does not validate content; it only removes duplicates. If layers contain injected user content, run S-77 (injection hardening) before dedup to ensure the clause index is not poisoned by user-controlled text.

## The move

**Build a normalized clause index from cached layers. Before concatenating uncached layers, remove clauses that match (exact or near-exact Jaccard ≥ 0.80) against the index.**

```js
// --- Cross-layer prompt instruction deduplicator ---
// Removes instructions from uncached layers that duplicate the cached system prompt.
// Exact match: normalize + Set lookup (< 0.001 ms).
// Near-exact: 2-gram Jaccard similarity, threshold 0.80 (≈ 0.6 ms per layer).
// Run after S-77 (injection hardening), before S-56 (preflight total check).
// Compose: S-58 layer assembly → S-180 dedup → S-59 density merge → concatenate.

function normalizeClause(clause) {
  return clause.trim().toLowerCase().replace(/\s+/g, ' ').replace(/[.,;!?]+$/, '');
}

function bigrams(str) {
  const bg = new Set(), words = str.split(/\s+/);
  for (let i = 0; i < words.length - 1; i++) bg.add(words[i] + ' ' + words[i + 1]);
  return bg;
}

function jaccardSim(a, b) {
  const bgA = bigrams(a), bgB = bigrams(b);
  let inter = 0;
  for (const g of bgA) { if (bgB.has(g)) inter++; }
  const union = bgA.size + bgB.size - inter;
  return union === 0 ? 1 : inter / union;
}

const NEAR_EXACT_THRESHOLD = 0.80;

function buildCachedClauseIndex(cachedLayerText) {
  const norms = cachedLayerText.split('\n')
    .map(l => l.trim()).filter(Boolean)
    .map(normalizeClause);
  return new Set(norms);
}

function deduplicateLayer(layerText, cachedIndex, opts) {
  opts = opts || {};
  const nearExact = opts.nearExact !== false;
  const cachedNorms = [...cachedIndex];
  const clauses = layerText.split('\n').map(l => l.trim()).filter(Boolean);
  const kept = [], removed = [];

  for (const clause of clauses) {
    const norm = normalizeClause(clause);

    if (cachedIndex.has(norm)) {
      removed.push({ clause, reason: 'EXACT_DUPLICATE' });
      continue;
    }
    if (nearExact) {
      const maxSim = Math.max(...cachedNorms.map(cn => jaccardSim(norm, cn)));
      if (maxSim >= NEAR_EXACT_THRESHOLD) {
        removed.push({ clause, reason: 'NEAR_DUPLICATE', similarity: maxSim.toFixed(3) });
        continue;
      }
    }
    kept.push(clause);
  }

  return { kept, removed, keptCount: kept.length, removedCount: removed.length };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Cached system prompt: 12 instructions, 172 tok. Uncached operator overlay: 6 instructions, 84 tok. Uncached user context: 2 instructions, 25 tok. Timed over 100 000 iterations.

```
=== Cross-Layer Prompt Instruction Deduplicator ===

System prompt (cached):      12 instructions  172 tok
Operator overlay (uncached):  6 instructions   84 tok
User context (uncached):      2 instructions   25 tok

--- Operator overlay dedup ---
  REMOVED (EXACT_DUPLICATE) "Always cite specific clauses when referencing contract terms."
  KEPT   "Respond only in the language of the contract."
  KEPT   "Do not fabricate clause content; always quote verbatim."
  KEPT   "Return JSON with camelCase keys for this tenant."
  KEPT   "Apply tenant-specific field aliases: contract_value → dealAmount."
  KEPT   "Route unrecognized contract types to human review queue."
  6 instructions → 5 kept, 1 removed

--- User context dedup ---
  KEPT   "Return structured JSON for extraction."       ← Jaccard 0.70 vs cached — below 0.80
  KEPT   "Focus on payment and term clause fields for this analysis."
  2 instructions → 2 kept, 0 removed

=== Cost model (10 000 calls/day, Haiku $0.80/M input) ===
Tokens saved per call (1 exact duplicate removed): 16 tok
Daily savings:  0.160M tokens/day  $0.13/day  ($47/year)
(saved tokens were in uncached overlay — billed at full $0.80/M, not cache-read $0.08/M)
At 5-10 duplicates/call (common in shared-system-prompt tenants): $235–$470/year

=== Compose chain ===
S-58 layer assembly → S-180 dedup → S-59 density merge → concatenate → S-56 preflight check

=== Timing (100 000 iterations, 6-clause overlay vs 12-clause cached index) ===
deduplicateLayer() exact only:              0.0266 ms
deduplicateLayer() exact + Jaccard bigrams: 0.6143 ms
Negligible vs API call latency (>200 ms). Run once per request at assembly time.
```

## See also

[S-58](s58-prompt-layering.md) · [S-59](s59-instruction-density.md) · [S-08](s08-prompt-caching.md) · [S-77](s77-system-prompt-injection-hardening.md) · [S-80](s80-prompt-cache-warming.md)

## Go deeper

Keywords: `prompt instruction deduplication` · `cross-layer prompt dedup` · `cached layer instruction overlap` · `prompt assembly deduplication` · `uncached overlay token savings` · `prompt layer dedup` · `instruction duplicate removal prompt` · `multi-tenant prompt dedup` · `prompt caching token optimization` · `Jaccard prompt instruction similarity`
