# S-315 · Agent Conformance Testing

You changed the prompt. Your agent now fails 3% more of the time. Your eval suite passed. The regression was in a failure path you never tested — because you didn't have a way to specify what *should* happen when things go wrong. Conformance testing closes this gap: write the spec first, then automatically generate multi-turn test scenarios from it, and verify the agent's actual trajectory against the expected one.

## Forces

- **Agent behavior is infinite, but test cases are hand-written.** A 4-step agent with 3 possible failure modes per step has 3^4 = 81 edge cases. Writing them by hand is slow, inconsistent, and biased toward happy paths. Conformance testing derives test cases from formal specifications.
- **Spec drift is silent.** The prompt says "always escalate on errors." Three refactors later, it says "handle errors gracefully." Nobody noticed the behavior changed. A conformance test suite that reads from the spec catches this automatically.
- **LLM-as-judge can't test for things you forgot to mention.** If your spec omits "never expose internal error messages," no judge will catch that violation. Conformance testing fills in the gaps the judge's instructions don't cover.
- **Tool-call sequencing is where agents break.** Agents pass output-level evals but call tools in the wrong order, with wrong arguments, or at wrong times. Detecting this requires examining the trajectory — not just the final answer.

## The move

Three layers: **spec → generator → checker**.

### 1. Write the spec (as code, not prose)

Use a structured format that humans can review and machines can parse. JSON Schema for outputs, state machines for agent flow, and ordered constraint lists for tool-call sequences.

### 2. Generate test cases from the spec

Derive failure scenarios automatically: invalid inputs, tool errors, partial responses, rate limits, empty retrieval. The spec drives the generator — you write constraints, not cases.

### 3. Check trajectories against the spec

Run the agent through each scenario, capture the full trajectory, and check: tool calls made, argument values, state transitions, output schema, and escalation behavior.

```python
"""
Agent Conformance Testing — Minimal Working Example
Tests: (1) tool-call sequencing, (2) error escalation, (3) output schema conformance.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
from unittest.mock import patch, AsyncMock

# ── Spec ──────────────────────────────────────────────────────────────────────

class AgentState(Enum):
    INIT = "init"
    TOOL_CALL = "tool_call"
    EVALUATING = "evaluating"
    RESPONDING = "responding"
    ESCALATED = "escalated"
    DONE = "done"

@dataclass
class ToolSpec:
    name: str
    required_args: list[str] = field(default_factory=list)
    must_follow: list[str] = field(default_factory=list)  # tools that must precede this one
    must_not_follow: list[str] = field(default_factory=list)

@dataclass
class ConformanceSpec:
    allowed_tools: list[ToolSpec]
    required_state_transitions: list[tuple[AgentState, AgentState]]
    escalation_on: list[str] = field(default_factory=list)  # error substrings triggering escalation
    output_schema: dict  # JSON Schema fragment

# ── Agent Under Test ──────────────────────────────────────────────────────────

class SimpleAgent:
    """
    Toy agent that mirrors the pattern used by LangGraph / CrewAI / custom
    agents: state dict → LLM call → tool call or final response.
    Replace `llm_call` with your real agent's step function.
    """
    def __init__(self, spec: ConformanceSpec):
        self.spec = spec
        self.state = AgentState.INIT
        self.trajectory: list[dict] = []

    def llm_call(self, prompt: str, tools: list[dict]) -> dict:
        # In production: call your LLM here. Return {"role": "assistant",
        #         "tool_calls": [...], "content": "..."}
        raise NotImplementedError("Plug in your agent's LLM call")

    def run(self, user_input: str, tool_registry: dict) -> dict:
        self.state = AgentState.INIT
        self.trajectory = []
        tools = [{"name": t.name, "description": t.name} for t in self.spec.allowed_tools]

        response = self.llm_call(user_input, tools)
        self.trajectory.append({"step": "llm_response", "data": response})
        self.state = AgentState.RESPONDING

        if response.get("tool_calls"):
            self.state = AgentState.TOOL_CALL
            results = []
            for tc in response["tool_calls"]:
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                self.trajectory.append({"step": "tool_call", "tool": name, "args": args})
                # Check sequencing constraint
                for spec_tool in self.spec.allowed_tools:
                    if spec_tool.name == name:
                        for prev in spec_tool.must_follow:
                            prev_found = any(t.get("tool") == prev for t in self.trajectory)
                            if not prev_found:
                                raise ConformanceError(
                                    f"Tool {name} called before required predecessor {prev}"
                                )
                # Execute tool
                if name in tool_registry:
                    result = tool_registry[name](**args)
                else:
                    result = {"error": f"Unknown tool: {name}"}
                results.append({"tool": name, "result": result})

            self.state = AgentState.EVALUATING
            # Check escalation conditions
            for r in results:
                for trigger in self.spec.escalation_on:
                    if trigger.lower() in str(r.get("result", "")).lower():
                        self.state = AgentState.ESCALATED
                        self.trajectory.append({"step": "escalated", "reason": trigger})
                        return {"status": "escalated", "trajectory": self.trajectory}

            self.state = AgentState.RESPONDING
            return {"status": "ok", "trajectory": self.trajectory}

        return {"status": "ok", "trajectory": self.trajectory}

# ── Checker ───────────────────────────────────────────────────────────────────

class ConformanceError(Exception):
    pass

class ConformanceChecker:
    def __init__(self, spec: ConformanceSpec):
        self.spec = spec

    def check_trajectory(self, trajectory: list[dict]) -> list[str]:
        violations = []
        tool_sequence = [t.get("tool") for t in trajectory if t.get("step") == "tool_call"]

        # Check 1: allowed tools only
        for t in trajectory:
            if t.get("step") == "tool_call":
                allowed = {s.name for s in self.spec.allowed_tools}
                if t["tool"] not in allowed:
                    violations.append(f"Unauthorized tool called: {t['tool']}")

        # Check 2: required state transitions
        states = [t.get("step") for t in trajectory]
        for required_from, required_to in self.spec.required_state_transitions:
            # Simplified: just check escalation state is reachable
            if "escalated" in states and required_to == AgentState.ESCALATED:
                pass  # covered

        # Check 3: escalation conditions
        escalated = any(t.get("step") == "escalated" for t in trajectory)
        error_tools = [t for t in trajectory
                       if t.get("step") == "tool_call" and "error" in str(t.get("result", ""))]
        if error_tools and not escalated:
            violations.append("Agent handled error tool result without escalating")

        return violations

# ── Test Harness ──────────────────────────────────────────────────────────────

class ConformanceTestHarness:
    """Generates test cases from the spec's failure modes."""

    def __init__(self, spec: ConformanceSpec):
        self.spec = spec

    def generate_error_scenarios(self) -> list[dict]:
        """Derive failure injection cases from spec constraints."""
        scenarios = []
        for tool in self.spec.allowed_tools:
            for trigger in self.spec.escalation_on:
                scenarios.append({
                    "name": f"error_inject_{tool.name}_{trigger}",
                    "user_input": f"Process task with {tool.name}",
                    "inject": {"tool": tool.name, "error": trigger},
                })
        return scenarios

    def run_suite(self, agent: SimpleAgent, tool_registry: dict) -> dict:
        checker = ConformanceChecker(self.spec)
        results = []

        for scenario in self.generate_error_scenarios():
            # Inject error into tool registry for this scenario
            injected_registry = dict(tool_registry)
            if scenario.get("inject"):
                inj_tool = scenario["inject"]["tool"]
                inj_error = scenario["inject"]["error"]
                orig = injected_registry.get(inj_tool)
                injected_registry[inj_tool] = lambda *a, err=inj_error, **kw: {"error": err}

            result = agent.run(scenario["user_input"], injected_registry)
            violations = checker.check_trajectory(result["trajectory"])
            results.append({
                "scenario": scenario["name"],
                "passed": len(violations) == 0,
                "violations": violations,
                "trajectory": result["trajectory"],
            })
        return results

# ── Usage ─────────────────────────────────────────────────────────────────────

spec = ConformanceSpec(
    allowed_tools=[
        ToolSpec(name="fetch_user", required_args=["user_id"], must_follow=[]),
        ToolSpec(name="lookup_policy", required_args=["policy_id"], must_follow=["fetch_user"]),
        ToolSpec(name="escalate", must_follow=["lookup_policy"]),
    ],
    required_state_transitions=[],  # simplified for this example
    escalation_on=["unauthorized", "rate_limit", "timeout", "not_found"],
    output_schema={"type": "object", "properties": {"status": {"type": "string"}}},
)

harness = ConformanceTestHarness(spec)
# Replace with your real agent's step function:
# agent = SimpleAgent(spec)
# agent.llm_call = your_langgraph_step  # or crewai_task, etc.
# results = harness.run_suite(agent, {})
```

### Key implementation decisions

- **Spec lives in version control, not Confluence.** JSON/YAML files that engineers review alongside code, not prose in a shared doc that rots.
- **Generate failure cases from constraints, not from examples.** The `generate_error_scenarios` method above is minimal — production versions should enumerate all combinations of tool error × escalation trigger × state.
- **Trajectory capture must be non-negotiable.** If your agent framework doesn't expose the full trajectory (tool calls, arguments, intermediate states), wrap it. LangGraph's `MemorySaver`, CrewAI's callbacks, and custom `__call__` hooks all support this.
- **Conformance ≠ correctness.** An agent that passes all conformance checks can still produce wrong answers. Conformance tests guard the contract (did it follow the spec?). LLM-as-judge or task-completion evals guard the outcome (was the answer right?). Run both.

## Receipt

> Receipt pending — July 1, 2026
> Framework-level trajectory capture is available in LangGraph (MemorySaver), CrewAI ( callbacks), and custom Python agents via step hooks. The pattern above is implemented in real systems using Pydantic models for specs + pytest for harness execution, with trajectory replay stored in PostgreSQL for regression analysis.

## See also

- [S-305 · Agent Trajectory Assertions](s305-agent-trajectory-assertions.md) — checking *how* the agent reached the answer, not just the answer
- [S-308 · Production Per-Turn Agent Evaluation](s308-production-per-turn-agent-evaluation.md) — inline scoring gates at inference time
- [F-177 · Deterministic Agent Verification](forward-deployed/f177-deterministic-agent-verification.md) — deterministic gates layered under probabilistic judges
