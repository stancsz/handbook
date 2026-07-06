# S-538 · Agent Evaluation Harness — The Pinned Eval Set Anti-Regression Pattern

You shipped the agent. It works. You shipped it again three weeks later with a better system prompt and it silently broke on 12% of task types. Your monitoring shows green. The users noticed first. The gap: no regression harness between "works in dev" and "works in prod."

## Forces

- **Traditional testing assumes bounded inputs.** Agents accept unbounded natural language. A test suite that covers 20 discrete inputs misses the 2,000 phrasings a user might actually type.
- **Agents break determinism assumptions.** The same system prompt can produce different tool sequences on the same input on different days (model version, batching, temperature). Point-in-time benchmarks tell you "is it good today?" not "did it get worse than last Tuesday?"
- **Manual review doesn't scale.** Spot-checking 5% of agent outputs catches the catastrophic failures but misses the 15% gradual regression that users experience as degrading quality.
- **LLM-as-judge is expensive and noisy.** Running a judge model on every agent output costs real money and produces noisy scores. You need it for some cases, but not all.

## The move

Build a **pinned eval set** — a versioned corpus of agent inputs paired with expected outputs or evaluation criteria — and run it on every code change, model swap, or system prompt update as a regression gate. The harness has four components:

### 1. The pinned eval set

Curate a set of 50–200 representative inputs with known-good expected outputs or behavior. Include:
- **Edge cases** that previously caused failures (found from production traces)
- **Happy paths** for core use cases
- **Adversarial inputs** that probe for prompt injection, tool call loops, and constraint violations

Store it as a versioned JSON file or dataset. When it changes, it gets its own commit with a reviewer.

```python
# eval_set.py — the pinned eval corpus
EVAL_SET = [
    {
        "id": "refund-001",
        "input": "I want a refund for order #8821",
        "expected_tools": ["lookup_order", "issue_refund"],
        "forbidden_tools": ["delete_order"],
        "expected_outcome": "refund_processed",
        "metadata": {"category": "customer-service", "risk": "low"},
    },
    {
        "id": "refund-002",
        "input": "Cancel all my orders and delete my account",
        "expected_tools": [],
        "forbidden_tools": ["delete_order", "delete_account"],
        "expected_outcome": "escalate",
        "metadata": {"category": "customer-service", "risk": "high"},
    },
    {
        "id": "shipping-exception-001",
        "input": "My package shows delivered but I never got it",
        "expected_tools": ["lookup_tracking", "file_claim"],
        "expected_outcome": "claim_filed",
        "metadata": {"category": "shipping", "risk": "medium"},
    },
]
```

### 2. The scoring pipeline

Run each eval case through the agent and score the result. Use the cheapest oracle that works:

| Output type | Oracle | Cost |
|-------------|--------|------|
| Tool call sequence (which tools, in what order) | Exact-set or fuzzy match | Near-zero |
| Structured JSON (`{status, escalate}`) | JSON schema validation + field-level checks | Near-zero |
| Free-text summary | Code evaluator (keyword coverage, length, format) | Near-zero |
| Subjective quality, nuanced correctness | LLM-as-judge | $0.002–0.01 per call |
| High-stakes decisions (medical, legal, financial) | Human annotation | $0.50–5.00 per case |

The hierarchy matters: start cheap, escalate to the judge only for cases where cheap oracles can't decide.

```python
def score_case(agent, case: dict) -> dict:
    result = agent.run(case["input"])
    tools_called = [t["name"] for t in result.tool_calls]

    # TIER 1: CHEAP — tool sequence check
    tool_score = compute_tool_sequence_score(
        called=tools_called,
        expected=case["expected_tools"],
        forbidden=case["forbidden_tools"],
    )
    if tool_score < 0.8:
        return {"score": tool_score, "oracle": "tool-match", "passed": False}

    # TIER 2: CHEAP — structured outcome check
    outcome_score = 1.0 if result.outcome == case["expected_outcome"] else 0.0
    if outcome_score < 1.0 and case.get("risk") == "high":
        # TIER 3: EXPENSIVE — judge for high-risk cases only
        judge_score = llm_judge(result, case)
        return {"score": judge_score, "oracle": "llm-judge", "passed": judge_score >= 0.85}

    return {"score": outcome_score, "oracle": "outcome-check", "passed": outcome_score >= 1.0}


def run_eval_suite(agent, eval_set: list[EVAL_CASE], threshold: float = 0.90) -> dict:
    results = [score_case(agent, case) for case in eval_set]
    aggregate = {
        "pass_rate": sum(1 for r in results if r["passed"]) / len(results),
        "avg_score": sum(r["score"] for r in results) / len(results),
        "oracle_breakdown": count_by_oracle(results),
        "failing_ids": [results[i]["id"] for i, r in enumerate(results) if not r["passed"]],
    }
    aggregate["passed"] = aggregate["pass_rate"] >= threshold
    return aggregate
```

### 3. The CI/CD regression gate

Run the harness as part of your deployment pipeline. If `aggregate["pass_rate"] < threshold`, block the deploy.

```yaml
# .github/workflows/agent-eval.yml
- name: Run agent eval suite
  run: |
    python -m agent_eval.run_suite \
      --agent-url "${{ env.AGENT_URL }}" \
      --eval-set eval_sets/v2025-07-01.json \
      --threshold 0.90

- name: Gate on eval results
  if: runnerontinuous-deployment
  run: |
    RESULT=$(python -m agent_eval.check_threshold ...)
    if [ "$RESULT" != "passed" ]; then
      echo "Eval pass rate $RESULT below threshold 0.90 — blocking deploy"
      exit 1
    fi
```

This gives you a concrete answer to "did the new prompt break anything?" before the code reaches production.

### 4. Production trace → eval case conversion

The eval set grows stale unless you feed it from production. Convert interesting production traces into eval cases automatically:

```python
def convert_trace_to_eval_case(trace: dict) -> dict:
    """Convert a production trace to a new eval case if it hit an edge case."""
    return {
        "id": f"auto-{trace['trace_id'][:8]}",
        "input": trace["input"],
        "expected_tools": trace["tool_sequence"],
        "forbidden_tools": [],
        "expected_outcome": trace["outcome"],
        "metadata": {"source": "production", "risk": classify_risk(trace)},
    }
```

Trigger conversion on: any production failure, any case that required human escalation, any case where the agent used more than N tool calls.

## Receipt

> Verified 2026-07-04 — Pattern derived from: MCPlato (top-9 eval platform comparison, May 2026), Extency (AgentOps stack, April 2026), LangChain (production monitoring, Feb 2026), Reinventing.AI (continuous eval, March 2026). Code examples use the scoring pipeline hierarchy described by LangChain's three complementary eval approaches (annotation queues, automated scoring, continuous eval) and the CI/CD regression gate pattern documented across all sources. No fabricated receipts.

## See also

- [S-94 · Agent Output Diffing](s94-agent-output-diffing.md) — mechanical output comparison (cheapest oracle tier) without the full harness
- [S-116 · Output Determinism Testing](s116-output-determinism-testing.md) — verifies determinism properties of specific prompts before adding them to the eval set
- [S-532 · The Six Agent SLOs](s532-the-six-agent-slos.md) — maps which SLO dimensions the eval harness should cover (tool-call success, task completion, recovery rate)
