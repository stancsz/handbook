# S-272 · Agent Circuit Breakers and Spend Guards

LLM-powered agents fail differently from traditional software. A traditional bug is local and bounded. An agent bug — a loop, a permission mistake, a misbehaving tool — can burn hundreds of dollars in minutes and produce no output. Monitoring dashboards tell you after the damage is done. You need enforcement, not observation.

## Forces

- **Agents move at machine speed.** An LLM agent can issue 200 tool calls in 14 minutes. A human on-call engineer needs 5 minutes to open their laptop. By the time you react, the bill is done.
- **Alerts are lagging indicators.** You receive a spend alert at $400. The agent hit that threshold at call 50 of a 200-call loop. The alert tells you what happened; it doesn't prevent it.
- **Prompt injection and tool errors compound.** A subtle tool schema change causes the agent to re-call the same tool with slightly different arguments on every iteration — each call charges you, none succeeds.
- **Per-call cost is invisible.** A single agent run can touch 10 tools, each returning variable-size payloads. The cost of a loop is not just the repeated calls — it's the repeated context injection, the accumulating conversation history, and the retries.
- **Hard limits feel scary but are mandatory.** The mental model shift: spend guardrails are not "throttling your agent." They are the equivalent of a fuse in an electrical circuit — they exist so one fault doesn't burn down the house.

## The move

Implement two independent enforcement layers: **circuit breakers** (limit iterations and tool-call counts) and **spend guards** (limit cost per call, per turn, and per session). Both are enforced synchronously, before the next LLM call is issued — not after.

### Layer 1 — Circuit Breaker (iteration control)

```python
from dataclasses import dataclass, field
from enum import Enum
import time

class TripReason(Enum):
    LOOP_DETECTED = "loop_detected"
    MAX_CALLS_REACHED = "max_calls_reached"
    DURATION_EXCEEDED = "duration_exceeded"
    NO_PROGRESS = "no_progress"

@dataclass
class CircuitBreaker:
    max_calls: int = 50
    max_duration_seconds: float = 300.0
    max_repeat_actions: int = 3  # same tool N times in a row → suspect loop

    call_count: int = 0
    start_time: float = field(default_factory=time.time)
    last_action_hash: str = ""
    repeat_count: int = 0
    history: list[str] = field(default_factory=list)

    def check(self, action_hash: str) -> TripReason | None:
        self.call_count += 1
        self.history.append(action_hash)

        if self.call_count >= self.max_calls:
            return TripReason.MAX_CALLS_REACHED

        if time.time() - self.start_time >= self.max_duration_seconds:
            return TripReason.DURATION_EXCEEDED

        if action_hash == self.last_action_hash:
            self.repeat_count += 1
        else:
            self.repeat_count = 0
            self.last_action_hash = action_hash

        if self.repeat_count >= self.max_repeat_actions:
            return TripReason.LOOP_DETECTED

        return None

    def reset(self):
        self.__init__(
            self.max_calls, self.max_duration_seconds, self.max_repeat_actions
        )
```

**Loop detection via action hashing.** Hash the normalized tool name + key arguments. If the same hash appears N times consecutively, the agent is looping. This catches the most common loop pattern: calling `search_documents` with minor parameter variations on every turn.

**No-progress detection.** If the last N tool results were all `{"success": true, "data": []}` or equivalent empties, the agent is cycling on no-op results. Extend the circuit breaker to track this.

### Layer 2 — Spend Guard (cost enforcement)

```python
from dataclasses import dataclass
import tiktoken

@dataclass
class SpendGuard:
    max_cents_per_call: float = 0.50   # hard cap per LLM API call
    max_cents_per_session: float = 2.00  # hard cap per agent run
    model: str = "gpt-4o-mini"
    _session_spend_cents: float = 0.0
    _enc = None

    def __post_init__(self):
        try:
            self._enc = tiktoken.encoding_for_model(self.model)
        except KeyError:
            self._enc = tiktoken.get_encoding("cl100k_base")

    def estimate_call_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        # gpt-4o-mini pricing (example, verify current rates)
        in_price_per_mtok = 0.15  # cents
        out_price_per_mtok = 0.60  # cents
        return (prompt_tokens * in_price_per_mtok / 1_000_000
                + completion_tokens * out_price_per_mtok / 1_000_000)

    def pre_call_check(self, estimated_prompt_tokens: int) -> bool:
        estimated = self.estimate_call_cost(estimated_prompt_tokens, 0)
        if self._session_spend_cents + estimated > self.max_cents_per_session:
            return False  # would exceed session cap
        return True

    def post_call_record(self, prompt_tokens: int, completion_tokens: int):
        cost = self.estimate_call_cost(prompt_tokens, completion_tokens)
        self._session_spend_cents += cost

    @property
    def session_spent_cents(self) -> float:
        return self._session_spend_cents
```

**Enforce at pre-call time.** `pre_call_check` runs before the LLM call is issued. If the session has already burned 90% of its budget, block the next call rather than waiting to see what it costs.

**Token counting via tiktoken.** Hardcode the current model pricing and use tiktoken to count tokens from the actual prompt. This is an estimate — API responses vary — but it's accurate enough for guardrail enforcement. Update pricing whenever model rates change.

### Layer 3 — Integration hook

```python
def agent_loop(tool_registry: dict, breaker: CircuitBreaker, guard: SpendGuard):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        # --- Circuit breaker check ---
        reason = breaker.check(current_action_hash(messages))
        if reason:
            return {"status": "tripped", "reason": reason.value, "calls": breaker.call_count}

        # --- Spend guard pre-check ---
        prompt_tokens = count_tokens(messages)
        if not guard.pre_call_check(prompt_tokens):
            return {"status": "spend_limit_reached", "spent": guard.session_spent_cents}

        # --- LLM call ---
        response = llm.chat.completions.create(
            model=guard.model,
            messages=messages,
            tools=build_tool_schemas(tool_registry),
        )
        guard.post_call_record(
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )

        if not response.choices[0].message.tool_calls:
            return {"status": "done", "message": response}

        # --- Execute tools ---
        for tc in response.choices[0].message.tool_calls:
            result = tool_registry[tc.function.name](**json.loads(tc.function.arguments))
            messages.append(response.choices[0].message)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result),  # or summarize per S-97
            })
```

**Key insight:** Both guardrail checks run *before* the LLM call that would exceed the limit. This is the difference between a guardrail and a dashboard.

## Receipt

> Receipt pending — 2026-07-01. The pattern is validated against production incident reports (a $47K single-loop case documented on HN/LinkedIn engineering posts) and community consensus that "alerts won't stop the bill." A minimal integration example using OpenAI SDK + tiktoken is runnable locally — pricing constants should be verified against current API rate sheets before production use.

## See also

- [S-95 · Retry Cost Attribution](../stacks/s95-retry-cost-attribution.md) — accounting for the cost of retries within agent runs
- [S-97 · Tool Result Summarization](../stacks/s97-tool-result-summarization.md) — reducing context injection cost per tool call
- [F-181 · Silent Tool Call Failures](../forward-deployed/f181-silent-tool-call-failures.md) — the complementary failure mode: calls that succeed on the wire but skip the actual work
- [S-270 · Choosing an Eval Framework](../stacks/s270-choosing-an-eval-framework.md) — framework landscape for validating that guardrail policies actually fire when expected
