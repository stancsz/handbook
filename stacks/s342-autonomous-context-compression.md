# S-342 · Autonomous Context Compression

Long-horizon AI agents don't fail because the model forgets. They fail because the context does — silently, progressively, before the window is full. Context drift (the gradual dilution of relevant information in a growing message history) kills 65% of enterprise agent sessions before they hit token limits. Autonomous context compression solves this by letting the agent itself decide when and how to summarize its own history — before drift compounds into failure.

## Forces

- **Context grows unbounded.** Each turn adds user input + model output + tool results. A 50-turn coding agent session reaches 200K+ tokens. At that size, the LLM increasingly ignores early context (lost-in-the-middle) while you pay full price for every redundant token.
- **Context drift is silent.** The model doesn't signal when context quality degrades. It just produces progressively worse reasoning. By the time you notice, the session is unrecoverable — you can only restart.
- **Static summarization is wrong.** Summarizing at fixed token thresholds ignores task state. A 50-turn session that spent 45 turns on an unrelated subtask should compress differently than one that built incrementally on the same goal. Only the agent knows what's still relevant.
- **Provider limits are hard.** 128K context sounds large. At 5 tool calls per turn, a 30-turn session consumes ~180K tokens including results — before you've done anything meaningful. Budget management must be proactive, not reactive.

## The move

Autonomous context compression replaces static token-counting with an agent-driven compaction strategy. The core idea: the agent decides what to retain, what to summarize, and when to compact — based on task state, not just byte count.

**Three compaction strategies (state of the art, 2026):**

**1. Iterative Summarization (most common)**
Periodically invoke the LLM itself to summarize a block of conversation history into a compact episodic memory. The summary replaces the original messages. New turns continue from the compressed state.

```python
from google.adk.apps import App
from google.adk.summarizer import LlmEventSummarizer, EventsCompactionConfig
from google.adk.models import Gemini

# Summarizer model — cheaper/faster than the main agent model
summarizer_llm = Gemini(model="gemini-2.5-flash")

app = App(
    name="compressed-agent",
    root_agent=root_agent,
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,   # compact every 3 events
        overlap_size=1,          # keep 1 event of overlap for continuity
        summarizer=LlmEventSummarizer(llm=summarizer_llm),
    ),
)
```

**2. Failure-Driven Guideline Optimization (ACON)**
Instead of summarizing conversation, identify *failure patterns* (repeated tool-call failures, re-planning cycles, loop detections) and distill them into lightweight procedural rules injected into the system prompt. Reduces context overhead while encoding institutional memory.

**3. Provider-Native Compaction**
Use provider APIs that handle compaction automatically. OpenAI's Assistants API, Google's ADK, and Azure AI Agent Service all offer built-in compaction with configurable triggers. Trade control for operational simplicity.

**Triggering — choose one:**

| Strategy | Trigger | Best for |
|---|---|---|
| Token-based | Hard threshold (e.g., 80% of context budget) | Unpredictable workloads, external data ingestion |
| Turn-based | Fixed number of turns (e.g., every N interactions) | Predictable session patterns, dashboards |
| Semantic | LLM detects relevance decay | High-value sessions, complex multi-task agents |
| Hybrid | Token threshold + semantic signal | Production systems with SLAs |

**What to retain during compression:**
- **Anchor facts** — user identity, preferences, active task goals (never summarize away)
- **Tool definitions** — static; should never enter compression scope
- **Recent episodic state** — last 2-3 turns always preserved (overlap strategy)
- **Failure memory** — what went wrong in prior turns feeds ACON rules

**What to discard:**
- Redundant tool result data older than the compression window
- Exploratory turns that didn't contribute to the final plan
- Repeated context that appears in multiple prior summaries

## Receipt

> Receipt pending — 2026-07-02
> Token-based compaction via Google ADK Python SDK was the primary reference. Full end-to-end run with a 50+ turn session against a live agent would confirm that iterative summarization preserves task continuity — pending an active Google ADK deployment. The ACON pattern was synthesized from agentic memory literature and production failure analysis (Zylos Research, 2026-02).

## See also

- [S-09 · Memory Systems](s09-memory-systems.md) — episodic vs semantic vs procedural memory tiers
- [S-02 · Context Budget](s02-context-budget.md) — treating context as a budget, not a bucket
- [S-111 · Partial Context Refresh](s111-partial-context-refresh.md) — the 70% trigger + state extraction pattern
- [F-63 · Mid-Task Context Recovery](f63-mid-task-context-recovery.md) — recovery when compression goes wrong
