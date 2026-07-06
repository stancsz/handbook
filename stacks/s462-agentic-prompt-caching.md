# S-462 · Agentic Prompt Caching: Cache-Aware Agent Loop Design

You have a 50-turn coding agent. The system prompt is 4K tokens. Tool definitions are 3K. Conversation history is 20K and growing. Without caching, every single turn re-pays the full 27K-token input cost. With naive caching, the moment the conversation turns a corner, the cache breaks and you're back to full price — sometimes worse, because you paid to build a cache you're now throwing away.

The move in agentic caching is architectural: design the loop so the static prefix dominates, the dynamic suffix is minimized, and cache breaks are intentional — not accidental.

## Forces

- Agentic loops are structurally cache-hostile — every turn produces new context that invalidates the prior cache boundary.
- System prompts, tool definitions, and stable persona content are identical across all turns in a session; these are the high-value cache targets.
- A single cache break mid-session can wipe out 10-20 turns of accumulated savings, making average cost worse than uncached.
- arXiv:2601.06007 (Jan 2026) shows 41-80% cost reduction across OpenAI, Anthropic, and Google for agentic tasks with proper caching strategy, vs. 13-31% time-to-first-token improvement.
- S-08 covers the static prompt caching API; it does not cover loop-level strategy, cache-boundary design, or incremental context building.

## The move

### 1. Layer your caching surface

Divide every agentic turn into three layers by update frequency:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer A: Static (cache once, reuse forever)                │
│  System prompt + persona + tool definitions + RAG schema    │
├─────────────────────────────────────────────────────────────┤
│  Layer B: Semi-stable (cache at session start, rebuild rarely)│
│  Session goals + known facts + prior tool call receipts      │
├─────────────────────────────────────────────────────────────┤
│  Layer C: Ephemeral (never cache)                          │
│  This turn's user input + latest tool results + scratchpad  │
└─────────────────────────────────────────────────────────────┘
```

Target: Layer A + B ≥ 80% of your per-turn tokens. Layer C should be < 20%.

### 2. Pick the right strategy per provider

Research (arXiv:2601.06007) evaluated three strategies across OpenAI, Anthropic, and Google:

| Strategy | Description | Best For | Risk |
|---------|-------------|----------|------|
| **Full Context** | Cache entire conversation | Short sessions (<20 turns) | High cache-break cost; history grows past cache window |
| **System Prompt Only** | Cache static prefix only | Long sessions, high-turn loops | Lower savings (40-50%) but zero cache-break overhead |
| **Hierarchical** | Cache Layer A + B separately, rebuild Layer B on milestone | Variable-length tasks, mixed workloads | Moderate complexity; highest net savings (60-75%) |

**System Prompt Only** is the safest starting point. It avoids cache-break events entirely and still saves 40-50% on the dominant cost component.

### 3. Design intentional cache boundaries

The enemy is accidental cache breaks. Every time your prompt structure changes — new tool added, system instruction updated, context template revised — you pay full price to re-populate the cache.

```python
# Bad: cache break on every turn because history grows past cache cutoff
messages.append({"role": "user", "content": user_input})
messages.append({"role": "assistant", "content": response})  # cache break at cutoff

# Good: separate static and dynamic, rebuild history structure
STATIC_PREFIX = [
    SystemMessage(system_prompt, cacheable=True),
    ToolDefinitions(tools, cacheable=True),
    SessionContext(session_goal, cacheable=True),
]

# In each turn:
turn = [
    DynamicUserInput(user_input),      # never cached
    ConversationSummary(recent_history) # summarization of history, ~500 tokens vs 5000
]
response = call_llm([...STATIC_PREFIX, ...turn])
```

### 4. Cache at milestone boundaries, not per-turn

For long-horizon agents (planner-worker, research agents, coding agents), cache at **milestone completion** rather than per interaction:

- After subtask completes: snapshot the planning context, start fresh for next subtask.
- On human-in-the-loop pause: checkpoint, release cache.
- On tool chain completion: summarize results, inject as Layer B on next turn.

```python
MILESTONE_SIZE_TURNS = 10  # rebuild cache every 10 turns

async def agent_turn(user_input: str, milestone: int):
    if milestone % MILESTONE_SIZE_TURNS == 0:
        # End of milestone: summarize accumulated context into Layer B
        summary = await summarize_session(milestone_history)
        cache_key = build_cache_key(milestone)  # stable across same milestone index
        # Layer B is rebuilt at each milestone boundary, not lost
        session_state = summary
    else:
        session_state = get_layer_b()  # pull from in-memory session state

    prompt = static_layer_a() + session_state + turn_input(user_input)
    return await llm.complete(prompt)
```

### 5. Provider specifics (2026)

**Anthropic:** Use `"cache_control": {"type": "ephemeral"}` on content blocks. Cache cutoff is typically at the last 128-1024 tokens. Pass `max_tokens_to_sample` to control output budget.

**OpenAI:** Automatic prefix caching — the API caches the longest common prefix across requests transparently. No explicit marking needed; the cache hits appear in `usage.cached_tokens`.

**Google Gemini:** Context cache on `contents` with explicit `ttl` (90s–24h). TTL must balance freshness vs. compute reuse. For agentic loops, use 90-300 second TTL; cache breaks are cheap if Layer A dominates.

```python
# Gemini context cache example
from google.genai import caches

cache = client.caches.create(
    model="gemini-2.5-flash",
    contents=[static_system_prompt, tool_definitions, session_goals],
    config=caches.CreateConfig(ttl="300s", system_instruction=system_prompt)
)
# Pass cache resource name in subsequent requests
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[cache.name, user_input],
    config=GenerateContentConfig(system_instruction=None)  # already in cache
)
```

### 6. Monitor the break rate

Track these metrics per agent session:

```
cache_hit_rate = turns_with_cache / total_turns
cache_break_cost = (rebuild_tokens * cache_rebuild_count) / total_turns
net_savings = (baseline_cost - actual_cost) / baseline_cost
```

Target: cache_hit_rate ≥ 0.75, net_savings ≥ 0.40. If cache_break_cost > 0.30, your prompt structure is too dynamic — switch to System Prompt Only strategy.

## Receipt

> Verified 2026-07-03 — arXiv:2601.06007 ("Don't Break the Cache," Jan 2026) benchmarked three providers across 500+ agent sessions with 10K-token system prompts. Hierarchical caching achieved 60-75% net savings on OpenAI and Anthropic. System Prompt Only achieved 40-50% savings consistently across all three providers. TTFT improved 13-31%. OpenAI automatic prefix caching hit 80% cost reduction on stable-prefix workloads. Anthropic ephemeral cache requires identical prefix tokens for hit; any insertion shifts the boundary and causes a miss.

## See also
- [S-08 · Prompt Caching](s08-prompt-caching.md) — static prompt caching API basics
- [S-461 · Multi-Agent Decision Framework](s461-multi-agent-decision-framework.md) — cost-aware decision patterns
- [S-401 · Agent Drift: The Longitudinal Regression Problem](s401-agent-drift-the-longitudinal-regression-problem.md) — monitoring production agent quality
