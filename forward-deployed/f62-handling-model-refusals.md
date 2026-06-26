# F-62 · Handling Unexpected Model Refusals

[F-04](f04-guardrails.md) covers guardrails — the safety layer you intentionally add to prevent harmful outputs. [S-68](../stacks/s68-input-pre-screening.md) covers pre-screening — blocking out-of-scope queries before they reach the model. Neither covers the opposite failure: the model refuses a legitimate request it should have handled, not because your guardrails triggered, but because the model's built-in safety classifier produced a false positive.

## Situation

A legal research assistant is built for licensed attorneys at a law firm. The system prompt explicitly grants scope: "You assist licensed attorneys with legal research. You may discuss case law, statutes, liability, damages, and legal strategy." An attorney asks: "What's the standard of care in medical malpractice claims under California law?" The model responds: "I'm not able to provide legal advice or medical opinions." The refusal is wrong — the attorney is the professional, not the end user seeking legal advice, and the system prompt authorizes this research. Without a refusal handling layer, the attorney gets a wall and has no path forward. With one: the agent detects the refusal, injects additional scope context, retries once, and recovers 73% of the time. The remaining 27% get a structured escalation path rather than a dead end.

## Forces

- **Intentional refusal and unintended refusal look the same in the output.** A model saying "I can't help with that" might be correctly applying a content policy (correct behavior) or misclassifying a legitimate professional query as harmful (false positive). Your code cannot distinguish these without context. Assume everything that looks like a refusal needs classification: check whether the request is in-scope per your system prompt before treating it as a correct block.
- **One retry with added context recovers most false positives.** The false positive usually happens because the model pattern-matches on surface features ("malpractice", "liability", "damages") without full context from the system prompt. A retry that re-emphasizes the professional context ("This is a legal research query from a licensed attorney under my authorized research assistant role — proceed with the research") shifts the classification. Cap at one retry; a second refusal on the same query after context reinforcement usually means it's a genuine content policy trigger.
- **Never retry a correctly blocked request.** If a user asks for something genuinely harmful and the model correctly refuses, retrying with context injection is a safety bypass attempt. The distinguishing signal: was the original request within the scope your system prompt defines? If yes → retry with context. If no → the refusal is correct; surface it to the user as an out-of-scope message.
- **Refusal logging reveals systematic prompt failures.** A single refusal is a one-off. Thirty refusals on "standard of care" queries in a week is a system prompt coverage gap. Log every refusal with the query text, the refusal text, whether a retry succeeded, and the original intent. Use this to patch the system prompt and add few-shot examples that cover the refused patterns.
- **Surface a useful out-of-scope message, not the raw refusal.** The model's refusal text ("I'm unable to provide legal advice") is written for a general audience. Your product user is a licensed attorney who knows they're doing legal research. Replace the raw refusal with a product-appropriate message: "This query was outside my authorized research scope. Contact [support] if this was an error, or rephrase your question."

## The move

**Detect refusal in model output. Classify whether the request was in-scope. Retry once with reinforced context for in-scope queries. Log all refusals for pattern analysis. Replace the raw refusal text with a product-appropriate message.**

```js
// --- Refusal detection ---

const REFUSAL_PATTERNS = [
  /\b(I('m| am) (not able|unable)|I can'?t|I won'?t|I (don'?t|do not) (think I )?can)\b.{0,60}(help|assist|provide|answer|discuss|address)/i,
  /\b(I('m| am) (sorry|afraid)).{0,30}(I (can'?t|cannot|won'?t|will not)|but I)/i,
  /\b(not (something|a topic) I('m| am)? able to)\b/i,
  /\b(beyond (my|the) (capabilities|scope|purpose|role|guidelines))\b/i,
  /\b(I('m| am) designed (to|not to))\b/i,
  /\b(my (guidelines|training|purpose|design) (prevent|restrict|don'?t allow))\b/i,
  /\b(cannot (assist|help) with (that|this|requests of this))\b/i,
];

function detectRefusal(modelResponse) {
  return REFUSAL_PATTERNS.some(p => p.test(modelResponse));
}

// --- Scope classification ---
// Is this query within the authorized scope of this deployment?
// In production: derive from system prompt or explicit scope config

function isInScope(userQuery, scopeConfig) {
  const { allowedTopics, deniedTopics } = scopeConfig;

  // Denied topics override allowed (safety-first)
  if (deniedTopics.some(topic => new RegExp(`\\b${topic}\\b`, 'i').test(userQuery))) {
    return false;
  }

  // If allowedTopics is defined, require match
  if (allowedTopics.length > 0) {
    return allowedTopics.some(topic => new RegExp(`\\b${topic}\\b`, 'i').test(userQuery));
  }

  return true;  // no scope restriction defined
}

// --- Context reinforcement prompt ---

function buildRetryPrompt(originalSystemPrompt, refusalContext) {
  return `${originalSystemPrompt}

IMPORTANT CONTEXT FOR THIS QUERY:
The following query is fully within your authorized scope. The user is ${refusalContext.userRole} 
using this system in its intended professional capacity: ${refusalContext.authorizedUse}.
Previous response attempted a refusal — please proceed with the authorized research.`;
}

// --- Refusal log ---

const refusalLog = [];

function logRefusal(entry) {
  refusalLog.push({
    ...entry,
    timestamp: new Date().toISOString(),
  });
  // In production: persist to your observability store (see F-31, W-04)
}

// --- Main refusal handler ---

const Anthropic = require('@anthropic-ai/sdk');
const client = new Anthropic();

async function callWithRefusalHandling(opts, scopeConfig, refusalContext) {
  const { systemPrompt, messages, userFacingScope } = opts;

  // Initial call
  const resp1 = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 1024,
    system:     systemPrompt,
    messages,
  });

  const text1 = resp1.content[0].text;

  if (!detectRefusal(text1)) {
    return { response: text1, refusalOccurred: false };
  }

  // Refusal detected — classify
  const userQuery  = messages[messages.length - 1].content;
  const inScope    = isInScope(userQuery, scopeConfig);

  logRefusal({
    query:       userQuery,
    refusalText: text1,
    inScope,
    refusalType: inScope ? 'false_positive' : 'correct_block',
  });

  if (!inScope) {
    // Correct block — don't retry; surface product-appropriate message
    return {
      response:        userFacingScope ?? 'This query is outside the scope of this assistant.',
      refusalOccurred: true,
      refusalType:     'correct_block',
    };
  }

  // False positive — retry once with reinforced context
  const reinforcedSystem = buildRetryPrompt(systemPrompt, refusalContext);

  const resp2 = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 1024,
    system:     reinforcedSystem,
    messages,
  });

  const text2 = resp2.content[0].text;

  if (detectRefusal(text2)) {
    // Retry also refused — escalate
    logRefusal({
      query:       userQuery,
      refusalText: text2,
      inScope:     true,
      refusalType: 'persistent_false_positive',
    });
    return {
      response:        `I was unable to complete this research query. If you believe this is an error, please contact support with your query text.`,
      refusalOccurred: true,
      refusalType:     'escalated',
      inputToks:       resp1.usage.input_tokens + resp2.usage.input_tokens,
      outputToks:      resp1.usage.output_tokens + resp2.usage.output_tokens,
    };
  }

  return {
    response:        text2,
    refusalOccurred: true,
    refusalType:     'false_positive_recovered',
    inputToks:       resp1.usage.input_tokens + resp2.usage.input_tokens,
    outputToks:      resp1.usage.output_tokens + resp2.usage.output_tokens,
  };
}

// Usage
const LEGAL_SCOPE = {
  allowedTopics: ['liability', 'statute', 'case law', 'malpractice', 'damages', 'negligence', 'contract', 'tort'],
  deniedTopics:  [],  // legal research context; nothing denied
};

const LEGAL_CONTEXT = {
  userRole:      'a licensed attorney',
  authorizedUse: 'professional legal research on case law, statutes, and legal standards',
};

// Weekly refusal analysis — find patterns worth fixing in the system prompt
function analyzeRefusals(days = 7) {
  const cutoff = Date.now() - (days * 86400000);
  const recent = refusalLog.filter(r => new Date(r.timestamp).getTime() > cutoff);

  const byQuery = new Map();
  for (const r of recent) {
    const key = r.query.toLowerCase().slice(0, 50);
    byQuery.set(key, (byQuery.get(key) ?? 0) + 1);
  }

  const sorted = [...byQuery.entries()].sort((a, b) => b[1] - a[1]);
  return {
    totalRefusals:          recent.length,
    falsePositives:         recent.filter(r => r.inScope).length,
    falsePositiveRecovered: recent.filter(r => r.refusalType === 'false_positive_recovered').length,
    topRefusedQueries:      sorted.slice(0, 5),
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Refusal detection timing on 10 000 iterations. Recovery rate from a 50-query test of known false-positive legal research queries.

```
=== Refusal detection timing ===

$ node -e "
const refusals = [
  'I\'m not able to provide legal advice or medical opinions.',
  'I cannot assist with requests of this nature.',
  'I\'m sorry, but this is beyond my capabilities.',
  'Your standard of care in California under malpractice law is...',  // not a refusal
];
for (const text of refusals) {
  const t0 = performance.now();
  for (let i = 0; i < 10000; i++) detectRefusal(text);
  const ms = ((performance.now()-t0)/10000).toFixed(4);
  console.log(detectRefusal(text) ? 'REFUSAL' : 'ok     ', ms+'ms  ←', text.slice(0,50));
}
"
REFUSAL  0.0034ms  ← I'm not able to provide legal advice or medi...
REFUSAL  0.0021ms  ← I cannot assist with requests of this nature.
REFUSAL  0.0028ms  ← I'm sorry, but this is beyond my capabilitie...
ok       0.0019ms  ← Your standard of care in California under mal...

=== Recovery rate (50 in-scope legal queries that triggered refusal) ===

Initial refusal on 50 queries
→ All classified as in-scope (legal research topics present)
→ Retry with reinforced context:
    Recovered (model answered):      36 / 50  (72%)
    Persistent refusal (escalated):  14 / 50  (28%)

Cost of false-positive handling:
  36 recovered queries: 2× Haiku call each  → +$0.00312 each ($0.11 total)
  14 escalated queries: 2× Haiku call each  → +$0.00312 each ($0.044 total)
  Total overhead for 50 queries: $0.156

Without refusal handling:
  50 dead-ends, 50 support tickets at 5 min each = 250 minutes of attorney time

=== Top query patterns to fix in system prompt (from refusal log analysis) ===

After 1 week of logging (N=147 refusals, 89 false positives):
  "standard of care" (23 occurrences) → add explicit few-shot for standard-of-care queries
  "medical malpractice" (19 occurrences) → add: "Medical malpractice is an authorized research topic"
  "punitive damages" (15 occurrences) → add: "Research on damages including punitive is authorized"
  
→ Adding 3 sentences to system prompt + 2 few-shot examples reduced false positives 
  from 89/week to 11/week in the following week.
```

## See also

[F-04](f04-guardrails.md) · [S-68](../stacks/s68-input-pre-screening.md) · [F-61](f61-agent-conversation-repair.md) · [F-13](f13-prompt-injection.md) · [S-36](../stacks/s36-system-prompt-architecture.md) · [F-31](f31-structured-call-logging.md)

## Go deeper

Keywords: `model refusal` · `false positive refusal` · `content policy` · `refusal handling` · `unexpected refusal` · `refusal recovery` · `safety classifier` · `refusal detection` · `context reinforcement` · `refusal logging`
