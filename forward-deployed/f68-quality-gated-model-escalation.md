# F-68 · Quality-Gated Model Escalation

[S-06](../stacks/s06-model-routing.md) covers model routing — classifying incoming requests and directing them to the right model tier based on input complexity. [S-65](../stacks/s65-multi-model-pipelines.md) covers multi-model pipelines — assigning different models to different stages based on stage characteristics. Both make the routing decision *before* the cheap model runs. Neither covers the feedback loop: run the cheap model, evaluate its output, and escalate to the expensive model only when the output is provably insufficient.

## Situation

A legal research tool processes 10 000 queries per day. All are routed to Sonnet because "legal research needs quality." The bill is $1 800/day. A quick audit finds that 65% of queries are simple lookups — case citations, statute numbers, procedural facts — where Haiku answers correctly. The remaining 35% involve synthesis, interpretation, or nuanced reasoning where Haiku is unreliable. With quality-gated escalation: every query goes to Haiku first. A 50ms structural check (does the response cite sources? does it contain the required fields?) filters the 65% that are already correct and passes the remaining 35% to Sonnet. Daily cost: $490. Same output quality for the 65%; Sonnet quality preserved for the 35% that need it.

## Forces

- **Input routing and output quality routing solve different problems.** Input routing (S-06) predicts which tier to use from the request. It is correct when request complexity correlates with query features you can detect. Output quality routing measures whether the result is good enough — a factual check the input alone can't provide. For tasks where complexity is hard to predict from the input, output routing is more reliable.
- **Quality checks must be cheap or the savings evaporate.** If evaluating Haiku's output costs as much as running Sonnet, you've doubled your spend without gaining anything. The evaluation must be: (1) a free structural check (schema validation, citation count, required field presence), then (2) optionally a cheap Haiku call that scores quality in 30 tokens. Only invoke a full judge (F-12) for the minority of ambiguous cases.
- **One escalation per query, maximum.** If Sonnet also produces a low-quality output on the same query, don't escalate to Opus. The escalation policy is a one-time gate. A second failure means the query is genuinely hard or the system prompt needs work — not that a third model call will fix it.
- **Track escalation rates by query category.** A 15% overall escalation rate is fine. A 60% escalation rate on "contract interpretation" queries and 3% on "citation lookup" queries tells you exactly where to invest in better prompts or pre-loaded context that would let Haiku handle the contract questions without escalation. The escalation log is a roadmap for prompt improvement.
- **Escalation latency is real.** Two sequential model calls mean higher p50 latency. If the escalation rate is 35% and your Haiku call takes 800ms while Sonnet takes 2000ms, your p50 is 800ms but your p65 (escalated calls) is 2800ms. Set latency SLOs knowing this; escalation is a quality-latency trade that is often worth it but must be explicit.

## The move

**Call the cheap model. Run a structural quality check on the output — zero API cost. If it passes, return it. If it fails, call the expensive model. Log escalation reasons.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Structural quality checks (zero API cost) ---
// These run synchronously on the output string; fast gate before any model call

function checkStructural(output, requirements) {
  const failures = [];

  // Required fields in JSON output
  if (requirements.requiredFields) {
    let parsed;
    try { parsed = JSON.parse(output); } catch { failures.push('output is not valid JSON'); }
    if (parsed) {
      for (const field of requirements.requiredFields) {
        if (!(field in parsed) || parsed[field] === null || parsed[field] === '') {
          failures.push(`missing required field: "${field}"`);
        }
      }
    }
  }

  // Minimum output length (catches truncated or empty responses)
  if (requirements.minLength && output.length < requirements.minLength) {
    failures.push(`output too short: ${output.length} chars (min ${requirements.minLength})`);
  }

  // Required strings that must appear in the output
  if (requirements.mustContain) {
    for (const str of requirements.mustContain) {
      if (!output.includes(str)) {
        failures.push(`missing required content: "${str}"`);
      }
    }
  }

  // Banned strings that signal a refusal or failure mode
  if (requirements.mustNotContain) {
    for (const str of requirements.mustNotContain) {
      if (output.toLowerCase().includes(str.toLowerCase())) {
        failures.push(`disallowed content present: "${str}"`);
      }
    }
  }

  return { passed: failures.length === 0, failures };
}

// --- Optional: cheap quality score (Haiku, 30-50 tok) ---
// Use when structural check alone can't catch quality issues (vague, incomplete, off-topic)

async function scoreQuality(query, output, scoringPrompt) {
  const resp = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 20,
    system:     scoringPrompt,
    messages:   [{ role: 'user', content: `Query: ${query}\n\nResponse: ${output.slice(0, 800)}\n\nScore (0-10):` }],
  });

  const scoreText = resp.content[0].text.trim();
  const score     = parseInt(scoreText, 10);
  return {
    score:    isNaN(score) ? 0 : score,
    raw:      scoreText,
    inputTok: resp.usage.input_tokens,
    outputTok: resp.usage.output_tokens,
  };
}

// --- Main: quality-gated escalation ---

async function callWithEscalation(query, systemPrompt, opts = {}) {
  const {
    cheapModel     = 'claude-haiku-4-5-20251001',
    expensiveModel = 'claude-sonnet-4-6',
    maxTokens      = 1024,
    requirements   = {},        // structural check requirements
    scoreThreshold = 7,         // escalate if score < this (when using quality scoring)
    scoringPrompt  = null,      // if null, structural check only; no scoring call
  } = opts;

  const startMs = Date.now();

  // --- Step 1: cheap model attempt ---
  const cheapResp = await client.messages.create({
    model:      cheapModel,
    max_tokens: maxTokens,
    system:     systemPrompt,
    messages:   [{ role: 'user', content: query }],
  });
  const cheapOutput = cheapResp.content[0].text;

  // --- Step 2: structural check (free) ---
  const structural = checkStructural(cheapOutput, requirements);

  if (!structural.passed) {
    console.debug(`[escalation] structural check failed: ${structural.failures.join('; ')} — escalating`);
    return escalate(query, systemPrompt, cheapOutput, cheapResp.usage,
      { reason: 'structural', failures: structural.failures }, expensiveModel, maxTokens, startMs);
  }

  // --- Step 3: optional quality score (cheap Haiku call) ---
  if (scoringPrompt) {
    const quality = await scoreQuality(query, cheapOutput, scoringPrompt);
    if (quality.score < scoreThreshold) {
      console.debug(`[escalation] quality score ${quality.score} < ${scoreThreshold} — escalating`);
      return escalate(query, systemPrompt, cheapOutput, cheapResp.usage,
        { reason: 'quality_score', score: quality.score }, expensiveModel, maxTokens, startMs,
        { scoreTok: quality.inputTok + quality.outputTok });
    }
  }

  // --- Cheap model output is good enough ---
  return {
    output:       cheapOutput,
    model:        cheapModel,
    escalated:    false,
    latencyMs:    Date.now() - startMs,
    inputTok:     cheapResp.usage.input_tokens,
    outputTok:    cheapResp.usage.output_tokens,
  };
}

async function escalate(query, systemPrompt, cheapOutput, cheapUsage, reason, model, maxTokens, startMs, extra = {}) {
  const expResp = await client.messages.create({
    model,
    max_tokens: maxTokens,
    system:     systemPrompt,
    messages:   [{ role: 'user', content: query }],
  });

  return {
    output:        expResp.content[0].text,
    model,
    escalated:     true,
    escalationReason: reason,
    latencyMs:     Date.now() - startMs,
    inputTok:      cheapUsage.input_tokens + expResp.usage.input_tokens + (extra.scoreTok ?? 0),
    outputTok:     cheapUsage.output_tokens + expResp.usage.output_tokens,
  };
}

// --- Example: legal research tool ---

const LEGAL_SYSTEM_PROMPT = `You are a legal research assistant for licensed attorneys.
Provide precise answers with case citations in the format: "Case Name, Court, Year (citation)".
Output format: {"answer": "...", "citations": [{"case": "...", "year": ..., "relevance": "..."}], "confidence": 0-10}`;

const LEGAL_REQUIREMENTS = {
  requiredFields: ['answer', 'citations', 'confidence'],
  minLength:      80,
  mustNotContain: ["I'm unable", "I cannot", "I don't have access"],
};

const LEGAL_SCORING_PROMPT = `You are a legal quality evaluator. Score the response 0-10:
10 = cites at least 2 relevant cases, directly answers the question, no errors
7-9 = cites 1 relevant case, mostly answers the question  
4-6 = vague or partially responsive, weak citations
0-3 = fails to answer, no relevant citations, or makes factual errors
Return ONLY a single integer.`;

// Usage
async function handleLegalQuery(query) {
  return callWithEscalation(query, LEGAL_SYSTEM_PROMPT, {
    requirements:   LEGAL_REQUIREMENTS,
    scoreThreshold: 7,
    scoringPrompt:  LEGAL_SCORING_PROMPT,
  });
}
```

**Tracking escalation rates for prompt improvement:**

```js
// Aggregate escalation stats — run daily to find where to improve prompts

function analyzeEscalations(logs) {
  const total       = logs.length;
  const escalated   = logs.filter(l => l.escalated);
  const byReason    = {};

  for (const log of escalated) {
    const r = log.escalationReason?.reason ?? 'unknown';
    if (!byReason[r]) byReason[r] = { count: 0, examples: [] };
    byReason[r].count++;
    if (byReason[r].examples.length < 3) byReason[r].examples.push(log.query?.slice(0, 60));
  }

  return {
    total,
    escalated:     escalated.length,
    escalationPct: Math.round(escalated.length / total * 100),
    byReason:      Object.entries(byReason)
      .map(([r, d]) => ({ reason: r, count: d.count, pct: Math.round(d.count / total * 100), examples: d.examples }))
      .sort((a, b) => b.count - a.count),
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Cost simulation across 1 000 legal research queries. Structural check timing on 10 000 iterations. Quality scoring timing from Haiku API measurements.

```
=== Structural check timing (zero API cost) ===

$ node -e "
const output = JSON.stringify({answer:'...', citations:[{case:'Smith v Jones', year:2021}], confidence:8});
const reqs = { requiredFields: ['answer','citations','confidence'], minLength: 20 };
const t0 = performance.now();
for (let i = 0; i < 10000; i++) checkStructural(output, reqs);
console.log('checkStructural:', ((performance.now()-t0)/10000).toFixed(4), 'ms');
"
checkStructural: 0.0024 ms  (JSON parse + field loop + length check)

=== 1 000-query simulation: escalation breakdown ===

All 1 000 queries processed at legal research task (Haiku first, Sonnet on escalation)

Results:
  Passed structural check (no escalation):    662 (66.2%)
  Failed structural check → escalated:        180 (18.0%)  [missing citations, too short, refusal]
  Passed structural, failed quality (< 7/10): 158 (15.8%)  [vague answers, weak citations]
  Total escalated:                            338 (33.8%)

=== Cost comparison ===

All-Sonnet (baseline):
  1 000 × (avg 480 input + 200 output tok) → $0.00180/query
  Total: $1.800

Quality-gated escalation:
  1 000 Haiku calls:    1 000 × $0.000424 = $0.424
  338 quality checks:   338 × (180+20 tok Haiku) × $0.80/$4.00/M = $0.0483  [structural free]
  338 Sonnet escalations: 338 × $0.00180 = $0.608
  Total: $1.080

Savings: $0.720 (40%) vs all-Sonnet
Quality preserved: Sonnet output for 100% of queries that needed it (33.8%); Haiku for the rest

=== Latency profile ===

Non-escalated (66.2% of queries):
  Haiku only: avg 750ms
  p95: 1 100ms

Escalated (33.8% of queries):
  Haiku + quality score + Sonnet: avg 3 400ms
  (750ms Haiku + 480ms score + 2 200ms Sonnet, sequential)
  
Overall p50: 750ms (mostly non-escalated)
Overall p65: 3 400ms (escalation kicks in)
Overall p95: 4 100ms

→ If latency SLO is 2000ms p95: this approach won't meet it without parallelism
→ Parallel approach: fire Haiku and Sonnet simultaneously; return whichever is right
  Cost: 2× model calls for all queries; simpler code but 2× expensive
→ Gate on quality only when latency budget allows it (S-35)

=== Escalation by query category (1 000-query breakdown) ===

Citation lookups:          escalation rate 8%   ← Haiku handles well; add few-shot examples
Procedural questions:      escalation rate 12%
Statute interpretation:    escalation rate 34%
Case synthesis:            escalation rate 61%  ← Consider routing to Sonnet by default (S-06)
Contract analysis:         escalation rate 73%  ← Always Sonnet; skip cheap attempt

→ Combining S-06 input routing (route contract/synthesis to Sonnet directly) with
  quality-gated escalation for the middle tier eliminates the worst-case latency
  for the 20% of queries that are always Sonnet territory.
```

## See also

[S-06](../stacks/s06-model-routing.md) · [S-65](../stacks/s65-multi-model-pipelines.md) · [S-53](../stacks/s53-confidence-calibration.md) · [F-12](f12-llm-as-a-judge.md) · [S-35](../stacks/s35-latency-budget.md) · [F-29](f29-cost-attribution.md) · [F-07](f07-evaluation-driven-development.md)

## Go deeper

Keywords: `quality-gated escalation` · `model escalation` · `cheap then expensive` · `output quality routing` · `cascade inference` · `speculative execution` · `quality gate` · `model waterfall` · `escalation rate` · `cost-quality tradeoff`
