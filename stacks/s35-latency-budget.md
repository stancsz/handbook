# S-35 · Latency Budget

End-to-end agent latency has four components: time to first token (TTFT), generation time, tool call round-trips, and network overhead. Most practitioners optimize the wrong one. TTFT is viscerally obvious and hard to change. Tool call RTT feels like the bottleneck when you're watching a spinner. The real dominant cost — generation time, which scales with output tokens times number of turns — sits silently in the background accumulating seconds. Model your latency budget before you optimize; you will be surprised where the time actually goes.

## Situation

Your agent takes 6 seconds per task and users notice. You reach for a faster model. Latency drops 10%. You add streaming. Perceived latency drops but actual latency is the same. The problem is that you optimized TTFT on a pipeline where generation time across 5 turns is accounting for 80% of wall-clock time. The right lever was output tokens per turn and number of turns — not the model's raw speed.

## Forces

- TTFT is visible (the pause before anything appears) but represents a small fixed cost. Generation time is invisible in aggregate but scales with every output token across every turn.
- A 5-turn loop at 80 output tokens/turn and 75 tok/s produces 5.3 seconds of generation time before TTFT or tool calls are counted. Switching to a 150 tok/s model halves that — but halving output tokens/turn would too, with no model change.
- Tool call RTT matters, but the gap between local (2–5 ms) and external (100–500 ms) tools is large and often invisible in architecture decisions.
- Output tokens are the only latency component that the agent's own reasoning controls: shorter, more direct turns cost less time and less money ([F-18](../forward-deployed/f18-architecture-sets-the-cost-floor.md)).
- Parallelizing independent tool calls converts serial latency into parallel — multiple tool calls in one turn cost the latency of the slowest, not the sum. This is often overlooked.
- [S-12](s12-streaming.md) reduces *perceived* latency by surfacing tokens as they generate. Actual end-to-end latency is unchanged. Streaming is a UX intervention, not a latency intervention.

## The move

**Model the budget before you ship.** For a T-turn loop with F output tokens per turn at R tok/s, plus K tool calls at L ms each:

```
latency ≈ TTFT + T × (F/R × 1000) + K × L
```

This is a back-of-envelope — it ignores queue time, prefill latency on long inputs, and caching effects — but it will tell you which component dominates.

**Reduce output tokens per turn first.** Prompt for concise tool calls: "reply with only the tool call, no reasoning, no preamble." A turn that generates 40 tokens instead of 120 costs one-third the generation time. This is the largest lever most teams haven't pulled.

**Reduce turns.** Batch related tool calls into one turn where possible. An agent that makes one tool call per turn on 5 sequential operations takes 5× the generation time of an agent that plans and batches. Fan out parallel calls inside one turn; don't chain unnecessarily ([S-05](s05-multi-agent-patterns.md)).

**Parallelize tool calls within a turn.** If two tool calls are independent, issue them together and wait for both. Serial RTT (L₁ + L₂) becomes parallel RTT (max(L₁, L₂)). This is free latency reduction — it only requires the orchestrator to support concurrent calls.

**Route to fast models for low-complexity turns.** If a turn is extracting a value or formatting output, a faster cheap model at 150 tok/s halves generation time vs a frontier model at 75 tok/s with no quality loss ([S-06](s06-model-routing.md)).

**Cache TTFT on repeated context.** Prompt caching ([S-08](s08-prompt-caching.md)) reduces the cost of TTFT on cached prefixes; it doesn't eliminate the generation component. Use it, but don't expect it to fix a generation-dominated pipeline.

**Attribute latency in production before you optimize.** Log TTFT, generation time, and tool RTT per turn. A week of data will show you whether your pipeline is generation-bound or tool-bound. Most teams are generation-bound and don't know it.

## Receipt

> Verified 2026-06-26 — Node, `perf_hooks.performance`. In-process tool call and loopback HTTP RTT are real measurements; generation time and external tool RTT are modeled from published API benchmarks (Sonnet-class ~75 tok/s; external API RTT 100–500ms conservative estimate). The 5-turn budget is a model, not a live API measurement — the component measurements are the verified part.

```
=== Real measurements ===
In-process tool call:  0.0003 ms/call  (10,000 calls, perf_hooks)
Loopback HTTP RTT:       2.5 ms median,   4.4 ms p95  (50 real calls)

=== Generation time (modeled, 75 tok/s) ===
 50 output tokens:   667 ms
200 output tokens: 2,667 ms

=== 5-turn agent loop budget ===
TTFT:                     300 ms  (fixed)
Generation (80 tok/turn): 1,067 ms × 5 turns = 5,335 ms
Tool RTT  (local, 2.5ms):     2.5 ms × 5     =    13 ms
Tool RTT  (external, 200ms):  200 ms × 5     = 1,000 ms

Total (local tools):    5,648 ms    generation fraction: 94%
Total (external tools): 6,635 ms    generation fraction: 80%
```

**What the receipt shows:**

- In-process tools are effectively free (0.0003 ms). Moving a fast lookup out of the model and into a local function costs no latency.
- Loopback HTTP RTT is 2.5 ms median — fast. But even at 200 ms (external API), tool calls account for only 15% of the 6.6-second total. Optimizing tool RTT first is optimizing the wrong thing.
- Generation time — the component most practitioners don't measure — accounts for 80–94% of end-to-end latency. It scales with output tokens per turn times number of turns. That is the lever.
- Cutting output tokens per turn from 80 to 40 saves 2.7 seconds on a 5-turn loop, for free, with the same model and the same infrastructure.

## See also

[S-12](s12-streaming.md) · [S-06](s06-model-routing.md) · [S-08](s08-prompt-caching.md) · [S-05](s05-multi-agent-patterns.md) · [F-18](../forward-deployed/f18-architecture-sets-the-cost-floor.md) · [S-55](s55-parallel-tool-calls.md)

## Go deeper

Keywords: `latency budget` · `TTFT` · `time to first token` · `generation time` · `tool call RTT` · `tokens per second` · `parallel tool calls` · `latency attribution` · `p95 latency` · `agent loop latency`
