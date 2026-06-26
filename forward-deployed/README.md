# Book of Production

Shipping AI to real users — the field methods, the failure modes, what production actually demands. This book is for anyone who has to put an AI system in front of a customer and keep it there.

| Code | Name | One-liner |
|---|---|---|
| [F-01](f01-shipping-ai.md) | Shipping AI | From prototype to production |
| [F-02](f02-evaluation-at-scale.md) | Evaluation at Scale | When you can't read every output |
| [F-03](f03-failure-modes.md) | Failure Modes | What breaks, when, and the receipts |
| [F-04](f04-guardrails.md) | Agentic Safety and Guardrails | Defense layers before an agent touches production |
| [F-05](f05-agent-failure-taxonomy.md) | Agent Failure Taxonomy | Agentic-specific failures that single-call LLMs don't produce |
| [F-06](f06-agent-sandboxing.md) | Agent Sandboxing | Isolate agent-run code so a bad command can't reach the host |
| [F-07](f07-evaluation-driven-development.md) | Evaluation-Driven Development | Make quality a CI gate, not a guess |
| [F-08](f08-agent-cost-control.md) | Agent Cost Control | See, cap, and attribute what an agent spends |
| [F-09](f09-human-in-the-loop.md) | Human in the Loop | Put a person at the right checkpoints |
| [F-10](f10-agent-identity-and-access.md) | Agent Identity and Access | Scoped, short-lived credentials per agent |
| [F-11](f11-agent-reliability.md) | Agent Reliability | Capability is "can it?"; reliability is "every time?" |
| [F-12](f12-llm-as-a-judge.md) | LLM-as-a-Judge | Score outputs with a model; validate the judge first |
| [F-13](f13-prompt-injection.md) | Prompt Injection | The Lethal Trifecta and why there's no clean fix |
| [F-14](f14-reading-agent-benchmarks.md) | Reading Agent Benchmarks | What leaderboards measure — and hide |
| [F-15](f15-durable-execution.md) | Durable Execution | Checkpoint, resume, and don't double-charge |
| [F-16](f16-tool-call-validation.md) | Tool Call Validation | The model proposes; your code decides whether to execute |
| [F-17](f17-synthetic-eval-generation.md) | Synthetic Eval Generation | Generate → Filter → Add: build eval suites faster than hand-labeling |
