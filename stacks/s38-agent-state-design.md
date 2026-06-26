# S-38 · Agent State Design

Context is the agent's working memory — it fills up, gets cut, and grows linearly with every turn. State is its filing cabinet — explicit, typed, and compact. Most agents keep everything in context and treat the conversation history as the record of what happened. That works for short tasks. For multi-step tasks it is expensive, lossy, and impossible to inspect. The fix is not a framework — it is a design decision: put task-tracking fields in a structured state object and inject only what the current turn needs.

## Situation

Your 10-step agent loses track of where it is by turn 7. Or a task that worked in testing fails silently in production because the history grew past a threshold and earlier results got cut. Or you can't debug a failure because the agent's "reasoning" is buried in 3,000 tokens of conversation and the only way to know what happened is to read the whole thing. These are not model failures. The task state was never made explicit.

## Forces

- Conversation history grows linearly with turns; a structured state object grows with *completed work*, not with *turns*. At turn 10, a history might carry 576 tokens; the equivalent state object carries 303. At turn 20 the gap is 699 tokens — per call, permanently.
- History has no index. To know what happened at step 3, something must read the whole history. A state object with a `completed` map is O(1) lookup.
- The agent reads context as one stream (see [S-13](s13-context-engineering.md)). Results buried in turn 4 of a 15-turn history compete for attention with everything that came after. A state field injected at the top of the prompt is always salient.
- [F-15](../forward-deployed/f15-durable-execution.md) is about crash recovery: checkpoint the state, resume from the last step. This is about the *design* of the state being checkpointed — what fields, what schema, what invariants. Both are needed.
- [S-09](s09-memory-systems.md) is about what the agent *knows* across sessions (episodic, semantic, procedural memory). Task state is what the agent *is doing right now* — a different scope and a different lifecycle.
- State that is explicit is state you can test, monitor, and alert on. State that lives only in context is invisible to any system that is not reading the full transcript.

## The move

**Design a task state object with six fields.**

```json
{
  "task":        "The original goal — verbatim from the user, never changed",
  "step":        3,
  "total_steps": 5,
  "status":      "in_progress",
  "completed": {
    "fetch_data": { "rows": 1847, "skus": 94 },
    "rank_skus":  { "top3": ["SKU-F22 -72.7%", "SKU-A09 -62.9%", "SKU-B44 -55.9%"] }
  },
  "next":        "generate_report",
  "error_count": 0
}
```

**`task`** — the original goal, injected every turn. Agents drift when the goal is only in the first message and grows distant as the history accumulates. Repeating it is cheap (one sentence); recovering from goal-drift is expensive.

**`step` + `total_steps`** — explicit position. Never derive where the agent is from the last assistant turn — that is parsing prose to get a number that should be a field.

**`status`** — a finite set: `in_progress`, `waiting_for_tool`, `waiting_for_human`, `done`, `failed`. The status field is what makes a paused agent resumable and a monitoring dashboard meaningful.

**`completed`** — per-step results keyed by step name. This replaces reading history. The model in turn 8 doesn't need to see the tool output from turn 2; it needs the structured result from that step, in 20 tokens, not 200.

**`next`** — the action the agent will take next, explicit. Not inferred from the last assistant turn. Makes the step transition testable: assert `next == "generate_report"` before running that step.

**`error_count`** — tracks retry pressure at the task level. Not visible from streamed output. Feeds the retry budget ([F-20](../forward-deployed/f20-rate-limits-and-retry.md)) and triggers escalation when it exceeds a threshold.

**Inject state at the top of each turn's prompt, not at the bottom.** Context position matters ([S-36](s36-system-prompt-architecture.md)); the state object should be the first thing the model reads after the system prompt, not buried after a long history.

**Keep history for the current turn only; archive everything else.** The agent needs to see the most recent tool output. It rarely needs the tool output from five turns ago — that result should live in `completed`, not in an ever-growing transcript.

**Persist state to a key-value store after every step — not to the context window.** State in context disappears when the context is compacted or truncated. State in a KV store is what F-15's checkpointing operates on. The state object is the artifact; the context window is the scratchpad.

## Receipt

> Verified 2026-06-26 — Node, `gpt-tokenizer`. A realistic 7-turn conversation history (fetch data → rank SKUs → prepare report) is compared to an equivalent structured state object. Turn-growth model: history grows ~linearly with turns; state object grows slowly (new `completed` entry per step, ~15 tokens each). Both are measured on the same task content.

```
=== Context-only vs explicit state per turn ===
Conversation history (7 turns):   336 tokens
Explicit state object:             153 tokens
Ratio:                             2.2x  (history is larger)

Full prompt to model at turn 7:
  Context-only:   351 tokens
  State-aware:    175 tokens
  Savings:        176 tokens  (50% reduction)

=== Token growth across turns (history vs state) ===
Turn   history   state   savings
   1        58     168     -110   ← state costs more at first
   3       173     198      -25   ← break-even approaching
   5       288     228       60   ← state wins
  10       576     303      273
  20      1152     453      699   ← 699 tokens saved per call
```

**What the receipt shows:**

- Explicit state costs *more* than history at turn 1 (168 vs 58 tokens). This is the honest trade-off: the overhead of a structured object is real and not worth it for a 1-step task.
- Break-even is around turn 3–5. By turn 10 the state object is saving 273 tokens per call — permanently, on every turn from that point forward. By turn 20, 699 tokens per call.
- The 50% per-turn reduction at turn 7 isn't a trick; it is the difference between injecting 153 tokens of structured results vs 336 tokens of conversational history that restates those results in prose.
- The inspectability benefit has no token cost: `state.completed.rank_skus.top3[0]` is a lookup; finding the same fact in 336 tokens of history requires reading all of it.

## See also

[F-15](../forward-deployed/f15-durable-execution.md) · [S-09](s09-memory-systems.md) · [S-13](s13-context-engineering.md) · [S-21](s21-context-compaction.md) · [F-20](../forward-deployed/f20-rate-limits-and-retry.md)

## Go deeper

Keywords: `agent state` · `task state` · `state object` · `context vs state` · `status field` · `completed map` · `state injection` · `inspectability` · `state schema` · `multi-step agent`
