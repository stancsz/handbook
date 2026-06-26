# S-23 · Workflows vs Agents

The first architecture decision, and the one most often gotten wrong. A **workflow** runs predefined steps — your code orchestrates, the model fills specific slots. An **agent** decides its own steps in a loop ([S-19](s19-agent-loop.md)). Most things called "agents" should be workflows.

## Forces
- A workflow is predictable, explainable, cheap, and easy to debug — but rigid; it can't handle a path you didn't design
- An agent is flexible and handles open-ended tasks — but variable, costlier (many calls), and hard to debug when it wanders
- "Agentic" is a marketing word; the 2026 production consensus is **workflows-first** — roughly 90% of shipped "agent" systems are workflows with a few strategic LLM calls
- The expensive mistake is reaching for autonomy when a fixed sequence would ship — you trade a working product for a brittle one

## The move
- **Default to a workflow.** Add autonomy only where the task *genuinely has no fixed correct path*. Start simple; let the problem prove it needs an agent (this is [Law 1](../laws.md)).
- **Decision rule:**
  - Need control, repeatability, compliance, or step-by-step explainability → **workflow**.
  - Problem is ill-defined and the exact path doesn't matter, only the outcome → **agent**.
  - If you can't explain the flow, don't use a workflow; if you can't accept variability, don't use an agent.
- **Most real systems are hybrid.** A workflow frames the boundaries (fixed stages, gates, retries); an agent gets freedom *within* a step. Reserve the agentic part for the one stage that needs judgment.
- **Cost follows the choice.** A workflow step is one call; an agent loop is many. Don't pay loop cost for slot-filling work.

## Receipt
> Verified 2026-06-25 — same task ("pull the facts from one sentence"), same model (llama3.2 via Ollama, localhost:11435), run 5× each. Only difference: how much latitude the prompt gives.

```
WORKFLOW step (fixed: "reply with ONLY this JSON: {company, metric, change_pct}"):
  run 1-5: {"company": "Acme Corp", "metric": "revenue", "change_pct": 12}   (identical)
  -> 1/5 distinct outputs  — fully repeatable, parseable, explainable

AGENT step (open: "do whatever you think is most useful, respond however you see fit"):
  run 1: "## Acme Corp — Quarterly..."     run 2: "I'll extract the structured facts..."
  run 3: "produce a few useful artifacts"  run 4: "**Restructured for clarity:**..."
  run 5: "```json {...}```"
  -> 5/5 distinct outputs  — every run a different shape
```

Same model, same input — the *only* variable is freedom. Constrain it and you get a repeatable workflow you can parse and audit; open it up and you get adaptability you can't predict. That tradeoff **is** the decision: pick the constraint level the task actually needs, not the most autonomous thing you can build.

## See also
[S-19](s19-agent-loop.md) · [S-05](s05-multi-agent-patterns.md) · [F-11](../forward-deployed/f11-agent-reliability.md) · [S-04](s04-structured-output.md) · [F-09](../forward-deployed/f09-human-in-the-loop.md)

## Go deeper
Keywords: `workflow vs agent` · `agentic workflow` · `LangGraph` · `orchestration` · `human-in-the-loop` · `hybrid architecture` · `state machine` · `deterministic pipeline`
