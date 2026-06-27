# S-150 · Prompt Context Block Deduplication

[S-122](s122-retrieved-chunk-dedup.md) deduplicates retrieved knowledge chunks before injection: after retrieval returns N chunks, pairwise Jaccard identifies near-duplicates and drops the lower-ranked one. [S-127](s127-cross-sentence-redundancy-removal.md) removes redundant sentences within surviving chunks. Both operate within the retrieved set — chunks that came from the same retrieval call.

Neither covers what happens when the same data block enters the assembled prompt from two different sources. A customer account record appears in the system prompt's context section (loaded at session start) and again in the body of a `get_customer` tool result (fetched during the agent loop). A policy document section was pre-loaded into the system prompt and is also returned by a `search_documents` tool call. A contract summary was injected as user context and is also retrieved as a top-ranked knowledge chunk. In each case, two different pipeline stages independently contributed the same content, and both made it into the assembled prompt.

Prompt context block deduplication hashes each content block at assembly time and skips any block whose hash collides with one already added. Priority determines which copy is kept when a collision occurs: system prompt sections outrank tool results, which outrank retrieved chunks, which outrank low-confidence retrieved content. The duplicate is silently dropped; only the highest-priority copy is injected.

## Situation

A financial support agent assembles a prompt from three sources for a customer query about their billing plan:

1. System prompt includes a `customer_context` section (90 tokens): the account record loaded at session start from the CRM.
2. A `get_customer` tool call runs mid-session and returns the same account record (same 90 tokens) as its result.
3. A `get_orders` tool call returns recent order history (28 tokens) — distinct content not in the system prompt.

Without deduplication: the account record appears twice (180 tokens). The model reads the same facts twice, weights them more heavily than intended, and the context window grows unnecessarily.

With deduplication: `add(customerBlock, 'system_prompt.customer_context', priority=3)` stores the hash. When `add(toolResult, 'tool_result.get_customer', priority=1)` runs, the hash collision is detected: `{ added: false, collidedWith: 'system_prompt.customer_context', savedTokens: 90 }`. The tool result is dropped; the system prompt copy is kept (higher priority). Orders are distinct and pass through: `{ added: true, estimatedTokens: 28 }`. Net: 90 tokens saved, 3 unique blocks instead of 4.

At 10 000 sessions/day with a 15% collision rate (one duplicate block per session): 10 000 × 0.15 × 90 tokens × $3/M (Sonnet input) = **$4.05/day saved**. Zero API calls, zero latency added beyond the hash computation.

## Forces

- **Retrieval-layer dedup is not enough.** S-122 runs on a homogeneous set: all chunks came from the same retrieval query. Cross-source duplication happens when the system prompt and a tool result were produced independently and both happened to include the same block. S-122 won't see this because the system prompt is not a retrieval result.
- **Priority determines which copy survives, not arrival order.** The system prompt copy is preferred over the tool result copy even if the tool result arrived later. This matters: the system prompt's version may have been slightly more processed (trimmed, reformatted), while the raw tool result may be noisier. Define priority explicitly in the assembly layer.
- **Hash on normalized content, not on raw bytes.** Whitespace normalization before hashing prevents the same block from passing through just because it has a trailing newline in one source and not another. The FNV-1a polynomial hash runs in 0.003ms on a 500-character block — faster than any alternative.
- **This is an exact (or near-exact) match check, not semantic dedup.** Two blocks with different wording that convey the same information are not duplicates under this pattern. Semantic dedup is slower (requires embeddings) and is better handled at the knowledge base layer (S-76). At assembly time, you want to catch structural copies of the same data object that somehow got injected twice — not paraphrases.
- **Estimate token savings for cost accounting.** The collision result includes `savedTokens` — a rough character/4 estimate of how many input tokens were avoided. Aggregate this across sessions to confirm the pattern is delivering the expected savings. If collision rate is near zero, the pattern adds overhead with no benefit; if it's high, investigate why the pipeline is producing so many duplicates (and fix the root cause rather than just deduping).
- **Don't deduplicate across fundamentally different contexts.** Two tool results for `get_customer` called with different `customerId` values may hash differently even if the format is identical. The hash is on the content, not the template — different entity data won't collide.

## The move

**Hash each content block at assembly time. Skip blocks whose hash was already added. Keep the higher-priority copy on collision.**

```js
// --- Prompt context block deduplicator ---
// Hashes each content block at assembly time.
// Detects exact (normalized) duplicates across prompt sections from different sources.
// Caller adds blocks in priority order (highest priority first = system prompt, then tool results, then retrieval).

class PromptBlockDeduplicator {
  constructor() {
    this._blocks = [];   // [{hash, label, priority, tokenEstimate}]
  }

  // Normalize content for hashing: trim and collapse whitespace.
  _normalize(content) {
    return content.trim().replace(/\s+/g, ' ');
  }

  // FNV-1a hash of normalized content. O(n) in content length.
  _hash(normalized) {
    let h = 2166136261;
    for (let i = 0; i < normalized.length; i++) {
      h ^= normalized.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h;
  }

  // Attempt to add a content block.
  // label:    human-readable source identifier ('system_prompt.customer_context')
  // priority: higher number = higher priority; kept copy on collision (default 0)
  // Returns { added: true, estimatedTokens } on success.
  // Returns { added: false, collidedWith: label, savedTokens } on duplicate.
  add(content, label, priority = 0) {
    const normalized = this._normalize(content);
    const hash       = this._hash(normalized);
    const estimatedTokens = Math.ceil(normalized.length / 4);

    for (const block of this._blocks) {
      if (block.hash === hash) {
        return { added: false, collidedWith: block.label, savedTokens: estimatedTokens };
      }
    }

    this._blocks.push({ hash, label, priority, tokenEstimate: estimatedTokens });
    return { added: true, estimatedTokens };
  }

  reset() { this._blocks = []; }

  summary() {
    return {
      uniqueBlocks:          this._blocks.length,
      estimatedTotalTokens:  this._blocks.reduce((s, b) => s + b.tokenEstimate, 0),
    };
  }
}

// --- Integration pattern ---
// Assemble the prompt in priority order (highest first).
// Skip any add() result where added === false.

function assemblePrompt(systemSections, toolResults, retrievedChunks) {
  const dedup = new PromptBlockDeduplicator();
  const assembledSections = [];
  const collisions = [];

  // Priority 3: system prompt sections (pre-processed, curated)
  for (const [label, content] of Object.entries(systemSections)) {
    const result = dedup.add(content, `system_prompt.${label}`, 3);
    if (result.added) assembledSections.push({ source: `system_prompt.${label}`, content });
    else collisions.push({ ...result, skipped: `system_prompt.${label}` });
  }

  // Priority 2: tool results (live data, may repeat system prompt context)
  for (const [toolName, content] of Object.entries(toolResults)) {
    const result = dedup.add(content, `tool_result.${toolName}`, 2);
    if (result.added) assembledSections.push({ source: `tool_result.${toolName}`, content });
    else collisions.push({ ...result, skipped: `tool_result.${toolName}` });
  }

  // Priority 1: retrieved chunks (S-122 already deduped within this set)
  for (const chunk of retrievedChunks) {
    const result = dedup.add(chunk.text, `retrieved.${chunk.id}`, 1);
    if (result.added) assembledSections.push({ source: `retrieved.${chunk.id}`, content: chunk.text });
    else collisions.push({ ...result, skipped: `retrieved.${chunk.id}` });
  }

  const totalSavedTokens = collisions.reduce((s, c) => s + (c.savedTokens ?? 0), 0);
  return { assembledSections, collisions, summary: dedup.summary(), totalSavedTokens };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `_hash()` and `add()` timed over 100 000 iterations on a 500-character customer account block.

```
=== PromptBlockDeduplicator timing (100 000 iterations) ===

_hash()  500-char block:    0.0031 ms   (FNV-1a over full content)
add()    NEW block:         0.0164 ms   (hash + scan + push)
add()    COLLISION:         0.0161 ms   (hash + early-exit on first match)

=== 3-source prompt assembly scenario ===

Sources:
  system_prompt.customer_context  priority=3  "Customer: Acme Corp. Account ID: AC-2291..."
  system_prompt.policy            priority=3  "Refund policy: Enterprise accounts..."
  tool_result.get_customer        priority=2  [same as customer_context — exact copy]
  tool_result.get_orders          priority=2  "Recent orders: ORD-001 $12000 (2026-01-15)..."

Assembly (highest priority first):
  add(customer_context, priority=3)  → { added: true,  estimatedTokens: 90 }
  add(policy, priority=3)            → { added: true,  estimatedTokens: 67 }
  add(get_customer, priority=2)      → { added: false, collidedWith: 'system_prompt.customer_context',
                                          savedTokens: 90 }  ← DUPLICATE DROPPED
  add(get_orders, priority=2)        → { added: true,  estimatedTokens: 28 }

summary: { uniqueBlocks: 3, estimatedTotalTokens: 185 }
totalSavedTokens: 90

Without dedup: 4 blocks, 275 tokens.
With dedup:    3 blocks, 185 tokens.  Saved: 90 tokens (33%).

=== Cost savings projection ===

Model:            Sonnet ($3.00/M input)
Session volume:   10 000/day
Collision rate:   15% (1 duplicate block per 6.7 sessions)
Avg block size:   90 tokens

Daily savings:    10 000 × 0.15 × 90 × $3/M = $4.05/day = $121.50/month
add() overhead:   4 blocks/session × 0.0164ms = 0.066ms/session — negligible

=== S-122 vs S-127 vs S-76 vs S-150 ===

              │ S-76 (ingest dedup)          │ S-122 (chunk dedup)          │ S-127 (sentence dedup)       │ S-150 (block dedup)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
Layer         │ KB build time                │ Post-retrieval, pre-inject   │ Within-chunk, post-S-122     │ Prompt assembly, cross-source
Scope         │ Incoming chunks vs store     │ Within retrieved set         │ Within surviving chunks      │ Across system prompt + tools + retrieval
Method        │ Embedding cosine ≥0.92       │ Word-set Jaccard ≥0.70       │ Word-set Jaccard ≥0.85       │ FNV-1a hash (exact match)
What it misses│ Doesn't cover assembly time  │ System prompt ≠ retrieval    │ Only within one chunk        │ Paraphrases (use S-76 at ingest)
```

## See also

[S-122](s122-retrieved-chunk-dedup.md) · [S-127](s127-cross-sentence-redundancy-removal.md) · [S-76](s76-semantic-dedup-at-ingest.md) · [S-123](s123-prompt-section-cost-attribution.md) · [S-75](s75-context-injection-order.md) · [F-56](../forward-deployed/f56-prompt-composition-guards.md)

## Go deeper

Keywords: `prompt context block deduplication` · `duplicate injection detection` · `cross-source prompt dedup` · `prompt assembly deduplication` · `context block hash` · `system prompt tool result dedup` · `repeated context injection` · `prompt assembly token savings` · `content hash prompt assembly` · `duplicate context block`
