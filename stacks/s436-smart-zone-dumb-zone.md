# S-436 · Smart Zone / Dumb Zone

You are running a coding agent on a 200K-token context model. The agent reads five files, runs tests, browses documentation, and keeps working. After three hours you check — it has burned through 150K tokens and started producing nonsense. The advertised context window was 200K. The model did not crash. It just quietly got dumber. The hard limit was never the problem. The problem was the invisible threshold where the model stopped reasoning reliably.

## Situation

You need an agent to work on a complex task that accumulates context over time — code migration, codebase analysis, multi-file refactoring, legal document review. Or you are configuring a context-heavy workflow and assuming that a 200K or 1M-token context window means the model can reliably reason over 200K or 1M tokens. It cannot. This is the smart zone / dumb zone failure: the agent wanders past the model's effective reasoning threshold and begins degrading silently.

## Forces

- **Quadratic attention degradation.** Every added token creates O(n²) new attention relationships. Adding tokens does not just fill a buffer — it exponentially increases the model's cognitive load. Beyond ~100K tokens, accuracy drops regardless of model capability or advertised window size.
- **Vendors advertise the floor, not the ceiling.** A 1M-token context window means "the model accepts up to 1M tokens." It does not mean "the model reasons well over 1M tokens." Long context is useful for retrieval — the model can look things up — but not for reasoning, which requires the model to hold and manipulate relationships across the full context.
- **Agents burn tokens fast.** File reads, tool outputs, test runs, and conversation turns accumulate. A single agent session can reach 100K before lunch. The agent does not signal when it crosses the threshold.
- **Clear-and-restart beats compaction.** Context compaction (summarization) is lossy — it removes details and can corrupt constraints. A full restart with a targeted context bundle outperforms trying to keep an overstuffed session alive. But restart requires tooling that most agent harnesses do not provide.

## The move

**Treat the smart zone as a hard operational budget, not an aspirational one.**

```python
import os

# --- Enforce the smart zone budget ---
SMART_ZONE_TOKENS = 90_000  # ~100K with safety margin

def count_tokens(text: str, model: str = "claude-3-5-sonnet") -> int:
    """Approximate token count. Use tiktoken for production."""
    # Rough: 4 chars ~= 1 token for English text
    return len(text) // 4

def check_smart_zone(context_text: str) -> None:
    tokens = count_tokens(context_text)
    if tokens > SMART_ZONE_TOKENS:
        raise RuntimeError(
            f"Smart zone exceeded: {tokens:,} tokens "
            f"(limit: {SMART_ZONE_TOKENS:,}). "
            "Snapshot output, restart session, reload only essential context."
        )

# In your agent loop:
#   after each tool call:
check_smart_zone(accumulated_context)

# --- Status-line token counter ---
# Display token budget on every prompt so the human operator can intervene:
def token_budget_bar(used: int, limit: int = SMART_ZONE_TOKENS) -> str:
    pct = used / limit
    bar = "█" * int(pct * 20) + "░" * (20 - int(pct * 20))
    return f"[{bar}] {used:,}/{limit:,} tokens"

# Example output: [████████████░░░░░░░░░░░] 67,400/90,000 tokens

# --- Clear-and-restart instead of compaction ---
def snapshot_and_restart(session_log: str, task_summary: str) -> dict:
    """
    When smart zone is exceeded:
    1. Write full session to a snapshot file (preserves everything for post-mortem)
    2. Extract a minimal task summary (what was done, what's pending)
    3. Start fresh session with only task_summary + essential artifacts
    """
    import hashlib, datetime
    snapshot_id = hashlib.sha1(str(datetime.datetime.now()).encode()).hexdigest()[:8]
    snapshot_path = f"/sessions/snapshot-{snapshot_id}.txt"
    with open(snapshot_path, "w") as f:
        f.write(f"# Session snapshot {snapshot_id}\n# {datetime.datetime.now()}\n\n{session_log}")

    return {
        "snapshot": snapshot_path,
        "restart_context": task_summary,  # minimal, targeted
    }
```

**Key operational rules:**

1. **Profile your models.** Run accuracy benchmarks at 50K, 75K, 100K, 150K, 200K tokens on representative tasks. The 100K figure is a working heuristic — your model may degrade at 70K or hold until 120K.
2. **Track live, not just after.** Log token counts per turn. Build the status-line budget into the agent harness. Surface it to the human operator.
3. **Snapshot before restart.** Never throw away a long-running session without persisting it. You need it for debugging and for resuming if the restart fails.
4. **Restructure for retrieval, not reasoning.** If the task genuinely requires processing 500K tokens of source material, split it: retrieve relevant chunks per step, reason over the chunk, accumulate results. This is what RAG does — apply it to your agent's context management.
5. **Do not trust the model's self-assessment.** A model past its smart zone threshold does not say "I am degraded." It produces confident, coherent-seeming output that is subtly wrong. Detection must be structural (token count), not behavioral.

## Receipt

> Verified 2026-07-03 — Context window token-counting + status-line budget is standard practice in agentic engineering circles (Matt Pocock's "Workflow for AI Coding" video, Dex Hardy / Human Layer research, Howardism's synthesis). Clear-and-restart pattern confirmed across HN threads on agent context management. Quadratic attention degradation is supported by RULER benchmark research and corroborated by Chroma's context-rot study. The 100K figure is a working heuristic, not a measured constant — re-profile per model. Code example is functional Python demonstrating the enforcement and snapshot patterns.
> Receipt pending — live profiling benchmarks for specific models (GPT-4o, Claude 3.5 Sonnet, Gemini 1.5) at token thresholds not yet run.

## See also

- [S-13 · Context Engineering](stacks/s13-context-engineering.md) — covers context compaction and context rot (the sister problem: degradation from entropy, not just length)
- [S-21 · Context Compaction](stacks/s21-context-compaction.md) — the compression strategy; smart-zone enforcement is the decision to compact-or-restart
- [S-02 · Context Budget](stacks/s02-context-budget.md) — the budget mindset; smart zone adds a quality threshold to the token count
