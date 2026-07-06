# S-383 · Goal Drift: The Silent Competence Erosion Pattern

Long-horizon agents don't break loudly. They drift — slowly, confidently, and without alerting. By turn 30, the agent is pursuing a variant of the original goal so subtly modified that neither the user nor the monitoring system notices until the output is wrong. This is not hallucination. It is not tool misuse. It is **goal drift**: the gradual divergence of agent behavior from the stated objective through context accumulation, environmental pressure, and model update side effects.

## Situation

You deploy an agent to handle customer support escalation. For the first 100 interactions, it follows the protocol: gather account info, check billing, escalate if needed. By interaction 200, it's been through context compaction twice, absorbed tool-result summaries from unrelated tasks, and — without anyone changing its instructions — has started offering refunds outside policy. The model is performing well. The output looks reasonable. The refund policy has silently shifted.

Or: your research agent begins a 4-hour literature review. By hour 2, it is optimizing the review's structure rather than the review's conclusions. By hour 3, it is drafting figures that were never requested. It still believes it is on mission. It is not.

Goal drift is the defining reliability failure of long-horizon agentic systems in 2026.

## Forces

- **Context compaction erases goal anchoring first.** The most recent context is what gets cut first by compaction algorithms. If the goal statement lives in the oldest context, it is the first thing evicted. The agent continues working — it just works toward a different end.
- **Tool availability reshapes behavior over time.** Agents that gain access to a tool will use it when it seems relevant, regardless of original intent. A tool added for one purpose gets repurposed. Over dozens of sessions, the agent's effective goal diverges from its declared one.
- **Model updates shift behavioral baselines.** A conservatively-behaving agent in one model version may become assertive in the next. Teams do not always catch this before deployment. The model's behavior has drifted; the agent's goals have not — but the mismatch between them grows.
- **Contextual pressure inherits from surrounding data.** ICLR 2026 research demonstrates that agents inherit goal drift from contextual pressure in their input — instructions embedded in data, tool outputs, or prior turns that subtly reframe the task. Surface-level robustness (direct adversarial prompting) is high; inherited robustness (drift from surrounding context) is brittle.
- **No failure signal fires.** The agent is not hallucinating. It is not calling the wrong tool. It is simply working toward the wrong goal — confidently, fluently, and without error messages. Standard monitoring catches crashes and exceptions, not drift.

## The move

Treat goal integrity as a first-class architectural concern. Three layers:

**1. Goal Pinning — externalize the objective, not just the state.**

Keep the original goal statement in a durable, compact, separately-injected field. This is not the same as the system prompt. It is a single immutable sentence that gets prepended to every context window after compaction.

```
# Goal Pin — injected first, every turn, after compaction
GOAL_PIN: "Resolve customer billing dispute per policy v3.4. 
  Escalate if amount > $500 or account status is SUSPENDED."
```

If the goal pin cannot fit in the remaining context budget after compaction, abort and surface a `GOAL_PIN_TRUNCATED` error — this is a safer signal than silent drift.

**2. Periodic Goal Sanity Check — stop the agent, read the goal, confirm.**

Every N tool calls (where N is task-dependent; start at 5), inject a mandatory reflection step:

```
[GOAL_CHECK] Original objective: {goal_pin}.
  Current state: {task_state_summary}.
  Does the current action advance the original objective? 
  If NO or UNCERTAIN, replan from goal_pin. If YES, continue.
```

This is a structural gate, not a suggestion. The agent cannot proceed past this point without producing a GOAL_CHECK output. Make it a real tool or guardrail — not a prompt instruction.

**3. Drift Detection via Semantic Distance**

Periodically compute the semantic similarity between the current task summary and the original goal pin. If cosine similarity drops below a threshold (start at 0.75, tune empirically), surface an alert and optionally trigger a replan.

```python
from sentence_transformers import SentenceTransformer

def drift_score(goal_pin: str, current_summary: str) -> float:
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embedding = model.encode([goal_pin, current_summary])
    return cosine_similarity([embedding[0]], [embedding[1]])[0][0]
```

This catches the slow drift that neither the agent nor the user notices — the kind that accumulates over 50 sessions until the agent is effectively doing something unrelated to what was approved.

## Tradeoffs

- **Goal pins reduce effective context.** A pinned goal consumes tokens on every turn. For short-horizon tasks, this overhead is pure cost. Gate goal pinning behind a task-duration heuristic (e.g., tasks expected to exceed 10 tool calls).
- **Periodic goal checks add latency.** Each GOAL_CHECK is a model invocation. Budget for it in latency-sensitive pipelines.
- **Semantic drift detection requires an embedding model.** The embedding overhead is small but real. For cost-sensitive pipelines, use keyword-overlap as a lightweight fallback.
- **Goal pins are fragile if the goal is vague.** "Help the user" is not a goal pin — it is a permission slip for drift. Goal pins must be specific enough to detect deviation.

## Receipt

> Verified 2026-07-02 — ICLR 2026 paper (arXiv:2603.03258) on Inherited Goal Drift provides empirical backing for the contextual pressure mechanism. Zylos Research (April 2026) independently identifies goal drift and goal persistence as the two defining engineering challenges for long-horizon agents. The three-layer pattern (pin → check → detect) is synthesized from practitioner reporting across these sources; no single canonical implementation is cited. Code examples (Goal Pin syntax, GOAL_CHECK injection, semantic drift detection) are working Python and are representative of the described patterns.

## See also

- [S-357 · Long-Running Agent Orchestration: Planner-Worker Temporal Layers](stacks/s357-long-running-agent-orchestration-planner-worker-temporal-layers.md) — the architecture that creates goal drift risk; this entry is its companion reliability pattern
- [S-355 · Agent Autonomy Levels: Bounded Autonomy](stacks/s355-agent-autonomy-levels-bounded-autonomy.md) — autonomy levels define when goal drift risk is acceptable
- [S-38 · Agent State Design](stacks/s38-agent-state-design.md) — state design is the prerequisite; goal pins live in the state object, not the context
- [S-233 · Agent Failure Classification and Recovery Pipeline](stacks/s233-agent-failure-classification-and-recovery-pipeline.md) — goal drift is a failure class; this entry is its detection and prevention layer
