# S-590 · Agent Metacognition: The Confidence Calibration Problem

An agent confidently edits the production database schema. It is wrong. An agent says "I'll handle it" to a task outside its training distribution. It cannot. An agent drafts a legal response it should not draft — and says it did so "correctly." These are not the same failure. They share the same root: the agent has no calibrated sense of what it can and cannot do, and every layer between the model and the output treats its confidence as if it were reliable.

This is the metacognition problem. The agent reasons about its own reasoning — but the output of that self-assessment is as uncalibrated as its answers.

## Forces

- **LLM confidence is token-generated, not estimated.** The phrase "I'm not sure" comes from training patterns about what uncertainty sounds like, not from a genuine probability estimate. A model can express doubt convincingly while being highly confident internally — and vice versa.
- **Agents compound overconfidence.** A single confident mistake feeds into the next reasoning step. By step 5, the agent has built a coherent narrative around a false premise. The final answer is confident because each intermediate step was confident, including the ones that were wrong.
- **Downstream systems trust the agent's signal.** Tools, guardrails, and human reviewers all treat the agent's stated confidence or refusal to escalate as evidence. When the agent doesn't know what it doesn't know, it also doesn't know when to stop.
- **Calibration and accuracy are orthogonal.** A model can be 95% accurate overall but systematically overconfident in the 5% it gets wrong — exactly the cases where calibrated uncertainty would trigger a human review.
- **Sampling-based calibration is expensive.** The most reliable methods (semantic entropy, ensemble sampling) cost 10–100x the base inference. You need them most where cost matters most.

## The move

Metacognition in agents operates at three layers. Each requires a different intervention.

### Layer 1 — Self-Evaluation at Output Time

Before the agent returns an answer, ask it to grade itself. Not "are you done?" but "how confident are you that this answer is correct, on a 1–5 scale, and on what basis?"

```python
def metacognitive_check(agent_response: str, task: str, client) -> dict:
    """Ask the agent to evaluate its own output before returning it."""
    eval_prompt = f"""Task: {task}
Your answer: {agent_response}

Evaluate your answer:
1. How certain are you that this is correct? (1=guessing, 5=highly certain)
2. What information would you need to be more certain?
3. Should a human review this before it's acted on? Answer yes if uncertain.

Respond in JSON: {{"confidence": int, "gap": str, "needs_review": bool}}"""

    eval_response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": eval_prompt}]
    )

    import json
    result = json.loads(eval_response.content[0].text)
    return result

# Gate downstream actions on metacognitive output
check = metacognitive_check(agent_output, task, client)
if check["needs_review"] or check["confidence"] < 3:
    route_to_human_review(agent_output)
```

This costs one extra LLM call but prevents the wrong answer from propagating. The model, asked to grade itself, frequently gives a more honest assessment than when answering the original task.

### Layer 2 — Semantic Entropy for High-Stakes Decisions

For consequential actions (database writes, external API calls, legal/compliance content), use semantic entropy — measure the variance in what the model *means*, not just what it *says*. Two token sequences can look different but carry the same meaning; semantic entropy clusters by meaning and measures dispersion.

```python
import numpy as np
from anthropic import Anthropic

client = Anthropic()

def semantic_entropy(text: str, n_samples: int = 30) -> float:
    """
    Estimate semantic entropy by sampling token sequences and clustering
    by semantic similarity. High entropy = the model has many ways to
    express the same answer = low confidence in the specific claim.
    """
    # Sample multiple token sequences with temperature > 1
    samples = []
    for _ in range(n_samples):
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=100,
            temperature=1.2,
            messages=[{"role": "user", "content": f"State the key factual claim from: {text}"}]
        )
        samples.append(response.content[0].text.strip())

    # Cluster by semantic similarity (simple: check overlap of key entities)
    unique_claims = set()
    for s in samples:
        # Extract named entities as a crude semantic fingerprint
        words = set(s.lower().split())
        unique_claims.add(frozenset(w for w in words if len(w) > 4))

    # Semantic entropy: log2 of unique semantic clusters
    if len(unique_claims) == 1:
        return 0.0
    return np.log2(len(unique_claims))

# Gate on semantic entropy threshold
if semantic_entropy(agent_action_description) > 1.5:
    escalate(f"High uncertainty in action: {agent_action_description}")
```

A semantic entropy above 1.5 bits means the agent's reasoning about the action is unstable — the same question produces substantially different factual framings. Block and escalate.

### Layer 3 — Explicit Capability Boundary Signaling

The agent should declare, at session start and at each escalation point, what category of task it is being asked to perform — and whether that category is within its demonstrated capability range.

```python
CAPABILITY_SIGNALS = {
    "code_generation": {"calibrated": True, "failure_mode": "plausible-wrong"},
    "legal_analysis": {"calibrated": False, "failure_mode": "overconfident-wrong"},
    "data_extraction": {"calibrated": True, "failure_mode": "schema-drift"},
    "reasoning_about_reasoning": {"calibrated": False, "failure_mode": "meta-confident-wrong"},
    "unknown_task": {"calibrated": False, "failure_mode": "confident-unknown"},
}

def classify_task(user_input: str) -> str:
    """Classify the task type from the user input."""
    # In production: use a lightweight classifier or keyword routing
    task_keywords = {
        "code_generation": ["write code", "implement", "fix bug", "refactor"],
        "legal_analysis": ["legal", "contract", "compliance", "regulatory"],
        "reasoning_about_reasoning": ["why do you think", "explain your reasoning", "are you sure"],
    }
    for category, keywords in task_keywords.items():
        if any(kw in user_input.lower() for kw in keywords):
            return category
    return "unknown_task"

def capability_preflight(task: str) -> dict:
    """Before answering, signal whether this task type is calibrated."""
    category = classify_task(task)
    cap = CAPABILITY_SIGNALS.get(category, CAPABILITY_SIGNALS["unknown_task"])
    return {
        "category": category,
        "calibrated": cap["calibrated"],
        "warning": f"Low calibration for {category} — high confidence may be misleading"
    }

# At session start
preflight = capability_preflight(user_task)
if not preflight["calibrated"]:
    add_warning_to_context(preflight["warning"])
    # Also surface to any human-in-the-loop gate
```

This is not a guardrail. It's a framing layer. The agent, knowing it is in a low-calibration domain, should be explicitly prompted to hedge, disclaim, and escalate — not because the prompt says "be careful," but because the task classification itself changes the agent's epistemic posture.

## When to use which layer

| Situation | Layer | Cost | Friction |
|-----------|-------|------|----------|
| Routine task, answer returned to user | Layer 1 self-eval | 1 extra call | Low — just one JSON prompt |
| Tool call with side effects | Layer 1 + semantic entropy | 1 + 30 calls | Medium — use only on consequential actions |
| High-stakes domain (legal, compliance, finance) | All three layers | High | High — appropriate for the domain |
| Unknown/edge-case task | Layer 3 preflight | 0 extra calls | Near-zero — just a routing decision |

## See also

- [S-186 · Model-Tier Calibration](s186-model-tier-calibration.md) — calibrating *which* model to use for a task
- [S-292 · LLM-as-Judge Failure Modes](s292-llm-as-judge-failure-modes.md) — when the evaluator also suffers from confidence miscalibration
- [S-204 · Agent Circuit Breaker](s204-agent-circuit-breaker.md) — structural protection when the agent won't self-regulate
- [S-500 · Action Hallucination Detection](s500-action-hallucination-detection.md) — a specific consequence of metacognition failure (the agent claims it did what it didn't)
