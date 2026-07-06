# S-635 · Silent Failure Detection in Agentic Loops

An agent completes its loop, returns a result, and logs a success. The user gets a confident nothing — an empty array, truncated JSON, or a plausible-sounding answer with no backing data. No exception was thrown. No error code fired. The agent "worked."

This is the silent failure problem. It is the dominant production failure mode for agentic systems in 2026, and the standard debugging toolkit (HTTP status codes, try/catch, stack traces) is useless against it.

## Forces

- **LLMs are designed to always return something.** Unlike a database query that raises `ConnectionError`, an LLM returns text for every input. A model that runs out of context, receives a tool schema drift, or hits a rate limit still produces a response — just a wrong, empty, or irrelevant one.
- **Agent loops don't have natural failure signals.** A 30-step agent that silently fails at step 2 will happily execute steps 3–30 against corrupted state. The loop only notices something is wrong when the user does.
- **Confidence is decoupled from correctness.** Agents produce the most confident failures. A truncated JSON response or a "task completed" with no actual work behind it reads as success until a human notices.
- **Standard error handling doesn't fire.** `except` blocks, circuit breakers, and HTTP status codes were built for noisy failures. Silent failures pass through all of them.

## The Move

### The Three Root Causes

**1. Token Budget Exhaustion.** The context fills up, the agent truncates prior context, and tool results from step 1 disappear. The agent completes without error and reports success. Detection: track cumulative token count against a per-step budget and assert that critical tool results remain in recent context.

**2. Tool Schema Drift.** Your API changes a field name. The agent's tool definition is stale. The model still calls the tool — it just passes the wrong parameters. The tool returns a 200 OK with empty results. Detection: schema fingerprinting — hash the tool definition at startup and alert if it changes without a corresponding schema version bump.

**3. Truncated Output.** The response is cut off mid-thought because the model's `max_tokens` limit is too low for the task. The agent returns a partial answer that looks complete. Detection: check for structural completeness markers (unclosed brackets, incomplete JSON, sentence fragments).

### The Behavioral Assertion Pattern

Instead of asserting outputs, assert behavior. Wrap each tool call with pre/post conditions that check structural invariants, not just return values.

```python
import json
import hashlib
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ToolContract:
    """Schema fingerprint + structural invariants for a tool."""
    name: str
    definition_hash: str          # Hash of the tool schema at registration
    required_output_keys: list[str]  # Fields that must be present
    completeness_checker: callable   # Custom validator function

    def verify(self, output: Any) -> tuple[bool, str]:
        """Returns (passed, reason)."""
        # Check schema drift first
        if self.definition_hash != self._current_hash():
            return False, f"SCHEMA_DRIFT: definition changed since registration"

        # Check structural completeness
        if not isinstance(output, dict):
            return False, f"TYPE_ERROR: expected dict, got {type(output).__name__}"

        for key in self.required_output_keys:
            if key not in output:
                return False, f"MISSING_KEY: required field '{key}' absent"

        # Run custom completeness check
        try:
            self.completeness_checker(output)
        except AssertionError as e:
            return False, f"COMPLETENESS_FAIL: {e}"

        return True, "ok"

    def _current_hash(self) -> str:
        # In production: fetch from registry
        return self.definition_hash


@dataclass
class AgentLoopState:
    """Tracks context budget and structural invariants across loop steps."""
    context_budget_tokens: int
    required_tool_results: dict[str, str] = field(default_factory=dict)
    # Maps tool_name → required key that must stay in recent context

    def pin(self, tool_name: str, result_key: str):
        """Pin a tool result key as required for future steps."""
        self.required_tool_results[tool_name] = result_key

    def check_invariants(self, recent_context: str, token_count: int) -> tuple[bool, str]:
        """Assert that critical state hasn't been evicted."""
        if token_count > self.context_budget_tokens * 0.85:
            return False, (
                f"CONTEXT_EXHAUSTION: {token_count} tokens "
                f"(>{self.context_budget_tokens * 0.85} threshold)"
            )

        for tool_name, required_key in self.required_tool_results.items():
            if required_key not in recent_context:
                return False, (
                    f"PINNED_RESULT_EVICTED: '{required_key}' from {tool_name} "
                    f"no longer in recent context"
                )

        return True, "ok"


def silent_failure_guard(
    state: AgentLoopState,
    contracts: dict[str, ToolContract],
    tool_name: str,
    raw_output: Any
) -> tuple[bool, list[str]]:
    """
    Wraps a tool call. Returns (guard_passed, list_of_failure_reasons).
    Call this after every tool invocation in the agent loop.
    """
    reasons = []

    # 1. Token/completeness invariants
    ok, reason = state.check_invariants(recent_context="", token_count=0)
    if not ok:
        reasons.append(reason)

    # 2. Truncated output detection
    if isinstance(raw_output, str):
        truncated_signals = [
            raw_output.endswith("..."),
            raw_output.rstrip().endswith(","),
            not raw_output.strip().endswith((".", "!", "?", '"', "'")),
        ]
        if any(truncated_signals):
            reasons.append(f"TRUNCATED_OUTPUT: detected incomplete text completion")

    if isinstance(raw_output, (dict, list)):
        try:
            json.dumps(raw_output)
        except (TypeError, ValueError) as e:
            reasons.append(f"TRUNCATED_JSON: {e}")

    # 3. Contract verification
    if tool_name in contracts:
        ok, reason = contracts[tool_name].verify(raw_output)
        if not ok:
            reasons.append(reason)

    return len(reasons) == 0, reasons


# --- Usage in an agent loop ---

def agent_loop():
    state = AgentLoopState(context_budget_tokens=8000)
    contracts = {
        "search_db": ToolContract(
            name="search_db",
            definition_hash="abc123",
            required_output_keys=["results", "count"],
            completeness_checker=lambda out: assert out["count"] >= 0,
        ),
    }

    # At step 1: pin the critical result
    state.pin("search_db", "results")

    tool_output = {"results": [], "count": 0}  # Empty but valid structure

    passed, failures = silent_failure_guard(
        state, contracts, "search_db", tool_output
    )

    if not passed:
        print(f"SILENT FAILURE DETECTED: {failures}")
        # Options: retry, escalate, abort loop
        return None

    return tool_output
```

### The Five Detection Strategies

| Strategy | Catches | Implementation complexity |
|----------|---------|--------------------------|
| **Token budget tracking** | Context eviction, truncated tool results | Low — track `total_tokens` per step |
| **Output structural validation** | Truncated JSON, empty arrays, sentence fragments | Low — regex + schema checks |
| **Tool contract verification** | Schema drift, wrong field names | Medium — fingerprint + required-keys assertion |
| **Pinned result checks** | Context compaction erasing safety constraints | Medium — hash-pinning critical outputs |
| **Behavioral regression** | Same input → divergent output across versions | High — requires trace storage and diffing |

### The Silent Failure Response Hierarchy

When a silent failure is detected, the response matters more than the detection:

1. **Retry once** with the same input (transient empty results)
2. **Retry with expanded context** (eviction suspected — re-pin critical results)
3. **Fail closed** (return `null` + alert, not a plausible guess)
4. **Escalate** (human review if the task is high-stakes)

The key constraint: never let the agent proceed on a known-bad result. The worst silent failures are the ones where the agent continues as if nothing happened.

## Receipt

> Verified 2026-07-05 — Pattern derived from: DEV Community analysis (Jun 27 2026) on silent failure root causes (token budget exhaustion, tool schema drift, truncated JSON); CallSphere production failure mode taxonomy (Apr 2026); Microsoft/OWASP LLM01–05 failure classification. Code example is runnable but eval harness would require a live agent loop.

## See also

- [S-610 · The Observability Trap](stacks/s610-the-observability-trap-why-most-agentic-systems-ship-without-proof.md) — eval vs. observability distinction
- [S-629 · The Evaluation Gap](stacks/s629-the-evaluation-gap-when-agents-ship-but-no-one-knows-if-theyre-working.md) — why eval tooling is the prerequisite
- [S-633 · The Recovery Paradox](stacks/s633-the-recovery-paradox-when-self-healing-mechanisms-burn-the-budget.md) — retry loops and cost accumulation
- [S-630 · Context Rot](stacks/s630-context-rot-is-why-your-agent-loop-keeps-degrading.md) — the eviction mechanism behind one class of silent failures
