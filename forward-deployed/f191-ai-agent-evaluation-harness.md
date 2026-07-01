# F-191 · AI Agent Evaluation Harness

You ship an AI agent. It works for the happy path. You ship it. Three months later, you discover it silently skips refunds on Tuesdays, hallucinates confidence on low-stakes queries, and loops forever when the search API returns HTML instead of JSON. You had no idea — because you never measured what it actually does, only what it outputs.

An evaluation harness is the difference between shipping blind and shipping with evidence.

## Forces
- **Output-only metrics miss process failures.** An agent can produce a correct answer through a broken plan (Google Cloud, 2026: "silent failure"). SWE-bench, GAIA, MMLU — these measure final output. Your agent's failure modes are behavioral: wrong tools called, wrong arguments passed, retries that never converge, tasks silently abandoned. Output metrics have zero signal on these.
- **Manual eval doesn't scale.** Human review catches what automation misses — tone, trust, contextual appropriateness — but you cannot have a human in the loop for every production run. The ratio is inverted: 95% of runs are production, 5% are human-reviewed.
- **State explosion makes exhaustive testing impossible.** An agent has combinatorial paths: tool A then B, tool B then A, tool A times out and retries, tool A returns malformed data. You cannot write a test for every path. You need a framework for choosing which paths matter and measuring what matters in each.
- **Eval quality degrades faster than code.** Model upgrades, prompt changes, upstream API shifts — all silently change agent behavior. Without a harness, you discover regressions in production, not in CI.

## The move

Build a harness around four metric tiers, run it in CI, gate deploys on thresholds:

**Tier 1 — Task Completion** (did the agent finish the job?)
- Task completion rate, partial completion rate, abandonment rate
- Ground-truth output matching (exact, fuzzy, semantic similarity)

**Tier 2 — Tool Use Correctness** (did the agent use the right tools the right way?)
- Tool selection accuracy: was the correct tool called?
- Argument accuracy: were the arguments correct?
- Call ordering: was the sequence correct?
- Error recovery: does the agent handle tool errors gracefully?

**Tier 3 — Process Quality** (is the agent working efficiently and safely?)
- Token efficiency (actual vs. estimated), latency per step, total cost per task
- Hallucination detection (factual claims cross-checked against sources)
- Policy compliance (PII handling, permission boundaries, escalation correctness)

**Tier 4 — User Experience** (would a human accept this?)
- Response coherence, helpfulness scoring (LLM-as-judge), escalation appropriateness
- Conversation-level metrics: context retention across turns, persona consistency

```python
"""
Minimal AI agent evaluation harness.
Captures full traces, scores across four metric tiers, gates deploys on thresholds.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class Verdict(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]
    result: Any
    latency_ms: float
    error: str | None = None


@dataclass
class TraceStep:
    model_input: str
    model_output: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_ms: float = 0.0
    tokens_spent: int = 0


@dataclass
class Trace:
    test_id: str
    task: str
    steps: list[TraceStep] = field(default_factory=list)
    final_output: str = ""
    expected_output: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0


@dataclass
class MetricResult:
    name: str
    score: float          # 0.0–1.0
    threshold: float
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def verdict(self) -> Verdict:
        if self.score >= self.threshold:
            return Verdict.PASS
        return Verdict.FAIL


# ── Tier 1: Task Completion ─────────────────────────────────────────────────

def completion_rate(trace: Trace, threshold: float = 0.9) -> MetricResult:
    """
    Did the agent reach a correct final state?
    For classification tasks: output matches label.
    For extraction tasks: key fields present.
    For generation tasks: use semantic similarity or LLM-as-judge.
    """
    if not trace.final_output:
        return MetricResult(
            name="task_completion",
            score=0.0,
            threshold=threshold,
            details={"reason": "no output produced"}
        )

    if trace.expected_output is None:
        # Fallback: check for empty/error signals in output
        error_signals = ["sorry", "couldn't", "unable", "error", "failed"]
        lower = trace.final_output.lower()
        failure_indicators = sum(1 for s in error_signals if s in lower)
        score = max(0.0, 1.0 - (failure_indicators * 0.3))
    else:
        # Exact match (binary) as floor — upgrade to semantic similarity for production
        score = 1.0 if trace.final_output.strip() == trace.expected_output.strip() else 0.0

    return MetricResult(
        name="task_completion",
        score=score,
        threshold=threshold,
        details={"output_length": len(trace.final_output)}
    )


# ── Tier 2: Tool Use Correctness ──────────────────────────────────────────

def tool_selection_accuracy(trace: Trace, expected_tools: list[str],
                           threshold: float = 0.85) -> MetricResult:
    """
    Were the correct tools called, in roughly the right order?
    expected_tools: ordered list of tool names the agent *should* call.
    """
    actual_calls = []
    for step in trace.steps:
        for tc in step.tool_calls:
            if tc.error is None:
                actual_calls.append(tc.tool_name)

    # Normalize and compare prefixes (some tools have versioned names)
    def normalize(name: str) -> str:
        return name.replace("_v2", "").replace("-v1", "").lower()

    expected_norm = [normalize(t) for t in expected_tools]
    actual_norm   = [normalize(t) for t in actual_calls]

    # Longest common subsequence as a proxy for correct ordering
    def lcs(a: list[str], b: list[str]) -> int:
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i-1] == b[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        return dp[m][n]

    recall = lcs(expected_norm, actual_norm) / max(len(expected_norm), 1)
    precision = lcs(expected_norm, actual_norm) / max(len(actual_norm), 1)
    score = 2 * precision * recall / (precision + recall + 1e-9)

    return MetricResult(
        name="tool_selection_accuracy",
        score=score,
        threshold=threshold,
        details={
            "expected_tools": expected_tools,
            "actual_tools": actual_calls,
            "recall": round(recall, 3),
            "precision": round(precision, 3)
        }
    )


def error_recovery_score(trace: Trace, threshold: float = 0.8) -> MetricResult:
    """
    When tool calls fail, does the agent recover gracefully?
    Penalize: silent skip, infinite retry, panic spiral.
    Reward: retry with corrected args, graceful fallback, escalation.
    """
    total_errors = sum(1 for step in trace.steps for tc in step.tool_calls if tc.error)
    if total_errors == 0:
        return MetricResult(name="error_recovery", score=1.0, threshold=threshold)

    recovery_signals = ["retry", "fallback", "escalate", "unable", "error", "failed", "sorry"]
    recoveries = 0
    for step in trace.steps:
        if any(tc.error for tc in step.tool_calls):
            # Check if the model output acknowledges the error
            if any(sig in step.model_output.lower() for sig in recovery_signals):
                recoveries += 1

    score = recoveries / total_errors
    return MetricResult(
        name="error_recovery",
        score=score,
        threshold=threshold,
        details={"total_errors": total_errors, "recoveries": recoveries}
    )


# ── Tier 3: Process Quality ─────────────────────────────────────────────────

def token_efficiency(trace: Trace, max_tokens_per_task: int = 8000,
                     threshold: float = 0.8) -> MetricResult:
    """Did the agent stay within token budget?"""
    total = sum(step.tokens_spent for step in trace.steps)
    score = max(0.0, 1.0 - (total / max_tokens_per_task))
    return MetricResult(
        name="token_efficiency",
        score=score,
        threshold=threshold,
        details={"total_tokens": total, "budget": max_tokens_per_task}
    )


def hallucination_score(trace: Trace, threshold: float = 0.9) -> MetricResult:
    """
    Cross-check factual claims in final_output against tool call results.
    Simplified: flag if final_output cites data that no tool call produced.
    Production: use NLI model or external knowledge base.
    """
    if not trace.steps:
        return MetricResult(name="hallucination", score=0.5, threshold=threshold)

    facts_provided = set()
    for step in trace.steps:
        for tc in step.tool_calls:
            if tc.result and isinstance(tc.result, str) and tc.error is None:
                # Truncate to first 500 chars as fact sample
                facts_provided.add(tc.result[:500].lower())

    claim_signals = ["according to", "the data shows", "the report states", "based on"]
    output_lower = trace.final_output.lower()
    has_claims = any(sig in output_lower for sig in claim_signals)

    if not has_claims:
        return MetricResult(name="hallucination", score=1.0, threshold=threshold)

    # Check overlap between claimed facts and tool results (simplified)
    score = 0.5  # Neutral when claims exist but overlap can't be confirmed
    return MetricResult(
        name="hallucination",
        score=score,
        threshold=threshold,
        details={"has_claims": has_claims, "note": "upgrade to NLI model for production"}
    )


# ── Tier 4: User Experience ────────────────────────────────────────────────

def llm_judge_coherence(trace: Trace, judge_model: str = "gpt-4o-mini",
                        threshold: float = 0.8) -> MetricResult:
    """
    Use an LLM to score response coherence and helpfulness.
    In production: use a consistent judge prompt, log scores for drift detection.
    """
    if not trace.final_output:
        return MetricResult(name="coherence", score=0.0, threshold=threshold)

    # Placeholder: integrate with your LLM gateway here
    # Example using OpenAI:
    # from openai import OpenAI
    # client = OpenAI()
    # response = client.chat.completions.create(
    #     model=judge_model,
    #     messages=[{"role": "user", "content": f"Score 1-10: {trace.final_output}"}]
    # )
    # score = float(response.choices[0].message.content) / 10.0

    # Default: structural sanity check
    word_count = len(trace.final_output.split())
    score = min(1.0, word_count / 50)  # Penalize very short responses
    return MetricResult(
        name="coherence",
        score=score,
        threshold=threshold,
        details={"word_count": word_count, "note": "plug in LLM judge for production"}
    )


# ── Harness Runner ─────────────────────────────────────────────────────────

@dataclass
class EvalSuite:
    test_cases: list[dict[str, Any]]  # {id, task, expected_output, expected_tools}
    thresholds: dict[str, float]       # metric_name -> threshold

    def run(self, agent_fn) -> dict[str, Any]:
        results = {"passed": 0, "failed": 0, "skipped": 0, "details": []}

        for tc in self.test_cases:
            trace = agent_fn(tc["task"], tc.get("expected_output"))
            trace.expected_output = tc.get("expected_output")

            metrics = {
                "completion":       completion_rate(trace, self.thresholds.get("completion", 0.9)),
                "tool_accuracy":    tool_selection_accuracy(trace, tc.get("expected_tools", []), self.thresholds.get("tool_accuracy", 0.85)),
                "error_recovery":   error_recovery_score(trace, self.thresholds.get("error_recovery", 0.8)),
                "token_efficiency": token_efficiency(trace, self.thresholds.get("max_tokens", 8000)),
                "hallucination":    hallucination_score(trace, self.thresholds.get("hallucination", 0.9)),
                "coherence":        llm_judge_coherence(trace),
            }

            all_pass = all(m.verdict == Verdict.PASS for m in metrics.values())
            results["passed" if all_pass else "failed"] += 1
            results["details"].append({
                "test_id": tc["id"],
                "metrics": {k: {"score": v.score, "threshold": v.threshold,
                                 "verdict": v.verdict.value, "details": v.details}
                            for k, v in metrics.items()}
            })

        results["pass_rate"] = results["passed"] / len(self.test_cases)
        return results


# ── CI Gate ───────────────────────────────────────────────────────────────

def gate(results: dict[str, Any], min_pass_rate: float = 0.9) -> bool:
    """
    Gate deploys on eval pass rate.
    Run in CI: if not gate(results): sys.exit(1)
    """
    rate = results["pass_rate"]
    passed = results["passed"]
    total = results["passed"] + results["failed"]
    print(f"Eval: {passed}/{total} passed ({rate:.1%})")
    if rate < min_pass_rate:
        print(f"DEPLOY BLOCKED: pass rate {rate:.1%} < threshold {min_pass_rate:.1%}")
        return False
    print("DEPLOY CLEARED")
    return True


# Example usage with a mock agent
if __name__ == "__main__":
    from typing import Callable

    def mock_agent(task: str, expected_output: str | None = None) -> Trace:
        """Replace with your real agent."""
        trace = Trace(test_id="mock", task=task)
        trace.final_output = f"Mock response to: {task}"
        return trace

    suite = EvalSuite(
        test_cases=[
            {
                "id": "triage-001",
                "task": "Classify this support ticket as billing, shipping, or returns",
                "expected_output": "billing",
                "expected_tools": ["classify_ticket"],
            },
            {
                "id": "refund-002",
                "task": "Process a refund for order #12345",
                "expected_output": "Refund processed: $49.99",
                "expected_tools": ["lookup_order", "process_refund"],
            },
            {
                "id": "research-003",
                "task": "Find the Q1 2026 revenue for Acme Corp",
                "expected_output": None,
                "expected_tools": ["web_search", "extract_facts"],
            },
        ],
        thresholds={
            "completion": 0.9,
            "tool_accuracy": 0.85,
            "error_recovery": 0.8,
            "max_tokens": 8000,
            "hallucination": 0.9,
        }
    )

    results = suite.run(mock_agent)
    gate(results, min_pass_rate=0.9)
    print(json.dumps(results, indent=2, default=str))
```

## Receipt
> Receipt pending — 2026-07-01

## See also
- [F-189 · Private Eval Dataset Construction](forward-deployed/f189-private-eval-dataset-construction.md) — complement: the harness is only as good as the eval data you feed it
- [F-188 · AI Agent Red Teaming](forward-deployed/f188-ai-agent-red-teaming.md) — the safety/governance dimension of the same problem space
- [S-318 · Multi-Agent Coordination Architectures](stacks/s318-multi-agent-coordination-architectures.md) — tool selection accuracy (Tier 2) is especially critical in multi-agent pipelines
