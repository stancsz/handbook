# S-541 · Agent Drift Detection

Your agent's refund approval rate dropped 12% last week. Nobody changed the prompt. Nobody changed the model version. The users noticed before you did. This is agent drift — behavioral degradation without explicit parameter changes — and it is one of the most poorly-monitored failure modes in production agentic systems.

## Forces

- **Vendor updates break assumptions silently.** OpenAI, Anthropic, and Google push model updates that can change tool-selection patterns, refusal behavior, and output format without notice. A pinned model name does not pin model behavior.
- **Agents are composite systems — drift has multiple sources.** Semantic drift (intent deviation), coordination drift (multi-agent misalignment), and behavioral drift (emergence of novel failure patterns) each require different detection signals. Most teams monitor none of them.
- **Traditional monitoring misses behavioral drift.** Uptime checks, latency percentiles, and error rates all stayed green while the refund approval rate dropped 12%. The agent was working — it was just working wrong.
- **Agents accumulate context and lose coherence.** Long interaction sequences amplify drift. A 200-turn conversation doesn't just cost more — it progressively degrades the agent's ability to maintain task goal, role boundaries, and cross-reference consistency.

## The move

**1. Pin behavioral baselines, not just model names.**

Run a drift suite — a fixed set of 50–200 test cases with known correct outputs — against every model version and prompt change. Store the behavioral fingerprint: tool-call sequence, refusal rate, output format, task completion rate. Compare the current run against the baseline with a composite ASI (Agent Stability Index) score. Treat the drift suite like a CI regression test, not a one-time evaluation.

```
ASI = (task_completion_rate / baseline) ×
      (1 − |refusal_rate − baseline_refusal|) ×
      (1 − tool_sequence_jaccard_distance)
```

**2. Monitor three distinct drift axes separately.**

| Type | Signal | Detection |
|------|--------|-----------|
| **Semantic drift** | Output meaning diverges from original intent | LLM-judged semantic similarity on drift suite |
| **Coordination drift** | Multi-agent consensus breaks down | Convergence rate, message agreement score |
| **Behavioral drift** | Novel failure patterns emerge | Per-task-type error rate trend over rolling 7-day window |

A single composite score masks which axis is drifting. Diagnosing requires axis-level visibility.

**3. Detect vendor model drift with shadow traffic.**

Route 5–10% of production requests through a shadow agent pinned to a frozen model version. Compare shadow outputs against live outputs on identical inputs. A divergence spike (e.g., >15% response difference across 100+ cases) indicates vendor model drift, not your code change. This separates provider updates from your own changes — the most common misattribution in agent incidents.

**4. Set automated alerts on behavioral metrics, not just system metrics.**

Track per-task-type completion rates as a leading indicator. A 2% drop in refund-approval task success over 3 days predicts a 10% drop within a week. Alert at the task-type granularity: `refund_task: success_rate < 0.87` fires before `overall_error_rate > 0.05`.

**5. Respond to drift with model pinning + rollback, not just tuning.**

When drift is detected: (a) pin the live agent to the last-known-good model version, (b) route high-stakes tasks through the shadow agent, (c) re-run the drift suite across candidate replacement models to find the best regression-free option. Tuning the prompt to compensate for vendor drift is a lagging solution that breaks when the next update arrives.

## Traps

- **Waiting for users to report drift** is too slow. By the time users notice, the damage (wrong decisions, bad data written, incorrect outputs shipped) is already done. Behavioral monitoring must run continuously, not on-demand.
- **Attributing drift to your code** when it's vendor-driven wastes days of debugging. Shadow traffic with a frozen model is the only reliable separator.
- **Treating context length as the only cause of drift** misses provider updates, input distribution shifts, and memory layer contamination. Drift is multi-causal — your monitoring must be too.
- **Tuning the prompt to match drifted behavior** creates a ratchet: each vendor update requires re-tuning. Fix the cause (provider change or system design) rather than compensating for the symptom.

## Sources

- arXiv:2601.04170 — *Agent Drift: Quantifying Behavioral Degradation in Multi-Agent LLM Systems* (Jan 2026): theoretical framework, ASI metric, three drift manifestations
- prefactor.tech — *How to Prevent Agent Performance Drift in Production* (May 2026): detection signals, root causes, multi-level alerting
- benchmarkingagents.com — Agent benchmark methodology and contamination analysis
