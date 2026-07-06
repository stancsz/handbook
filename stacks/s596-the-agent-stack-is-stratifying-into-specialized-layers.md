# S-596 · The Agent Stack Is Stratifying Into Specialized Layers

Every compute era eventually decomposes into specialized layers with different winners at each level. The enterprise AI agent stack is doing this now — splitting into distinct horizontal layers that require independent architectural decisions. Teams that treat the stack as a monolithic bundle make worse decisions than teams that reason about layers separately.

## Forces

- **Sandboxing is not orchestration, and orchestration is not tool-calling.** Early agent frameworks bundled these concerns. In production, they need independent versioning, evaluation, and access control.
- **The defensible asset is not the model — it's the organizational layer.** Model commoditization is accelerating. What separates production agents is the domain-specific logic, tool integrations, and memory architectures sitting above the model.
- **40% of enterprise apps will feature AI agents by 2026, but 40%+ of agentic projects will be canceled by end of 2027.** The gap between adoption and success is an architectural failure pattern — teams pick monolithic stacks, then discover they can't swap components or enforce governance independently.
- **Multi-agent workflows grew 327% between June and October 2025.** The explosion in multi-agent systems is exposing the brittleness of bundled architectures. As agent counts scale, the need for layer separation becomes acute.

## The Move

When designing a production agent system, explicitly plan for six independent layers:

- **Foundation model** — Choose per task class. Don't commit the whole stack to one provider. 37% of enterprises now use 5+ AI models in production.
- **Orchestration** — LangGraph for DAG-based control flow, CrewAI for role-playing team patterns, Temporal for durable execution with external events. Pick based on workflow predictability, not feature lists.
- **Sandboxing/execution environment** — Treat this as its own layer. E2B, Modal, Shuru, Firecracker wrappers. Isolates untrusted code, enforces resource limits, handles credential scoping.
- **Tool layer** — MCP (Model Context Protocol) is becoming the standard for tool discovery and schema management. REST integrations remain common for enterprise backends.
- **Memory and persistence** — Semantic memory (vector DBs), short-term conversational context, and long-term episodic memory are separate concerns. Qdrant and Weaviate are gaining share over Pinecone in cost-sensitive production deployments.
- **Observability and governance** — LangSmith, Arize Phoenix, or Langfuse for tracing; automated LLM-as-judge evaluation in CI for quality gates. Governance (permission escalation, spend limits, audit logs) needs to be runtime-enforced, not post-hoc.

## Evidence

- **Blog post (Philipp D. Dubach, 2026):** The agent stack is splitting into six specialized layers with different defensibility profiles — the orchestration layer has low defensibility (commoditized by open source), while the organizational world model layer is where competitive moat actually accumulates. — [philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Industry report (Databricks State of AI Agents, 2025 via MHTECHIN):** Multi-agent workflows grew 327% between June and October 2025. Technology companies are building multi-agent systems at 4× the rate of other industries, with over 126,000 GitHub stars across major orchestration frameworks. — [mhtechin.com/support/orchestration-frameworks-for-agentic-ai-langchain-autogen-crewai-the-complete-2026-guide](https://www.mhtechin.com/support/orchestration-frameworks-for-agentic-ai-langchain-autogen-crewai-the-complete-2026-guide)
- **End-of-year review (Technspire, December 2025):** Four categories shipped reliably in 2025: developer tooling (tight compile-test-human-review loops), internal ops automation (clear success criteria, low blast radius), research/analysis agents (tool-augmented LLMs scaling where humans don't), and customer support augmentation (not full deflection — shared workspace with human escalation). Common failure: agents scoped too broadly without bounded feedback loops. — [technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Picking an orchestration framework by feature count is the wrong signal.** CrewAI excels at role-playing multi-agent teams with shared context. LangGraph excels at explicit DAG control flow with durable state. Temporal excels when agents must survive infrastructure restarts. The choice should follow from workflow characteristics, not framework popularity.
- **Sandboxing as an afterthought creates security blast radius.** In multi-agent systems where agents invoke code on behalf of users, the execution environment is not optional. Teams that skip this layer early pay in retrofit complexity.
- **Observability is not optional in multi-agent systems.** A 6-agent workflow with no tracing is undebuggable. The minimum viable observability stack tracks per-span latency, token counts, retrieval similarity scores, and automated quality evaluation — not just final output correctness.
