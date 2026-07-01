# S-274 · Orchestration Beats Model Selection in Agent Systems

Production teams are spending cycles obsessing over which LLM to pick when the real leverage is in how agents are wired together. Andrew Ng's own data shows GPT-3.5 with a proper agentic workflow outperforms GPT-4 zero-shot — 48% → 95.1% on HumanEval. The orchestration gap is wider than the model gap, and most teams haven't closed it.

## Forces

- **Model differentiation is shrinking.** Frontier models from Anthropic, OpenAI, and Google are close enough on benchmarks that swapping one for another rarely moves the needle. The remaining gains are in workflow design.
- **Orchestration quality is hard to assess pre-production.** A well-orchestrated GPT-3.5 agent beats a poorly orchestrated Claude agent — but you only discover this after running both at scale.
- **Framework maturity varies wildly for production.** The "5 lines to build an agent" pitch from CrewAI and LangChain collapses the moment you need retry logic, observability, or graceful degradation under load.
- **Cost compounds through orchestration decisions.** A naive multi-agent architecture can cost 10-50x more than a well-routed single-agent design — not because of model prices, but because of redundant calls.

## The move

Pick orchestration patterns based on task complexity, not framework popularity. Then validate with real cost and quality data.

- **Simple retrieval + generation → single ReAct agent.** One model, one tool call loop, minimal overhead. Don't add multi-agent complexity unless the task decomposes cleanly.
- **Multi-step reasoning → LangGraph state machine.** Explicit graph structure, typed state, replay/debug capability. This is the production-grade choice — Uber, LinkedIn, Klarna run LangGraph at scale. The learning curve pays back when workflows grow.
- **Rapid prototyping + role-based teams → CrewAI.** Intuitive agent/role/task abstraction. Expect to migrate toward LangGraph when you hit the observability and failure-handling ceiling. Common migration path: CrewAI → LangGraph, preserving tools via LangChain interface compatibility.
- **Model cascading for cost control.** Route simple queries to fast/cheap models (Haiku, GPT-4o-mini), escalate to premium models only when confidence is low. Teams report 40-60% cost reduction with <5% quality degradation.
- **Measure what matters: end-to-end task success rate.** Not per-call accuracy. Not benchmark scores. The metric is whether the agent completes the user's actual task — and that depends on orchestration, not raw model capability.

## Evidence

- **Andrew Ng / DeepLearning.AI:** Agentic workflow with GPT-3.5 (95.1%) outperforms GPT-4 zero-shot (48%) on HumanEval coding benchmark — the orchestration improvement (47 percentage points) dwarfs the model improvement from GPT-3.5 → GPT-4. — [Source](https://www.deeplearning.ai/){:target="_blank"}
- **Amazon AWS ML Blog (2026):** Enterprise agent evaluation requires assessing tool selection accuracy, multi-step reasoning coherence, memory retrieval efficiency, and task completion rates — not just output quality. HITL (human-in-the-loop) is non-negotiable for multi-agent systems due to emergent behaviors automated metrics miss. — [Source](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/){:target="_blank"}
- **Gheware DevOps Blog (2026 comparison):** LangGraph used in production by 400+ companies (Uber, LinkedIn, Klarna) for complex workflows. Enterprise RAG failure rate is 72% in first year — most failures trace to orchestration gaps, not model quality. Production teams targeting retrieval precision ≥70%, generation groundedness ≥90%, end-to-end task success ≥85%. — [Source](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html){:target="_blank"}
- **Xpress AI lessons learned (Jan 2026):** Fifth agent framework iteration before landing on production-grade design. "Tutorial cliff" — frameworks that work in demos collapse under production load. Root cause in all cases: treating the orchestration layer as an implementation detail rather than a first-class concern. — [Source](https://xpress.ai/blog/2025-agent-lessons){:target="_blank"}

## Gotchas

- **Don't use CrewAI's default async loop without decoupling from synchronous LLM inference.** Direct coupling is the top source of production incidents in CrewAI deployments (Markaicode production audit, 2026). Use a task queue (Celery, BullMQ) between agent steps and LLM calls.
- **Hybrid frameworks are valid.** CrewAI → LangGraph migration preserves tools (both use LangChain tool interface). Some teams run CrewAI agents as nodes inside LangGraph graphs — the frameworks are complementary, not mutually exclusive.
- **MCP (Model Context Protocol) adoption is accelerating fast.** ~14,000 MCP servers, 41% of surveyed organizations in production (Stacklok 2026). If you're still building custom tool integrations, you're reinventing what MCP standardizes. Anthropic's MCP is now the de facto tool-calling standard, replacing bespoke REST tool schemas.
- **Enterprise RAG failure is a coordination problem, not a retrieval problem.** The 72% first-year failure rate (aliac.eu, 2026) mostly traces to agentic workflow failures — wrong routing, untyped handoffs, missing escalation paths — not to embedding quality or chunk size.
