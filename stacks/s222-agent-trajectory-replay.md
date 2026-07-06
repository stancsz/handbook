# S-222 · Agent Trajectory Replay

An agent fails in production. You have the final output — wrong answer, empty result, crash — and a 3,000-token trace log. You know the agent called `tool_X` at step 7 but you don't know *why* it chose that tool, what the prior step's output looked like when fed to the LLM, or whether the failure was a one-in-a-thousand fluke or a reproducible regression. Without replay — the ability to re-run that exact trajectory with the exact same inputs and instrument it live — you can only guess. This is the debugging crisis in production AI: agents are non-deterministic, failures are expensive, and most teams have no way to reproduce what happened.

## Forces

- Agent behavior is non-deterministic by design — same input can produce different outputs across runs due to temperature, sampling, or model version changes; a bug that appears once in 500 runs never surfaces in a local test
- Production failures arrive without reproducible test cases — by the time you hear about it, the session is gone and you only have the final output, not the intermediate state
- Existing software replay tools (deterministic execution, time-travel debuggers) assume deterministic inputs; replaying a trajectory means replaying the exact LLM call with the exact random seed, exact tool responses, and exact context window
- Span tracing (W-07) tells you *what* happened but not *why* — to understand why a tool was called incorrectly, you need to see the LLM's input at that exact step, not just the span metadata
- Debugging in production without replay means shipping blind changes — you modify the prompt, deploy, and wait to see if the support tickets stop
- The compounding failure math (S-200) means early-step errors propagate — the bug's root cause is usually 3–5 steps before the visible failure, requiring full trajectory traversal to find

## The move

Build a trajectory capture → storage → deterministic replay pipeline. Every production agent run is a candidate for replay. Capture complete state, not just outcomes.

### Capture the right data

Not all data in a trace is replay-relevant. Capture precisely:

```python
import hashlib, json, time
from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class TrajectoryStep:
    step_index: int
    llm_input_tokens: list[str]        # actual token IDs, not text
    llm_output_tokens: list[int]       # for exact reproduction
    model: str
    temperature: float
    tool_calls: list[dict]             # what the model requested
    tool_results: list[Any]            # actual returned data
    seed: int | None                   # RNG seed if used
    timestamp: float

@dataclass
class TrajectoryCapture:
    trace_id: str
    session_id: str
    user_input_hash: str               # SHA-256 of the actual input
    agent_config: dict                 # model, tools, system prompt version
    steps: list[TrajectoryStep]
    final_output: Any
    outcome: str                       # "success" | "wrong_answer" | "error" | "loop"

    def capture(self, agent_state: dict, step: int) -> None:
        """Call after each agent loop iteration."""
        self.steps.append(TrajectoryStep(
            step_index=step,
            llm_input_tokens=agent_state["input_token_ids"],
            llm_output_tokens=agent_state["output_token_ids"],
            model=agent_state["model"],
            temperature=agent_state["temperature"],
            tool_calls=agent_state["tool_calls"],
            tool_results=agent_state["tool_results"],
            seed=agent_state.get("seed"),
            timestamp=time.time(),
        ))

    def persist(self, storage_adapter) -> str:
        """Write to object storage or DB. Returns the trace_id."""
        payload = json.dumps(asdict(self), indent=2)
        key = f"trajectories/{self.trace_id}.json"
        storage_adapter.write(key, payload.encode())
        return self.trace_id
```

### Store with content-addressing

Use the SHA-256 of the user input as part of the trace key. This lets you find all trajectories for the same input across model versions:

```python
def content_address(trajectory: TrajectoryCapture) -> str:
    """Deduplication + retrieval key based on actual input content."""
    h = hashlib.sha256()
    h.update(trajectory.user_input_hash.encode())
    h.update(trajectory.agent_config["model"].encode())
    h.update(trajectory.agent_config["system_prompt_version"].encode())
    return h.hexdigest()[:16]
```

### Replay deterministically

The core replay function: feed the exact same token sequence back through the agent with instrumentation turned on:

```python
def replay_trajectory(trace_id: str, storage_adapter,
                      agent_factory,
                      instrumentation_fn) -> dict:
    """
    Re-run a captured trajectory with live inspection.
    instrumentation_fn is called after each step with the live agent_state
    so you can inspect internal decisions, not just final output.
    """
    trajectory = storage_adapter.read(f"trajectories/{trace_id}.json")
    trajectory = TrajectoryCapture(**json.loads(trajectory))

    agent = agent_factory(
        model=trajectory.agent_config["model"],
        temperature=0.0,           # zero temperature for determinism
        fixed_seed=42,              # override seed for reproducibility
        tools=trajectory.agent_config["tools"],
    )

    # Inject the exact token sequence from step 0
    agent.inject_state(
        input_token_ids=trajectory.steps[0].llm_input_tokens,
        tool_results=trajectory.steps[0].tool_results,
    )

    divergence_points = []
    for i, captured_step in enumerate(trajectory.steps):
        live_state = agent.step()
        instrumentation_fn(i, live_state)

        if live_state["tool_calls"] != captured_step.tool_calls:
            divergence_points.append({
                "step": i,
                "expected": captured_step.tool_calls,
                "actual": live_state["tool_calls"],
                "live_llm_input": live_state["llm_input_tokens"],
            })

    return {
        "trace_id": trace_id,
        "divergence_count": len(divergence_points),
        "divergences": divergence_points,
        "live_output": agent.final_output(),
    }
```

### Use divergence points to root-cause

When `replay_trajectory` returns divergences, the first divergence is almost always the root cause. Compare the LLM input at the divergence step:

- **Context mismatch**: was the captured step's context longer or shorter? (context compaction ran between runs)
- **Tool result difference**: did a tool return a different value? (external state changed)
- **Model behavior shift**: same input, same model, different output? (model version changed silently)

### Integrate into incident workflow

```
Production failure reported
    ↓
Search trace store by user_input_hash + time window
    ↓
Load matching trajectory(ies)
    ↓
replay_trajectory() with divergence detection
    ↓
Inspect first divergence point → fix prompt/tool/context
    ↓
Add to behavioral regression suite (S-220)
```

## Receipt

> Receipt pending — 2026-06-30

## See also

- [W-07 · Agent Span Tracing](workspace/w07-agent-span-tracing.md) — span types and instrumentation patterns; S-222 complements W-07 by adding replay capability on top of spans
- [S-219 · Agent Eval Harness](stacks/s219-agent-eval-harness.md) — eval harnesses catch regressions; replay helps you understand *why* a regression happened
- [S-220 · Agentic Behavioral Regression Suite](stacks/s220-agentic-behavioral-regression-suite.md) — replay sessions are the source material for regression test cases
- [S-217 · Agent Capability Authorization](stacks/s217-agent-capability-authorization.md) — replay is essential for post-incident audit; knowing what the agent *should* have done requires knowing what it *did* do
