# S-361 · The Agent Stack Is Stratifying: Sandboxing as Infrastructure, Framework Migration as Pattern

The "AI agent stack" is not one thing — it is four layers under active reorganization. Orchestration frameworks (LangGraph, CrewAI, AutoGen) are fragmenting by use case. The code execution layer is becoming its own tier (E2B, Modal, Daytona, Firecracker wrappers). And teams that built on early LangChain are migrating to lighter, more explicit alternatives. Understanding which layer does what — and where the failure modes live — is the difference between an agent that ships and one that stalls at the pilot gate.

## Forces

- **The code execution problem is unsolved by traditional cloud infra.** Lambda and Cloud Run weren't designed for persistent filesystem state across tool calls, sub-200ms cold starts, and LLM-generated code that has never been reviewed. Standard containers share a host kernel — insufficient for agents running untrusted code at runtime.
- **The agent stack is stratifying into four distinct infrastructure layers.** Sandboxing, orchestration, model access, and tool registries are each developing their own vendors, abstractions, and defensibility profiles. Monolithic frameworks that try to own all layers are hitting the wrong trade-offs at each one.
- **LangChain is losing teams to lighter alternatives, not because it is wrong but because it is overengineered for simple agents.** The migration pattern — LangChain → Pydantic AI or bare state machines — consistently cites explicit state control and reduced abstraction overhead as the trigger.
- **AutoGen entered maintenance mode in October 2025.** Microsoft redirected to the Agent Framework. Teams using AutoGen as a long-term foundation face a migration decision.

## The move

**Treat agent infrastructure as four independent layers. Buy or build each one at the right level of abstraction, and resist the monolithic framework impulse.**

### 1. Isolate the execution layer — it is not your orchestration problem

- Use purpose-built sandboxing (E2B, Modal, Daytona) rather than containers or Lambda for agent code execution. These provide persistent filesystem state across multi-step tool calls, sub-second cold starts, and SDK-level lifecycle management that general cloud functions don't.
- E2B scaled from 40,000 sandbox executions/month (March 2024) to 15 million/month (March 2025) — 375x growth. 88% of Fortune 100 companies were signed up by early 2026. This is mainstream infrastructure, not experimental.
- Evaluate sandboxes on governance primitives: egress policies, execution audit logging, enterprise identity provider integration. Microsoft's Agent Governance Toolkit (April 2026) addresses all 10 OWASP agentic AI risks with sub-millisecond enforcement — the enterprise procurement bar is rising.
- Sandboxed agents reduce security incidents by ~90% vs agents with unrestricted host access (Fordel Studios, citing 2026 research).

### 2. Choose your orchestration framework by failure mode, not by feature count

- **LangGraph** — use when you need durable execution, time-travel debugging, checkpoint/resume, and typed state with reducers. Used in production at Klarna, Replit, Elastic. Best for long-running, stateful workflows where mid-task failure is expensive. Native LangSmith observability.
- **CrewAI** — use when you need fast delivery on role-based pipelines (research → writing → editing → review). Active development as of 2025, v0.98+. Best for content pipelines and multi-agent workflows where the agent roles map cleanly to business roles. Simpler mental model than LangGraph.
- **Pydantic AI** — use when you are migrating off LangChain and need type-safe, explicit state without framework magic. The MindsDB team achieved 10x agent performance improvement after migrating from LangChain, citing explicit control over step-level state. Best for teams that want agents to behave like software, not like magic.
- **AutoGen** — avoid for new projects. Entered maintenance mode October 2025. Microsoft's successor Agent Framework is the replacement.

### 3. Treat observability as a day-one decision, not an afterthought

- Log every tool call, prompt, response, and decision from the start. Agent failures cascade in ways that are hard to reconstruct without trace data.
- LangSmith (LangChain/LangGraph ecosystem), Phoenix (Ariolabs), and custom structured logging are the main approaches. The Gennoor production lessons article cites observability gaps as a primary reason enterprise agent deployments fail to iterate after launch.
- Implement cost tracking per agent step — agents can burn through five-figure budgets over a weekend if cost guardrails aren't in place before launch.

### 4. Start with narrow scope and deterministic guardrails

- Open-ended autonomy fails catastrophically in regulated environments. Start with narrow, well-scoped tasks: ticket triage, code review, document processing, internal search. The four categories that consistently shipped from pilot to production in 2025 were: developer tooling, internal operations automation, customer service automation, and structured data extraction.
- Only 30% of GenAI pilots reached production in 2025. The 70% failure rate is concentrated in: hallucination in production (wrong retrieval → wrong answer), cost explosion ($500/month in dev → $50,000/month at real scale), and data governance mismatches with legacy systems.
- Design human-in-the-loop as a permanent feature for high-stakes decisions, not a temporary checkpoint while you "get the agent ready."

## Evidence

- **HN Post / Blog:** The agent stack is splitting into specialized layers and sandboxing is becoming its own thing — "Shuru, E2B, Modal, Firecracker wrappers" — with different defensibility profiles per layer — [philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/) (HN: news.ycombinator.com/item?id=47114201)
- **Company Blog / Case Study:** MindsDB migrated from LangChain to Pydantic AI and achieved 10x agent performance improvement — "In a month, we were already 10 times better, just because we could really control the state of each of the steps that we have" — [pydantic.dev/case-studies/mindsdb](https://pydantic.dev/case-studies/mindsdb)
- **Engineering Blog:** E2B sandbox executions grew 375x in 12 months (40K → 15M/month); 88% Fortune 100 signed up by early 2026; sandboxed agents reduce security incidents by ~90% — [fordelstudios.com/research/ai-agent-sandboxing-isolation-production-2026](https://fordelstudios.com/research/ai-agent-sandboxing-isolation-production-2026)
- **Industry Analysis:** AutoGen entered maintenance mode October 2025; LangGraph used at Klarna/Replit/Elastic; CrewAI active development v0.98+; framework choice driven by observability needs and execution durability requirements — [jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)
- **Industry Analysis:** The three-layer cost structure of agent production: Layer 1 (infrastructure, predictable), Layer 2 (LLM API calls, variable), Layer 3 (operational overhead, hidden). Teams budget Layer 1, discover Layers 2 and 3 in production — [islands-hq.xyz/blog/the-real-cost-of-production-ai-agents-infrastructure-apis-and-hidden-operational-expenses](https://www.islandshq.xyz/blog/the-real-cost-of-production-ai-agents-infrastructure-apis-and-hidden-operational-expenses)
- **Enterprise Analysis:** 7 of 10 GenAI projects never past pilot; root causes are hallucination at retrieval, cost explosion, and governance mismatches — [dataa.dev/2026/01/01/from-ai-pilots-to-production-reality-architecture-lessons-from-2025-and-what-2026-demands](https://www.dataa.dev/2026/01/01/from-ai-pilots-to-production-reality-architecture-lessons-from-2025-and-what-2026-demands)

## Gotchas

- **Do not use Lambda/Cloud Run as your agent execution environment.** They reset between invocations (no persistent state), weren't designed for LLM-generated code patterns, and lack the lifecycle SDK needed for agent tool-call workflows.
- **Do not add cost guardrails after launch.** Build them before the first user query. Teams that skip this routinely discover five-figure weekend bills.
- **Do not use AutoGen for new projects.** It is in maintenance mode. The migration to Microsoft's successor Agent Framework will be necessary — plan for it now rather than discovering it in a production incident.
- **Do not treat the orchestration framework as the entire stack.** The sandboxing layer, observability layer, and tool registry are independent decisions with independent failure modes. A great LangGraph setup with no sandbox isolation is a production security incident waiting to happen.
