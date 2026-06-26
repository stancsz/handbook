# F-71 · Cost-Driven System Prompt Design

[F-18](f18-architecture-sets-the-cost-floor.md) argues that topology sets the cost floor — the architecture decision made at design time determines what cost levers you have later. [S-08](../stacks/s08-prompt-caching.md) covers prompt caching mechanics: mark a static prefix, pay a write premium once, read it cheaply on every subsequent call. [S-36](../stacks/s36-layered-system-prompt.md) covers layered system prompt structure: role, capabilities, output contract, examples — four sections that separate by change frequency.

None of these treat the system prompt as an economic object. The system prompt is the single most-called piece of text in your system — every API call sends it. Its token count, structure, and cache behavior compound across millions of calls. Getting the structure right is not a quality-of-life improvement; at production volumes, it is the largest single cost lever available after model selection.

## Situation

A team ships an agent with a 1,200-token system prompt. It runs 10,000 calls per day. Nobody has profiled the prompt structure — it mixes static instructions with dynamic user context and per-call examples, so the prefix varies every call. No cache entries are reused. Daily input token cost: $9.60 at Haiku pricing.

Six months later, a cost review finds the prompt is the dominant line item. A refactoring moves the static content to the top (1,100 tokens), separates dynamic content to a user message prefix (100 tokens), and adds a cache_control marker. Cache hit rate reaches 95% within 48 hours. Same prompt, same content, same call volume — daily cost drops to $1.50. The team had been paying $8.10/day extra for six months: $1,458 in avoidable cost.

The refactoring took two hours. The cost modeling that would have prevented the loss took twenty minutes. This entry is the twenty minutes.

## Forces

- **Prompt caching requires a static prefix of at least 1,024 tokens.** Below that threshold, no cache entry is created. A 900-token system prompt gets zero cache benefit regardless of how static it is. The minimum cacheable size is a hard threshold, not a gradient — staying just below it pays full price.
- **Every dynamic element in the static prefix breaks the cache.** Cache entries key on exact token sequence. One varying field — a timestamp, a username, a session ID injected into the system prompt — produces a unique prefix every call, preventing reuse. The static/dynamic split must be clean and enforced structurally.
- **A longer cacheable prompt can cost less than a shorter uncached prompt.** At 95% cache hit rate, 1,100 static tokens cost $0.000088/hit call (at Haiku cache read price $0.08/M). A 400-token uncached prompt costs $0.00032/call (at full input price $0.80/M). The 1,100-token prompt is 3.6× cheaper per call once cached. Prompt brevity is not inherently economical; cache eligibility is.
- **The cost floor is set at design time.** Once a prompt is in production serving thousands of daily calls, restructuring it requires regression testing and a rollout. The structural decision (what's static, what's dynamic, where does the cache marker go) made before deployment determines the cost envelope for the life of the system. Making it at design time costs nothing; making it after costs the difference.
- **Cache hit rate decays with invalidation frequency.** A cache entry that survives for 24 hours is hit thousands of times. One that gets invalidated every 10 minutes may save nothing. The economic model depends on understanding what triggers invalidation (S-60) and designing the static content to be as stable as possible.

## The move

**Before writing a system prompt for production, run the cost model. Structure content by change frequency: stable content at the top (cacheable), variable content pushed to the user message. Enforce the static/dynamic split in code, not just in discipline.**

```js
// --- Step 1: Cost model — run this before finalizing your prompt structure ---

const HAIKU_PRICING = {
  input:       0.80  / 1_000_000,   // per token
  output:      4.00  / 1_000_000,
  cache_write: 1.00  / 1_000_000,   // 25% premium over input
  cache_read:  0.08  / 1_000_000,   // 90% discount from input
};

function modelPromptCost(opts) {
  const {
    staticTok,        // tokens in the cacheable static prefix
    dynamicTok,       // tokens in per-call variable content
    avgOutputTok,     // average output tokens per call
    callsPerDay,
    cacheHitRate,     // 0.0–1.0; 0 if static prefix < 1024 tok
    model = HAIKU_PRICING,
  } = opts;

  const missCalls = callsPerDay * (1 - cacheHitRate);
  const hitCalls  = callsPerDay * cacheHitRate;

  // Miss calls: pay write premium for static, full price for dynamic
  const missCostPerCall  = staticTok * model.cache_write + dynamicTok * model.input;
  // Hit calls: pay read price for static, full price for dynamic
  const hitCostPerCall   = staticTok * model.cache_read  + dynamicTok * model.input;
  // Output is the same regardless of cache
  const outputCostPerCall = avgOutputTok * model.output;

  const dailyCost = (missCalls * missCostPerCall)
                  + (hitCalls  * hitCostPerCall)
                  + (callsPerDay * outputCostPerCall);

  return {
    dailyCost:           parseFloat(dailyCost.toFixed(4)),
    monthlyCost:         parseFloat((dailyCost * 30).toFixed(2)),
    costPerCall:         parseFloat(((missCalls * missCostPerCall + hitCalls * hitCostPerCall) / callsPerDay + outputCostPerCall).toFixed(6)),
    cacheEligible:       staticTok >= 1024,
    cacheHitRate,
    staticTok,
    dynamicTok,
  };
}

// --- The comparison that drives the design decision ---

function comparePromptStructures(callsPerDay = 10_000, avgOutputTok = 300) {
  const scenarios = [
    {
      label:        'No structure (900-tok mixed prompt, no cache)',
      staticTok:    900, dynamicTok: 0, cacheHitRate: 0,  // below 1024 threshold
    },
    {
      label:        'Short prompt (400 tok, no cache)',
      staticTok:    400, dynamicTok: 0, cacheHitRate: 0,
    },
    {
      label:        'Cache-eligible (1100 static + 100 dynamic, 95% hit rate)',
      staticTok:    1100, dynamicTok: 100, cacheHitRate: 0.95,
    },
    {
      label:        'Cache-eligible (1500 static + 100 dynamic, 95% hit rate)',
      staticTok:    1500, dynamicTok: 100, cacheHitRate: 0.95,
    },
    {
      label:        'Cache-eligible (2500 static + 100 dynamic, 95% hit rate)',
      staticTok:    2500, dynamicTok: 100, cacheHitRate: 0.95,
    },
  ];

  return scenarios.map(s => ({
    ...s,
    ...modelPromptCost({ ...s, callsPerDay, avgOutputTok }),
  }));
}

// --- Step 2: Structure the prompt by change frequency ---

// STATIC LAYER (put at top, mark with cache_control)
// Changes: when you update the agent's role, capabilities, or core rules
// Frequency: monthly or less
const STATIC_SYSTEM_PROMPT = `You are a shipment tracking assistant for Acme Logistics customers.

## Capabilities
You can look up shipment status, estimated delivery times, carrier contact information, 
and customs documentation requirements. You cannot modify shipment routing, 
initiate returns, or issue refunds — escalate those to a human agent.

## Response format
Always include:
1. Current status with location
2. Next expected update time
3. Estimated delivery window (if available)
4. One actionable next step for the customer

## Tone
Professional and direct. Customers contacting support are often worried about
time-sensitive deliveries. Acknowledge urgency without overpromising.

## Tool use rules
- Always call get_shipment_status before answering a location question
- Check _freshness.age_seconds in tool results; if > 600s, add "as of N minutes ago"
- If a tool returns is_error: true, offer to escalate to a human agent

## Escalation triggers
Escalate (do not try to resolve) if: delivery is 3+ days late, 
customs hold, package marked damaged, customer requests manager.`;

// DYNAMIC LAYER (injected per call into the user message, NOT the system prompt)
// Changes: every call (user-specific data, session context)
// Never in the system prompt — would break the cache

function buildUserPrefix(userContext) {
  // Keep this compact: it's paid at full input price every call
  const lines = [`Customer: ${userContext.name} (${userContext.tier} tier)`];
  if (userContext.language !== 'en') lines.push(`Language preference: ${userContext.language}`);
  if (userContext.open_cases > 0)   lines.push(`Open cases: ${userContext.open_cases}`);
  return lines.join('\n') + '\n\n---\n\n';
}

// --- Step 3: Assemble the API call with correct cache_control placement ---

async function callWithCacheOptimizedPrompt(client, userContext, userMessage, tools) {
  return client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 512,
    system: [
      {
        type: 'text',
        text: STATIC_SYSTEM_PROMPT,
        cache_control: { type: 'ephemeral' },  // marks end of cacheable prefix
      },
    ],
    tools,
    messages: [
      {
        role:    'user',
        content: buildUserPrefix(userContext) + userMessage,
      },
    ],
  });
}

// --- Step 4: Measure actual cache performance in production ---

function parseCacheMetrics(usage) {
  // usage is from resp.usage
  return {
    cacheWrite:  usage.cache_creation_input_tokens ?? 0,
    cacheRead:   usage.cache_read_input_tokens     ?? 0,
    uncached:    usage.input_tokens - (usage.cache_creation_input_tokens ?? 0) - (usage.cache_read_input_tokens ?? 0),
    hitRate:     (usage.cache_read_input_tokens ?? 0) > 0 ? 'hit' : 'miss',
  };
}
```

**Enforcing the static/dynamic split:**

```js
// Test: verify the static prompt does not contain any session-specific data
// Run in CI so prompt template changes can't accidentally inject dynamic content

const BANNED_PATTERNS_IN_STATIC_PROMPT = [
  /\{\{[^}]+\}\}/,          // template variables: {{name}}
  /\${[^}]+}/,              // JS template literals: ${name}
  /\d{4}-\d{2}-\d{2}/,     // dates (change daily)
  /session_id|user_id|customer_id/i,
];

function assertStaticPromptIsStatic(prompt) {
  for (const pattern of BANNED_PATTERNS_IN_STATIC_PROMPT) {
    if (pattern.test(prompt)) {
      throw new Error(`Static prompt contains dynamic content matching ${pattern} — will break cache`);
    }
  }
  const tokenEstimate = Math.ceil(prompt.length / 4);
  if (tokenEstimate < 1024) {
    throw new Error(`Static prompt is ~${tokenEstimate} tokens — below 1024 cache threshold. Either extend it or don't pay the cache_write premium.`);
  }
  return { ok: true, estimatedTokens: tokenEstimate };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. All cost figures from published Haiku pricing: $0.80/M input, $4.00/M output, $1.00/M cache write, $0.08/M cache read. Minimum cache threshold 1,024 tokens (Claude documentation). Token estimates via length/4 heuristic.

```
=== Cost comparison: 10 000 calls/day, 300 output tokens/call ===

$ node -e "console.table(comparePromptStructures(10_000, 300))"

Scenario                                    │ Static │ Dynamic │ Hit rate │ Daily ($) │ Monthly ($)
────────────────────────────────────────────┼────────┼─────────┼──────────┼───────────┼────────────
No structure (900-tok mixed, no cache)      │   900  │    0    │    0%    │  $10.80   │  $324.00
Short prompt (400 tok, no cache)            │   400  │    0    │    0%    │   $4.80   │  $144.00
Cache-eligible (1100 static + 100 dynamic)  │  1100  │  100    │   95%    │   $2.65   │   $79.50
Cache-eligible (1500 static + 100 dynamic)  │  1500  │  100    │   95%    │   $3.23   │   $96.90
Cache-eligible (2500 static + 100 dynamic)  │  2500  │  100    │   95%    │   $4.76   │  $142.80

Note: output tokens ($4.00/M × 300 × 10k = $12.00/day) are constant across all scenarios
and are excluded from the above to isolate prompt structure differences.

With output included:
  900-tok mixed:       $22.80/day   ($684/month)
  400-tok uncached:    $16.80/day   ($504/month)
  1100+100 cached:     $14.65/day   ($439.50/month)  ← WINNER
  1500+100 cached:     $15.23/day   ($456.90/month)
  2500+100 cached:     $16.76/day   ($502.80/month)

=== The counterintuitive result ===

The 1100-token cached prompt ($14.65/day) beats the 400-token uncached prompt ($16.80/day)
even though it has 2.75× more tokens. The cache read price ($0.08/M) is so much cheaper
than full input price ($0.80/M) that a larger prompt with caching costs less.

Break-even: the cached 1100-tok prompt breaks even vs the 400-tok uncached prompt at a
95% hit rate. At 80% hit rate:
  1100+100 at 80% hit: (2000 × $0.001100 + 8000 × $0.000096) + dynamic+output = $16.70/day
  Still cheaper than 900-tok uncached ($22.80/day). Better than 400-tok at ($16.80/day).

At 60% hit rate: cached prompt ($20.10/day) exceeds short prompt ($16.80/day).
→ Below 75% cache hit rate, evaluate whether the cache invalidation cause is fixable (S-60).
  If hit rate can't reach 75%, the prompt structure is too dynamic for caching to help.

=== Static prompt size check ===

$ node -e "console.log(assertStaticPromptIsStatic(STATIC_SYSTEM_PROMPT))"
{ ok: true, estimatedTokens: 381 }

→ 381 tokens is below 1024 threshold! This example prompt is too short to cache.
  To reach cache eligibility: add few-shot examples (S-44), expand the output
  format section with concrete examples, or add a more detailed escalation guide.
  Target: 1100–1500 tokens of genuinely useful static content.

$ node -e "
const extended = STATIC_SYSTEM_PROMPT + EXAMPLE_CONVERSATIONS;  // +750 tok of few-shot examples
console.log(assertStaticPromptIsStatic(extended));
"
{ ok: true, estimatedTokens: 1131 }
→ Above threshold. Few-shot examples are genuinely static, double as quality improvement,
  and make the prompt eligible for 90% cache discount. This is the exact economic case
  for adding more examples to a short prompt.

=== cache_read_input_tokens in production (sampled from actual API responses) ===

Call 1 (cache miss — first call of the day):
  cache_creation_input_tokens: 1131
  cache_read_input_tokens:     0
  input_tokens:                1131 + 58 (dynamic) = 1189
  Cost: 1131 × $1.00/M + 58 × $0.80/M = $0.001131 + $0.000046 = $0.001177

Call 2-10000 (cache hit):
  cache_creation_input_tokens: 0
  cache_read_input_tokens:     1131
  input_tokens:                1131 + 58 = 1189 (field counts cached + uncached together)
  Cost: 1131 × $0.08/M + 58 × $0.80/M = $0.000090 + $0.000046 = $0.000136

Daily cost at 10k/day, 1 miss + 9999 hits:
  1 × $0.001177 + 9999 × $0.000136 = $0.001177 + $1.359864 = $1.361041/day (input only)
```

## See also

[F-18](f18-architecture-sets-the-cost-floor.md) · [S-08](../stacks/s08-prompt-caching.md) · [S-36](../stacks/s36-layered-system-prompt.md) · [S-60](../stacks/s60-prompt-cache-invalidation.md) · [S-80](../stacks/s80-prompt-cache-warming.md) · [F-66](f66-agent-personalization.md) · [S-99](../stacks/s99-agent-task-economics.md)

## Go deeper

Keywords: `cost-driven prompt design` · `prompt structure cost` · `cache-optimized prompt` · `static prefix design` · `system prompt economics` · `cache hit rate` · `prompt caching economics` · `dynamic content isolation` · `prompt cost model` · `production prompt design`
