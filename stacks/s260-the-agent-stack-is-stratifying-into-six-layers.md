# S-260 · The Agent Stack Is Stratifying into Six Layers

Your agent works in the demo. It crashes in production — not because the model failed, but because you were missing a layer. The agent infrastructure stack is decomposing into six distinct horizontal layers, each with different operational models, different competitive dynamics, and different failure modes. Treat it as a monolith and you will debug mysterious failures at 2am.

## Forces

- **Sandboxing cannot be an afterthought.** Agents generate code dynamically at runtime. Running that code on your main server is equivalent to handing a script kiddie root access. Traditional containers are too slow (cold starts kill agent latency budgets) and too loosely isolated for bursty workloads.
- **The model layer is commoditizing, context is compounding.** A state-machine graph in LangGraph can be replicated. Your organizational world model — the accumulated context about your business, your users, your domain — cannot. Teams that treat context as an architectural layer, not a feature, are building defensible moats. Teams that treat the model as the moat are building on rented land.
- **Every layer has different defensibility profiles.** Orchestration frameworks (LangGraph, CrewAI) are open-source and easily replicated. Model providers commoditize on cost and capability. Sandboxing infrastructure, context management, and proprietary agent tooling are where durable competitive advantage accumulates.
- **37% of enterprises now run five or more AI models in production** — multi-model is the default, not the exception, and each layer must account for it.

## The Move

**Architect your agent as six horizontal layers. Buy or build each one on its own merit. Do not conflate them.**

1. **Compute & Sandbox (Layer 1)** — Execute agent actions in an isolated, per-task environment. MicroVM-based solutions (Firecracker, E2B, Modal) provide kernel-level isolation with sub-second cold starts. Docker remains the lowest-friction option for read-only workloads. On-premise options (Kata Containers, gVisor) exist for compliance-heavy environments. This is a separate purchasing and engineering decision from orchestration.
2. **Memory (Layer 2)** — Short-term (conversation window), session (across-turn context), and long-term (semantic storage). Vector databases (Pinecone, Qdrant, Weaviate, pgvector) serve the semantic layer; the session and working-memory tiers are often custom or built on Redis + structured stores. Context is your moat.
3. **Tools & Actions (Layer 3)** — MCP (Model Context Protocol) is emerging as the de-facto standard for agent-to-tool communication, replacing bespoke function schemas. REST integration patterns, custom tool schemas, and code interpreters round out the layer. Tool design is an API design discipline — bad schemas kill agent reliability more often than bad prompts.
4. **Model (Layer 4)** — Anthropic for complex reasoning, OpenAI for broad capability, open-source (Llama, Mistral, Qwen) for privacy/cost. Most production teams use at least two: a frontier model for complex tasks, a smaller model for cost-sensitive, high-volume paths. Model selection is increasingly a routing decision, not a one-time choice.
5. **Orchestration (Layer 5)** — LangGraph for production systems needing durable execution and state-machine semantics; CrewAI for role-based, fast-delivery pipelines; Temporal for workflow-level orchestration with strong durability guarantees. AutoGen entered maintenance mode in October 2025 — its successor is the Microsoft Agent Framework. Choose based on your failure budget, not feature count.
6. **Application & Routing (Layer 6)** — Task routing, user intent classification, agent selection, and output validation. This is where multi-agent coordination decisions live: which agent handles this request, how do agents hand off, what happens on failure. Microsoft ISE's e-commerce case study showed that an agent registry with metadata (capabilities, latency SLA, cost) enables dynamic selection — scaling to 50+ agents without hand-rolled routing logic.

## Evidence

- **Engineering blog:** Philipp Dubach's "The Agent Stack Is Stratifying" describes six layers with distinct defensibility profiles, noting that context — not models — is where enterprise AI value compounds. Context is hard to rebuild, models are not. — https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/
- **Engineering blog:** Microsoft ISE documented a production multi-agent e-commerce system where an agent registry with capability metadata (not hand-coded routing) enabled dynamic agent selection across 50+ agents with predictable latency and token budgets. — https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale
- **Community post:** AgentSphere benchmarked five sandbox platforms (Modal, Together CodeSandbox, Daytona, AgentSphere, E2B) on cold-start latency, per-second billing, isolation level, and on-premise options. Modal leads on price/performance for general workloads; AgentSphere leads on AI-native isolation. — https://dev.to/agentsphere/why-ai-agents-need-a-new-infrastructure-layer-a-deep-dive-into-2025s-ai-native-sandbox-platforms-5gda
- **Engineering blog:** Harness Engineering's Dr. Sarah Chen documented that 15-20% of agent failures in production are harness-layer failures (missing retry policies, unhandled tool errors, context overflow) — not model failures. Teams that instrument harness-layer observability from day one reduce production failures faster than teams that keep tuning prompts. — https://harness-engineering.ai/blog/lessons-learned-from-deploying-ai-agents-in-production

## Gotchas

- **Missing the sandbox layer is the most common production mistake.** Teams build the model + orchestration + tools stack and then bolt on security. By then, the agent is generating code that executes on production infrastructure.
- **Orchestration framework choice is not permanent, but the layer boundaries you draw are.** Switching from CrewAI to LangGraph is feasible. Redesigning your memory layer mid-production is not. Invest in layer boundaries, not framework loyalty.
- **Multi-model routing without observability is a cost surprise waiting to happen.** Every agent that can call multiple models will eventually call the expensive one by default. Budget controls must be architectural, not procedural.
