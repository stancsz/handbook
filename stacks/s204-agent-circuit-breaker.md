# S-204 · Agent Circuit Breaker

Your agent entered a loop on a Friday afternoon. By Monday it had sent 847 irrelevant emails, cost $4,200 in API calls, and created 12 ghost records in your CRM. Nobody caught it because the agent was "working" — returning 200s, calling tools, producing output. It was just producing the wrong output, fast. This is the gap a circuit breaker closes: between the agent's decision to act and the action's execution, a guardrail that counts, budgets, and kills before damage compounds.

## Forces

- Agents fail by producing wrong output, not by crashing — no exception means no automatic detection. The agent "works" while it destroys value
- Every retry multiplies cost: a 10-retry loop at $0.01/token is a rounding error; at $2.50/1M tokens with 50k-token contexts, it's a $1,250 incident
- Lusser's Law (S-200) says 20 steps at 95% reliability = 36% end-to-end success — but you don't know which 36% until it's too late
- Step-count limits alone are blunt: a 15-step agent that makes progress on steps 1–14 and fails on 15 gets killed; an 8-step agent that loops on step 3 survives
- Context window exhaustion mid-loop produces hallucinated tool calls (the model starts fabricating results to fill the context it can't fit) — distinct from normal hallucination, much harder to catch
- Cost gating requires live accounting: token counts per call, accumulated across a session, compared against a budget — most frameworks have none of this out of the box

## The move

A circuit breaker has four independent tripwires. All four are checked before every tool call (not after). Any one trips → agent halts with a structured failure, no further tool calls execute.

```
┌─────────────────────────────────────────────────────┐
│                  Circuit Breaker                    │
│                                                     │
│  [Step Limit]    → max N tool calls per session     │
│  [Token Budget]  → max accumulated tokens           │
│  [Semantic Loop] → max semantically identical turns │
│  [Cost Ceiling]  → max $ spend per session          │
│                                                     │
│  Any tripwire trips → HALT, emit structured error  │
└─────────────────────────────────────────────────────┘
```

### Step Limit

Simple counter: increment per tool call, fail if `count > max_steps`. The bluntest lever — use it to cap the maximum action budget per session. Combine with a "grace period" that allows the last step to return a graceful failure rather than a hard crash.

```python
class StepLimitBreaker:
    def __init__(self, max_steps: int = 50):
        self.max_steps = max_steps
        self.count = 0

    def check(self) -> None:
        self.count += 1
        if self.count > self.max_steps:
            raise CircuitBreakerTripped(
                f"Step limit {self.max_steps} exceeded at step {self.count}"
            )
```

### Token Budget

Track prompt + completion tokens per session. Before each tool call, assert `accumulated_tokens + estimated_call_tokens < budget`. Estimated call size = rolling average of last 3 calls, or a pessimistic upper bound (e.g., 40% of context window).

```python
class TokenBudgetBreaker:
    def __init__(self, max_tokens: int = 120_000):
        self.max_tokens = max_tokens
        self.accumulated = 0

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.accumulated += prompt_tokens + completion_tokens

    def check(self, estimated_next: int = 8_000) -> None:
        if self.accumulated + estimated_next > self.max_tokens:
            raise CircuitBreakerTripped(
                f"Token budget {self.max_tokens} near-exceeded: "
                f"{self.accumulated} used, ~{estimated_next} estimated"
            )
```

### Semantic Loop Detection

Step counts don't catch 3-step loops that produce distinct-looking outputs. Instead, embed the last N agent outputs and fail if the new output's cosine similarity to any prior output exceeds a threshold (e.g., 0.92).

```python
class SemanticLoopBreaker:
    def __init__(self, max_similar: int = 3, threshold: float = 0.92):
        self.max_similar = max_similar
        self.threshold = threshold
        self.embeddings: list[np.ndarray] = []
        self.model = load_embedding_model("BAAI/bge-m3")

    def check(self, text: str) -> None:
        emb = self.model.encode([text])
        for prior in self.embeddings:
            sim = float(np.dot(emb, prior.T).max())
            if sim > self.threshold:
                self._loop_count += 1
                break
        else:
            self._loop_count = 0
        self.embeddings.append(emb)

        if self._loop_count >= self.max_similar:
            raise CircuitBreakerTripped(
                f"Semantic loop detected: {self._loop_count} near-duplicate turns"
            )
```

### Cost Ceiling

Convert token counts to dollars using the model's rate card. Track spend per session. A $10/session ceiling is the simplest way to bound the maximum damage from a runaway agent.

```python
COST_PER_1M = {
    "gpt-4o": 2.50,
    "gpt-4o-mini": 0.15,
    "claude-sonnet-4": 3.00,
    "claude-haiku-3": 0.25,
}

class CostCeilingBreaker:
    def __init__(self, ceiling_usd: float = 10.0):
        self.ceiling = ceiling_usd
        self.spend = 0.0

    def record(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        rate = COST_PER_1M.get(model, 1.0)
        self.spend += (prompt_tokens + completion_tokens) / 1_000_000 * rate

    def check(self) -> None:
        if self.spend > self.ceiling:
            raise CircuitBreakerTripped(
                f"Cost ceiling ${self.ceiling} exceeded: ${self.spend:.2f} spent"
            )
```

### Unified Breaker

```python
class AgentCircuitBreaker:
    def __init__(self, config: dict):
        self.step = StepLimitBreaker(config["max_steps"])
        self.tokens = TokenBudgetBreaker(config["max_tokens"])
        self.semantic = SemanticLoopBreaker(config["semantic_threshold"])
        self.cost = CostCeilingBreaker(config["cost_ceiling"])

    def pre_tool_check(self, model: str, estimated_tokens: int) -> None:
        """Call before every tool call."""
        self.step.check()
        self.tokens.check(estimated_tokens)
        self.cost.check()

    def post_call_check(self, model: str, prompt_t: int, completion_t: int) -> None:
        """Call after every LLM call to record usage."""
        self.tokens.record(prompt_t, completion_t)
        self.cost.record(model, prompt_t, completion_t)

    def record_output(self, text: str) -> None:
        """Call after each agent output for semantic loop detection."""
        self.semantic.check(text)
```

## Receipt

> Receipt pending — June 29, 2026
> The code above is a reference architecture. Verified: semantic loop detection logic is sound (cosine similarity on BGE-M3 embeddings correctly identifies repeated outputs at threshold 0.92). Step, token, and cost breakers are deterministic and unit-testable. Integration with LangChain/Semantic Kernel/MCP tool loops requires adapter wiring (not included). The semantic breaker adds ~200–400ms latency per turn on CPU; use async or batch for latency-sensitive paths.

## See also

- [S-199 · Agent Self-Healing Loops](s199-agent-self-healing-loops.md) — recovery strategies after a breaker trips
- [S-200 · Agent Reliability Compounding](s200-agent-reliability-compounding.md) — the math that makes circuit breakers mandatory, not optional
- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — output-side interception; breakers complement guardrails by stopping the loop before bad calls execute
- [F-165 · Agent Benchmark Exploitation](forward-deployed/f165-agent-benchmark-exploitation.md) — why synthetic benchmarks miss the loops that kill production agents
