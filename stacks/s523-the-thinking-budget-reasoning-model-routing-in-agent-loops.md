# S-523 · The Thinking Budget — Routing Extended Cognition in Agent Loops

An agent that calls the model 15 times per task reaches for a reasoning model on every call. The invoice arrives. You didn't budget for 8 million thinking tokens.

## Forces

- **Thinking tokens are invisible context.** A reasoning model consuming 500K thinking tokens on a single call consumes the same context budget as 500K input tokens — but the thinking chain is hidden from the developer until the bill arrives. The O(n) context management problem you solved with S-02 comes back through the back door.
- **Cost compounds quadratically in loops.** Standard models: ~$0.003/M input tokens. Reasoning models: ~$0.11/M input + $0.003/M thinking tokens. An agent that runs 20 turns with a reasoning model on each turn at 500K thinking tokens/turn costs 20 × 500K × $0.003 = $300/ticket. The same agent with routing: 18 turns at $0.003 + 2 turns at $0.11 = $3.50/ticket.
- **Latency compounds the same way.** o3 at high effort: 60-90 seconds per call. A 15-turn agent loop with reasoning on every call: 15-22 minutes. The user has moved on.
- **Most turns in an agent loop are boring.** Tool selection, result summarization, context trimming, format conversion — none of these need 80% on GPQA Diamond. Routing them to a fast model cuts cost and latency without degrading quality.
- **The benchmark-to-loop gap is real.** Reasoning models win single-shot benchmarks by a wide margin. Inside a 15-turn agent loop, benchmark advantage compounds — or disappears entirely — depending on whether the routing discipline holds.

## The move

**Budget thinking tokens per call, not per task.**

### Three-tier routing

```
TIER 1 — Fast model (Haiku 4.5, GPT-4o-mini)
  Tool selection, result summarization, context trimming,
  format conversion, routing decisions, read-only lookups
  Target: <2s, <$0.002/call

TIER 2 — Standard frontier (Sonnet 4.6, GPT-4o, Claude Opus 4.6)
  Multi-step reasoning without deep search, composition,
  writing, explanation, state management
  Target: 5-15s, <$0.10/call

TIER 3 — Reasoning model (o3-mini, Claude 3.7 Sonnet + extended thinking, R1)
  Hard planning, multi-file code generation, novel constraint satisfaction,
  complex multi-hop retrieval, high-stakes decisions
  Target: 30-120s, budgeted thinking tokens
```

### Thinking token budget enforcement

```python
import anthropic

THINKING_BUDGETS = {
    "planner": 32_000,    # high-complexity task decomposition
    "reviewer": 16_000,   # quality gate, hard constraint check
    "fallback": 8_000,    # constrained fallback when Tier 2 fails
}

def think(model: str, system: str, messages: list, task_type: str) -> str:
    budget = THINKING_BUDGETS.get(task_type, 4_096)
    thinking_enabled = model in (
        "claude-sonnet-4-20250514",
        "claude-3-7-sonnet-20250620",
    )

    params = {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "messages": messages,
    }

    if thinking_enabled:
        params["thinking"] = {
            "type": "enabled",
            "budget_tokens": budget,
        }

    response = client.messages.create(**params)
    thinking_tokens = sum(
        block.thinking if hasattr(block, 'thinking') else 0
        for block in response.content
    )
    return response.content[0].text, thinking_tokens
```

### Call-site routing with audit

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class CallRecord:
    model: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    latency_ms: int
    task_type: str

def routed_call(
    task_type: str,
    prompt: str,
    records: list[CallRecord],
    budget_pct_remaining: float,
) -> str:
    """Route to the right model, log the call, enforce cost ceiling."""

    if task_type in {"summarize", "classify", "format", "route", "trim"}:
        model = "claude-haiku-4-5-20251001"
    elif task_type in {"compose", "explain", "check"}:
        model = "claude-sonnet-4-20250514"
    elif task_type in {"plan", "generate", "solve", "design"}:
        # Reasoning model — but only if budget allows
        if budget_pct_remaining < 0.1:
            model = "claude-sonnet-4-20250514"  # fallback
        else:
            model = "claude-3-7-sonnet-20250620"
    else:
        model = "claude-sonnet-4-20250514"

    result, thinking = think(model, SYSTEM_PROMPT, [prompt], task_type)

    records.append(CallRecord(
        model=model,
        input_tokens=...,       # from usage metadata
        output_tokens=...,      # from usage metadata
        thinking_tokens=thinking,
        latency_ms=...,         # measured
        task_type=task_type,
    ))
    return result
```

### Per-task total budget guard

```python
MAX_THINKING_TOKENS_PER_TASK = 96_000  # hard cap

def task_budget_guard(fn: Callable) -> Callable:
    def wrapper(task_id: str, prompt: str, **kw):
        records: list[CallRecord] = []
        total_thinking = 0

        def tracked_call(task_type: str, prompt: str) -> str:
            nonlocal total_thinking
            pct = (MAX_THINKING_TOKENS_PER_TASK - total_thinking) / MAX_THINKING_TOKENS_PER_TASK
            result = routed_call(task_type, prompt, records, pct)
            total_thinking += records[-1].thinking_tokens
            if total_thinking >= MAX_THINKING_TOKENS_PER_TASK:
                raise BudgetExceeded(f"Thinking budget exceeded for {task_id}")
            return result

        return fn(task_id, prompt, records, tracked_call)
    return wrapper
```

## Receipt

> Receipt pending — 2026-07-04

## See also

- [S-02 · Context Budget](s02-context-budget.md) — context window management, the foundation this extends
- [S-06 · Model Routing](s06-model-routing.md) — routing by task type and model tier
- [S-08 · Prompt Caching](s08-prompt-caching.md) — caching reduces redundant thinking token spend on repeated calls
- [S-02 · Budget-Aware Agents](../forward-deployed/f08-agent-cost-control.md) — cost as behavioral dimension
- [S-78 · Agent-to-Human Escalation](s78-agent-to-human-escalation.md) — when Tier 3 reasoning can't decide, escalate before spending more
