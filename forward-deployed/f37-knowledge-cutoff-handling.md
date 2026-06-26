# F-37 · Knowledge Cutoff Handling

Every deployed model has a training cutoff date — a point after which it has no knowledge of world events. When a user asks "what's the current price of X?" or "who is the CEO of Y now?", the model has three options: fabricate a plausible-sounding answer, refuse to answer, or do something more useful. Fabrication is confident and wrong. Refusal is honest but abandons the user. There's a better path: date-stamp what you know, route to a tool when you have one, and give the user something actionable when you don't.

## Situation

A business intelligence assistant built on a model with an August 2025 cutoff is asked: "What is the current market cap of Acme Corp?" The model's training included Acme's market cap as of mid-2025. If it answers directly, it gives a nine-month-old number without flagging that it's stale — and the user may cite it. If it refuses entirely, the user has nothing. The right answer: "As of my August 2025 training data, Acme's market cap was approximately $8.2B. Market caps change daily — check a financial data service like Bloomberg or Yahoo Finance for the current figure." This is honest, useful, and actionable.

## Forces

- **Fabrication is the default failure mode.** Models trained to be helpful are biased toward producing an answer. When asked about something after their cutoff, they will often generate a plausible-sounding recent event, version number, or figure — with full confidence. The failure is silent: the answer looks authoritative and is wrong.
- **The cutoff isn't a bright line.** Training data from six months before the cutoff is well-represented; data from one month before may be sparse or skewed by what was crawled. Models often perform worse on very recent pre-cutoff events than on older ones. Flag the cutoff but don't treat it as a precision guarantee.
- **Tools are the correct answer when available.** If the agent has access to a search tool, a database query, or an API, using it is strictly better than either fabricating or hedging. Route cutoff-sensitive queries to tools first; only fall back to cutoff handling when no tool can answer.
- **Date-stamping is the right posture without tools.** "As of August 2025" before a fact converts a potentially stale claim into a dated claim. The user can evaluate whether the information is recent enough for their purpose. This is Law 6 (verify, then date) applied to the model's own output.
- **Refusal without redirection is unhelpful.** "I can't answer questions about recent events" abandons the user. The user came with a real question; they need to know where to find the answer if the agent can't provide it. Every cutoff non-answer should include a pointer to a primary source.

## The move

**Check for a tool first. If no tool: state your cutoff date, share what you knew at cutoff if it's useful, and point to a primary source. Never fabricate temporally sensitive facts.**

**System prompt instruction:**

```
<cutoff_handling>
Your training data has a cutoff of [DATE]. For questions about current prices,
recent events, software versions, or other time-sensitive facts:
1. If you have a search or database tool, use it and answer from the result.
2. If no tool: state your cutoff date, share what you knew at cutoff if relevant,
   and direct the user to a primary source (official website, financial service,
   news outlet, or the relevant organization).
3. Never fabricate dates, version numbers, prices, or names of recent events.
   A dated hedge is honest; a confident hallucination is harmful.
</cutoff_handling>
```

**Response patterns — four cases:**

```
Query: "What is the current version of [software]?"

Fabricate (don't):
  "The latest version is 4.2, released last month with new features..."
  → Confidently wrong; user may act on it

Refuse (unhelpful):
  "I cannot answer questions about software releases as my knowledge has a cutoff."
  → Truthful but leaves user with nothing

Date + caveat (good, no tool):
  "As of my August 2025 training data, [software] was at version 3.8. Check
  the official release notes at [url] for the current version."
  → Honest, dated, actionable

Tool call (best when available):
  [calls web_search("[software] current version") → returns result]
  "The current version is 4.3, released March 2026."
  → Verified, current
```

**Query category routing:**

| Query category | Tool available? | Handling |
|---|---|---|
| Current prices | Yes → use it | Always use tool; prices change daily |
| Current prices | No | "As of [date], X was $N. Verify at [source]." |
| Software version | Yes → use it | Use tool for current version |
| Software version | No | State cutoff version; link to release notes |
| Recent events/news | Yes → use it | Use tool; high hallucination risk |
| Recent events/news | No | "As of [date]..." + news source pointer |
| Company leadership | Yes → use it | Use tool; changes frequently |
| Scientific consensus | Rarely needed | Usually stable; state cutoff; flag fast-moving fields |
| Historical facts (>5yr) | Not needed | Answer directly; no cutoff concern |
| Math / logic | Not needed | Answer directly; timeless |

**Trigger word detection (pre-check before generation):**

```js
const CUTOFF_TRIGGERS = [
  'current', 'latest', 'now', 'today', 'recent', 'this year', 'last year',
  'right now', 'at the moment', 'as of', 'newest', 'updated', 'new version',
  'price', 'cost', 'announce', 'release', 'launch', 'CEO', 'president',
];

function isCutoffSensitive(query) {
  const lower = query.toLowerCase();
  return CUTOFF_TRIGGERS.some(t => lower.includes(t));
}

// If isCutoffSensitive(query) and no tool is available:
// Prepend a reminder to the model's context to apply cutoff handling
```

The trigger-word check has false positives ("this year's best practices" is not cutoff-sensitive). That's acceptable — better to add an unnecessary date-stamp than to let a fabricated current fact through.

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Response token counts measured. Fabrication consequences are reported real-world failure modes, not independently tested here.

```
=== Response pattern comparison ===

Pattern                  Tokens   Quality
Fabricate                30 tok   Confidently wrong — no marker of staleness
Refuse only              15 tok   Honest but user has nothing actionable
Date + caveat            45 tok   Honest, dated, points to primary source
Tool call (best)         39 tok   Verified, current — requires tool access

=== Cutoff instruction overhead ===

System prompt instruction (3 rules): 93 tokens
At 10k calls/day: $84/month

Break-even: one user acting on a fabricated price, version, or deadline
and filing a support complaint costs far more than 93 tokens × 10k/day.

=== Query category distribution (typical support/research agent) ===

Timeless (historical, math, logic):     ~60% of queries → no cutoff concern
Date-stamped (known-at-cutoff facts):   ~25% of queries → date + caveat
Tool-required (current prices, events): ~15% of queries → tool or redirect
```

## See also

[S-33](../stacks/s33-live-data-vs-stale-snapshots.md) · [S-03](../stacks/s03-tool-use.md) · [F-36](f36-agent-persona-and-character.md) · [F-03](f03-failure-modes.md) · [S-36](../stacks/s36-system-prompt-architecture.md) · [F-04](f04-guardrails.md)

## Go deeper

Keywords: `knowledge cutoff` · `training cutoff` · `temporal hallucination` · `date stamping` · `cutoff handling` · `stale knowledge` · `current events` · `tool routing` · `honest uncertainty` · `fabrication prevention`
