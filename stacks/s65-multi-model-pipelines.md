# S-65 · Multi-Model Pipelines

[S-06](s06-model-routing.md) routes individual requests to the right model tier based on difficulty. Multi-model pipelines are the complementary architectural decision: within a single workflow that makes multiple model calls, assign each stage to the model tier it actually needs. A triage step doesn't need frontier reasoning. A formatting step definitely doesn't. Only the synthesis step does. Running the entire workflow on a frontier model wastes money on steps that a smaller, cheaper model handles identically.

## Situation

A contract analysis workflow runs four stages: classify the document type, extract key entities and dates, synthesize risks and obligations, and format the output as a JSON report. Running all four on Sonnet costs $0.034/workflow. Routing triage and format to Haiku (mechanical tasks) while keeping extraction and synthesis on Sonnet costs $0.027. At 10 000 workflows/day, the tiered pipeline saves $1 917/month. The output quality is indistinguishable — Haiku is not worse at mechanical classification or templating, only at novel reasoning.

## Forces

- **Intelligence requirement varies by stage.** Classification and formatting are well-defined, bounded tasks — the right model for these is the cheapest model that is reliable at structured output and instruction following, not the model that can write a PhD thesis. Synthesis is where intelligence pays: the model must connect evidence across chunks, infer implications, and surface risks not explicitly stated.
- **Quality is not uniform across the pipeline.** Sending a hard reasoning step to Haiku produces plausible-sounding output that may be wrong in subtle ways. Sending a triage step to Opus produces correct output with no quality benefit. The cost of misassignment flows in both directions — too-cheap stages introduce errors that poison downstream; too-expensive stages waste budget without improving output.
- **Stage boundaries are also context boundaries.** Each model call gets a fresh context window; it only sees what you pass. This means the synthesis call doesn't need to reproduce the triage output unless you include it. Pipeline design and context design are the same decision.
- **Latency compounds across stages.** Four sequential model calls add latency. Where stages are independent, run them in parallel ([S-55](s55-parallel-tool-calls.md)). Where they depend on each other's output, minimize the number of sequential frontier calls — they dominate wall-clock time.

## The move

**Map each stage to its minimum sufficient model. Run mechanical stages on the cheapest reliable tier. Reserve frontier models for synthesis and novel reasoning only.**

**Stage-to-model assignment:**

| Task type | Model tier | Criteria |
|---|---|---|
| Classification / routing | Haiku / flash / mini | Binary or small-label output; well-defined categories |
| Structured extraction | Sonnet | Entities, dates, amounts from a document; JSON output |
| Reasoning / synthesis | Sonnet / Opus | Connecting evidence, drawing implications, nuanced judgment |
| Frontier reasoning | Opus only | Novel problem, research-grade output, multi-step logic chains |
| Formatting / templating | Haiku | Converting structured form to another; mechanical task |
| Embedding queries | Embedding model | Semantic similarity; high volume; price-sensitive |

**Pipeline structure:**

```js
const STAGE_MODELS = {
  triage:     'claude-haiku-4-5-20251001',  // $0.80/M in, $4.00/M out
  extraction: 'claude-sonnet-4-6',           // $3.00/M in, $15.00/M out
  synthesis:  'claude-sonnet-4-6',
  format:     'claude-haiku-4-5-20251001',
};

async function analyzeContract(documentText) {
  // Stage 1: triage (Haiku — mechanical classification)
  const triageResp = await client.messages.create({
    model:      STAGE_MODELS.triage,
    max_tokens: 60,
    messages:   [{ role: 'user', content: triagePrompt(documentText) }],
  });
  const { docType, complexity } = JSON.parse(triageResp.content[0].text);

  // Stage 2: extraction (Sonnet — structured, but requires reliability)
  const extractResp = await client.messages.create({
    model:      STAGE_MODELS.extraction,
    max_tokens: 800,
    messages:   [{ role: 'user', content: extractionPrompt(documentText, docType) }],
  });
  const entities = JSON.parse(extractResp.content[0].text);

  // Stage 3: synthesis (Sonnet — reasoning; escalate to Opus if complexity === 'high')
  const synthModel = complexity === 'high' ? 'claude-opus-4-8' : STAGE_MODELS.synthesis;
  const synthResp = await client.messages.create({
    model:      synthModel,
    max_tokens: 1200,
    messages:   [{ role: 'user', content: synthesisPrompt(documentText, entities) }],
  });
  const analysis = synthResp.content[0].text;

  // Stage 4: format (Haiku — templating; input is structured, output is structured)
  const formatResp = await client.messages.create({
    model:      STAGE_MODELS.format,
    max_tokens: 600,
    messages:   [{ role: 'user', content: formatPrompt(entities, analysis) }],
  });
  return JSON.parse(formatResp.content[0].text);
}
```

**Conditional escalation:**

```js
// Only pay Opus prices when the task proves it needs Opus
const model = complexity === 'high' || docType === 'litigation'
  ? 'claude-opus-4-8'
  : 'claude-sonnet-4-6';
```

This is dynamic tier selection within the pipeline — not per-request routing of the whole workflow, but per-stage escalation based on what the prior stage returned.

**Parallelizing independent stages:**

```js
// Extraction and a preliminary risk scan can run in parallel —
// they both read the document but don't depend on each other
const [entities, prelimRisks] = await Promise.all([
  callModel(STAGE_MODELS.extraction, extractionPrompt(doc)),
  callModel(STAGE_MODELS.triage,     riskScanPrompt(doc)),
]);
// Synthesis runs after, using both results
const analysis = await callModel(STAGE_MODELS.synthesis, synthesisPrompt(entities, prelimRisks));
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Haiku pricing approximate — verify at provider. Sonnet: $3.00/M input, $15.00/M output.

```
=== Multi-model pipeline vs all-Sonnet: 4-stage contract analysis ===

Stage         Model              Input   Output   Tiered        All-Sonnet
triage        Haiku              280     45       $0.00040      $0.00152
extraction    Sonnet            1200    380       $0.00930      $0.00930
synthesis     Sonnet            2100    620       $0.01560      $0.01560
format        Haiku              850    310       $0.00192      $0.00720

Tiered total:     $0.02722/workflow
All-Sonnet total: $0.03361/workflow
Saving:           19% ($0.00639/workflow)
At 10k/day:       $1 917/month saved

Stage token totals: 4 430 input + 1 355 output = 5 785 tokens

Where savings come from:
  Triage on Haiku vs Sonnet: $0.00112 saved per run (74% reduction for that stage)
  Format on Haiku vs Sonnet: $0.00528 saved per run (73% reduction for that stage)
  Extraction and synthesis: unchanged — Sonnet is the right tier for both
```

The 19% overall saving comes entirely from two mechanical stages (triage and format) that don't benefit from Sonnet capability. Escalating synthesis to Opus (when complexity is high) costs ~$0.025 more per run — reserve it for the subset of documents that genuinely require it.

## See also

[S-06](s06-model-routing.md) · [S-05](s05-multi-agent-patterns.md) · [S-55](s55-parallel-tool-calls.md) · [F-08](../forward-deployed/f08-agent-cost-control.md) · [F-35](../forward-deployed/f35-workflow-token-budget.md) · [F-23](../forward-deployed/f23-cost-estimation.md)

## Go deeper

Keywords: `multi-model pipeline` · `stage routing` · `model tier` · `tiered inference` · `cascade` · `Haiku pipeline` · `Sonnet pipeline` · `cost optimization` · `pipeline architecture` · `conditional escalation`
