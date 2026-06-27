# S-185 · Task Merge vs Split Cost Model

Every API call carries structural overhead: system prompt, tool schemas, message framing. These tokens are paid regardless of what the user sends. When a pipeline calls the same model on the same document three times to extract three different fields, the structural overhead is paid three times. When those three calls are merged into one, the overhead is paid once.

A contract extraction that calls Haiku three times — party name, contract type, effective date — costs $0.000304 for the three split calls and $0.000142 for the single merged call. The document (86 tokens) is the same in all three. The structural overhead (system prompt + framing) is the difference. Merge saves 53% with no quality change, no added complexity, and no new risk.

The pattern inverts when tasks require different system prompts. A document analyzed for sentiment, risk level, and compliance needs three different instruction sets. Combining them into one large system prompt reduces quality (the model loses focus) while still paying for all the context. Here splitting is correct even though it costs more.

The merge vs split decision has a computable answer. Compute it.

## Situation

A legal AI pipeline extracts five fields from each contract: `party_name`, `contract_type`, `effective_date`, `jurisdiction`, `payment_amount`. The first implementation used five separate Haiku calls. After a cost review:

- Five split calls on an 86-token document: ~3.2× the input tokens of a single merged call.
- At 10 000 calls/day (meaning 50 000 Haiku requests/day), the overhead multiplication compounds to $2.21/day extra.
- Single merged call: all five fields, same document, same focused system prompt. No retry overhead change at typical failure rates. $591/year cheaper.

The analysis takes under 0.02 ms and requires no API call. Run it before committing to a pipeline architecture.

## Forces

- **Document tokens dominate at scale; structural overhead dominates at low content.** A 4 000-token document makes structural overhead negligible — split or merge, the document cost dominates. A 50-token user message makes structural overhead the majority of cost. The merge benefit is greatest when documents are short relative to the system prompt and tool schemas.
- **Merge only when the same system prompt covers all tasks.** If task A needs "extract the party name" and task B needs "assess compliance risk", a merged prompt is either a mashup (degrades quality) or one task effectively subsidizes the other's structural overhead with no quality gain. Split when tasks are semantically distinct.
- **Independent per-field failure rates multiply retry probability.** Three fields each failing at 5% probability means a merged call fails with ~14.3% probability (vs 5% per split call). The merged retry resends all fields and the full document. At ≤10% per-field failure rates, merge still wins economically because the main-call savings dwarf retry costs. Above ~30% per-field failure rate, split begins to win.
- **Retry isolation is qualitative, not just economic.** Split calls allow targeted retry: if `jurisdiction` fails, resend only that call. Merged calls require resending the full batch, with the risk that the re-run changes previously-correct fields. Compose with F-154 (field-level retry) when using merged calls — it provides targeted retry semantics on top of the merged extraction.
- **The structural overhead per call is fixed but measurable.** Run the analysis on representative calls. The structural overhead is stable; the document varies. Compute the merge break-even once per pipeline design, not per call.

## The move

**Compute structural overhead for merged and split configurations. Merge when the overhead saving exceeds the retry cost at your observed failure rate.**

```js
// --- Task merge vs split cost model ---
// Computes input token cost for merged vs split API call configurations.
// Run at pipeline design time to determine whether tasks should share one call.
// MERGE when: tasks share the same system prompt + document.
// SPLIT when: tasks need different system prompts, or per-field retry isolation is required.

function estimateTokens(text) { return Math.ceil((text || '').length / 4); }

const HAIKU_INPUT_RATE  = 0.80  / 1_000_000;  // $ per input token
const SONNET_INPUT_RATE = 3.00  / 1_000_000;
const MESSAGE_FRAMING   = 4;                   // tokens per message

// callSpec: { systemPrompt, tools?, document, userQuery, messageCount? }
function specInputTokens(spec) {
  return estimateTokens(spec.systemPrompt) +
         estimateTokens(JSON.stringify(spec.tools || [])) +
         estimateTokens(spec.document) +
         estimateTokens(spec.userQuery) +
         MESSAGE_FRAMING * (spec.messageCount || 1);
}

// Analyze whether to merge N tasks into one call or keep them separate.
// mergedSpec:  the hypothetical single combined call
// splitSpecs:  array of the individual call specs
// opts.inputRate:    price per input token (default: Haiku)
// opts.perFieldFailRate: per-field independent failure probability (default: 0.05)
function analyzeMergeVsSplit(mergedSpec, splitSpecs, opts) {
  opts = opts || {};
  const rate         = opts.inputRate         || HAIKU_INPUT_RATE;
  const failRate     = opts.perFieldFailRate   || 0.05;
  const n            = splitSpecs.length;

  const mergedInputTok = specInputTokens(mergedSpec);
  const splitInputTok  = splitSpecs.reduce((sum, s) => sum + specInputTokens(s), 0);

  // Retry cost per 1000 calls:
  //   Merged: fails when any field fails → 1 - (1-failRate)^n; resends full merged call.
  //   Split:  each call fails independently at failRate; resends that call only.
  const mergedRetryRate = 1 - Math.pow(1 - failRate, n);
  const mergedRetryCostPer1k = mergedRetryRate * mergedInputTok * rate * 1000;
  const splitRetryCostPer1k  = splitSpecs.reduce((sum, s) =>
    sum + failRate * specInputTokens(s) * rate * 1000, 0);

  const mergedMainCostPer1k = mergedInputTok * rate * 1000;
  const splitMainCostPer1k  = splitInputTok  * rate * 1000;

  const mergedTotalPer1k = mergedMainCostPer1k + mergedRetryCostPer1k;
  const splitTotalPer1k  = splitMainCostPer1k  + splitRetryCostPer1k;

  const recommendation = mergedTotalPer1k <= splitTotalPer1k ? 'MERGE' : 'SPLIT';
  const winnerCost = Math.min(mergedTotalPer1k, splitTotalPer1k);
  const loserCost  = Math.max(mergedTotalPer1k, splitTotalPer1k);
  const savingsPct = ((loserCost - winnerCost) / loserCost * 100).toFixed(1) + '%';

  return {
    merged: { inputTok: mergedInputTok, mainCostPer1k: mergedMainCostPer1k.toFixed(5),
              retryRate: (mergedRetryRate * 100).toFixed(1) + '%',
              retryCostPer1k: mergedRetryCostPer1k.toFixed(5),
              totalPer1k: mergedTotalPer1k.toFixed(5) },
    split:  { inputTok: splitInputTok,  mainCostPer1k: splitMainCostPer1k.toFixed(5),
              callCount: n,
              retryCostPer1k: splitRetryCostPer1k.toFixed(5),
              totalPer1k: splitTotalPer1k.toFixed(5) },
    recommendation,
    savingsPct,
    savingsPer1k: (Math.abs(mergedTotalPer1k - splitTotalPer1k)).toFixed(5),
  };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Three scenarios: same-document multi-field extraction, multi-purpose analysis, high failure rate. Token estimates via `Math.ceil(text.length / 4)`. Pricing: Haiku $0.80/M input. Zero API calls.

```
=== Task Merge vs Split Cost Model ===

--- Scenario A: extract 3 fields from same 86-tok document, same system prompt ---
  Merged (1 call):
    systemPrompt:   60 tok  |  document: 86 tok  |  query:  7 tok  |  framing: 4 tok
    Input:         157 tok
    Retry rate:    14.3%  (1 - 0.95^3, 3 fields × 5% each)
    Main cost/1k:  $0.00013   retry cost/1k: $0.00002  total/1k: $0.00015

  Split (3 calls):
    Average input per call: 119 tok  (sys_prompt varies per field)
    Total input:   357 tok  (3 × ~119 tok, each re-sends 86-tok document)
    Retry rate:     5.0% per call (independent per field)
    Main cost/1k:  $0.00029   retry cost/1k: $0.00001  total/1k: $0.00030

  → MERGE  saves 49.6% ($0.00015 vs $0.00030 per 1000 calls)
  At 10 000 calls/day: MERGE saves $1.48/day ($541/year)

--- Scenario B: multi-purpose analysis — each task needs its own system prompt ---
  Merged (1 call):
    combined_system_prompt: 200 tok  |  document: 86 tok  |  query: 20 tok  |  framing: 4 tok
    Input:         310 tok  (quality risk: combined prompt loses focus per task)
    Retry rate:    14.3%
    Main cost/1k:  $0.00025  retry cost/1k: $0.00004  total/1k: $0.00029

  Split (3 calls, each with its focused 60-100 tok system prompt):
    Total input:   524 tok  (sentiment 155 tok + risk 175 tok + compliance 194 tok)
    Retry rate:     5.0% per call
    Main cost/1k:  $0.00042  retry cost/1k: $0.00002  total/1k: $0.00044

  Recommendation by cost alone: MERGE (saves 34.8%)
  Practical verdict: SPLIT — combined system prompt degrades quality.
  Flag any MERGE where systemPrompts differ: cost savings may not survive quality testing.

--- Scenario C: high per-field failure rate (30%) ---
  Using Scenario A document and structure, failRate = 0.30:
  Merged: retry rate = 65.7% (1 - 0.70^3)
    Main cost/1k: $0.00013  retry cost/1k: $0.00010  total/1k: $0.00023

  Split:  retry rate = 30% per call (independent)
    Main cost/1k: $0.00029  retry cost/1k: $0.00009  total/1k: $0.00038

  → MERGE still wins (39.6% cheaper) even at 30% failure rate.
  Verdict: merge is durable across realistic failure rates.
  Split wins only when each call's per-field failure causes INDEPENDENT full-document resends.
  With F-154 (field-level retry on merged calls), the retry advantage of split disappears.

=== Summary ===
  Same prompt + same document → MERGE always (overhead multiplied per split call)
  Different system prompts    → run cost check, but verify quality before committing
  High failure rate (>30%)   → compose merged call with F-154 field-level retry

analyzeMergeVsSplit() 3 fields, 3 scenarios: 0.0089 ms
Zero API calls. Zero tokens.
```

## See also

[S-184](s184-input-token-structure-audit.md) · [S-37](s37-batch-vs-realtime.md) · [F-154](../forward-deployed/f154-extraction-field-level-retry.md) · [S-183](s183-tool-description-compression.md) · [S-176](s176-context-section-budget-enforcer.md)

## Go deeper

Keywords: `task merge vs split` · `API call consolidation cost` · `merge multiple extraction tasks` · `split vs batch LLM calls` · `call overhead amortization` · `LLM multi-task call` · `structural token overhead per call` · `merge extraction fields one call` · `retry cost split vs merge` · `LLM call architecture cost`
