# S-606 · The Benchmark Laundering Problem

Your team evaluates three agent frameworks. Vendor A's agent scores 78% on SWE-bench. Vendor B's scores 82% on WebArena. You pick B. Three months later, B fails on 34% of real customer tasks while A handles them cleanly. The benchmarks were honest — the decisions built on them were wrong. The problem is not that benchmarks lie. The problem is that teams don't know what benchmarks measure, what they miss, and what they cost to misread.

## Forces

- **Public benchmarks measure proxy tasks, not your task.** SWE-bench tests Python gitHub issue resolution. WebArena tests browser-based web navigation. Neither measures whether your agent handles your internal CRM API, your ticket escalation logic, or your multi-agent handoff protocol. A 90% WebArena score tells you nothing about that.
- **Dataset contamination is endemic, not rare.** UC Berkeley RDI researchers (2026) examined eight of the most prominent agent benchmarks — SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench — and found all eight could be exploited via test-set contamination, metric manipulation, and task-specificity overfitting. Near-ceiling scores were achievable without genuine capability improvement. The contamination problem isn't a bug fixable by scrubbing; it's structural.
- **Vendor benchmarks are marketing, not measurement.** A model vendor's reported SWE-bench score is a cherry-picked, often cherry-tuned number. The eval was run by the party with the most to gain from a high score, on a version of the benchmark they may have seen during training, using inference compute budgets the vendor controls. This is benchmark laundering: transforming a vendor-controlled input into an apparently objective quality signal.
- **Static task-completion scores miss the non-functional dimensions that sink production agents.** Reliability under load, cost per task, graceful degradation on out-of-distribution inputs, safety boundary compliance, and long-horizon competence — none of these appear in pass/fail benchmark scores. Yet these are exactly what separates a shipping agent from an incident.
- **The benchmark-to-production gap compounds with agentic complexity.** A single-call LLM application might generalize well from a benchmark. A five-step agent with tool calls, memory, and a governance layer has a decision tree whose branches grow exponentially with benchmark task complexity. What a benchmark tests is one path through that tree. What production serves is all paths.

## The Move

Stop treating public benchmark scores as inputs to production decisions. Treat them as directional hints at best, and treat the gap between "benchmark performance" and "production performance" as a measurement problem to be solved with private evals.

**Build a private eval sovereignty stack in three layers:**

**Layer 1 — Trace-Derived Eval Sets (your production data)**

Capture real agent traces from production. Convert them to eval examples by annotating the outcome. This gives you data that matches your actual distribution, not the benchmark's proxy distribution.

```python
# Trace-to-eval pipeline: convert production traces to grounded eval examples
# Dependencies: opentelemetry-sdk, anthropic or openai SDK

from opentelemetry import trace
from collections import defaultdict

def traces_to_eval_examples(trace_store, min_turns=2, sample_rate=0.01):
    """
    Convert a trace store into (input, expected_output, metadata) eval examples.
    Only includes traces with known-good outcomes (e.g., task_completed=True).
    """
    examples = []
    for trace in trace_store.query(min_tool_calls=min_turns, sample_rate=sample_rate):
        # Extract the canonical task from the user input
        user_input = trace.spans[0].attributes.get("user.message", "")
        
        # Reconstruct the reference output from the trace
        # The last assistant message with a final answer is the ground truth
        final_output = None
        for span in reversed(trace.spans):
            if span.name == "assistant.message" and span.attributes.get("message.role") == "assistant":
                final_output = span.attributes.get("message.content", "")
                break
        
        if final_output and trace.outcome == "success":
            examples.append({
                "id": trace.trace_id,
                "input": user_input,
                "reference_output": final_output,
                "tool_sequence": [s.name for s in trace.spans if s.name.startswith("tool.")],
                "latency_ms": trace.duration_ms,
                "cost_usd": trace.compute_cost,
                "cohort": trace.user_segment,
            })
    
    return examples

# Export as JSONL for eval harness ingestion
def export_eval_set(examples, path="eval_set.jsonl"):
    import json
    with open(path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    print(f"Exported {len(examples)} eval examples → {path}")
```

**Layer 2 — Adversarial Benchmark Auditing (check before trusting)**

Before trusting a public benchmark score, run a contamination check: see whether the model can solve tasks from the benchmark's validation set when those tasks are paraphrased with a second LLM. A score that drops more than 15% on paraphrasing suggests the model memorized the test set rather than learned the task.

```python
# Contamination audit: paraphrase-sensitivity check
# If accuracy drops >15% on paraphrased eval items, suspect contamination

def contamination_audit(model, eval_set, paraphrase_model="claude-sonnet-4-7", threshold_drop=0.15):
    """
    Check if a model's eval-set performance survives paraphrase.
    Run the model on the original eval set, then on LLM-paraphrased versions.
    Flag if accuracy drops more than threshold_drop.
    """
    import anthropic
    
    client = anthropic.Anthropic()
    paraphraser = anthropic.Anthropic()
    
    # Step 1: baseline accuracy on original set
    baseline_score = evaluate(model, eval_set)
    
    # Step 2: paraphrase each item and re-evaluate
    paraphrased_set = []
    for item in eval_set:
        # Paraphrase the input to break surface-pattern memorization
        para_prompt = f"Rephrase this task description without changing its core requirements:\n\n{item['input']}"
        para_response = paraphraser.messages.create(
            model=paraphrase_model,
            max_tokens=512,
            messages=[{"role": "user", "content": para_prompt}]
        )
        paraphrased_item = item.copy()
        paraphrased_item["input"] = para_response.content[0].text
        paraphrased_set.append(paraphrased_item)
    
    paraphrased_score = evaluate(model, paraphrased_set)
    drop = baseline_score - paraphrased_score
    
    return {
        "baseline": baseline_score,
        "paraphrased": paraphrased_score,
        "drop": drop,
        "flagged": drop > threshold_drop,
        "verdict": "CONTAMINATED" if drop > threshold_drop else "CLEAN"
    }
    
    # Interpretation:
    # drop > 0.15: likely contaminated — benchmark performance doesn't generalize
    # drop 0.05-0.15: suspicious — verify with held-out items
    # drop < 0.05: likely genuine capability
```

**Layer 3 — Production-Grade Eval Metrics (beyond pass/fail)**

Score every eval run across five dimensions, not one. A agent that scores 100% on task completion but 40% on safety boundary compliance is not production-ready, regardless of what the benchmark says.

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class AgentEvalScore:
    task_completion: float      # 0-1: did the agent achieve the goal?
    tool_call_accuracy: float   # 0-1: correct tools, correct arguments?
    safety_compliance: float   # 0-1: stayed within defined behavioral boundaries?
    cost_efficiency: float     # 0-1: tokens + latency within budget for task type?
    robustness: float           # 0-1: performance on out-of-distribution inputs?

    def composite(self) -> float:
        # Weighted composite — tune weights for your domain
        return (
            self.task_completion * 0.35 +
            self.tool_call_accuracy * 0.25 +
            self.safety_compliance * 0.20 +
            self.cost_efficiency * 0.10 +
            self.robustness * 0.10
        )
    
    def gate(self, thresholds: dict[str, float]) -> bool:
        """Fail the eval if any dimension is below its threshold."""
        dims = {
            "task_completion": self.task_completion,
            "tool_call_accuracy": self.tool_call_accuracy,
            "safety_compliance": self.safety_compliance,
            "cost_efficiency": self.cost_efficiency,
            "robustness": self.robustness,
        }
        for dim, threshold in thresholds.items():
            if dims[dim] < threshold:
                return False
        return True
    
    def report(self) -> str:
        return (
            f"Task: {self.task_completion:.0%} | "
            f"Tool: {self.tool_call_accuracy:.0%} | "
            f"Safety: {self.safety_compliance:.0%} | "
            f"Cost: {self.cost_efficiency:.0%} | "
            f"Robustness: {self.robustness:.0%} | "
            f"Composite: {self.composite():.0%}"
        )
```

## Receipt

> Verified 2026-07-05 — Research synthesis from three independent sources:
> - Zylos Research (2026-05-13): "AI Agent Evaluation and Benchmarking: Beyond Task Completion" — Berkeley RDI finding that 8/8 major agent benchmarks are exploitable
> - Benchmarking Agents Review Vol. III (June 2026): Independent reference covering 17 benchmarks across 6 categories; documents the benchmark crisis and advocates Layer 3 production metrics
> - MetaTech/Bedda (2026-04-12): Analysis of Berkeley RDI study — three attack vectors: dataset contamination, metric manipulation, task-specificity exploitation
> - AgentMarketCap (2026-04-13): 40-60% cost reduction via dynamic model routing; routing classifier quality degrades when model updates ship — reinforces need for private eval infrastructure
>
> No fabricated receipts — benchmarks tested against published research findings.

## See also

- [S-219 · Agent Eval Harness](stacks/s219-agent-eval-harness.md) — the foundational pattern for building eval infrastructure
- [S-246 · The Production Eval Pipeline](stacks/s246-production-eval-pipeline-the-four-stage-loop.md) — four-stage eval system; Layer 3 shadow traffic catches what benchmarks miss
- [S-249 · The Eval Gap](stacks/s249-the-eval-gap-why-agents-ship-without-proof.md) — 89% of teams have observability, 52% have evals; the gap this entry explains is structural, not a tooling problem
- [S-251 · Golden Dataset Curation as Code](stacks/s251-golden-dataset-curation-as-code.md) — Layer 1 of the private eval stack; trace-to-dataset at scale
