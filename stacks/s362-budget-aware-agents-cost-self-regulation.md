# S-362 · Budget-Aware Agents: Cost as a First-Class Behavioral Dimension

Your agent silently spent $340 in a weekend session — 17× the expected $20. Not because it was compromised. Not because it looped. It was doing its job: reasoning carefully, re-reading documents, verifying outputs. Every decision was individually justified. The total was not. Budget-Aware Agents address this: the pattern of embedding cost signals into the agent's decision architecture so it reasons about resource consumption the same way it reasons about correctness.

## Forces

- **Agents treat context as free.** A single user request triggers 50–100 LLM calls in a multi-step workflow. Each call feels small; the total is not. Most agents have no concept of "I have spent enough tokens on this task."
- **Static budget caps are reactive, not preventive.** A $50 session cap lets an agent burn $49.99 before stopping. By the time the cap fires, the damage is done. The real need is a mechanism that shapes *behavior* before the budget runs out.
- **The right answer at $0.05 is not the right answer at $50.** An agent that searches 20 documents to answer a question has produced a better output — but at a cost the user never authorized. The agent's objective function needs a cost term.
- **Cost and quality are not always monotonically related.** Going from 3 search iterations to 30 increases token spend ~10× but rarely improves answer quality by 10×. The agent needs to know when "good enough" is good enough.
- **Context accumulation compounds silently.** Every turn adds tokens to the context. A long conversation that started at 2K tokens grows to 50K — each turn more expensive than the last. Without budget awareness, agents are perpetually on a rising cost slope with no off-ramp.

## The move

### 1. Declare the cost budget explicitly

Embed a cost budget in the system prompt as a structured constraint, not an implicit assumption:

```
You have a token budget of {max_tokens} for this entire task.
Each tool call and LLM response consumes from this budget.
When you are at 50% budget consumed, switch to conservative mode:
- Use faster/cheaper tools first
- Reduce the number of search iterations
- Prefer synthesis over exhaustive analysis
When you are at 80% budget, produce your best answer and stop — even if incomplete.
```

The key is making the budget *visible and actionable* to the agent, not just a system-level enforcement.

### 2. Instrument the cost tracker

Capture per-step spend as structured metadata the agent can observe:

```python
class CostTracker:
    def __init__(self, budget_tokens: int):
        self.budget = budget_tokens
        self.spent = 0
        self.step_costs = []

    def record(self, step_name: str, tokens: int, cost_usd: float):
        self.spent += tokens
        self.step_costs.append({
            "step": step_name,
            "tokens": tokens,
            "cost": cost_usd,
            "budget_pct": self.spent / self.budget
        })

    @property
    def budget_fraction(self) -> float:
        return self.spent / self.budget

    @property
    def should_conserve(self) -> bool:
        return self.budget_fraction > 0.50

    @property
    def should_stop(self) -> bool:
        return self.budget_fraction > 0.80

tracker = CostTracker(budget_tokens=120_000)
```

### 3. Inject cost state into context

Pass the cost tracker output into the agent's context at every turn:

```
[BUDGET STATE] Tokens used: {tracker.spent:,} / {tracker.budget:,}
  ({tracker.budget_fraction:.0%} consumed)
  Conservative mode: {tracker.should_conserve}
  Stop and finalize: {tracker.should_stop}
  Most expensive step: {max(tracker.step_costs, key=lambda x: x['tokens'])['step']}
```

This turns an invisible system metric into an actionable context signal. The agent can now make cost-aware tool selections.

### 4. Build cost into tool selection

Wrap tool selection with a cost-routing layer that prefers cheaper alternatives when budget is constrained:

```python
def select_tool(capable_tools: list[str], budget_pct: float) -> list[str]:
    if budget_pct > 0.80:
        # Stop: return only the essential tool, no alternatives
        return [capable_tools[0]]
    elif budget_pct > 0.50:
        # Conserve: drop expensive multi-step tools
        return [t for t in capable_tools if t not in {"deep_search", "re_rank"}]
    else:
        # Normal: full capability
        return capable_tools
```

### 5. Add a cost termination criterion

Beyond the hard stop, define an acceptable cost-per-outcome threshold:

```python
ACCEPTABLE_COST_PER_TASK = 0.50  # USD

def should_terminate_early(tracker: CostTracker, quality_estimate: float) -> bool:
    cost_so_far = tracker.spent * COST_PER_TOKEN
    quality_per_dollar = quality_estimate / cost_so_far if cost_so_far > 0 else float('inf')

    # If we're getting diminishing returns on quality per dollar
    if cost_so_far > ACCEPTABLE_COST_PER_TASK * 3:
        return True
    # If quality is plateauing (measure via partial eval)
    if tracker.should_conserve and quality_estimate < 0.7:
        return True
    return False
```

## The three budget modes

| Mode | Budget consumed | Behavior |
|------|-----------------|----------|
| **Full capability** | 0–50% | All tools, all reasoning depth, exhaustive search |
| **Conservative** | 50–80% | Cheaper tools, fewer iterations, prefer synthesis |
| **Terminate** | 80–100% | Produce best answer so far, wrap up, stop |

## What this prevents

- **Silent runaway sessions:** A research agent that would spend $200 on a question gets redirected at $100 and delivers a 95%-quality answer instead.
- **Context accumulation spirals:** Budget pressure forces the agent to summarize and compact context proactively, not when the context window forces it.
- **Un economically-scoped tasks:** "Analyze all our data" without a budget produces a $500 answer. With a budget, the agent clarifies scope first.

## Receipt

> Verified 2026-07-02 — Concept validated against three production patterns documented in: AgentMarketCap (Apr 2026) on 40–60% cost reduction via budget-aware agent design, Orq.ai FinOps guide (Jun 2026) on cost-per-outcome as the primary KPI, and Zylos Research on semantic caching + model routing + prefix caching achieving 80%+ reduction. The specific "budget mode switching" pattern (conservative at 50%, terminate at 80%) is synthesized from the production eval pipeline literature (s246) and cost velocity monitoring (f192). Receipt pending — live experiment with budget-aware agent vs. unconstrained agent on equivalent task set.

## See also

- [S-346 · The Token Cost Trap](s346-the-token-cost-trap-multi-agent-economics-and-fixes.md) — the compounding token math that makes this necessary
- [F-192 · Cost Velocity Circuit Breaker](forward-deployed/f192-cost-velocity-circuit-breaker.md) — the reactive complement; velocity-based hard stops
- [S-322 · Multi-Agent Cost Observability](s322-multi-agent-cost-observability-patterns.md) — surfacing where the tokens go
- [S-02 · Context Budget](s02-context-budget.md) — the context-window dimension of budget management
