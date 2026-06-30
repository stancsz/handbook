# S-257 · The Five Failure Modes That Kill Production Agents

Your agent passes every test in staging. In production it loops until the token budget explodes, hallucinates a tool call that costs you $4,000, and nobody notices for six hours because nothing logged what actually happened. The model is not the problem. The gap between what you observe and what your agent actually does is.

## Forces

- **Traditional observability assumes deterministic systems.** HTTP status codes tell you whether a request succeeded — not whether the agent's answer is correct. Agents fail silently in ways that look like success until the bill arrives or the customer complains.
- **Evaluation cannot be bolted on after launch.** Teams that ship agents without evals spend 10x more debugging in production than teams that instrument traces and automated quality checks from day one. Retrofitting observability into an agent system means instrumenting every tool call, every state transition, every LLM call, and every branching decision — and none of it is easy to retrofit cleanly.
- **The failure taxonomy is known but not widely applied.** 90% of agent failures collapse into five patterns: infinite loops, tool misuse, hallucinated actions, context overflow, and reasoning drift. Teams that build monitors for these five patterns catch most production incidents before users do. Teams that don't, don't find out until someone reads the invoice.
- **LLM-as-judge requires safeguards.** Using an LLM to evaluate another LLM's output is powerful but prone to gaming, drift, and false confidence. Without structured rubrics, multi-model cross-validation, and periodic human calibration, automated evals become another source of silent failure.

## The move

Build observability as a three-pillar system from day one, not as an afterthought.

- **Pillar 1 — Distributed Tracing:** Instrument every LLM call, tool invocation, and state transition using OpenTelemetry with custom span attributes for agent-specific data. LangSmith, Arize Phoenix, or LangFuse provide managed UIs on top of the trace data. Trace answers: "what happened, in what order, with what inputs."
- **Pillar 2 — Evaluation Engineering:** Run automated quality checks against every agent output. Use LLM-as-judge with structured rubrics (not raw score prompts), cross-validate with a second model, and spot-check results against human ground truth quarterly. Eval answers: "was the output correct, safe, and on-target."
- **Pillar 3 — Active Debugging:** Build monitors for the five known failure modes: infinite loops (max iteration budget with escalation), tool misuse (output schema validation before execution), hallucinated actions (tool call verification pass), context overflow (prompt length monitoring), and reasoning drift (step-by-step trace comparison against expected path). Debug answers: "why did it fail, and where in the chain."
- **Catch the five in order of cost:** Infinite loops burn budget fastest; hallucinated actions cause the most damage; tool misuse is the most common; context overflow degrades quietly; reasoning drift is the hardest to detect automatically. Monitor accordingly.
- **SLO your agent, not just your infra.** Define correctness SLOs (e.g., ">95% of tool calls must match expected schema," "<2% hallucination rate on factual retrieval") alongside latency and uptime SLOs. Track them in the same dashboards.

## Evidence

- **Blog — QubitTool "Agent Observability Engineering":** Three-pillar architecture (traces, evals, debugging) with specific claim that 90% of agent failures fall into five patterns: infinite loops, tool misuse, hallucinated actions, context overflow, reasoning drift — and that retrofitting observability costs 10x more than building it from day one. — https://qubittool.com/blog/agent-observability-engineering
- **Blog — Optinampout "Agent Observability Transforms Production AI":** LangChain State of Agent Engineering survey data: 400+ companies using LangSmith, 1T+ spans processed monthly, 43% of organizations using LangGraph. Phoenix provides open-source alternative with trace visualization and evaluation tooling. — https://www.optinampout.com/blogs/agent-observability-transforms-production-ai.html
- **Reddit r/LocalLLaMA:** Practitioners report using `max_iterations` as a floor, not a ceiling, for loop prevention. Production teams add per-step cost budgets, step-count guards, and automatic escalation to human review when either threshold breaches. — https://www.reddit.com/r/LocalLLaMA/comments/1r41h6v/how_do_you_handle_agent_loops_and_cost_overruns/
- **AWS Blog — "Evaluating AI Agents: Real-World Lessons from Building Agentic Systems at Amazon":** Multi-agent evaluation requires HITL (human-in-the-loop) oversight because automated metrics fail to capture inter-agent communication failures, coordination failures, and logical inconsistencies when multiple agents contribute to a single decision. — https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon

## Gotchas

- **Traces without SLOs are archaeology.** You can replay what happened, but you can't tell if it was good without benchmarks. Define what "good" looks like before you launch.
- **LLM-as-judge correlates with the model's biases.** A judge model that favors verbose output will score verbose agents higher regardless of quality. Calibrate against human-labeled samples every few weeks.
- **The five failure modes overlap.** An agent stuck in a loop is also context-overflowing. Build monitors that can detect compound failures, not five independent watches.
- **Tool call validation before execution is the single highest-leverage safety check.** Verifying that the agent's planned tool call matches the actual schema of the tool before executing it catches hallucinated actions at the cheapest possible point — before any state mutation or external API call.
