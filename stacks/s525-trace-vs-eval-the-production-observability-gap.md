# S-525 · Trace vs. Eval: The Production Observability Gap

Teams instrument traces on day one. Teams instrument evals on the day after their first $47,000 runaway agent bill. That gap — between "I can see what the agent did" and "I can tell if what the agent did was right" — is where production agent reliability actually lives.

## Forces
- **89% of teams have observability; only 52% have evals** — traces are cheap and familiar (standard APM mindset), evals require ground truth that most teams haven't labeled yet
- **Retrofitting observability costs 10x more than instrumenting on day one** — agent traces, tool call sequences, and per-turn quality signals are invisible to standard APM and require purpose-built instrumentation
- **Agent failures look like success** — a looping agent returns 200s, calls tools, produces output. Only the output is wrong. Standard health checks don't catch this
- **Eval without trace is guesswork** — a failing eval tells you something broke; a trace tells you which node, which tool call, which context shift caused the regression
- **Guardrails and observability are different things** — input/output validation blocks bad acts; observability tells you what happened when something got through

## The move

**Instrument traces from the first prototype, evals from the first happy-path run.**

1. **Add OpenTelemetry spans to every node and tool call** from the start — not just LLM calls. The agent's decisions are in the tool call sequences, not just the model outputs. LangSmith, LangFuse, and Arize Phoenix all accept OTel, so you decouple the instrumentation from the vendor.

2. **Define success criteria as executable evals before you ship** — not after. A correct-answer eval, a tool-call-sequence eval, and a hallucination detector (citation check, source-grounding) cover most cases. Label 20-50 golden examples. Run them in CI.

3. **Distinguish trace from eval**: traces answer "what happened?" — step-by-step decision paths, token counts, latencies, tool return values. Evals answer "was the outcome correct?" — whether the agent's action matched the expected behavior. Most teams have traces. Few have evals. Fewer have both wired into a single pipeline.

4. **Close the loop: failing eval → trace → fix → re-eval**. The trace narrows the regression to a specific node or tool. The eval confirms the fix. Without traces, you re-prompt-blind. Without evals, you don't know the fix worked.

5. **Instrument cost per task, not per call**. An agent loop at $0.01/call is a rounding error; at $2.50/1M tokens with 50k-token contexts, it becomes a $1,250 incident. Track task-level spend (sum of all calls for one task) with a span attribute from the root node down.

6. **Add guardrails at the output boundary, not just the input**. Input validation blocks bad acts going in. Output validation catches what got through — hallucinated facts, wrong entity extraction, risky content. A citation-grounding check (does the response cite only retrieved sources?) catches hallucination at negligible cost.

7. **Use structured logs for replay, not just traces for viewing**. An agent that fails at step 7 needs to be re-run from step 6 with the same state. Checkpoint the state graph, not just the trace. LangGraph's built-in checkpointer or Temporal's workflow replay both serve this.

## Evidence
- **Research survey:** 95 engineering/AI leaders with agents live in production — 89% have observability but <1 in 3 are satisfied with their guardrails/reliability. 63% plan to improve observability/evaluation next year — the top planned investment. (Cleanlab / MIT State of AI in Business 2025, August 2025) — https://cleanlab.ai/ai-agents-in-production-2025/
- **HN thread:** "How are you monitoring AI agents in production?" — respondents identified four failure modes that traces alone don't catch: surprise LLM bills from untracked token usage, risky outputs going undetected, no audit trail for post-mortems, and intent-execution gaps invisible in real time. A commenter built AgentShield specifically to close this: step-level execution tracing, output risk detection, per-agent cost tracking, and human-in-the-loop approval for high-risk actions. (HN Ask, Item #47301395, ~3 months ago) — https://news.ycombinator.com/item?id=47301395
- **Case study:** A developer running AI agents in production for 18 months documented optimizing costs from $847 to $312/month and production success rate from 55% to 78%. Three catastrophic failures cost $18,700 total — all occurred before evals were in place. After adding task-level cost tracking and output-grounding evals, the team caught a looping agent within 4 minutes and $12 of spend. (Calder's Lab, January 2025) — https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/

## Gotchas
- **Traces without evals tell you what broke, not that it broke.** You can stare at a 200-step trace and still not know if the agent's final answer was correct. You need a reference signal.
- **A failing eval without a trace is a mystery.** Without the decision path, you re-prompt in the dark and can't confirm the fix without re-running the full task.
- **LLM-based judges (evals run through an LLM) are expensive at scale.** Budget for them: 1 golden-eval set per workflow stage × periodic sampling in production, not every call.
- **Vendor lock-in on observability is real.** Teams that instrument directly against LangSmith's SDK have a migration problem if costs spike. Instrument against OpenTelemetry; route to your observability backend of choice.
- **Eval ground truth rots.** When your product changes, your labeled examples drift. Version your eval sets and re-label on a schedule or trigger — stale golden examples give false confidence.
