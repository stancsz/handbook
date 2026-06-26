# The Laws

The fixed front of the handbook. Everything else hangs from these. They move rarely and never silently.

---

## Law 1 · Cheapest sufficient intelligence

Use the smallest model and the least context that does the job. Reach up only when the job proves it needs it.

A GPT-4-class call costs 10–100× a small model call. Most tasks don't need the frontier. Classification, extraction, simple summarization: start small. If quality fails, move up — but measure first, don't guess.

**The ladder:** local 7B → hosted small (Haiku, GPT-4o-mini) → hosted mid (Sonnet, GPT-4o) → frontier (Opus, GPT-5). Climb only when the rung below provably fails.

---

## Law 2 · Tokens are the budget

Every token spent is defended or cut. This is not a style preference — it is arithmetic.

Input tokens cost money. Output tokens cost more. Context length limits what fits. Bloated prompts push useful information out. Bloated outputs hide the signal. The model that writes less is often right more.

This law applies to the handbook's own prose.

---

## Law 3 · Receipts over claims

Show the count, the break, the date. An entry without a receipt is a guess wearing a lab coat.

A technique that "works" without evidence is folklore. A cost estimate without a run log is fiction. A model comparison without a benchmark is marketing. Mark everything with when it was verified. The frontier moves; honesty about staleness is the moat.

`Receipt pending` is an honest stub. A fabricated receipt is disqualifying.

---

## Law 4 · Plain names

A thing is named what it does. No codenames, metaphors, or branding.

"Semantic layer" → context injection. "Brain of the agent" → system prompt. "Orchestration fabric" → the loop that calls tools. Plain names travel farther — they work in search, in conversation, and in code.

---

## Law 5 · Ship the atom

Every entry must stand on its own, out of context, on a hostile feed.

No entry should require reading anything else to be useful. Cross-link for depth, not for dependency. If you can't ship the entry to someone who found it via a search engine at 2am — cut it or rewrite it until you can.

---

## Law 6 · Verify, then date

Mark what was true and when you confirmed it. The frontier moves; honesty about staleness is the moat.

A model capability verified in 2024 may be obsolete in 2025. A cost figure from last quarter may be half what it is today. Every claim in the handbook carries a timestamp, explicit or implied by the entry's last-verified date. Staleness is not failure — unacknowledged staleness is.

---

## Amending a Law

Rare. Must have a written reason. Must be recorded in [CONTRIBUTING.md](CONTRIBUTING.md). The entry that exposed the flaw goes in the receipt.
