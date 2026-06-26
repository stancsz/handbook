# S-13 · Context Engineering

Curating the smallest high-signal set of tokens the agent needs to succeed — and stripping everything else. The discipline that contains prompt engineering and RAG, not a rival to them.

## Forces
- More context *feels* safer; it isn't — every frontier model degrades as the window fills ("context rot," Chroma 2025)
- Token spend is dollar spend, and a bloated window dilutes the signal the model attends to
- Prompt caching cuts cost, not quality — a perfect prompt inside a bloated context still underperforms
- The failure is silent: answers drift and the agent loses the thread before you notice

## The move

The job: find the fewest tokens that maximize the chance of the right outcome. Four levers, plus a layout rule.

- **Offload.** Push stable, bulky info (documents, long tool outputs, scratch history) out of the prompt — onto disk, a vector store, or behind a tool. Pull it back only when the current turn needs it. See [S-09](s09-memory-systems.md).
- **Retrieve.** Fetch dynamic info lazily. Don't front-load everything the agent *might* need; pay for what it actually uses. See [S-07](s07-rag.md).
- **Isolate.** Keep subtasks in separate contexts so one branch's scratchwork can't poison the next. This is when sub-agents earn their cost. See [S-05](s05-multi-agent-patterns.md).
- **Compact.** Summarize history proactively. Budget by *fill percentage*, not raw token count — compact past ~60% to keep headroom before quality drops. See [S-21](s21-context-compaction.md) for the compact-and-continue pattern with a real run.
- **Split static from dynamic.** System prompt and tool schemas go at the front and get cached ([S-08](s08-prompt-caching.md)); user input and tool outputs stay minimal at the tail.

This is the operational form of [Law 2](../laws.md) (Tokens are the budget): every token is defended or cut.

## Receipt
> Term formalized by Anthropic, Sept 2025 — ["curating and maintaining the optimal set of tokens during LLM inference"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents). ["Context rot"](https://research.trychroma.com/context-rot) measured by Chroma (Hong, Troynikov, Huber — July 2025): all 18 frontier models tested degraded as input length grew, well before the window filled. Distinct from context-window *overflow* — a 200K model can rot at 50K. The ~60% compaction threshold is a working rule of thumb, not a measured optimum — re-derive per model. Sources verified 2026-06-25; the frontier moves fast, so re-check the framing against current Anthropic docs.

## See also
[S-21](s21-context-compaction.md) · [S-28](s28-progressive-disclosure.md) · [S-02](s02-context-budget.md) · [S-07](s07-rag.md) · [S-08](s08-prompt-caching.md) · [S-09](s09-memory-systems.md)

## Go deeper
Keywords: `context engineering` · `context rot` · `compaction` · `context window management` · `AGENTS.md` · `prefix caching` · `Anthropic context engineering`
