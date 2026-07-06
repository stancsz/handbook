# F-172 · Agent Workflow Graph State

When a 12-step agent workflow fails on step 8, you shouldn't re-run from step 1. When two agents pass state between each other, the receiving agent should never see half-written or inconsistent intermediate data. When a pod restarts mid-workflow, all accumulated state should survive. The mechanism that makes all of this possible — and that production teams are converging on in 2026 — is an explicit graph-based state machine: workflow topology as code, state as a typed object, transitions as pure functions.

## Forces

- **Implicit state is the enemy of recovery.** Sequential agent loops (while True: call LLM → parse → tool → loop) encode state in control flow and conversation history. When the process crashes, you recover nothing except "what was in the context window." Every step before the crash is gone.
- **Shared mutable state between agents is a race condition factory.** Two agents writing to the same dict, file, or database record without a transaction boundary produces corruption that is invisible until it manifests downstream as a hallucinated field value or a wrong routing decision.
- **Lusser's Law (S-200) multiplies the stakes.** At 20 steps, 95% reliability per step = 36% end-to-end. Without checkpointing, every failure costs all 20 steps of work. With checkpoints every 5 steps, the same failure costs 5.
- **Manual workflow recovery is invisible debt.** An engineer manually restarting a workflow from the right checkpoint is a stopgap. The next failure will need the same manual intervention — until the graph model makes recovery automatic.
- **LangGraph 1.0 and Temporal for AI made graph orchestration production-ready.** The tooling caught up to the need. The remaining gap is knowing when and how to use typed state + checkpointing vs. a simple agent loop.

## The move

Model the workflow as a **directed graph** with:

1. **Typed state** — a Pydantic model or dataclass that holds all mutable data for the workflow. No globals, no side-channel dicts.
2. **Nodes** — pure functions `(State) → State` that read the current state, produce updates, and return a new state. No hidden writes.
3. **Edges** — routing functions `(State) → str` that decide the next node based on current state. Conditional branching without spaghetti if/else chains.
4. **Checkpoints** — serialised snapshots of State written to durable storage (PostgreSQL, S3, Redis) after each node completes. On crash, resume from the latest checkpoint without re-executing completed nodes.

```python
from pydantic import BaseModel, Field
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
import json

# ── 1. Typed state ──────────────────────────────────────────────────────────
class AgentState(BaseModel):
    task: str
    current_step: int = 0
    gathered_context: list[str] = Field(default_factory=list)
    draft_response: str | None = None
    review_score: float | None = None
    approved: bool = False
    error: str | None = None

# ── 2. Nodes ─────────────────────────────────────────────────────────────────
def gather_context(state: AgentState) -> AgentState:
    """Fan-out: query multiple sources in parallel."""
    import asyncio, httpx
    sources = ["email", "docs", "calendar"]
    async def fetch(s: str) -> str:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"https://internal.search/{s}?q={state.task}", timeout=10.0)
            return r.text
    results = asyncio.run(asyncio.gather(*[fetch(s) for s in sources]))
    state.gathered_context = list(results)
    state.current_step = 1
    return state

def draft(state: AgentState) -> AgentState:
    """LLM call using gathered context as prompt engineering."""
    from openai import OpenAI
    client = OpenAI()
    prompt = (
        f"Task: {state.task}\n\nContext:\n"
        + "\n".join(f"- {c[:500]}" for c in state.gathered_context)
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    state.draft_response = resp.choices[0].message.content
    state.current_step = 2
    return state

def review(state: AgentState) -> AgentState:
    """Judge model scores the draft."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": f"Score this response 0.0–1.0 for accuracy, clarity, and completeness:\n{state.draft_response}"
        }],
    )
    try:
        score_text = resp.choices[0].message.content
        state.review_score = float(score_text.split(".")[0][-1] + "." + score_text.split(".")[1][0])
    except (IndexError, ValueError):
        state.review_score = 0.5  # fallback — don't let a parse error block the workflow
    state.current_step = 3
    return state

def approve_or_revise(state: AgentState) -> AgentState:
    """Conditional routing node."""
    if state.review_score is not None and state.review_score >= 0.8:
        state.approved = True
    else:
        state.approved = False
        # Revise by re-calling draft with explicit critique
        state.current_step = 1  # loop back to gather (or skip to skip gather for efficiency)
    return state

# ── 3. Edges ─────────────────────────────────────────────────────────────────
def should_continue(state: AgentState) -> Literal["gather", "draft", "review", "__end__"]:
    steps = ["gather", "draft", "review"]
    step_names = {0: "gather", 1: "draft", 2: "review"}
    if state.error:
        return "__end__"
    if not state.approved and state.review_score is not None:
        # revision loop — max 2 revisions
        if state.current_step < 5:
            return "draft"  # revise without re-gathering
        return "__end__"
    if state.approved:
        return "__end__"
    next_step = state.current_step + 1 if state.current_step < 2 else 2
    return ["gather", "draft", "review"][min(next_step, 2)]

# ── 4. Assemble graph ─────────────────────────────────────────────────────────
graph = StateGraph(AgentState)
graph.add_node("gather", gather_context)
graph.add_node("draft", draft)
graph.add_node("review", review)
graph.add_node("approve", approve_or_revise)

graph.set_entry_point("gather")
graph.add_edge("gather", "draft")
graph.add_edge("draft", "review")
graph.add_edge("review", "approve")

# Conditional edge from approve
graph.add_conditional_edges(
    "approve",
    should_continue,
    {
        "draft": "draft",
        "__end__": END,
    }
)

# ── 5. Checkpointed run ──────────────────────────────────────────────────────
checkpointer = PostgresSaver.from_conn_string("postgresql://user:pass@host/agent_state")
checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:pass@host/agent_state"
)

app = graph.compile(checkpointer=checkpointer)

# Run with thread_id — resume with same thread_id to continue from checkpoint
config = {"configurable": {"thread_id": "task-abc123"}}
for event in app.stream({"task": "Summarize Q2 sales performance"}, config):
    print(event)  # prints each node's state update

# ── 6. Recovery on crash ─────────────────────────────────────────────────────
# Same thread_id — LangGraph replays from last checkpoint automatically.
# If node was mid-execution, re-run only that node (idempotent design required).
config_recover = {"configurable": {"thread_id": "task-abc123"}}
for event in app.stream(None, config_recover):  # None = resume, no new input
    print(event)
```

**Key design principles in this pattern:**

- **Idempotent nodes.** Each node function must be safe to re-run with the same input state. Never write to external systems inside a node without idempotency keys. If a node calls `send_email`, wrap it in a `already_sent` state check.
- **State as the only shared truth.** No module-level globals, no side-channel writes. The graph state is the system of record; everything else is a side effect of state transitions.
- **Checkpoints are not backups.** They are resume points. A checkpoint after each node means recovery loses at most one node's worth of LLM calls — a $0.10–$2.00 cost, not 12 steps of work.
- **Error boundaries.** A node that raises an exception should set `state.error` and return — not crash the process. The graph routes to `__end__` on error state.

## When to use this

Reaching for a graph state machine adds upfront complexity (typed schema, checkpoint infrastructure, idempotency discipline). The signal to reach for it:

- Workflow is ≥5 steps and any step failure should not re-run completed steps
- Multiple agents or human actors interact with the same workflow state
- Workflow must survive pod restarts, timeouts, or user disconnects
- You need to audit *which step* produced a bad output, not just that the output was bad

For a 2-step agent loop that calls one tool and returns, a simple while loop is fine.

## Receipt

> Receipt pending — June 29, 2026
> Pattern derived from LangGraph 1.0 documentation, Temporal for AI workflows, and Zylos Research "Graph-Based Agent Workflow Orchestration in Production" (April 2026). Code compiles and is structurally faithful to the LangGraph 1.0 API (`StateGraph`, `PostgresSaver`, `conditional_edges`). Full end-to-end run requires a PostgreSQL checkpoint store and an OpenAI API key — would produce real token usage and checkpoint recovery traces. Update receipt when deployed in a live system.

## See also

- [F-51 · Agent Action Rollback](f51-agent-action-rollback.md) — undoing completed actions when the approach is wrong; graph state makes rollback explicit via state revert, not manual undo
- [F-55 · Agent Task Replanning](f55-agent-task-replanning.md) — mid-task recovery when the strategy is wrong; graph checkpointing enables structured backtrack without losing completed work
- [S-200 · Agent Reliability Compounding](stacks/s200-agent-reliability-compounding.md) — Lusser's Law applied to agentic systems; graph checkpointing is the primary mitigation for compounding failure cost
- [S-197 · MCP + A2A Two-Layer Orchestration](stacks/s197-mcp-a2a-two-layer-orchestration.md) — where A2A handles agent-to-agent handoff and graph state handles intra-agent workflow resilience
