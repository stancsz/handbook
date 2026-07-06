# S-546 · The Answer Flip — Architecting Stability Under Non-Determinism

[You ran the same agent request twice with identical prompts and got two different answers. You ran it a third time and got a third answer. Your CI tests passed on Tuesday and failed on Wednesday for the same input. This is the answer flip — and it is not a bug in your code. It is a structural property of LLM-based systems that you must architect around, not debug away.]

## Forces

- **Hardware-level non-determinism survives temperature=0.** GPU cluster scheduling, batch composition, and floating-point operation ordering produce different token choices at sampling boundaries even with greedy decoding. API providers do not expose this; you cannot control it.
- **Pinned model names do not pin model behavior.** A model version update can change tool-selection patterns, refusal thresholds, and output format between runs. Your "pinned" model may have silently changed overnight.
- **Single-run checks are worthless.** A test that asserts a single output pass/fail tells you nothing about stability. You need distribution checks across N runs, not a single sample.
- **The cost of non-determinism compounds in multi-step agents.** If step 1 flips, step 2 operates on a different premise, and step 3 compounds the divergence. By step 10, two agent runs of the same task have produced entirely different outcomes — both "correct" by their own internal logic.
- **"Stable enough" is a business decision, not a technical one.** Some use cases (code formatting) need 99.9% consistency. Others (brainstorming) need diversity. The target drives the architecture.

## The move

### 1. Pin the behavior, not just the model name

```python
# WRONG: pinning by name only
model = "claude-sonnet-4-20250514"

# RIGHT: pin by semantic contract + version hash
model = "claude-sonnet-4-20250514"
model_hash = get_model_fingerprint(model)  # hash of first-run output on canonical input
assert model_hash == EXPECTED_HASH, f"Model behavior changed: {model_hash}"
```

Store the expected fingerprint (hash of a canonical input's output) in your CI gate. If the fingerprint drifts, the model updated and you need to re-evaluate before shipping.

### 2. Run N-times voting for critical decisions

For decisions above a cost or accuracy threshold, run the agent N times and take the majority vote:

```python
def stable_classify(query: str, n: int = 5, threshold: float = 0.6) -> str:
    outcomes = Counter(run_agent(query) for _ in range(n))
    majority, count = outcomes.most_common(1)[0]
    if count / n < threshold:
        raise AmbiguityError(f"No consensus: {outcomes}")
    return majority
```

This catches flips before they propagate. Set `n` based on the consequence of a flip — high-stakes decisions need `n=7` or higher.

### 3. Separate determinism requirements by task type

| Task type | Acceptable flip rate | Architecture |
|---|---|---|
| Code formatting, extraction | ~0% | Voting or pinning |
| Classification, routing | <5% | Voting with threshold |
| Brainstorming, synthesis | Intentional diversity | Run once, embrace variance |
| Tool selection | <2% | Voting + fingerprinting |
| Guardrail checks | ~0% | Redundant checks with different models |

### 4. Instrument flip rates as first-class metrics

```python
@datetrics.metric(group="stability")
def flip_rate(window: pd.DataFrame) -> float:
    """Fraction of identical queries that produced different outputs."""
    groups = window.groupby(["query_hash", "run_id"])
    return (groups["output_hash"].nunique() > 1).mean()
```

Alert when flip rate exceeds baseline by >2× on any query cluster. A sudden spike indicates a model update, a tool-description change, or upstream data shift.

### 5. Use stratified model selection for stability-sensitive paths

Route stability-critical sub-tasks to the model with the lowest known flip rate. Smaller models (Haiku-class) often flip less than frontier models on structured tasks because they have less reasoning variance:

```python
def stable_extract(entity: str, text: str) -> dict:
    # Small model: faster, less variance on extraction
    # Frontier model: more capable but more flip-prone
    return route(entity_type=entity, 
                 capability_needed="extraction",
                 stability_needed=True,
                 fallback_model="haiku-4.5")
```

### 6. The flip-aware checkpoint pattern

For long-horizon agents, save decision checkpoints as hashes, not full state:

```python
@dataclass
class DecisionCheckpoint:
    query: str
    decision_hash: str  # hash of tool calls + arguments
    output_hash: str
    model_version: str

def check_stability(checkpoints: list[DecisionCheckpoint]) -> StabilityReport:
    flips = sum(1 for i in range(1, len(checkpoints)) 
                if checkpoints[i].output_hash != checkpoints[i-1].output_hash)
    return StabilityReport(flip_count=flips, flip_rate=flips/len(checkpoints))
```

If a session resumes and the checkpoint hashes don't match the pre-run plan, surface a divergence alert before continuing.

## Receipt

> Verified 2026-07-04 — Research confirmed via web search and code pattern review. Key sources: James M (jamesm.blog, "Agent Reliability Problem: Debugging Non-Deterministic Systems," May 2026), skillgen.io (Test-Time Compute, May 2026), S-116 (Output Determinism Testing), LaderaLabs (500 enterprise deployments, March 2026: 80% of IT pros report agents acting unexpectedly). Flip rate patterns confirmed as a top-5 production failure driver across all sources.

## See also

- [S-116](s116-output-determinism-testing.md) — Testing whether your prompts hold the determinism property
- [S-101](s101-deterministic-agent-sessions.md) — Near-determinism conditions at the session level
- [S-199](s199-agent-self-healing-loops.md) — Self-healing when non-determinism causes a failure cascade
- [S-541](s541-agent-drift-detection.md) — Detecting behavioral drift including flip-rate anomalies
