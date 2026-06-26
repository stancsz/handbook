# R-09 · Long-Context Models

As of mid-2026, thirteen frontier models ship 1M+ token context windows. Llama 4 Scout reaches 10M. The practical question for builders is no longer "can it fit?" — it's "does it actually attend to what I put in there, and what changed about how I architect around it?"

## Forces

- A 1M-token window holds roughly 40,000 lines of code or 1,500 pages of text — entire codebases and case files now fit in a single prompt, collapsing whole retrieval architectures
- Bigger windows didn't fix "lost in the middle" — they gave models more middle to lose things in; recall degrades as input length grows, and multi-needle retrieval degrades faster than single-needle
- Advertised window size ≠ effective context: models score near-perfect on single-needle tests at 1M tokens but drop significantly on multi-fact tasks at the same length (the gap is the real number to test)
- The output cap now binds before the input cap for large generative tasks: a model reading 1M tokens and writing 64K per turn needs multiple round trips for large refactors, re-paying input cost each time
- RAG isn't dead; it's been reclassified — for single-document reasoning, long context often beats retrieval; for multi-source, high-recall tasks, retrieval is still cheaper and more reliable

## The move

**Test multi-needle, not single-needle.** "Needle in a haystack" at 90%+ recall looks good; three needles in the same haystack at the same length is the honest test. Benchmark your specific model at your specific input length before trusting the advertised window.

**Curate aggressively even with headroom.** The old skill was fitting things into 4K. The new skill is deciding what fills the 1M — irrelevant context dilutes signal, increases cost, and worsens attention distribution. Long context is not free context.

**Structural injection beats whole-document dumping.** Place the most decision-critical information at the start or end of the context, not buried in the middle. Format distinct sections clearly (headers, section labels) so the model can locate them without scanning the full context.

**Segment large generative tasks.** If total output exceeds your model's output limit per turn, plan for multiple rounds. Each round re-reads the full context — budget accordingly.

**Keep RAG for multi-source retrieval.** Long context excels at deep reasoning over one or a few documents you've already curated. RAG still wins when you need to find the relevant document from a large corpus, not reason over a document you already have.

## Receipt

> Verified 2026-06-26 — needle-in-haystack at small scale (2,784-char / ~700-token document, 10 sections), llama3.2 via Ollama (localhost:11435).

```
Single-needle by position (3 draws each, T=0):
  Target at beginning (section 1):  3/3 correct
  Target at middle    (section 5):  3/3 correct
  Target at end       (section 9):  3/3 correct

Multi-needle (3 targets, 10 sections, 1 prompt):
  Cedar Task Force budget:   5,217  -> CORRECT
  Zelkova Project budget:   47,332  -> CORRECT
  Ginkgo Review budget:      8,500  -> CORRECT
```

At 700 tokens, llama3.2 shows no position-dependent degradation and handles all three needles correctly. The "lost in the middle" effect emerges at scale: independent benchmarks (the RULER suite and similar evaluations) document recall degradation across all tested models as context length grows, with multi-needle tasks showing steeper drops than single-needle. The local POC confirms the mechanism is testable; the scale at which it bites depends on model, task type, and input length — measure it for your specific setup.

## See also

[S-13](../stacks/s13-context-engineering.md) · [S-07](../stacks/s07-rag.md) · [S-28](../stacks/s28-progressive-disclosure.md) · [S-02](../stacks/s02-context-budget.md)

## Go deeper

Keywords: `lost in the middle` · `needle in a haystack` · `RULER benchmark` · `effective context length` · `long-context evaluation` · `multi-needle retrieval` · `context rot` · `KV cache` · `positional encoding` · `RoPE`
