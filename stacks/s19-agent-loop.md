# S-19 · The Agent Loop

The reason–act–observe cycle that turns a model into an agent. Tools ([S-03](s03-tool-use.md)), memory ([S-09](s09-memory-systems.md)), and context ([S-13](s13-context-engineering.md)) are the parts; this is the loop that drives them.

## Forces
- A single LLM call answers once; real tasks need the model to act, see the result, and adjust
- Reacting step-by-step adapts well but loses the thread on tasks with many dependent steps
- A loop that learns mid-task costs extra calls; a loop that can't stop costs you the whole budget
- Handing control to the model buys flexibility but loses the predictability of fixed code

## The move

- **Run the core loop.** Reason → Act → Observe, repeated until done (ReAct). Observing each result and adapting is exactly what separates an agent from a single call.
- **Layer three patterns by need.** *ReAct* recalibrates every step — best when the path is unpredictable, weak on long dependency chains ("short-term thinking"). *Plan-and-Execute* commits to a plan upfront — better when steps depend on each other. *Reflection/Reflexion* adds self-critique that writes lessons to memory and improves within a single session — at the cost of extra LLM calls.
- **Compose them in production.** A common shape: a Plan-and-Execute outer loop, each step a ReAct agent with its own tools, wrapped in a Reflection pass that re-runs on failure.
- **Always bound the loop.** A hard max-iteration cap, a token/time budget, no-progress detection, and a verifier that confirms the goal is actually met. Unbounded loops burn money and hang — the failure mode in [F-05](../forward-deployed/f05-agent-failure-taxonomy.md).
- **Reset, don't just retry; allow refusal.** When the inner loop stalls, reset the strategy at the outer loop rather than repeating the same step. Give the agent an explicit "cannot complete" path so it refuses instead of fabricating. And decide workflow-vs-agent first: if the steps are known ahead of time, write fixed code paths — reach for an agent loop only when the path can't be predetermined.

## Receipt
> ReAct (interleave reasoning and acting) is from ["ReAct: Synergizing Reasoning and Acting in Language Models"](https://arxiv.org/abs/2210.03629) (Yao et al., arXiv 2210.03629, 2022), which reported gains over action-only baselines (e.g. +34% on ALFWorld, +10% on WebShop). Reflexion (Actor + Evaluator + self-reflection into episodic memory) is from ["Reflexion: Language Agents with Verbal Reinforcement Learning"](https://arxiv.org/abs/2303.11366) (Shinn et al., arXiv 2303.11366, 2023). The layered design-pattern framing and loop-safety guidance are the 2026 consensus across agent-engineering writeups — directional. Verified 2026-06-25; not independently reproduced here.

## See also
[S-03](s03-tool-use.md) · [S-05](s05-multi-agent-patterns.md) · [S-09](s09-memory-systems.md) · [F-05](../forward-deployed/f05-agent-failure-taxonomy.md) · [F-07](../forward-deployed/f07-evaluation-driven-development.md)

## Go deeper
Keywords: `ReAct` · `Reflexion` · `Plan-and-Execute` · `agent loop` · `OODA loop` · `reason-act-observe` · `loop engineering` · `max iterations` · `workflow vs agent`
