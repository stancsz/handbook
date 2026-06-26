# S-28 · Progressive Disclosure

Don't load everything the agent *might* need up front. Load a lightweight **index** — names and one-line descriptions — and pull an item's full content only when the task actually reaches for it. The temporal dimension of [context engineering](s13-context-engineering.md): right content, right moment.

## Forces
- Most reference material, tools, and docs never fire on any given task — front-loading them all is pure waste
- An oversized window doesn't just cost tokens; it degrades the answer (context rot, [S-13](s13-context-engineering.md))
- But the agent can't use what it doesn't know exists — it needs *some* signal that an item is available
- A two-step "look, then load" costs an extra round-trip, and a bad index description means the agent fetches the wrong thing

## The move
- **Index first, body on demand.** Keep a compact catalog in context: `id: one-line description` per item. The body loads only when the agent picks that id.
- **Make the agent choose.** Show the index, let it name the item it needs for the current subtask, then fetch only that. This is index-based / just-in-time loading.
- **Agent Skills are the standard instance.** A SKILL.md header (~60 tokens) is always in context; the multi-hundred-token body loads only when the skill triggers ([S-20](s20-agent-skills.md)). Same idea applies to docs, schemas, and large tool sets ([S-22](s22-tool-selection-at-scale.md)).
- **Invest in the descriptions.** The index line is the *only* thing the agent sees when deciding — a vague description is a silent retrieval failure. Treat it like the docstring it is.
- **Know when not to.** If almost every task needs almost every item, the index step is pure overhead — just load it. Progressive disclosure wins when the hit rate per item is low.

## Receipt
> Verified 2026-06-25 — a 5-doc support knowledge base, query "refund on a $90 order from last week — what's the rule?", against llama3.2 (Ollama, localhost:11435). Naive (load all docs) vs. progressive (load index → agent picks → load one doc). Context measured in characters (a reliable proxy; the bridge's token counts aren't).

```
NAIVE (load all 5 docs):              context = 698 chars   answer correct: yes
PROGRESSIVE (index -> pick -> 1 doc): context = 270 chars   answer correct: yes
  agent picked: "refunds" (the correct doc)
context cut: 61% less, same answer
```

The agent read a 5-line index, named the right doc, and answered from *only* that doc — 61% less context for an identical answer. The win compounds with scale: the index grows one line per item, but every un-fired body stays out of the window. With five short docs it's 61%; with dozens of multi-hundred-token skills or files, deferring the bodies is the difference between a focused window and context rot. The cost is the extra "pick" call and a dependence on good index descriptions — here the description was enough for the model to choose correctly.

## See also
[S-13](s13-context-engineering.md) · [S-20](s20-agent-skills.md) · [S-22](s22-tool-selection-at-scale.md) · [S-21](s21-context-compaction.md) · [S-09](s09-memory-systems.md)

## Go deeper
Keywords: `progressive disclosure` · `just-in-time context` · `index-based loading` · `Agent Skills` · `SKILL.md` · `context rot` · `lazy loading` · `context engineering` · `tool retrieval`
