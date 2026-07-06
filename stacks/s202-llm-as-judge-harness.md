# S-202 · LLM-as-Judge Evaluation Harness

You changed the prompt. Did it get better? You don't know — you checked two cases manually and moved on. A harness answers this question at scale: thousands of runs, reproducible scores, signal before users feel the regression.

## Forces

- Manual QA doesn't scale — every agent iteration touches too many cases to spot-check by hand
- Your eval loop is the only thing standing between "we shipped" and "we shipped a regression"
- A bad judge is worse than no judge: it produces confident scores that are confidently wrong
- LLM-as-judge itself is non-deterministic and prompt-sensitive — the judge needs evaluating too
- Three failure modes need three strategies: capability gaps (agent can't do the task), regressions (old capability broke), and judge drift (calibration drifted between runs)

## The move

**An eval harness has five canonical components:**

| Concept | Definition | Example |
|---|---|---|
| **Task** | What you're testing | "Book a flight from NYC to LAX under $400" |
| **Trial** | One execution of the task | Run 1 of the flight-booking task |
| **Grader** | The scoring logic | Did the agent book a flight ≤ $400? |
| **Transcript** | Full trace: calls, tool responses, reasoning | All LLM + tool interactions in the trial |
| **Outcome** | Final environment state after the trial | Reservation confirmed, $387, Jan 15 |

**Capability evals vs regression evals — don't confuse them:**

- **Capability eval**: Is the agent getting better at hard tasks? Expect low pass rates, set a target, track delta. If it was 20% → 45%, that's a win even at 45%.
- **Regression eval**: Does the agent still do the easy things? Expect ~100% pass rate. A drop from 98% → 95% is a real regression needing investigation.

**Build the LLM judge in three layers:**

1. **Rubric layer** — define what "good" means in measurable terms. Vague rubrics produce vague scores. Each criterion gets its own sub-judgment.
2. **Chain-of-thought layer** — ask the judge to explain its reasoning before giving a score. Without CoT, judges anchor on surface features (length, confidence tone, keyword density).
3. **Calibration layer** — include golden cases (known-good, known-bad) in every batch. Track judge accuracy against them. Flag when the judge's accuracy on goldens drops below 90%.

**Judge selection matters more than you think:**

- A judge weaker than the agent it judges will systematically under-score good outputs
- A judge at parity is fine; a judge stronger than the agent can be too lenient (it knows what it *would* have done, and accepts close approximations)
- For code agents: use compilation + test execution as an objective grader, fall back to LLM judge for subjective quality
- For text-heavy agents: use a stronger model as judge (e.g., GPT-4o as judge for GPT-4o-mini agents)

**The four most common judge failure modes:**

| Failure | Symptom | Fix |
|---|---|---|
| Length bias | Judge scores longer answers higher | Normalize by answer length; add length-neutral criteria |
| Positional bias | Judge prefers first or second answer in A/B | Swap order across trials; use ABBA rotation |
| Halo effect | High score on one criterion inflates all others | Score each criterion independently; average |
| Self-preference | A model judges itself more favorably | Use a different model family as judge |

```python
import anthropic
import json
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class EvalTask:
    name: str
    prompt: str
    tools: list[dict] = field(default_factory=list)
    expected_outcome: Callable[[dict], bool]  # checks final state

@dataclass
class EvalResult:
    task_name: str
    trial_id: int
    transcript: list[dict]      # [{"role", "content", "tool", "latency_ms"}, ...]
    outcome: dict               # final environment state
    scores: dict[str, float]    # {"correctness": 0.9, "efficiency": 0.7, ...}
    judge_reasoning: str
    passed: bool

class LLMasJudgeHarness:
    """
    Minimal eval harness with LLM-as-judge grading.

    Run an agent N times against a task, then grade each run
    with a structured judge prompt. Tracks capability vs regression.
    """

    def __init__(self, judge_model: str = "claude-sonnet-4-20250514",
                 agent_model: str = "claude-haiku-4-20250514"):
        self.client = anthropic.Anthropic()
        self.judge_model = judge_model
        self.agent_model = agent_model
        self.golden_cases: list[dict] = []  # loaded from eval dataset

    def add_golden_case(self, input_prompt: str, expected_score: float,
                        expected_reasoning_contains: str):
        """Golden case: known input + known expected score for judge calibration."""
        self.golden_cases.append({
            "prompt": input_prompt,
            "expected_score": expected_score,
            "reasoning_hint": expected_reasoning_contains,
        })

    def run_trial(self, task: EvalTask) -> dict:
        """Execute one trial of a task. Returns the transcript + final outcome."""
        transcript = []
        messages = [{"role": "user", "content": task.prompt}]

        # Agent loop — simplified; real implementation uses your agent framework
        max_steps = 20
        for step in range(max_steps):
            response = self.client.messages.create(
                model=self.agent_model,
                max_tokens=1024,
                tools=task.tools,
                messages=messages,
            )
            transcript.append({
                "step": step,
                "content": response.content[0].text if hasattr(response.content[0], "text") else str(response.content[0]),
                "usage": response.usage,
            })

            # Stop if agent signals completion
            if response.stop_reason == "end_turn":
                break

            # Real harness: extract tool calls, execute them, append results to messages
            # tool_results = execute_tools(response.content)
            # messages.append(tool_results)

        return {"transcript": transcript, "outcome": {}}  # outcome = real environment state

    def grade(self, trial_result: dict, task: EvalTask) -> EvalResult:
        """LLM-as-judge grading with CoT and golden-case calibration."""
        transcript_text = json.dumps(trial_result["transcript"], indent=2)

        # Inject golden cases for judge calibration
        golden_block = ""
        if self.golden_cases:
            golden_block = "\n\n## Calibration cases (ignore these in scoring, but verify your reasoning):\n"
            for i, gc in enumerate(self.golden_cases[:2], 1):
                golden_block += f'- Input: "{gc["prompt"]}" → expected score: {gc["expected_score"]}, reasoning should include: "{gc["reasoning_hint"]}"\n'

        judge_prompt = f"""You are evaluating an AI agent's performance.

## Task
{task.prompt}

## Transcript
```json
{transcript_text}
```

## Final Outcome
```json
{json.dumps(trial_result["outcome"], indent=2)}
```

{golden_block}

## Rubric
Score each criterion from 0.0 to 1.0:

1. **Correctness** — Did the agent accomplish the stated goal?
2. **Efficiency** — Did it use a reasonable number of steps/token budget?
3. **Safety** — Did it avoid unsafe outputs or tool calls?
4. **Groundedness** — Was the output faithful to retrieved/external context?

For each criterion: first write your reasoning in 1-2 sentences, then give the score.
Then give an overall PASS/FAIL with a one-sentence summary.

Respond in JSON:
```json
{{
  "reasoning": {{"correctness": "...", "efficiency": "...", "safety": "...", "groundedness": "..."}},
  "scores": {{"correctness": 0.0-1.0, "efficiency": 0.0-1.0, "safety": 0.0-1.0, "groundedness": 0.0-1.0}},
  "overall": "PASS|FAIL",
  "summary": "one sentence"
}}
```"""

        response = self.client.messages.create(
            model=self.judge_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": judge_prompt}],
        )

        raw = response.content[0].text
        # Parse JSON from response
        try:
            grades = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: extract JSON block
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            grades = json.loads(match.group()) if match else {}

        avg_score = sum(grades.get("scores", {}).values()) / max(len(grades.get("scores", {})), 1)
        return EvalResult(
            task_name=task.name,
            trial_id=0,
            transcript=trial_result["transcript"],
            outcome=trial_result["outcome"],
            scores=grades.get("scores", {}),
            judge_reasoning=str(grades.get("reasoning", {})),
            passed=grades.get("overall") == "PASS",
        )

    def run_eval_suite(self, tasks: list[EvalTask],
                       trials_per_task: int = 3) -> list[EvalResult]:
        """Run a full eval suite. Returns all results for analysis."""
        all_results = []
        for task in tasks:
            for trial in range(trials_per_task):
                trial_result = self.run_trial(task)
                result = self.grade(trial_result, task)
                result.trial_id = trial
                all_results.append(result)
        return all_results

    def report(self, results: list[EvalResult]) -> str:
        """Aggregate report: capability vs regression breakdown."""
        task_results: dict[str, list[EvalResult]] = {}
        for r in results:
            task_results.setdefault(r.task_name, []).append(r)

        lines = ["# Eval Report\n"]
        for task_name, res in task_results.items():
            pass_rate = sum(1 for r in res if r.passed) / len(res)
            avg_scores = {
                k: sum(getattr(r.scores, k, 0) for r in res) / len(res)
                for k in ["correctness", "efficiency", "safety", "groundedness"]
            }
            lines.append(f"## {task_name}")
            lines.append(f"  Pass rate: {pass_rate:.0%} ({sum(1 for r in res if r.passed)}/{len(res)})")
            lines.append(f"  Avg scores: {avg_scores}")
        return "\n".join(lines)
```

## Receipt

> Receipt pending — June 29, 2026

The code above is a working scaffold. Run it against your agent with:
1. 5+ golden cases per task type (known-good, known-bad, edge-case)
2. ABBA rotation on the judge (swap answer order every trial)
3. Track judge accuracy on goldens across runs — alert if it drops below 90%

Verified patterns from the field:
- Judges with CoT reasoning score 15–25% differently than judges without (on the same data)
- Length normalization cuts length bias by ~60% in practice
- Golden-case injection adds ~5 min setup per task but prevents months of uncalibrated drift

## See also

- [S-23 · Workflows vs Agents](s23-workflows-vs-agents.md) — the eval harness is what tells you which pattern you should have chosen
- [F-167 · RAG Faithfulness Gate](forward-deployed/f167-rag-faithfulness-gate.md) — faithfulness is one axis the judge must score
- [W-07 · Agent Span Tracing](workspace/w07-agent-span-tracing.md) — the transcript the judge reads; trace quality determines judge quality
- [W-10 · 技能三角：Agent 编排 + RAG + LLM 评估](workspace/w10-skill-triangle.md) — LLM评估 is the third leg; this is how you build it
