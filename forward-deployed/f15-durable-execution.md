# F-15 · Durable Execution

A long-running agent that restarts from scratch on every crash is a fragile script with a model in the middle. Durable execution persists *where the agent is* in its task, so it resumes from the last completed step — not the beginning. (Distinct from [S-09](../stacks/s09-memory-systems.md): that's what the agent *knows*; this is *how far it got*.)

## Forces
- Agents now run for minutes to hours across dozens of tool calls; an API timeout or a container restart shouldn't burn the whole run
- Re-running a completed step isn't free — it re-pays tokens *and* can fire the side effect again (a second charge, a duplicate email)
- LLM steps aren't deterministic: re-executing "extract the number" can return a *different* answer, so a naive restart isn't even reproducible
- Human-in-the-loop means an agent may need to pause for *days* awaiting approval, then wake with full context ([F-09](f09-human-in-the-loop.md))

## The move
- **Four pillars:**
  1. **Checkpoint** the execution state (which steps are done + their results) to durable storage after each meaningful step — write *atomically* (temp file + rename) so a crash mid-write can't leave a corrupt checkpoint.
  2. **Resume** from the latest checkpoint on restart — skip completed steps.
  3. **Retry** transient step failures with backoff.
  4. **Idempotency** — a retried step must not duplicate side effects. Give writes an idempotency key; read-only calls (search, lookup) are safe to replay freely.
- **Pause = checkpoint + sleep.** Human approval and long waits use the same mechanism: persist state, sleep, wake on an external event. Don't block a thread or poll.
- **Don't roll your own if you can help it.** Frameworks ship this: Temporal replays event history to reconstruct state; LangGraph/Google ADK have checkpointers (dev = in-memory/SQLite, prod = Postgres/Cloud SQL). DIY means a state schema, partial-write recovery, stale-checkpoint detection, and cleanup — all easy to get subtly wrong.
- **Test by killing the worker mid-run.** Inject a crash and assert the invariants hold: no duplicate side effects, no continuation past a denied approval, no resume from an untrusted/stale checkpoint.

## Receipt
> Verified 2026-06-25 — a 4-step agent pipeline (each step a real llama3.2 call via Ollama, localhost:11435 + an external "side effect" write), crashed after step 2, then restarted. Run with checkpointing vs. without.

```
WITH checkpointing:
  run1: ran classify, ran extract, *** CRASH ***
  run2 (restart): skip classify (done), skip extract (done), ran translate, ran summarize
  side-effect counts: {classify:1, extract:1, translate:1, summarize:1}   <- each once

WITHOUT checkpointing (naive restart from scratch):
  run1: ran classify, ran extract, *** CRASH ***
  run2: ran classify, ran extract, ran translate, ran summarize
  side-effect counts: {classify:2, extract:2, translate:1, summarize:1}   <- DUPLICATED
```

Checkpointing resumed at the exact step of failure and each side effect fired **exactly once**. The naive restart re-ran the two pre-crash steps, firing their side effects **twice** — two charges, two emails. It also re-ran `extract` and got a *different* answer (4471 → 2), so the redo wasn't even consistent. That double-firing is the whole reason idempotency is pillar four: without it, "just retry" silently corrupts state.

## See also
[S-09](../stacks/s09-memory-systems.md) · [F-09](f09-human-in-the-loop.md) · [F-11](f11-agent-reliability.md) · [S-23](../stacks/s23-workflows-vs-agents.md) · [F-05](f05-agent-failure-taxonomy.md) · [S-38](../stacks/s38-agent-state-design.md)

## Go deeper
Keywords: `durable execution` · `checkpointing` · `resumability` · `idempotency key` · `Temporal` · `LangGraph checkpointer` · `event sourcing` · `continue-as-new` · `human-in-the-loop` · `exactly-once`
