# F-14 · Reading Agent Benchmarks

A leaderboard number is marketing until you know how it was produced. Agent benchmarks ask "can it complete a multi-step task with tools and recovery?" — not "can it answer a question?" — and the headline score hides more than it shows.

## Forces
- High MMLU/GPQA/HumanEval scores don't predict *agentic* capability — planning, tool discipline, and error recovery are what break
- The same model scores wildly differently depending on the scaffold around it — the number measures a *system*, not a model
- Most leaderboards report one trajectory per task; production retries the same task and gets a lower, noisier result
- Cost and safety are almost never in the score — an 88% at \$50/task ranks identically to 88% at \$0.50/task

## The move
- **Match the benchmark to your use case — never collapse them into one ranking:**
  - **SWE-bench Verified** — 500 human-verified real GitHub issues; the agent's patch must pass the repo's test suite in a sandbox. Pass/fail by running tests, no LLM judge. The gold standard for *coding* agents.
  - **GAIA** — multi-step general-assistant research tasks (web, files, tools), scored against short ground-truth answers.
  - **τ-bench / τ²-bench** — tool use plus *policy adherence* in multi-turn conversation; notably reports `pass^k`. Best for conversational/policy agents.
  - (WebArena → browser; OSWorld → computer-use; METR HCAST → long-horizon.)
- **Before trusting a score, ask four questions:**
  1. **System or model?** Bare model, vendor-scaffolded, or full integrator stack? These differ by tens of points. Demand the scaffold, system prompt, and retry budget.
  2. **pass@1 or pass^k?** One run overstates reliability; the production number is `pass^k` and it's lower ([F-11](f11-agent-reliability.md)).
  3. **At what cost?** A score without \$/task and latency is half the story ([F-08](f08-agent-cost-control.md)).
  4. **Contaminated?** Coding benchmarks leak into training data; prefer contamination-resistant variants and check the release date.
- **Run your own slice.** Public benchmarks rank the field; only your own eval on your own tasks predicts *your* result ([F-02](f02-evaluation-at-scale.md)).

## Receipt
> Verified 2026-06-25 — the "system vs model" gap, reproduced. Same model (llama3.2 via Ollama, localhost:11435), same verifiable task ("arrangements of MISSISSIPPI", correct = 34650), same verifier, 15 trials each.

```
BARE MODEL (1 attempt):           13/15 = 87%
SCAFFOLDED (best-of-3 + verifier): 15/15 = 100%
gap from scaffolding alone:        +13 points
```

A trivial scaffold — three tries and keep the verified-correct one — moved the *same model* 13 points on the *same task*. Real agent scaffolds (retry, tools, planning) move scores far more; this is why bare-model, vendor-scaffolded, and full-system rows for one benchmark can differ by 30–50 points. The lesson: a benchmark number names a *system*, so "which model is best" is unanswerable from a leaderboard alone — you must know what was wrapped around it. (Benchmark methodology facts — e.g. SWE-bench Verified's 500 human-verified tasks — are from public sources; spring-2026 leaderboard *scores* move weekly, so check the official leaderboards, not blog snapshots.)

## See also
[F-11](f11-agent-reliability.md) · [F-02](f02-evaluation-at-scale.md) · [F-08](f08-agent-cost-control.md) · [R-01](../frontier/r01-model-landscape.md) · [F-12](f12-llm-as-a-judge.md)

## Go deeper
Keywords: `SWE-bench Verified` · `GAIA` · `tau-bench` · `WebArena` · `OSWorld` · `METR HCAST` · `pass^k` · `agent scaffolding` · `benchmark contamination` · `SWE-bench Pro`
