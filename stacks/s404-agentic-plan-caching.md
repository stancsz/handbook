# S-404 · Agentic Plan Caching — Reuse the Skeleton, Not the Context

Your customer support agent handles 50 requests about account recovery today. Tomorrow it gets 50 more. The agent re-plans the entire account-recovery decomposition from scratch for each one — same steps, same logic, same thought process — because context caching only works on identical prefixes, and each user's conversation is unique. You pay for the same reasoning 50 times.

Agentic Plan Caching (APC) fixes this. Instead of caching the conversation, cache the *plan skeleton* — the high-level decomposition of *what to do* — and reuse it across semantically similar task types. arXiv 2506.14852 (Zhang et al., Stanford / NeurIPS 2025) shows 20–40% cost reduction and 27% latency improvement on workloads with recurring task shapes.

## Forces

- **Prompt caching fails on agentic workloads.** Context caching requires identical prefix tokens. In a multi-turn agent, every conversation diverges after 2–3 turns. The cache hit rate approaches zero exactly when the expensive planning step happens.
- **Planning is the most expensive part of a multi-step agent.** A 10-step task might cost $0.80 total. The planner's 5 reasoning steps are $0.50 of that — 62% of cost in 50% of steps. But those 5 steps are nearly identical across task instances of the same type.
- **Parallelization kills prefix caching.** The most impactful agent optimization is also the one that destroys your cache hit rate. Running N tasks in parallel means N cache writes for the same prefix instead of one write + (N−1) hits.
- **Plan reuse ≠ hallucination risk.** Naive output caching would reuse conclusions — dangerous. APC caches *methodology* (the structure of steps), not *outputs* (the results of those steps). Each step still runs against the real current state.

## The move

**Extract → Store → Retrieve → Adapt**

Four-stage cycle, replacing the planner on every step:

```
1. EXTRACT:  On successful task completion, extract the step-by-step plan.
             Use a structured output schema: { task_type, steps: [{action, purpose}] }

2. STORE:    Index by task-type keywords + step-count fingerprint.
             Persist in a plan store (vector DB or key-value).

3. RETRIEVE: On new task, match against stored plans by intent keywords.
             Similar task type → candidate plan retrieved.

4. ADAPT:    A small, cheap model adapts the cached plan to the new specifics
             (user ID, account type, specific fields). Main execution uses the
             adapted plan without re-running full planning inference.
```

**The planner-only-when-needed version** (cheapest):

```python
import anthropic
from anthropic import NOT_GIVEN

client = anthropic.Anthropic()

PLAN_STORE = {}  # task_type -> {"steps": [...], "count": N}

def get_or_create_plan(task_type: str, user_message: str) -> dict:
    if task_type in PLAN_STORE:
        # Cache hit: adapt cached plan with new specifics
        cached = PLAN_STORE[task_type]
        return {
            "source": "cache",
            "plan": cached["steps"],
            "adapt_from": user_message  # new specifics injected at adapt step
        }

    # Cache miss: run expensive planner
    planner_prompt = f"""You are a task planner. Decompose this request into
numbered steps. Return JSON: {{"task_type": "...", "steps": [{{"action": "...", "purpose": "..."}}]}}.

Request: {user_message}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": planner_prompt}]
    )

    plan = response.content[0].text
    PLAN_STORE[task_type] = json.loads(plan)
    return {"source": "planned", "plan": json.loads(plan)["steps"]}

def execute_plan(plan: dict, user_message: str):
    """Run each step, injecting new specifics into cached steps."""
    for step in plan["steps"]:
        # Substitute placeholders: {user_id}, {account_type}, etc.
        adapted_action = substitute(step["action"], {"user_message": user_message})
        result = run_step(adapted_action)
        if result.failed:
            # Fall back to full replan on step failure
            return get_or_create_plan(detect_task_type(user_message), user_message)
    return result
```

**When to use APC:**

| Workload | APC Benefit |
|----------|------------|
| High-volume, repetitive task types (support, onboarding, triage) | High — plan reuse rate 60–80% |
| Long-horizon tasks (research, PR automation, multi-step ops) | High — planning cost is the dominant expense |
| One-off, novel tasks | None — no reuse benefit |

**The key tradeoff:** APC caches *structure*, not *outcomes*. The adaptation step must be robust — a bad adaptation silently propagates through every downstream step. Validate the adapted plan against a few guardrail conditions before execution (e.g., expected step count ± 2, required action types present).

**When NOT to cache plans:** Tasks where the plan structure itself encodes sensitive information, where step ordering carries legal or compliance implications, or where the task type fingerprint is unreliable (ambiguous intent that resolves differently on each occurrence).

## Receipt

> Verified 2026-07-02 — arXiv 2506.14852 (Zhang et al., Stanford/NeurIPS 2025): 20–40% cost reduction, 27% latency improvement on recurring task types. OpenAI Agents SDK 2026 includes a `PlanCache` primitive in beta. AgentMarketCap (April 2026) reports teams achieving 50% planner cost reduction on customer support workloads with rule-based task-type routing. The parallelization/caching tension is real: batch parallelism destroys prefix cache hit rates; APC's plan-level caching is orthogonal to parallel execution.

## See also

- [S-357 · Long-Running Agent Orchestration: Planner-Worker Temporal Layers](stacks/s357-long-running-agent-orchestration-planner-worker-temporal-layers.md) — the architectural pattern APC sits inside
- [S-08 · Prompt Caching](stacks/s08-prompt-caching.md) — prefix caching for static content; APC for dynamic planning
- [S-187 · Prompt Cache Break-Even Calculator](stacks/s187-prompt-cache-break-even-calculator.md) — economics of caching; APC shifts the break-even point
