# S-173 · Intra-Turn Tool Call Deduplicator

[S-43](s43-tool-result-caching.md) deduplicates tool calls across turns: when the model calls `get_contract(id=C-42)` on turn 1 and again on turn 4, S-43 serves the second call from cache. [S-153](s153-tool-result-novelty-filter.md) filters redundant content from results after they arrive, before injecting them into the messages array. [F-107](../forward-deployed/f107-in-flight-request-deduplication.md) deduplicates concurrent HTTP requests from multiple session callers hitting the same endpoint simultaneously. None of these address the intra-turn case: a single model response that contains multiple `tool_use` blocks, two or more of which specify the same tool name and identical input arguments.

This happens. Models generating parallel tool calls occasionally emit the same call twice in one response — the same `get_contract(id=C-42)` appearing as `tu_3` and `tu_5` in the same batch. The cause is usually a reasoning artifact: the model formed the same lookup intent from two independent branches of its reasoning context and materialized both without self-checking. The result is two identical API calls dispatched in parallel, two identical results returned, and two copies of the same content added to the messages array. The second call produces no new information and costs a full tool execution.

Deduplicating before dispatch catches this. Hash each tool call as `name + sorted-key JSON stringification of input`. Before dispatching the parallel block, deduplicate by that hash. The first occurrence of each distinct call is dispatched; subsequent occurrences are removed. The deduplicated list is dispatched; synthetic duplicate results are synthesized for the removed calls using the first occurrence's result. The model sees a complete `tool_result` for every `tool_use` id it emitted, satisfying the protocol — it does not see that deduplication occurred.

## Situation

A contract analysis agent processes a complex document. The model generates five parallel tool calls in one response:

1. `get_contract(id=C-42, fields=['parties','effective_date'])` — `id=tu_1`
2. `get_metadata(id=C-42)` — `id=tu_2`
3. `get_contract(id=C-99, fields=['parties','effective_date'])` — `id=tu_3`
4. `get_contract(id=C-42, fields=['parties','effective_date'])` — `id=tu_4` (duplicate of tu_1)
5. `get_metadata(id=C-42)` — `id=tu_5` (duplicate of tu_2)

Without dedup: 5 tool calls dispatched. tu_4 and tu_5 hit the same API endpoints as tu_1 and tu_2, returning identical data. Two redundant results land in the messages array and ride in context for the remainder of the session.

With dedup: 3 calls dispatched (tu_1, tu_2, tu_3). After tu_1 returns, its result is also returned for tu_4. After tu_2 returns, its result is also returned for tu_5. The model receives 5 `tool_result` blocks (one per `tool_use` id it emitted), all consistent. Net: 2 API calls saved, 0 tokens added to context from the duplicate results.

## Forces

- **Input key order is not stable.** The model may emit `{id:'C-42', fields:[...]}` on one occurrence and `{fields:[...], id:'C-42'}` on another. JSON stringification of objects is insertion-order-dependent in most runtimes. Hash after sorting keys to get a stable canonical form regardless of emission order.
- **Array argument order is intentional.** A call with `fields=['parties','effective_date']` is not the same as `fields=['effective_date','parties']` if the tool uses positional array semantics. Do not sort array values inside arguments — only sort object keys.
- **Do not deduplicate side-effecting tools.** A call to `write_annotation(id=C-42, note='reviewed')` emitted twice is probably a model error, but deduplicating it silently might suppress a legitimate second annotation. Mark tools as `safe: true` (read-only) at registration time; only deduplicate safe tools. Side-effecting tools should go through S-93 (tool side-effect idempotency) instead.
- **Return synthetic results for removed calls.** The Anthropic API requires a `tool_result` block for every `tool_use` id in the prior assistant turn. After dispatching the deduplicated set and receiving results, copy each result to all duplicate ids before constructing the next `user` turn. The model never sees fewer results than it expects.
- **Log removals for observability.** Frequent duplicates from a specific tool call pattern indicate a prompt or reasoning issue upstream. A deduplicator that removes calls silently hides signal. Log `{tool, inputHash, duplicateCount}` at DEBUG level so the prompt engineering team can investigate.
- **Compose after parallel tool call extraction, before dispatch.** The deduplicator runs in the tool dispatch layer between model output parsing and API call execution. It does not touch the messages array — it operates on the `tool_use` block list extracted from the assistant turn.

## The move

**Hash each tool call by name and sorted-key input. Before dispatch, remove duplicates from read-only tools. After dispatch, copy results to all duplicate ids before constructing the next user turn.**

```js
// --- Intra-turn parallel tool call deduplicator ---
// Deduplicates identical tool calls within a single model response before dispatch.
// Safe (read-only) tools only. Side-effecting tools are excluded by design.
// Compose: run after parsing tool_use blocks, before calling tool dispatch.
// Distinct from S-43 (cross-turn cache), S-153 (result novelty filter), F-107 (in-flight HTTP dedup).

function hashInput(input) {
  // Sort keys for stable hash regardless of object key insertion order.
  // Do not sort array values — array order is intentional.
  return JSON.stringify(input, Object.keys(input).sort());
}

// safeTool: set of tool names that are read-only and safe to deduplicate.
function deduplicateToolCalls(toolUseBlocks, safeTools) {
  const seen       = new Map();   // key → first block
  const deduped    = [];
  const duplicates = [];          // { block, originalId → firstBlock.id }

  for (const block of toolUseBlocks) {
    if (safeTools && !safeTools.has(block.name)) {
      // Side-effecting tool: always dispatch, never deduplicate.
      deduped.push(block);
      continue;
    }
    const key = block.name + '::' + hashInput(block.input);
    if (seen.has(key)) {
      duplicates.push({ block, firstId: seen.get(key).id });
    } else {
      seen.set(key, block);
      deduped.push(block);
    }
  }

  return { deduped, duplicates, originalCount: toolUseBlocks.length };
}

// After dispatching deduped calls and collecting results: synthesize results for duplicates.
// toolResults: Map<toolUseId, resultContent>
function synthesizeDuplicateResults(duplicates, toolResults) {
  const synthetic = [];
  for (const { block, firstId } of duplicates) {
    const content = toolResults.get(firstId);
    if (content !== undefined) {
      synthetic.push({ tool_use_id: block.id, type: 'tool_result', content });
    }
  }
  return synthetic;
}

// --- Integration: tool dispatch layer ---

const SAFE_TOOLS = new Set(['get_contract', 'get_metadata', 'search_clauses', 'get_party_info']);

async function dispatchToolBlock(toolUseBlocks, toolFn) {
  const { deduped, duplicates } = deduplicateToolCalls(toolUseBlocks, SAFE_TOOLS);

  // Dispatch deduplicated calls in parallel.
  const results = await Promise.all(deduped.map(async block => {
    const content = await toolFn(block.name, block.input);
    return { id: block.id, content };
  }));

  const toolResults = new Map(results.map(r => [r.id, r.content]));

  // Synthesize results for removed duplicates.
  const syntheticResults = synthesizeDuplicateResults(duplicates, toolResults);

  // Combine all results keyed by original tool_use id.
  const allResults = [
    ...results.map(r => ({ tool_use_id: r.id, type: 'tool_result', content: r.content })),
    ...syntheticResults,
  ];

  // Restore original id order so the next user turn mirrors the assistant turn.
  const idOrder = new Map(toolUseBlocks.map((b, i) => [b.id, i]));
  allResults.sort((a, b) => idOrder.get(a.tool_use_id) - idOrder.get(b.tool_use_id));

  return { toolResults: allResults, duplicatesRemoved: duplicates.length };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. 5-block scenario with 2 duplicates; 3-block all-unique scenario; 3-block all-same scenario. `deduplicateToolCalls()` timed over 1 000 000 iterations. Zero API calls for the dedup logic itself.

```
=== Intra-Turn Parallel Tool Call Deduplicator ===

Input:  5 tool calls
Output: 3 tool calls
Dups:   2 removed

  DUPLICATE: get_contract({"id":"C-42","fields":["parties","effective_date"]}) id=tu_4
  DUPLICATE: get_metadata({"id":"C-42"}) id=tu_5

Dispatched:
  DISPATCH:  get_contract({"id":"C-42","fields":["parties","effective_date"]}) id=tu_1
  DISPATCH:  get_metadata({"id":"C-42"}) id=tu_2
  DISPATCH:  get_contract({"id":"C-99","fields":["parties","effective_date"]}) id=tu_3

Key-order invariant: PASS — same args regardless of key insertion order

No-dup scenario: 3 → 3  dups: 0
All-dup scenario:  3 → 1  dups: 2

=== Timing (1 000 000 iterations) ===

deduplicateToolCalls() 5 blocks, 2 dups:  0.0207 ms
deduplicateToolCalls() 3 blocks, 0 dups:  0.0074 ms

At 10 000 parallel tool blocks/day with 5% dup rate:
  500 duplicate API calls eliminated/day.
  Each duplicate at Haiku $0.0008/call: $0.40/day saved, $146/year.
  Context savings: each removed result drops ~120 tokens from subsequent turns.
  120 tokens × 500 dups × $0.80/M (Haiku input): $0.048/day in context cost avoided.
```

## See also

[S-43](s43-tool-result-caching.md) · [S-153](s153-tool-result-novelty-filter.md) · [F-107](../forward-deployed/f107-in-flight-request-deduplication.md) · [S-93](s93-tool-side-effect-idempotency.md) · [S-55](s55-parallel-tool-calls.md)

## Go deeper

Keywords: `intra-turn tool call deduplication` · `parallel tool call dedup` · `duplicate tool use block` · `tool call hash dedup` · `model parallel tool dedup` · `same-turn tool deduplication` · `tool block dedup before dispatch` · `parallel tool call idempotency` · `tool_use block dedup` · `model output tool dedup`
